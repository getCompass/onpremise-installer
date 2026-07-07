#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, glob, re, json, shlex
import docker

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils, team_mysql_settings
from pathlib import Path
from time import sleep
from loader import Loader

scriptutils.assert_replication_available()

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="Название values файла окружения")
parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="Окружение, в котором разворачиваем")
parser.add_argument("--buffer-pool-size", required=False, default=None, type=int,
                    help="innodb_buffer_pool_size для MySQL команды в мегабайтах")
parser.add_argument("--innodb-thread-concurrency", required=False, default=None, type=int,
                    help="innodb_thread_concurrency для MySQL команды")
parser.add_argument("--table-open-cache", required=False, default=None, type=int,
                    help="table-open-cache для MySQL команды")

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())
team_config_path = Path("%s/../../configs/team.yaml" % script_dir)

# ---СКРИПТ---#

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"

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

current_values = get_values()

service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

client = docker.from_env()

# получаем контейнер monolith
timeout = 30
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "%s_php-monolith" % (stack_name),
            "health": "healthy",
        }
    )

    if len(docker_container_list) > 0:
        found_pivot_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для создания команды. Убедитесь, что окружение поднялось корректно"
        )

print(scriptutils.warning("Восстанавливаю команды..."))

is_success = True

space_id = input("Выберете id команды, которую нужно восстановить:").strip().lower()
try:
    space_id_int = int(space_id)
except ValueError:
    scriptutils.die("Некорректный id команды")

is_cli_mysql_settings = (
    args.buffer_pool_size is not None
    or args.innodb_thread_concurrency is not None
    or args.table_open_cache is not None
)

try:
    if is_cli_mysql_settings:
        mysql_settings = team_mysql_settings.make_settings(
            args.buffer_pool_size,
            args.innodb_thread_concurrency,
            args.table_open_cache,
        )
    else:
        mysql_settings = team_mysql_settings.get_for_company(team_config_path, space_id_int)
except ValueError as e:
    scriptutils.die(str(e))

mysql_settings_json = team_mysql_settings.to_json(mysql_settings)

log_text = "Восстанавливаем команду %s" % space_id
print(log_text)

repair_command = 'php src/Compass/Pivot/sh/php/domino/repair_company.php --company-id="%s"' % space_id
if mysql_settings_json != "":
    repair_command += " --mysql-settings-json=%s" % shlex.quote(mysql_settings_json)

output = found_pivot_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        repair_command,
    ],
)
if output.exit_code != 0:
    output = found_pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            repair_command,
        ],
    )
    if output.exit_code != 0:
        print(output.output.decode("utf-8", errors="ignore"))
        is_success = False
        print(scriptutils.error("Не смог восстановить команду %s" % space_id))
        scriptutils.die(
            "Что то пошло не так. Не смогли восстановить команду %s. Проверьте, что окружение поднялось корректно" % space_id
        )

if is_success:
    if is_cli_mysql_settings and mysql_settings_json != "":
        team_mysql_settings.set_for_company(team_config_path, space_id_int, mysql_settings)

    print(scriptutils.success("Команды восстановлены"))
