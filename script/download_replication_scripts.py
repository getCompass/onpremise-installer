#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Загрузить скрипты заполнения для stage сервера

import sys
sys.dont_write_bytecode = True

import argparse, yaml, psutil
import docker
from time import sleep
import subprocess
import os

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('--from-path', required=False, default="/home/replication_scripts", type=str, help='Путь, откуда копируем скрипты')
args = parser.parse_args()

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
scripts_from_path = args.from_path if args.from_path else ""

# искомый контейнер
partial_name = "%s-%s-monolith_php-monolith" % (environment, values_arg)

result = subprocess.run(['docker', 'ps', '--filter', f'name={partial_name}', '--format', '{{.Names}}'],
                        stdout=subprocess.PIPE)
container_name = result.stdout.decode('utf-8').strip()

try:
    subprocess.run(
        ["docker", "cp", scripts_from_path, f"{container_name}:/app/dev/php"],
        check=True
    )
    print(f"Файлы успешно скопированы в контейнер {container_name}")
except subprocess.CalledProcessError as e:
    print(f"Ошибка: {e}")
