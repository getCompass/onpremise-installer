#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# миграции данных из slack в Compass On-premise

import sys
import time

sys.dont_write_bytecode = True

import argparse, yaml, pwd, psutil, shutil
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
import socket

# получение свободного порта на сервере
def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('', 0))
        return sock.getsockname()[1]

# распаршивает строку с параметрами в словарь
def parse_string_to_dict(string):
    params = {}
    parts = string.split()
    current_key = None

    for part in parts:
        if '=' in part:
            key, value = part.split('=')
            params[key.strip()] = value.strip()
            current_key = key.strip()
        else:
            if current_key:
                params[current_key] += ' ' + part

    return params

# выводит список имен из массива данных
def print_options(data):
    for i, item in enumerate(data):
        print(f"{i + 1}. {item['name']}")

# получает выбор пользователя из консоли и возвращает выбранный элемент
def get_user_choice(data):
    print_options(data)
    choice = int(input("Введите company_id команды в Compass (в которой делали ранее миграцию): "))
    return data[choice - 1]

def list_of_dicts_to_strings(data):
    result = []
    for item in data:
        if isinstance(item, str):
            item = parse_string_to_dict(item)
            result.append(dict_to_string(item))
        elif isinstance(item, dict):
            result.append(dict_to_string(item))
        else:
            raise ValueError(f"Expected a dictionary or string in the list, but got {type(item)}")
    return result

def list_of_strings_to_dicts(data):
    result = []
    for item in data:
        if isinstance(item, str):
            result.append(parse_string_to_dict(item))
        elif isinstance(item, dict):
            result.append(item)
        else:
            raise ValueError(f"Expected a dictionary or string in the list, but got {type(item)}")
    return result

def dict_to_string(params):
    # Проверяем, действительно ли params является словарем
    if not isinstance(params, dict):
        raise ValueError(f"Expected a dictionary, but got {type(params)}")

    # Преобразуем словарь в строку с параметрами
    parts = [f"{key}={value}" for key, value in params.items()]
    return ' '.join(parts)

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('--manticore_host', required=False, default="", type=str, help='Введите ip хоста на котором будет поднята manticore (ip текущего сервера)')
parser.add_argument('--manticore_port', required=False, default="", type=str, help='Введите port на котором будет поднята manticore (например: 9315)')
parser.add_argument('--manticore_mount_workdir', required=True, type=str, help='Введите путь папки маунта manticore')
parser.add_argument('--slack_export_workdir', required=True, type=str, help='Введите путь до директории экспорта данных из slack')

args = parser.parse_args()

slack_export_workdir = args.slack_export_workdir
manticore_host = args.manticore_host
manticore_mount = args.manticore_mount_workdir

if args.manticore_port == "":
    # получаем свободный порт для мантикоры
    manticore_port = int(get_free_port())
else:
    manticore_port = int(args.manticore_port)

script_dir = str(Path(__file__).parent.resolve())
values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, args.values))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект'))

    nginx_company_port = current_values['projects']['domino']['d1']['service']['nginx']['external_https_port']
    company_host = current_values['projects']['domino']['d1']['code_host']
    domino_url = "https://" + company_host + ":" + str(nginx_company_port)

    # для onedomain
    if 'url_path' in current_values['projects']['domino']['d1'] and current_values['projects']['domino']['d1']['url_path']:
        domino_url = domino_url + "/" + current_values['projects']['domino']['d1']['url_path']

    # для production
    if args.environment == "production":
        domino_url = domino_url + "/" + current_values['projects']['domino']['d1']['label']

if manticore_host == "":
    # получаем ip тачки
    manticore_host = current_values['projects']['pivot']['host']

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

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
            "Не был найден необходимый docker-контейнер для создания пользователя. Убедитесь, что окружение поднялось корректно"
        )

# получаем контейнер file_node
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "%s_php-file-node-file1" % stack_name,
            "health": "healthy",
        }
    )

    if len(docker_container_list) > 0:
        found_php_file_node_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для импорта файлов. Убедитесь, что окружение поднялось корректно"
        )

# ---Поднимаем контейнер мантикоры и мигратора---#

# получаем контейнер поднятого manticore
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "compass-migration-manticore",
        }
    )

    if len(docker_container_list) > 0:
        manticore_container = docker_container_list[0]

        # Получаем информацию о контейнере
        container_info = manticore_container.attrs

        # Извлекаем порт из информации о контейнере
        ports = container_info['NetworkSettings']['Ports']

        # Находим порт, который нас интересует (например, порт 9308)
        for port_key, port_value in ports.items():
            if port_key == '9306/tcp':
                manticore_port = int(port_value[0]['HostPort'])
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        print("Не нашли ранее развернутый контейнер мантикоры")
        exit(1)

# получаем контейнер поднятого exporter
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "compass-migration-exporter",
        }
    )

    if len(docker_container_list) > 0:
        exporter_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        print("Не нашли ранее развернутый контейнер мигратора")
        exit(1)

# ---Получение списка компаний из pivot---#

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Pivot/sh/php/migration/get_active_company_list.php",
    ],
)

if output.exit_code != 0:
    print(output.output.decode("utf-8"))
    scriptutils.error('Получение списка компаний завершилось неудачей')
    exit(1)

output_arrays = output.output.decode("utf-8").splitlines()

# Исправьте данные предварительно
corrected_data = list_of_strings_to_dicts(output_arrays)

# Получаем выбор пользователя
selected_item = get_user_choice(corrected_data)

# Выводим выбранный элемент
print("Вы выбрали:", selected_item)

# ---чистим чаты---#
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Conversation/sh/php/migration/leave_from_conversations.php --local_manticore_host='%s' --local_manticore_port=%s --company_url='%s' --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)

for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Успешно очистили чаты"))
else:
    print(scriptutils.warning("Ошибка при очистке перенесенных чатов"))
    sys.exit(0)

# ---трем файл с текущими загрузками---#
output = found_php_file_node_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        ">/app/src/Compass/FileNode/sh/php/migration/migration-file-download.log"
    ],
)

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Очистили скаченные файлы"))
else:
    print(scriptutils.warning("Ошибка при очистке перенесенных файлов"))
    sys.exit(0)

print(scriptutils.success("Очистка перенесенных данных выполнена"))
print(scriptutils.success("Процесс завершен"))