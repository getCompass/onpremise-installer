#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачи:
# – загружает/обновляет дефолтные файлы
# – обновляет аватары ботов
# – создает системных ботов (если они не были созданы ранее)
# Скрипт может быть запущен неоднократно

import sys

sys.dont_write_bytecode = True

import os, argparse, yaml, pwd, json, psutil
import docker
from utils import scriptutils
from time import sleep

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')
parser.add_argument('--service_label', required=False, default="", type=str,
                    help='Метка сервиса, к которому закреплён стак')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
service_label = args.service_label if args.service_label else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

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

# получаем контейнер php-монолита
timeout = 30
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={'name': '%s_php-monolith' % (stack_name), 'health': 'healthy'})

    if len(docker_container_list) > 0:
        found_php_monolith_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            'Не был найден необходимый docker-контейнер для запуска скриптов. Убедитесь, что окружение поднялось корректно')

exec_script_list = [
    'php src/Compass/Pivot/sh/php/service/upload_default_file_list.php',
    'php src/Compass/Pivot/sh/php/service/check_default_file_list.php',
    'php src/Compass/Pivot/sh/start/create_system_bot_list.php',
    'php src/Compass/Pivot/sh/php/update/update_notice_bot.php',
    'php src/Compass/Pivot/sh/php/update/update_remind_bot.php',
    'php src/Compass/Pivot/sh/php/update/update_support_bot.php',
    'php src/Compass/Pivot/sh/php/update/replace_userbot_avatar.php',
    'php src/Compass/Pivot/sh/php/update/replace_preview_for_welcome_video.php',
]

for script in exec_script_list:

    output = found_php_monolith_container.exec_run(user='www-data', cmd=['bash', '-c', script])

    if output.exit_code != 0:
        print(output.output.decode("utf-8"))
        scriptutils.error('Что-то пошло не так. Выполнение одного из скриптов завершилось неудачей')
        exit(1)

scriptutils.success('Pivot успешно инициализирован')
