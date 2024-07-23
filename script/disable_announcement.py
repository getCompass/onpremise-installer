#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# отключения анонса в Compass On-premise

import sys

sys.dont_write_bytecode = True

import argparse, yaml, psutil
import docker
from utils import scriptutils
from time import sleep

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('--announcement-id', required=True, type=int, help='Введите путь до директории экспорта данных из slack')

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
            "Не был найден необходимый docker-контейнер для работы с анонсами технических работ. Убедитесь, что окружение поднято корректно."
        )

# ---Убираем анонс технических работ с компании---#

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Announcement/sh/php/migration/disable_announcement.php --announcement_id=%i" % args.announcement_id,
    ],
)

if output.exit_code == 0:
    print(output.output.decode("utf-8"))
    print(scriptutils.success("Убрали анонс технических работ с команды"))
else:
    print(scriptutils.warning("Ошибка - не смогли убрать анонс технических работ с команды"))
    sys.exit(0)
