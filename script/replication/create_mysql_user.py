#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, re, json
import docker
import glob
from time import sleep
from typing import Dict

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
parser.add_argument('-y', '--yes', required=False, action='store_true', help='Согласиться на все')
parser.add_argument("--is_logs", required=False, default=1, type=int, help="нужны ли логи при создании mysql-пользователя")
parser.add_argument("--is-create-team", required=False, default=0, type=int, help="создание новой команды")

args = parser.parse_args()
values_name = args.values
mysql_type = args.type.lower()
is_logs = args.is_logs
is_logs = bool(is_logs == 1)
is_create_team = bool(args.is_create_team == 1)

script_dir = str(Path(__file__).parent.resolve())

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

    client = docker.from_env()

    mysql_host = "localhost"
    replicator_user = security["replication"]["mysql_user"]
    replicator_pass = security["replication"]["mysql_pass"]

    mysql_command = "CREATE USER IF NOT EXISTS '%s'@'%%' IDENTIFIED WITH mysql_native_password BY '%s';" % (replicator_user, replicator_pass) + \
                    "GRANT REPLICATION SLAVE ON *.* TO '%s'@'%%';" % replicator_user + \
                    "FLUSH PRIVILEGES;"

    if mysql_type == "team":
        mysql_user = "root"
        mysql_pass = "root"
        cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % (mysql_host, mysql_user, mysql_pass, mysql_command)

        timeout = 300
        n = 0
        while n <= timeout:

            # формируем список активных пространств
            space_config_obj_dict, space_id_list = get_space_dict(current_values)

            if len(space_config_obj_dict) < 1:
                error_text = "Не найдено ни одного пространства на сервере. Окружение поднято?"
            else:
                break
            n = n + 5
            sleep(5)
            if n == timeout:
                scriptutils.die(error_text)

        chosen_space_index = 1
        if is_create_team:
            space_id = space_id_list[-1]
            space_config_obj = space_config_obj_dict[space_id]
            space_config_obj_dict = {}
            space_config_obj_dict[space_id] = space_config_obj
            space_id_list = [space_id]
            space_config_obj_dict

        if not is_create_team and len(space_id_list) > 1:
            space_option_str = "Выберете команду, для которой создадим mysql-пользователя для репликации:\n"
            for index, option in enumerate(space_id_list):
                space_option_str += "%d. ID команды = %s\n" % (index + 1, option)
            space_option_str += "%d. Все\n" % (len(space_id_list) + 1)

            chosen_space_index = input(space_option_str)

        # проходимся по каждому пространству
        if int(chosen_space_index) == (len(space_id_list) + 1):
            for space_id, space_config_obj in space_config_obj_dict.items():
                if is_logs:
                    print("Создаём mysql-пользователя для компании %s" % space_id)
                found_container = scriptutils.find_container_mysql_container(client, mysql_type, domino_id, space_config_obj.port)
                result = found_container.exec_run(cmd)
        else:
            space_id = space_id_list[int(chosen_space_index) - 1]
            space_config_obj = space_config_obj_dict[space_id]
            if is_logs:
                print("Создаём mysql-пользователя для компании %s" % space_id)
            found_container = scriptutils.find_container_mysql_container(client, mysql_type, domino_id, space_config_obj.port)
            result = found_container.exec_run(cmd)
    else:
        mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
        mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]
        if is_logs:
            print("Создаём mysql-пользователя для монолита")
        found_container = scriptutils.find_container_mysql_container(client, mysql_type, domino_id)
        cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % (mysql_host, mysql_user, mysql_pass, mysql_command)
        if not found_container:
            print("Не удалось найти контейнер pivot mysql!")
            sys.exit(1)
        result = found_container.exec_run(cmd)

    if result.exit_code != 0:
        print("Ошибка при создании mysql-пользователя")
        if result.output:
            print("Результат выполнения:\n", result.output.decode("utf-8", errors="ignore"))
        sys.exit(result.exit_code)
    else:
        if is_logs:
            print(scriptutils.success("Пользователь для mysql успешно создан!"))

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
