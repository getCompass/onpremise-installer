#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, subprocess, re, json
import docker
import glob
import logging
from typing import Dict
from time import sleep

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path

scriptutils.assert_root()

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="окружение")
parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="название файла со значениями для деплоя")
parser.add_argument("-t", "--type", required=False, default="monolith", type=str, help="тип mysql (monolith|team)")
parser.add_argument("--is-logs", required=False, default=1, type=int, help="нужны ли логи старта репликации")
parser.add_argument("--is-choice-space", required=False, default=1, type=int, help="нужно ли предоставлять выбор компании для старта репликации")

args = parser.parse_args()
environment = args.environment
values_name = args.values
is_logs = args.is_logs
is_logs = bool(is_logs == 1)
is_choice_space = bool(args.is_choice_space)
mysql_type = args.type.lower()

script_dir = str(Path(__file__).parent.resolve())

# настройка логирования
logging.basicConfig(filename='/var/log/start-slave-replication.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# класс конфига пространства
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password


# получить данные окружение из values
def get_values() -> Dict:
    default_values_file_path = Path("%s/../../src/values.yaml" % (script_dir))
    values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_name))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = scriptutils.merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


def start():
    # получаем значения для выбранного окружения
    current_values = get_values()
    security = scriptutils.get_security(current_values)
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    domino_id = domino["label"]

    stack_name = current_values["stack_name_prefix"] + "-monolith"
    master_service_label = current_values["master_service_label"]
    if master_service_label is None or master_service_label == "":
        values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_name))
        scriptutils.die("Пустое значение master_service_label в файле src/values.%s.yaml" % values_name)

    stack_name = stack_name + "-" + master_service_label

    client = docker.from_env()

    mysql_host = "localhost"

    replicator_user = security["replication"]["mysql_user"]
    replicator_pass = security["replication"]["mysql_pass"]

    if mysql_type == "team":
        mysql_user = "root"
        mysql_pass = "root"

        # формируем список активных пространств
        timeout = 60
        n = 0
        while n <= timeout:
            space_config_obj_dict, space_id_list = get_space_dict(current_values)
            if len(space_config_obj_dict) > 0:
                break
            n = n + 5
            sleep(5)
            if n == timeout:
                scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

        logging.info("Старт репликации для команд")

        if is_choice_space:
            space_option_str = "Выберете команду, для которой запускаем репликацию:\n"
            for index, option in enumerate(space_id_list):
                space_option_str += "%d. ID команды = %s\n" % (index + 1, option)
            space_option_str += "%d. Все\n" % (len(space_id_list) + 1)

            chosen_space_index = input(space_option_str)

            if (not chosen_space_index.isdigit()) or int(chosen_space_index) < 0 or int(chosen_space_index) > (len(space_id_list) + 1):
                scriptutils.die("Выбран некорректный вариант")

        # проходимся по каждому пространству
        if is_choice_space == False or int(chosen_space_index) == (len(space_id_list) + 1):
            for space_id, space_config_obj in space_config_obj_dict.items():
                logging.info("Запускаем репликацию для команды %s" % space_id)
                found_container = scriptutils.find_container_mysql_container(client, mysql_type, domino_id, space_config_obj.port)
                master_host = "%s-%s-%s-company_mysql-%s" % (current_values["stack_name_prefix"], master_service_label, domino_id, space_config_obj.port)
                mysql_cert_name = "mysql-%s" % ("master" if current_values["mysql_server_id"] == 1 else "replica")
                change_master_mysql_command = "CHANGE MASTER TO MASTER_HOST='%s', MASTER_PORT=%s, MASTER_USER='%s', MASTER_PASSWORD='%s', MASTER_AUTO_POSITION=1," % (
                    master_host, space_config_obj.port, replicator_user, replicator_pass) + \
                    "MASTER_SSL = 1, MASTER_SSL_CA = '/etc/mysql/ssl/mysqlRootCA.crt'," + \
                    f"MASTER_SSL_CERT='/etc/mysql/ssl/{mysql_cert_name}-cert.pem', MASTER_SSL_KEY='/etc/mysql/ssl/{mysql_cert_name}-key.pem'," + \
                    "MASTER_TLS_VERSION = 'TLSv1.2,TLSv1.3';"
                mysql_start_replication(found_container, change_master_mysql_command, mysql_host, mysql_user, mysql_pass, space_id)
        else:
            space_id = space_id_list[int(chosen_space_index) - 1]
            space_config_obj = space_config_obj_dict[space_id]
            logging.info("Запускаем репликацию для команды %s" % space_id)
            found_container = scriptutils.find_container_mysql_container(client, mysql_type, domino_id, space_config_obj.port)
            master_host = "%s-%s-%s-company_mysql-%s" % (current_values["stack_name_prefix"], master_service_label, domino_id, space_config_obj.port)
            mysql_cert_name = "mysql-%s" % ("master" if current_values["mysql_server_id"] == 1 else "replica")
            change_master_mysql_command = "CHANGE MASTER TO MASTER_HOST='%s', MASTER_PORT=%s, MASTER_USER='%s', MASTER_PASSWORD='%s', MASTER_AUTO_POSITION=1," % (
                master_host, space_config_obj.port, replicator_user, replicator_pass) + \
                "MASTER_SSL = 1, MASTER_SSL_CA = '/etc/mysql/ssl/mysqlRootCA.crt'," + \
                f"MASTER_SSL_CERT='/etc/mysql/ssl/{mysql_cert_name}-cert.pem', MASTER_SSL_KEY='/etc/mysql/ssl/{mysql_cert_name}-key.pem'," + \
                "MASTER_TLS_VERSION='TLSv1.2,TLSv1.3';"
            mysql_start_replication(found_container, change_master_mysql_command, mysql_host, mysql_user, mysql_pass, space_id)

        logging.info("Успешно завершили репликацию для команд")

    else:
        mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
        mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

        found_container = scriptutils.find_container_mysql_container(client, mysql_type, domino_id)
        if not found_container:
            print("Не удалось найти контейнер pivot mysql.")
            sys.exit(1)

        logging.info("Старт репликации для монолита")

        master_host = "%s_mysql-%s" % (stack_name, current_values["projects"]["monolith"]["label"])
        mysql_cert_name = "mysql-%s" % ("master" if current_values["mysql_server_id"] == 1 else "replica")
        change_master_mysql_command = "CHANGE MASTER TO MASTER_HOST='%s', MASTER_USER='%s', MASTER_PASSWORD='%s', MASTER_AUTO_POSITION=1," % (
            master_host, replicator_user, replicator_pass) + \
            "MASTER_SSL = 1, MASTER_SSL_CA = '/etc/mysql/ssl/mysqlRootCA.crt'," + \
            f"MASTER_SSL_CERT='/etc/mysql/ssl/{mysql_cert_name}-cert.pem', MASTER_SSL_KEY='/etc/mysql/ssl/{mysql_cert_name}-key.pem'," + \
            "MASTER_TLS_VERSION='TLSv1.2,TLSv1.3';"
        mysql_start_replication(found_container, change_master_mysql_command, mysql_host, mysql_user, mysql_pass, 0)

        logging.info("Успешно завершили репликацию для монолита")

# запускаем старт репликации в полученном контейнере
def mysql_start_replication(found_container: docker.models.containers.Container, change_master_mysql_command: str, mysql_host: str, mysql_user: str, mysql_pass: str, space_id: int):

    mysql_command = "SET GLOBAL super_read_only = ON; STOP SLAVE;" + \
                    change_master_mysql_command + \
                    "START SLAVE;"
    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % (mysql_host, mysql_user, mysql_pass, mysql_command)

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nНе нашли mysql контейнер для компании")
        return

    if result.exit_code == 0:
        if is_logs:
            if space_id > 0:
                print("\nРепликация запущена в команде %s" % space_id)
            else:
                print("\nРепликация запущена для монолита")
    else:
        print("Ошибка при запуске репликации")
        if result.output:
            print("Результат выполнения:\n", result.output.decode("utf-8", errors="ignore"))
        sys.exit(result.exit_code)

    if is_logs:
        log_text = "Ожидаем завершение репликации mysql"
        if space_id > 0:
            log_text = log_text + " для команды %s" % space_id
        print(log_text)
    subprocess.run(
        [
            "python3",
            script_dir + "/wait_slave_replication_done.py",
            "-e",
            environment,
            "-v",
            values_name,
            "--type",
            mysql_type,
            "--container-id",
            found_container.id
        ]
    )
    if is_logs:
        if space_id > 0:
            print("\nРепликация завершена в команде %s" % space_id)
        else:
            print("\nРепликация завершена для монолита")

    # отключаем read_only режим
    mysql_command = "SET GLOBAL super_read_only = OFF;" + \
                    "SET GLOBAL read_only = OFF;"
    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % (mysql_host, mysql_user, mysql_pass, mysql_command)

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nКонтейнер %s не найден - пропускам" % found_container.id)
        return
    except Exception as e:
        return

    if result.exit_code == 0:
        if is_logs:
            print("\nRead-only режим отключен")
    else:
        print("Ошибка при отключении read-only режима")
        if result.output:
            print("Результат выполнения:\n", result.output.decode("utf-8", errors="ignore"))
        sys.exit(result.exit_code)

# сформировать список конфигураций пространств
def get_space_dict(current_values: Dict) -> Dict[int, DbConfig]:
    # получаем название домино
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]
    domino_id = domino["label"]

    # формируем список пространств
    # пространства выбираются по наличию их конфига
    space_config_obj_dict = {}
    space_id_list = []
    for space_config in glob.glob("%s/*_company.json" % space_config_dir):

        s = re.search(r'([0-9]+)_company', space_config)

        if s is None:
            continue

        space_id = s.group(1)
        f = open(space_config, "r")
        space_config_dict = json.loads(f.read())
        f.close()
        if space_config_dict["status"] not in [1, 2]:
            continue

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            domino_id,
            int(space_id),
            space_config_dict["mysql"]["host"],
            space_config_dict["mysql"]["port"],
            "root",
            "root",
        )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
        space_id_list.append(space_config_obj.space_id)
    space_id_list.sort()
    return dict(sorted(space_config_obj_dict.items())), space_id_list

# точка входа в скрипт
start()
