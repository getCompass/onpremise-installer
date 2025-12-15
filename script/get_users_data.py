#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# миграции данных из slack в Compass On-premise

import sys
import time

sys.dont_write_bytecode = True

import argparse, yaml, pwd, psutil
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
import socket

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект')

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

# необходимые пользователи для окружения
required_user_list = ['www-data']

script_dir = str(Path(__file__).parent.resolve())
values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, args.values))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

# получаем путь до директории установки компаса
with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект'))

    root_mount_path = current_values['root_mount_path']

# проверяем наличие необходимых пользователей
for user in required_user_list:

    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die('Необходимо создать пользователя окружения' + user)

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
            "Не был найден необходимый docker-контейнер для получения пользователей. Убедитесь, что окружение поднялось корректно"
        )

# ---Получение списка пользователей pivot---#
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Pivot/sh/php/migration/get_users_data.php",
    ],
)

print(output.output.decode())