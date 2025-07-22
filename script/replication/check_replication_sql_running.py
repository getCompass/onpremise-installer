#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, time, re, glob, json
import docker
from typing import Dict
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="окружение")
parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="название файла со значениями для деплоя")
args = parser.parse_args()
values_name = args.values

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
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    domino_id = domino["label"]

    stack_name = current_values["stack_name_prefix"] + "-monolith"
    if current_values.get("service_label") is None or current_values.get("service_label") == "":
        confirm = input("\nService_label в файле values оказался пустым. Продолжаем? (y/n): ").strip().lower()
        if confirm != "y":
            scriptutils.error("Завершаем выполнение скрипта")

    stack_name = stack_name + "-" + current_values.get("service_label")

    client = docker.from_env()

    mysql_host = "localhost"
    mysql_user = "root"
    mysql_pass = "root"

    # формируем список активных пространств
    space_config_obj_dict, space_id_list = get_space_dict(current_values)

    if len(space_config_obj_dict) < 1:
        scriptutils.die("Не найдено ни одной команды на сервере. Окружение поднято?")

    # проходимся по каждому пространству
    for space_id, space_config_obj in space_config_obj_dict.items():
        found_container = scriptutils.find_container_mysql_container(client, "team", domino_id, space_config_obj.port)
        sql_running = mysql_get_sql_running(found_container, mysql_host, mysql_user, mysql_pass, space_id)

        # если получили 0 - значит в какой-то компании Slave_SQL_Running = No/Null
        if sql_running == 0:
            print(sql_running)
            sys.exit(0)

    # проверяем Slave_SQL_Running для пивот баз данных
    mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
    mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

    found_container = scriptutils.find_container_mysql_container(client, "monolith", domino_id)
    if not found_container:
        print("Не удалось найти контейнер pivot mysql.")
        sys.exit(1)

    sql_running = mysql_get_sql_running(found_container, mysql_host, mysql_user, mysql_pass, 0)
    print(sql_running)

# получить статус репликации в полученном контейнере
def mysql_get_sql_running(found_container: docker.models.containers.Container, mysql_host: str, mysql_user: str, mysql_pass: str, space_id: int):

    cmd = f"mysql -h {mysql_host} -u {mysql_user} -p{mysql_pass} -e \"SHOW SLAVE STATUS\\G\""

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nНе нашли mysql контейнер для компании")
        return

    if result.exit_code != 0:
        scriptutils.die("Ошибка при получении статуса репликации")

    output = result.output.decode("utf-8", errors="ignore")

    patterns = {"Slave_SQL_Running": r"Slave_SQL_Running:\s*(\w*)"}

    lines = [line.strip() for line in output.split('\n') if line.strip()]

    result = {}
    current_field = None
    accumulated_value = []

    for line in lines:
        # проверяем, начинается ли строка с нового поля
        field_match = re.match(r'^(\w+):\s*(.*)', line)
        if field_match:
            # если нашли новое поле, сохраняем предыдущее накопленное значение
            if current_field:
                result[current_field] = '\n'.join(accumulated_value).strip() or None
                accumulated_value = []

            current_field = field_match.group(1)
            value_part = field_match.group(2)
            if value_part:
                accumulated_value.append(value_part)
        else:
            # если это продолжение предыдущего поля
            if current_field and current_field in ['Last_IO_Error', 'Last_SQL_Error', 'Slave_IO_State']:
                accumulated_value.append(line)

    # добавляем последнее накопленное значение
    if current_field:
        result[current_field] = '\n'.join(accumulated_value).strip() or None

    slave_sql_running = None
    if 'Slave_SQL_Running' in result:
        if result['Slave_SQL_Running'] == 'NULL':
            slave_sql_running = "NULL"
        elif result['Slave_SQL_Running']:
            slave_sql_running = result['Slave_SQL_Running']

    return 1 if slave_sql_running == "Yes" else 0

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
