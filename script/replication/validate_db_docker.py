#!/usr/bin/env python3
import sys

import argparse
import os
from pathlib import Path

import yaml

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils

# region АРГУМЕНТЫ СКРИПТА #
parser = scriptutils.create_parser(
    "Скрипт для проверки, что внешние базы данных не используются при настройке репликации.",
    usage="python3 script/replication/validate_db_docker.py [-v VALUES] [-e ENVIRONMENT]",
    epilog="Пример: python3 script/replication/validate_db_docker.py -v compass -e production",
)

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
args = parser.parse_args()

script_dir = str(Path(__file__).parent.resolve())
root_path = str(Path(script_dir + "/../").resolve())

environment = args.environment
values_name = args.values

# проверяем конфигурационный файл с параметрами бд
database_config_path = Path(script_dir + "/../../configs/database.yaml")

if not database_config_path.exists():
    scriptutils.die(
        f"Отсутствует файл конфигурации {str(database_config_path.resolve())}. " +
        f"Запустите скрипт create_configs.py и заполните конфигурацию"
    )

# загружаем конфигурационный файл с параметрами бд
with database_config_path.open("r") as database_config_file:
    database_config: dict = yaml.load(database_config_file, Loader=yaml.BaseLoader)

# проверяем конфигурационный файл с параметрами бд
replication_config_path = Path(script_dir + "/../../configs/replication.yaml")

if not replication_config_path.exists():
    exit(0)

# загружаем конфигурационный файл с параметрами бд
with replication_config_path.open("r") as replication_config_file:
    replication_config: dict = yaml.load(replication_config_file, Loader=yaml.BaseLoader)

# проверяем значение service_label
service_label = replication_config.get("service_label", None)
if service_label is None or service_label == "":
    exit(0)

# проверяем, что не используется внешняя база
if database_config.get("database_connection", {}).get("driver") == "host":
    exit(1)
