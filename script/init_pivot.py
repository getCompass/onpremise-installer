#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl python_on_whales mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачи:
# – загружает/обновляет дефолтные файлы
# – обновляет аватары ботов
# – создает системных ботов (если они не были созданы ранее)
# Скрипт может быть запущен неоднократно

import sys

sys.dont_write_bytecode = True

import os, argparse, yaml, pwd, json, psutil
from python_on_whales import docker, exceptions
from utils import scriptutils
from time import sleep

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')

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

# получаем контейнер php-монолита
timeout = 10
n = 0
while n <= timeout:

    if environment == '' or values_arg == '':
        docker_container_list = docker.container.list(filters={'name': 'monolith_php-monolith', 'health': 'healthy'})
    else:
        docker_container_list = docker.container.list(filters={'name': '%s-monolith_php-monolith' % (stack_name_prefix), 'health': 'healthy'})

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

try:

    for script in exec_script_list:
        output = found_php_monolith_container.execute(user='www-data', command=['bash', '-c', script])

except exceptions.DockerException as e:

    print(e.stderr)
    print(e.stdout)
    scriptutils.error('Что-то пошло не так. Выполнение одного из скриптов завершилось неудачей')

scriptutils.success('Pivot успешно инициализирован')
