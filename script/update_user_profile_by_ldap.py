#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачи:
# - обновляет профили пользователей в компас, соответственно их профилям в ldap
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

# импортируем в compass сообщения
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Federation/sh/php/update_ldap_user_profile.php"
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Скрипт успешно выполнен"))
else:
    print(scriptutils.error("Ошибка при попытке обновить пользователей"))
    sys.exit(0)