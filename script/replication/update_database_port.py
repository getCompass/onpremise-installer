#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, glob, re
import docker

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path
from time import sleep
from loader import Loader

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument(
    "-v",
    "--values",
    required=False,
    default="compass",
    type=str,
    help="Название values файла окружения",
)
parser.add_argument(
    "-e",
    "--environment",
    required=False,
    default="production",
    type=str,
    help="Окружение, в котором разворачиваем",
)
parser.add_argument(
    '--service_label',
    required=False,
    default="",
    type=str,
    help='Метка сервиса, к которому закреплён стак'
)

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())

# ---СКРИПТ---#

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"
service_label = args.service_label if args.service_label else ''
if service_label != "":
    stack_name = stack_name + "-" + service_label


# получить данные окружение из values
def get_values() -> dict:
    default_values_file_path = Path("%s/../../src/values.yaml" % (script_dir))
    values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_arg))

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


client = docker.from_env()
current_values = get_values()

keys_list = list(current_values["projects"]["domino"].keys())
domino = current_values["projects"]["domino"][keys_list[0]]

found_container = scriptutils.find_container_mysql_container(client, "monolith", domino["label"])

mysql_host = "localhost"
mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

go_database_controller_port = domino["go_database_controller_port"]
print(go_database_controller_port)

mysql_command = "UPDATE pivot_company_service.domino_registry SET `extra` = JSON_SET(extra, '$.extra.go_database_controller_port', %s);" % go_database_controller_port
cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % (mysql_host, mysql_user, mysql_pass, mysql_command)
found_container.exec_run(cmd)
