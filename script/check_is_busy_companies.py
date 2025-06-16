#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker python-dotenv psutil

import sys

sys.dont_write_bytecode = True

import os
import argparse
import yaml
import pwd
import psutil
import docker
from pathlib import Path
from time import sleep
from utils import scriptutils

# --- АРГУМЕНТЫ СКРИПТА ---#
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')
args = parser.parse_args()
# --- КОНЕЦ АРГУМЕНТОВ ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

# проверка нужных системных пользователей
for user in ('www-data',):
    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die(f"Необходимо создать пользователя окружения: {user}")

# docker-клиент
client = docker.from_env()

# ищем healthy php-monolith контейнер
timeout = 30
interval = 5
elapsed = 0
found_monolith = None

while elapsed < timeout:
    containers = client.containers.list(
        filters={
            'name': f'{stack_name_prefix}-monolith_php-monolith',
            'health': 'healthy'
        }
    )
    if containers:
        found_monolith = containers[0]
        break
    sleep(interval)
    elapsed += interval

if not found_monolith:
    scriptutils.die(
        'Не был найден необходимый docker-контейнер для php-monolith. '
        'Убедитесь, что сервис поднят и контейнер помечен как healthy.'
    )

output = found_monolith.exec_run(user='www-data', cmd=['bash', '-c',
                                                       'php /app/src/Compass/Pivot/sh/php/domino/check_is_busy_companies.php'])
if output.exit_code != 0:
    print(output.output.decode("utf-8"))
    exit(1)
