#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql-connector-python python-dotenv psutil

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

# ищем healthy MySQL-контейнер
timeout = 30
interval = 5
elapsed = 0
found_mysql = None

while elapsed < timeout:
    containers = client.containers.list(
        filters={
            'name': f'{stack_name_prefix}-monolith_mysql-monolith',
            'health': 'healthy'
        }
    )
    if containers:
        found_mysql = containers[0]
        break
    sleep(interval)
    elapsed += interval

if not found_mysql:
    scriptutils.die(
        'Не был найден необходимый docker-контейнер для MySQL. '
        'Убедитесь, что сервис поднят и контейнер помечен как healthy.'
    )

# загружаем values.yaml
script_dir = Path(__file__).parent.resolve()
default_vals = script_dir / '..' / 'src' / 'values.yaml'
env_vals = script_dir / '..' / 'src' / f'values.{values_arg}.yaml'
if not env_vals.exists():
    scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")


def merge(a: dict, b: dict):
    for k, v in b.items():
        if k in a and isinstance(a[k], dict) and isinstance(v, dict):
            merge(a[k], v)
        else:
            a[k] = v
    return a


with open(default_vals) as f:
    defaults = yaml.safe_load(f) or {}
with open(env_vals) as f:
    current = yaml.safe_load(f) or {}

vals = merge(defaults, current)
try:
    svc = vals["projects"]["monolith"]["service"]["mysql"]
    mysql_user = svc["user"]
    mysql_password = svc["password"]
except KeyError:
    scriptutils.die("Не удалось прочитать данные для MySQL из values-файла")

# делаем запрос только тех компаний, у которых is_busy = 1
query = (
    "SELECT company_id, is_busy "
    "FROM pivot_company_service.company_registry_d1 "
    "WHERE is_busy = 1;"
)
cmd = [
    "mysql",
    f"-u{mysql_user}",
    f"-p{mysql_password}",
    "-N",  # убираем заголовки столбцов
    "-e", query
]

exit_code, streams = found_mysql.exec_run(cmd=cmd, demux=True)
stdout, stderr = streams if isinstance(streams, tuple) else (streams, b'')

out_text = (stdout or b'').decode('utf-8', errors='ignore').strip()
err_text = (stderr or b'').decode('utf-8', errors='ignore').strip()

# если mysql вернул ошибку — сразу фатал
if exit_code != 0:
    print("Не смогли проверить компании")
    exit(1)

# если в stdout есть хоть что-то — это реальные строки
if out_text:
    exit(1)