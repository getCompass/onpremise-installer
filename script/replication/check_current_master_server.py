#!/usr/bin/env python3
import sys

sys.dont_write_bytecode = True

import yaml, json
import os
import docker

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path
from typing import Dict

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для проверки является ли текущий сервер мастером.",
    usage="python3 script/replication/check_current_master_server.py [-v VALUES]",
    epilog="Пример: python3 script/replication/check_current_master_server.py -v compass",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
args = parser.parse_args()

values_name = args.values

# путь до директории с инсталятором
installer_dir = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

values_file_name = "values.%s.yaml" % values_name
values_file_path = Path("%s/../src/%s" % (installer_dir, values_file_name))


def start():
    current_values = get_values()

    if current_values.get("company_config_mount_path") is None or current_values.get("company_config_mount_path") == "":
        scriptutils.die("В файле для деплоя %s отсутствует значение для company_config_mount_path" % values_file_name)

    if current_values.get("servers_companies_relationship_file") is None or current_values.get(
            "servers_companies_relationship_file") == "":
        scriptutils.die(
            "В файле для деплоя %s отсутствует значение для servers_companies_relationship_file" % values_file_name)

    # получаем путь к файлу для связи компаний между серверами
    servers_companies_relationship_file_path = current_values.get(
        "company_config_mount_path") + "/" + current_values.get("servers_companies_relationship_file")

    if not Path(servers_companies_relationship_file_path).exists():
        scriptutils.die(
            "Не найден файл для связи компаний между серверами: %s" % servers_companies_relationship_file_path)

    if current_values.get("service_label") is None or current_values.get("service_label") == "":
        scriptutils.die("В файле для деплоя %s отсутствует значение для service_label" % values_file_name)
    service_label = current_values.get("service_label")

    with open(servers_companies_relationship_file_path, "r") as file:
        reserve_relationship_str = file.read()
        reserve_relationship_dict = json.loads(reserve_relationship_str) if reserve_relationship_str != "" else {}

    # получаем флаг master = true/false
    is_master_current_server = False
    if reserve_relationship_dict.get(service_label) is not None:
        current_server_data = reserve_relationship_dict.get(service_label)
        if current_server_data["master"] is not None and current_server_data["master"] == True:
            is_master_current_server = True

    if is_master_current_server:
        print(scriptutils.success("Данный сервер является активным мастер сервером"))
    else:
        print(scriptutils.warning("Данный сервер НЕ является активным мастер сервером"))


# получить данные окружения из values
def get_values() -> Dict:
    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


start()
