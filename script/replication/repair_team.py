#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, glob, re, json
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

parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="Название values файла окружения")
parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="Окружение, в котором разворачиваем")
parser.add_argument('--service_label', required=False, default="", type=str, help='Метка сервиса, к которому закреплён стак')

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

space_id = input("Выберете id команды, которую нужно восстановить:").lower()

log_text = "Восстанавливаем команду %s" % space_id
print(log_text)
output = found_pivot_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        'php src/Compass/Pivot/sh/php/domino/repair_company.php --company-id="%s"' % space_id,
    ],
)
if output.exit_code != 0:
    output = found_pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            'php src/Compass/Pivot/sh/php/domino/repair_company.php --company-id="%s"' % space_id,
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
    print(scriptutils.success("Команды восстановлены"))
