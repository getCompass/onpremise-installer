#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Удаление команды

import sys
import time

sys.dont_write_bytecode = True

import argparse, yaml, pwd, psutil
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
import socket

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('-c', '--company-id', required=True, type=int, help='ID команды для удаления')

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
company_id = args.company_id if args.company_id else 0
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

script_dir = str(Path(__file__).parent.resolve())
values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, args.values))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

if company_id < 1:
    scriptutils.die(('Некорректный id компании'))

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

# необходимые пользователи для окружения
required_user_list = ['www-data']

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
            "name": "%s_php-monolith" % stack_name,
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
            "Не был найден необходимый docker-контейнер. Убедитесь, что окружение поднялось корректно"
        )

# ---Получение информации о команде и запрос подтверждения---#
# Сначала получаем информацию о команде
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Pivot/sh/php/service/delete_team.php --company_id=%s --confirm=0"
        % company_id,
    ],
)

output_str = output.output.decode()

# Проверяем, есть ли информация о команде
if "Компания не найдена" in output_str:
    print(output_str)
    sys.exit(1)

print(output_str)
print("Вы действительно хотите удалить эту команду? [Y/n]")

# Запрашиваем подтверждение у пользователя
try:
    result = input().strip().lower()
except (EOFError, KeyboardInterrupt):
    result = "n"

if result != "y":
    print("Действие отменено")
    sys.exit(1)

# ---Удаление команды---#
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Pivot/sh/php/service/delete_team.php --company_id=%s --confirm=1"
        % company_id,
    ],
)

print(output.output.decode())