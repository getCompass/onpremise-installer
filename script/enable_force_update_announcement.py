#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Повесить анонс принудительного обновления

import sys

sys.dont_write_bytecode = True

import argparse, yaml, psutil
import docker
from utils import scriptutils
from time import sleep
from pathlib import Path


# ---АГРУМЕНТЫ СКРИПТА---#
def print_usage():
    print("""
Скрипт для установки анонса принудительного обновления приложения

Использование:
    python3 script/enable_force_update_announcement.py -v VALUES -e ENVIRONMENT -p PLATFORM -c VERSION

Обязательные параметры:
    -v, --values        Название values файла окружения (например: compass)
    -e, --environment   Окружение, в котором развернут проект (например: production)
    -p, --platform      Платформа (electron/ios/android)
    -c, --code-version  Версия кода (например: 1001111)

Пример:
    python3 script/enable_force_update_announcement.py -v compass -e production -p ios -c 1001111
    """)
    sys.exit(1)


parser = argparse.ArgumentParser(add_help=False)
parser.error = lambda message: print_usage()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('-p', '--platform', required=True, type=str, choices=['electron', 'ios', 'android'],
                    help='Платформа (electron/ios/android)')
parser.add_argument('-c', '--code-version', required=True, type=str, help='Версия кода (например: 1102339)')

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

service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

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
            "Не был найден необходимый docker-контейнер для работы с анонсами. Убедитесь, что окружение поднято корректно."
        )

# Add platform mapping
PLATFORM_TYPE_MAP = {
    'electron': 33,
    'ios': 31,
    'android': 32
}

# Convert platform name to announcement type
announcement_type = PLATFORM_TYPE_MAP[args.platform]

# ---Вешаем анонс принудительного обновления---#
cmd = f"""echo '{announcement_type}
y

y
0
y
0

<{args.code_version}
y' | php /app/src/Compass/Announcement/sh/php/publish_announcement.php"""

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        cmd
    ],
)
if output.exit_code == 0:
    print(scriptutils.success("Установили анонс принудительного обновления"))
else:
    print(output.output.decode("utf-8"))
    print(scriptutils.error("Ошибка - не смогли поставить анонс принудительного обновления"))
    sys.exit(0)
