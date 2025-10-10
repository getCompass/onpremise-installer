#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, subprocess, re, json
import docker
import glob
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
parser.add_argument(
    "-t", "--type", required=False, default="monolith", type=str, help="тип mysql (monolith|team)", choices=["monolith", "team"]
)
parser.add_argument("--all-teams", required=False, action="store_true", help="выбрать все команды")
parser.add_argument("--all-types", required=False, action="store_true", help="выбрать все типы mysql")

args = parser.parse_args()
environment = args.environment
values_name = args.values
mysql_type = args.type.lower()
is_all_teams = args.all_teams
is_all_types = args.all_types


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

    stack_name = current_values["stack_name_prefix"] + "-monolith"
    master_service_label = current_values["master_service_label"]
    if master_service_label is None or master_service_label == "":
        scriptutils.die("Пустое значение master_service_label в файле src/values.%s.yaml" % values_name)

    stack_name = stack_name + "-" + master_service_label

    client = docker.from_env()

    mysql_host = "localhost"

    replicator_user = security["replication"]["mysql_user"]
    replicator_pass = security["replication"]["mysql_pass"]

    if is_all_types or mysql_type == scriptutils.MONOLITH_MYSQL_TYPE:
        mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
        mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

        print("Выполняем сброс репликации для монолита")
        found_container = scriptutils.find_container_mysql_container(client, scriptutils.MONOLITH_MYSQL_TYPE, domino_id)
        if not found_container:
            print("Не удалось найти контейнер pivot mysql.")
            sys.exit(1)

        mysql_restart_replication(found_container, mysql_host, mysql_user, mysql_pass, 0)

    if is_all_types or mysql_type == scriptutils.TEAM_MYSQL_TYPE or is_all_teams:
        mysql_user = "root"
        mysql_pass = "root"

        # формируем список активных пространств
        space_config_obj_dict, space_id_list = get_space_dict(current_values)

        if len(space_config_obj_dict) < 1:
            scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

        chosen_space_index = 1
        if not is_all_teams:
            space_option_str = "Выберете команду, для которой выполняем сброс репликации:\n"
            for index, option in enumerate(space_id_list):
                space_option_str += "%d. ID команды = %s\n" % (index + 1, option)
            space_option_str += "%d. Все\n" % (len(space_id_list) + 1)

            chosen_space_index = input(space_option_str)

            if (not chosen_space_index.isdigit()) or int(chosen_space_index) < 0 or int(chosen_space_index) > (len(space_id_list) + 1):
                scriptutils.die("Выбран некорректный вариант")

        # проходимся по каждому пространству
        if is_all_teams or int(chosen_space_index) == (len(space_id_list) + 1):
            space_iteration = 1
            for space_id, space_config_obj in space_config_obj_dict.items():

                log_text = "Выполняем сброс репликации для команды %s" % space_id
                if len(space_config_obj_dict.items()) > 1:
                    log_text = log_text + " (%s из %s)" % (space_iteration, len(space_config_obj_dict.items()))
                print(log_text)
                found_container = scriptutils.find_container_mysql_container(client, scriptutils.TEAM_MYSQL_TYPE, domino_id, space_config_obj.port)
                mysql_restart_replication(found_container, mysql_host, mysql_user, mysql_pass, space_id)
                space_iteration += 1
        else:
            space_id = space_id_list[int(chosen_space_index) - 1]
            space_config_obj = space_config_obj_dict[space_id]
            print("Выполняем сброс репликации для команды %s" % space_id)
            found_container = scriptutils.find_container_mysql_container(client, scriptutils.TEAM_MYSQL_TYPE, domino_id, space_config_obj.port)
            mysql_restart_replication(found_container, mysql_host, mysql_user, mysql_pass, space_id)

    print(scriptutils.success("Сброс репликации завершён"))

# выполняем рестарт репликации в полученном контейнере
def mysql_restart_replication(found_container: docker.models.containers.Container, mysql_host: str, mysql_user: str, mysql_pass: str, space_id: int):

    mysql_command = "STOP SLAVE; RESET SLAVE;" + \
                    "SET GLOBAL super_read_only = OFF;" + \
                    "SET GLOBAL read_only = OFF;"
    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % (mysql_host, mysql_user, mysql_pass, mysql_command)

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nНе нашли mysql контейнер для space_id %d" % space_id)
        return

    if result.exit_code != 0:
        print("Ошибка при рестарте репликации")
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
