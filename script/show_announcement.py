#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Показать активные анонсы

import sys

sys.dont_write_bytecode = True

import argparse, yaml, psutil
import docker
from utils import scriptutils
from time import sleep

# ---АГРУМЕНТЫ СКРИПТА---#
def print_usage():
    print("""
Скрипт для отображения активных анонсов

Использование:
    python3 script/show_announcement.py -v VALUES -e ENVIRONMENT -c COMPANYID

Обязательные параметры:
    -v, --values        Название values файла окружения (например: compass)
    -e, --environment   Окружение, в котором развернут проект (например: production)
    -c, --company-id    Id компании из которой показать анонсы. 0 - если показываем глобальные анонсы

Пример:
    python3 script/show_announcement.py -v compass -e production -c 0
    """)
    sys.exit(1)

parser = argparse.ArgumentParser(add_help=False)
parser.error = lambda message: print_usage()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('-c', '--company-id', required=False, default=0, type=str, help='Id компании в которой хотим посмотреть анонсы')

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

client = docker.from_env()

# получаем контейнер monolith
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "%s-monolith_php-monolith" % stack_name_prefix,
            "health": "healthy",
        }
    )

    if len(docker_container_list) > 0:
        found_php_monolith_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для работы с анонсами. Убедитесь, что окружение поднято корректно."
        )

# ---Показываем все активные анонсы---#
cmd = f"""echo '{args.company_id}

' | php /app/src/Compass/Announcement/sh/php/show_active.php"""

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        cmd
    ],
)

if output.exit_code == 0:
    output_lines = output.output.decode("utf-8").splitlines()
    filtered_output = "\n".join(output_lines[2:])
    
    if filtered_output.strip():
        print(filtered_output)
    else:
        print(scriptutils.success("Нет активных анонсов"))
else:
    print(output.output.decode("utf-8"))
    print(scriptutils.error("Ошибка - не смогли вывести все активные анонсы"))
    sys.exit(0)
