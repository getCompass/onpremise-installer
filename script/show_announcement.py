#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Показать активные анонсы

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
Скрипт для отображения активных анонсов

Использование:
    python3 script/show_announcement.py -v VALUES -e ENVIRONMENT -c COMPANYID

Обязательные параметры:
    -v, --values        Название values файла окружения (например: compass)
    -e, --environment   Окружение, в котором развернут проект (например: production)
    -c, --company-id    Id компании из которой показать анонсы. 0 - если показываем глобальные анонсы

Пример:
    python3 script/show_announcement.py -v compass -e production -c 0
    """)
    sys.exit(1)

parser = argparse.ArgumentParser(add_help=False)
parser.error = lambda message: print_usage()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('-c', '--company-id', required=False, default=0, type=str, help='Id компании в которой хотим посмотреть анонсы')

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

# ---Показываем все активные анонсы---#
cmd = f"""echo '{args.company_id}

' | php /app/src/Compass/Announcement/sh/php/show_active.php"""

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        cmd
    ],
)

if output.exit_code == 0:
    output_lines = output.output.decode("utf-8").splitlines()
    filtered_output = "\n".join(output_lines[2:])
    
    if filtered_output.strip():
        print(filtered_output)
    else:
        print(scriptutils.success("Нет активных анонсов"))
else:
    print(output.output.decode("utf-8"))
    print(scriptutils.error("Ошибка - не смогли вывести все активные анонсы"))
    sys.exit(0)
