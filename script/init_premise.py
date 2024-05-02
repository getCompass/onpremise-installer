#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачи:
# – создаёт пользователей в premise окружении
# – создаёт связь пользователей и пространств в premise окружении
# Скрипт может быть запущен неоднократно

import sys

sys.dont_write_bytecode = True

import os, argparse, yaml, pwd, json, psutil
import docker
from utils import scriptutils
from time import sleep

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

# необходимые пользователи для окржуения
required_user_list = ['www-data']

# проверяем наличие необходимых пользователей
for user in required_user_list:

    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die('Необходимо создать пользователя окружения' + user)

client = docker.from_env()

# получаем контейнер php-monolith
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(filters={'name': '%s-monolith_php-monolith' % (stack_name_prefix), 'health': 'healthy'})

    if len(docker_container_list) > 0:
        found_php_monolith_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            'Не был найден необходимый docker контейнер для запуска скриптов. Проверьте, что окружение поднялось корректно')

exec_script_list = [
    'php src/Compass/Premise/sh/php/migrations/1_add_users.php',
    'php src/Compass/Premise/sh/php/migrations/2_actualize_space_users.php',
]

for script in exec_script_list:
    output = found_php_monolith_container.exec_run(user='www-data', cmd=['bash', '-c', script])

    if output.exit_code != 0:

        print(output.output.decode("utf-8"))
        print(scriptutils.error('Что-то пошло не так. Выполнение одного из скриптов закончилось неудачей'))
        exit(1)

print(scriptutils.success('Скрипт обновления premise окружения успешно выполнен'))
