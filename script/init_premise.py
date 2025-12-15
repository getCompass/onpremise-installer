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
from pathlib import Path
from utils import scriptutils
from time import sleep

# ---АРГУМЕНТЫ СКРИПТА---#
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
stack_name = stack_name_prefix + "-monolith"

script_dir = str(Path(__file__).parent.resolve())

values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, values_arg))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))


with values_file_path.open('r') as values_file:

    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

    domino_project = current_values['projects']['domino']

    if len(domino_project) < 1:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

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

    docker_container_list = client.containers.list(filters={'name': '%s_php-monolith' % (stack_name), 'health': 'healthy'})

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
