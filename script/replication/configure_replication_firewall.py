#!/usr/bin/env python3
import sys

sys.dont_write_bytecode = True

# ограничиваем порты репликации (manticore, mysql монолита и команды) на уровне
# цепочки DOCKER-USER: ufw не видит трафик к опубликованным портам (DNAT в PREROUTING
# уводит его в FORWARD мимо INPUT), а DOCKER-USER проходится первой для всех
# публикаций docker - и swarm-сервисов (DOCKER-INGRESS), и обычных контейнеров (DOCKER)

import argparse
import glob
import ipaddress
import json
import os
import re
import shlex
import socket
import subprocess
from pathlib import Path
from typing import List, NoReturn, Optional, Tuple

import yaml

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

script_dir = str(Path(__file__).parent.resolve())

RULE_TAG = "compass-ha-repl"
DOCKER_USER_CHAIN = "DOCKER-USER"
MANTICORE_PORTS = (9312, 9360, 9361)
MULTIPORT_LIMIT = 15
IPTABLES_WAIT = "5"

TAG_SUFFIX = " -m comment --comment %s" % RULE_TAG


def die(message: str) -> NoReturn:
    print("Ошибка: %s" % message)
    sys.exit(1)


# разбиваем список портов на чанки: multiport поддерживает не больше 15 портов в правиле
def chunk_ports(ports: List[int], size: int = MULTIPORT_LIMIT) -> List[List[int]]:
    unique = sorted(set(int(port) for port in ports))
    return [unique[i:i + size] for i in range(0, len(unique), size)]


# целевой набор правил цепочки DOCKER-USER (порядок важен: RETURN-правила раньше DROP)
def build_rules(peer_ips: List[str], ingress_subnet: Optional[str], manticore_ports: List[int],
                mysql_ports: List[int]) -> List[str]:
    rules = [
        "-m conntrack --ctstate RELATED,ESTABLISHED -j RETURN" + TAG_SUFFIX,
        "-i docker_gwbridge -j RETURN" + TAG_SUFFIX,
    ]

    for peer_ip in peer_ips:
        rules.append("-s %s -j RETURN%s" % (peer_ip, TAG_SUFFIX))

    if ingress_subnet is not None and ingress_subnet != "":
        # исходящие подключения репликации к соседу идут с адреса контейнера в ingress-сети
        rules.append("-s %s -j RETURN%s" % (ingress_subnet, TAG_SUFFIX))

    for chunk in chunk_ports(manticore_ports):
        rules.append("-p tcp -m multiport --dports %s -j DROP%s" % (",".join(map(str, chunk)), TAG_SUFFIX))

    for chunk in chunk_ports(mysql_ports):
        rules.append("-p tcp -m multiport --dports %s -j DROP%s" % (",".join(map(str, chunk)), TAG_SUFFIX))

    return rules


# файрвол нужен только на отказоустойчивой паре: обе ноды имеют уникальные mysql_server_id и адрес соседа
def is_firewall_needed(current_values: dict) -> bool:
    mysql_server_id = current_values.get("mysql_server_id")
    peer_host = current_values.get("peer_host")
    return bool(mysql_server_id) and bool(peer_host and str(peer_host).strip())


# порты mysql: монолитная база + все активные базы команд (как в ensure_replication.get_db_list)
def collect_mysql_ports(current_values: dict) -> List[int]:
    ports = [int(current_values["projects"]["monolith"]["service"]["mysql"]["port"])]

    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]

    for space_config in glob.glob("%s/*_company.json" % space_config_dir):
        match = re.search(r'([0-9]+)_company', space_config)
        if match is None:
            continue

        with open(space_config, "r") as config_file:
            space_config_dict = json.loads(config_file.read())

        if space_config_dict.get("status") not in [1, 2]:
            continue

        ports.append(int(space_config_dict["mysql"]["port"]))

    return ports


# подсеть swarm ingress-сети, из которой контейнеры ходят к опубликованным портам
def get_ingress_subnet() -> Optional[str]:
    try:
        result = subprocess.run(
            ["docker", "network", "inspect", "ingress", "-f", "{{(index .IPAM.Config 0).Subnet}}"],
            capture_output=True, text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


# peer_host может быть hostname: iptables сам разворачивает его в ip-адреса и печатает в -S только их,
# поэтому разворачиваем заранее - иначе сверка с установленными правилами никогда не сойдется
def resolve_peer_ips(peer_host: str) -> Optional[List[str]]:
    try:
        return [str(ipaddress.IPv4Address(peer_host))]
    except ValueError:
        pass

    try:
        addresses = socket.getaddrinfo(peer_host, None, socket.AF_INET)
    except OSError:
        return None

    return sorted(set(address[4][0] for address in addresses), key=ipaddress.IPv4Address) or None


# ищем рабочий инструмент управления цепочкой: обычный iptables (legacy или nft-обертка), затем iptables-nft
def detect_tool() -> Optional[str]:
    for binary in ("iptables", "iptables-nft"):
        try:
            result = subprocess.run([binary, "-w", IPTABLES_WAIT, "-S", DOCKER_USER_CHAIN],
                                    capture_output=True, text=True)
        except FileNotFoundError:
            continue

        if result.returncode == 0:
            return binary

    return None


# текущие правила с нашим тегом (в порядке цепочки, в виде, котором их печатает -S)
def tagged_rules(tool: str) -> Optional[List[str]]:
    result = subprocess.run([tool, "-w", IPTABLES_WAIT, "-S", DOCKER_USER_CHAIN],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return None

    prefix = "-A %s " % DOCKER_USER_CHAIN
    rules = []
    for line in result.stdout.splitlines():
        if line.startswith(prefix) and RULE_TAG in line:
            rules.append(line[len(prefix):])

    return rules


# адрес в том виде, в котором его печатает iptables -S: одиночный адрес - с маской /32
def normalize_address(address: str) -> str:
    try:
        return str(ipaddress.ip_network(address, strict=False))
    except ValueError:
        return address


# iptables -S печатает правило в своем порядке (условия, затем комментарий, затем цель -j),
# дописывает маску к одиночному адресу и может взять комментарий в кавычки (их снимает shlex) -
# перед сравнением приводим правило к одному виду
def normalize_rule(rule: str) -> Tuple[str, ...]:
    tokens = shlex.split(rule)
    conditions, comment, target = [], [], []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-j":
            target = tokens[index:index + 2]
            index += 2
        elif token == "-m" and tokens[index + 1:index + 2] == ["comment"]:
            comment = tokens[index:index + 4]
            index += 4
        elif token in ("-s", "-d") and index + 1 < len(tokens):
            conditions += [token, normalize_address(tokens[index + 1])]
            index += 2
        else:
            conditions.append(token)
            index += 1

    return tuple(conditions + comment + target)


def check_rules(tool: str, rules: List[str]) -> bool:
    actual = tagged_rules(tool)
    if actual is None:
        return False

    return [normalize_rule(rule) for rule in actual] == [normalize_rule(rule) for rule in rules]


def flush_rules(tool: str) -> bool:
    for _ in range(3):
        actual = tagged_rules(tool)
        if actual is None:
            return False
        if not actual:
            return True

        for rule in actual:
            result = subprocess.run(
                [tool, "-w", IPTABLES_WAIT, "-D", DOCKER_USER_CHAIN] + shlex.split(rule),
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print("Не удалось удалить правило файрвола репликации: %s" % result.stderr.strip())
                return False

    return not (tagged_rules(tool) or [])


def apply_rules(tool: str, rules: List[str]) -> bool:
    if not flush_rules(tool):
        return False

    for position, rule in enumerate(rules, start=1):
        result = subprocess.run(
            [tool, "-w", IPTABLES_WAIT, "-I", DOCKER_USER_CHAIN, str(position)] + shlex.split(rule),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print("Не удалось применить правило файрвола репликации: %s" % result.stderr.strip())
            return False

    if check_rules(tool, rules):
        return True

    print("Правила файрвола репликации после применения не совпадают с ожидаемыми.\nОжидаются:\n%s\nУстановлены:\n%s"
          % ("\n".join(rules), "\n".join(tagged_rules(tool) or [])))
    return False


# переводим наши фиксированные формы правил в нативный синтаксис nft -
# подсказка для ручного применения на экзотическом хосте без iptables-бинарников
def to_nft_rule(rule: str) -> Optional[str]:
    body = rule[: -len(TAG_SUFFIX)] if rule.endswith(TAG_SUFFIX) else rule
    comment = ' comment "%s"' % RULE_TAG

    if body == "-m conntrack --ctstate RELATED,ESTABLISHED -j RETURN":
        return "ct state established,related return" + comment

    match = re.fullmatch(r"-s (\S+) -j RETURN", body)
    if match is not None:
        return "ip saddr %s return%s" % (match.group(1), comment)

    match = re.fullmatch(r"-i (\S+) -j RETURN", body)
    if match is not None:
        return 'iifname "%s" return%s' % (match.group(1), comment)

    match = re.fullmatch(r"-p tcp -m multiport --dports ([0-9,]+) -j DROP", body)
    if match is not None:
        return "tcp dport { %s } drop%s" % (match.group(1).replace(",", ", "), comment)

    return None


def manual_nft_commands(rules: List[str]) -> str:
    commands = [to_nft_rule(rule) for rule in rules]
    lines = ["nft add rule ip filter %s %s" % (DOCKER_USER_CHAIN, command)
             for command in commands if command is not None]
    return "\n".join(lines)


# полная проверка и при необходимости применение; true - правила на месте.
# на установке без репликации удаляем устаревшие правила (например, репликацию выключили)
def ensure_firewall(current_values: dict) -> bool:
    if not is_firewall_needed(current_values):
        tool = detect_tool()
        if tool is None:
            return True

        if tagged_rules(tool):
            print("Репликация отключена - удаляем устаревшие правила файрвола репликации")
            return flush_rules(tool)

        return True

    peer_host = str(current_values["peer_host"]).strip()
    peer_ips = resolve_peer_ips(peer_host)

    if peer_ips is None:
        print("Ошибка: не удалось определить ip-адрес peer_host %s - правила файрвола репликации не применены"
              % peer_host)
        return False

    ingress_subnet = get_ingress_subnet()

    if ingress_subnet is None:
        print("Ошибка: не удалось определить подсеть ingress-сети docker "
              "(docker не запущен?) - правила файрвола репликации не применены")
        return False

    rules = build_rules(peer_ips, ingress_subnet, list(MANTICORE_PORTS), collect_mysql_ports(current_values))

    tool = detect_tool()
    if tool is None:
        print("Ошибка: не найден инструмент управления цепочкой %s (iptables/iptables-nft), "
              "либо цепочка отсутствует. Порты репликации остаются без ограничения!" % DOCKER_USER_CHAIN)
        print("Вариант ручного применения через nft:\n%s" % manual_nft_commands(rules))
        return False

    if check_rules(tool, rules):
        return True

    return apply_rules(tool, rules)


def merge(a: dict, b: dict) -> dict:
    for key in b:
        if key in a and isinstance(a[key], dict) and isinstance(b[key], dict):
            merge(a[key], b[key])
        else:
            a[key] = b[key]
    return a


def get_values(values_name: str) -> dict:
    values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_name))
    default_values_file_path = Path("%s/../../src/values.yaml" % script_dir)

    if not values_file_path.exists():
        die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file) or {}

    with default_values_file_path.open("r") as default_file:
        default_values = yaml.safe_load(default_file) or {}

    current_values = merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


def main():
    parser = argparse.ArgumentParser(
        description="Ограничение портов репликации (manticore/mysql) цепочкой DOCKER-USER.",
        usage="python3 script/replication/configure_replication_firewall.py [-v VALUES] [-e ENVIRONMENT] [--check] [--flush]",
        epilog="Пример: python3 script/replication/configure_replication_firewall.py -v compass -e production",
    )
    parser.add_argument("-v", "--values", required=False, default="compass", type=str,
                        help="Название values файла окружения")
    parser.add_argument("-e", "--environment", required=False, default="production", type=str,
                        help="Окружение, в котором развернут проект")
    parser.add_argument("--check", required=False, action="store_true",
                        help="Только сверка правил, без применения")
    parser.add_argument("--flush", required=False, action="store_true",
                        help="Удалить все правила файрвола репликации")
    args = parser.parse_args()

    if os.geteuid() != 0:
        die("Скрипт должен быть запущен от root")

    current_values = get_values(args.values)

    if args.flush:
        tool = detect_tool()
        if tool is None:
            die("Не найден инструмент управления цепочкой %s" % DOCKER_USER_CHAIN)
        sys.exit(0 if flush_rules(tool) else 1)

    if args.check:
        if not is_firewall_needed(current_values):
            sys.exit(0)

        ingress_subnet = get_ingress_subnet()
        if ingress_subnet is None:
            print("Ошибка: не удалось определить подсеть ingress-сети docker")
            sys.exit(1)

        peer_host = str(current_values["peer_host"]).strip()
        peer_ips = resolve_peer_ips(peer_host)
        if peer_ips is None:
            print("Ошибка: не удалось определить ip-адрес peer_host %s" % peer_host)
            sys.exit(1)

        rules = build_rules(peer_ips, ingress_subnet, list(MANTICORE_PORTS), collect_mysql_ports(current_values))
        tool = detect_tool()
        if tool is None:
            print("Ошибка: не найден инструмент управления цепочкой %s" % DOCKER_USER_CHAIN)
            sys.exit(1)

        sys.exit(0 if check_rules(tool, rules) else 1)

    sys.exit(0 if ensure_firewall(current_values) else 1)


if __name__ == "__main__":
    main()
