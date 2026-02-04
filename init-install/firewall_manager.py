#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для управления фаерволом (iptables/nftables/firewalld).
"""

import subprocess, os
from subprocess import Popen, PIPE
import utils

import shutil
from pathlib import Path
from typing import Tuple, Optional, List, Union

KNOWN_SSH_SERVERS = ["dropbear", "sshd"]

NETSTAT_UTIL_ADDRESS_COLUMN = {
    "ss": 5,
    "netstat": 4,
}

def detect_firewall() -> Optional[str]:
    """
    Определяет, какой фаервол используется в системе.

    Returns:
        str: 'firewalld', 'nftables', 'iptables' или None если не найден
    """
    # Проверяем firewalld
    if shutil.which("firewall-cmd"):
        try:
            result = subprocess.run(
                ["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return "firewalld"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Проверяем nftables
    if shutil.which("nft"):
        try:
            result = subprocess.run(
                ["nft", "list", "tables"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return "nftables"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Проверяем iptables
    if shutil.which("iptables"):
        try:
            result = subprocess.run(
                ["iptables", "-L"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return "iptables"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return None


def get_firewall_rules_description(ssh_ports: List[str]) -> str:
    """
    Возвращает описание правил фаервола, которые будут применены.

    Returns:
        str: Описание правил
    """
    description = """
Будут открыты следующие порты:
  - (%s)/tcp (SSH) - для удаленного администрирования сервера
  - 80/tcp (HTTP) - для получения SSL-сертификатов Let's Encrypt
  - 443/tcp (HTTPS) - основной порт веб-приложения Compass
  - 53794/tcp (Веб-установщик) - для установки Compass On-Premise через веб-интерфейс
  - 10000/udp (Jitsi) - для медиатрафика видеозвонков и конференций

Будут разрешены входящие соединения с внешних IP:
  - 45.92.177.63:443 (TCP) - сервер лицензий Compass (только для активации, после активации можно закрыть)
  - 77.223.115.66:10000 (UDP) - coturn сервер для ВКС

Будут разрешены исходящие соединения к внешним IP:
  - 45.92.177.63:443 (TCP) - сервер лицензий Compass
  - 77.223.115.66:443 (TCP) - coturn сервер для ВКС
""" % ", ".join(ssh_ports)
    return description.strip()


def configure_firewalld(ssh_ports: List[str]) -> Tuple[bool, str]:
    """
    Настраивает правила фаервола через firewalld.

    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    rules = [
        ("80/tcp", "http"),
        ("443/tcp", "https"),
        ("53794/tcp", "installer"),
        ("10000/udp", "jitsi"),
    ]
    for i, port in enumerate(ssh_ports):
        rules.append(("%d/tcp" % int(port), "ssh%d" % i))
    
    try:
        # Открываем порты
        for port, name in rules:
            result = subprocess.run(
                ["firewall-cmd", "--permanent", "--add-port", port],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return False, f"Ошибка добавления порта {port}: {result.stderr}"

        # Разрешаем исходящие соединения к специфичным адресам
        external_ips = [
            ("45.92.177.63", "443"),
            ("77.223.115.66", "443"),
        ]

        for ip, port in external_ips:
            result = subprocess.run(
                [
                    "firewall-cmd",
                    "--permanent",
                    "--add-rich-rule",
                    f"rule family='ipv4' source address='{ip}' port port='{port}' protocol='tcp' accept",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                print(f"[WARN] Не удалось добавить правило для {ip}:{port}")

        # Применяем изменения
        result = subprocess.run(
            ["firewall-cmd", "--reload"],
            check=True,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки firewalld"
    except Exception as e:
        return False, str(e)


def configure_nftables(ssh_ports: List[str]) -> Tuple[bool, str]:
    """
    Настраивает правила фаервола через nftables.

    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """

    ssh_ports_block = ""
    for port in ssh_ports:
        ssh_ports_block += f"tcp dport {port} accept\n"
    try:
        # Создаем базовую таблицу и цепочки, если их нет
        nft_script = """
table inet filter {
    chain input {
        type filter hook input priority 0;
        # Разрешаем loopback
        iif lo accept
        # Разрешаем установленные соединения
        ct state established,related accept
        # Разрешаем SSH
        %s
        # Разрешаем HTTP/HTTPS
        tcp dport 80 accept
        tcp dport 443 accept
        # Разрешаем установщик
        tcp dport 53794 accept
        # Разрешаем Jitsi
        udp dport 10000 accept
        # Разрешаем входящие с внешних IP
        ip saddr 77.223.115.66 udp dport 10000 accept
        ip saddr 45.92.177.63 tcp dport 443 accept
        # По умолчанию отклоняем
        drop
    }
    chain forward {
        type filter hook forward priority 0;
        accept
    }
    chain output {
        type filter hook output priority 0;
        # Разрешаем исходящие к внешним IP
        ip daddr 45.92.177.63 tcp dport 443 accept
        ip daddr 77.223.115.66 tcp dport 443 accept
        accept
    }
}
""" % ssh_ports_block
        # Применяем правила
        result = subprocess.run(
            ["nft", "-f", "-"],
            input=nft_script,
            text=True,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            return False, f"Ошибка применения nftables правил: {result.stderr}"

        # Сохраняем правила
        with open("/etc/nftables.conf", "w") as f:
            subprocess.run(["nft", "list", "ruleset"], stdout=f, timeout=10, check=True)

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки nftables"
    except Exception as e:
        return False, str(e)


def configure_iptables(ssh_ports: List[str]) -> Tuple[bool, str]:
    """
    Настраивает правила фаервола через iptables.

    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    try:
        # Очищаем существующие правила (осторожно!)
        subprocess.run(
            ["iptables", "-F"],
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Устанавливаем политики по умолчанию
        subprocess.run(["iptables", "-P", "INPUT", "DROP"], check=True, timeout=10)
        subprocess.run(["iptables", "-P", "FORWARD", "ACCEPT"], check=True, timeout=10)
        subprocess.run(["iptables", "-P", "OUTPUT", "ACCEPT"], check=True, timeout=10)

        # Разрешаем loopback
        subprocess.run(
            ["iptables", "-A", "INPUT", "-i", "lo", "-j", "ACCEPT"],
            check=True,
            timeout=10,
        )

        # Разрешаем установленные соединения
        subprocess.run(
            [
                "iptables",
                "-A",
                "INPUT",
                "-m",
                "state",
                "--state",
                "ESTABLISHED,RELATED",
                "-j",
                "ACCEPT",
            ],
            check=True,
            timeout=10,
        )

        # Разрешаем порты: 80/tcp (HTTP), 443/tcp (HTTPS), 53794/tcp (установщик)
        ports = [80, 443, 53794] + ssh_ports
        for port in ports:
            subprocess.run(
                [
                    "iptables",
                    "-A",
                    "INPUT",
                    "-p",
                    "tcp",
                    "--dport",
                    str(port),
                    "-j",
                    "ACCEPT",
                ],
                check=True,
                timeout=10,
            )

        # Разрешаем UDP для Jitsi: 10000/udp
        subprocess.run(
            [
                "iptables",
                "-A",
                "INPUT",
                "-p",
                "udp",
                "--dport",
                "10000",
                "-j",
                "ACCEPT",
            ],
            check=True,
            timeout=10,
        )

        # Разрешаем входящие с внешних IP
        external_rules = [
            ("45.92.177.63", "443", "tcp"),
            ("77.223.115.66", "443", "tcp"),
        ]

        for ip, port, proto in external_rules:
            subprocess.run(
                [
                    "iptables",
                    "-A",
                    "INPUT",
                    "-s",
                    ip,
                    "-p",
                    proto,
                    "--dport",
                    port,
                    "-j",
                    "ACCEPT",
                ],
                check=True,
                timeout=10,
            )

        # Сохраняем правила
        if shutil.which("iptables-save"):
            Path("/etc/iptables").mkdir(parents=True, exist_ok=True)
            with open("/etc/iptables/rules.v4", "w") as f:
                subprocess.run(["iptables-save"], stdout=f, timeout=10, check=True)

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки iptables"
    except subprocess.CalledProcessError as e:
        return False, f"Ошибка выполнения iptables команды: {e}"
    except Exception as e:
        return False, str(e)


def configure_firewall() -> Tuple[bool, str]:
    """
    Настраивает фаервол, автоматически определяя доступный бэкенд.

    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    firewall_type = detect_firewall()
    
    if firewall_type == "firewalld":
        return configure_firewalld(get_listening_ssh_ports())
    elif firewall_type == "nftables":
        return configure_nftables(get_listening_ssh_ports())
    elif firewall_type == "iptables":
        return configure_iptables(get_listening_ssh_ports())
    else:
        return False, "Не найден доступный фаервол (firewalld/nftables/iptables)"


def get_documentation_url() -> str:
    """
    Возвращает URL документации для ручной настройки фаервола.

    Returns:
        str: URL документации
    """
    return "https://doc-onpremise.getcompass.ru/preparation.html"
    
def get_listening_ssh_ports() -> List[str]:
    """
    Возвращает прослушиваемые порты для ssh

    Returns:
        list[str]: список ssh портов
    """
    for util, column_number in NETSTAT_UTIL_ADDRESS_COLUMN.items():
        if shutil.which(util):

            command_pipe = [
                [util, "-tulpn"],
                ["grep", "-E", "|".join(KNOWN_SSH_SERVERS)],
                ["awk", '{split($%d, a, ":"); print a[2]}' % column_number],
                ["sed", "/^$/d"],
            ]

            stdout, stderr = utils.run_pipe_commands(command_pipe)
            break

    
    port_list = stdout.strip().decode().split("\n")
    if port_list == ['']:
        port_list = []
    return list(set(port_list))