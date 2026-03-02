#!/usr/bin/env python3
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse, re, yaml, json, glob, os, tarfile, shutil
import docker
import docker.errors, docker.models, docker.models.containers, docker.types
from utils import scriptutils
from pathlib import Path
from loader import Loader
from datetime import datetime
from math import ceil
import subprocess
import mysql.connector
import socket

scriptutils.assert_root()

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для разблокировки процесса бэкапов баз данных.",
    usage="python3 script/unlock_backups.py [-v VALUES] [-e ENVIRONMENT]",
    epilog="Пример: python3 script/backup_db.py -v compass -e production",
)

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
args = parser.parse_args()

values_name = args.values
environment = args.environment

stack_name_prefix = f"{environment}-{values_name}"

client = docker.from_env()
script_dir = str(Path(__file__).parent.resolve())

# класс конфиг бд
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str,
                 backup_user: str, backup_password: str, driver: str, container_name: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password
        self.backup_user = backup_user
        self.backup_password = backup_password
        self.driver = driver
        self.container_name = container_name


# точка входа в скрипт
def start():
    # получаем значения для выбранного окружения
    current_values = get_values()

    stack_name_monolith = stack_name_prefix + "-monolith"
    stack_name_domino = stack_name_prefix
    service_label = current_values.get("service_label") if current_values.get("service_label") else ""
    if service_label != "":
        stack_name_monolith = stack_name_monolith + "-" + service_label
        stack_name_domino = stack_name_domino + "-" + service_label

    # unlock монолита
    unlock_monolith_backup(current_values, stack_name_monolith)

    # unlock пространств
    unlock_space_backup(current_values, stack_name_domino)


# выполняем unlock монолита
def unlock_monolith_backup(current_values: dict, stack_name_monolith: str):

    db_host = current_values["database_connection"]["driver_data"]["project_mysql_hosts"]["monolith"]["host"] if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["host"]

    db_port = current_values["database_connection"]["driver_data"]["project_mysql_hosts"]["monolith"]["port"] if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["port"]

    db_root_user = "root" if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["user"]

    db_root_password = current_values["database_connection"]["driver_data"]["project_mysql_hosts"]["monolith"][
        "root_password"] if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["password"]

    monolith = DbConfig(
        "",
        0,
        db_host,
        db_port,
        db_root_user,
        db_root_password,
        current_values["backup_user"],
        current_values["backup_user_password"],
        current_values["database_connection"]["driver"],
        "%s_mysql-monolith" % stack_name_monolith
    )

    unlock_backup([monolith])


# выполняем unlock пространств
def unlock_space_backup(current_values: dict, stack_name_domino: str):

    # формируем список активных пространств
    space_config_obj_dict = get_space_dict(current_values, stack_name_domino)

    if len(space_config_obj_dict) < 1:
        scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

    need_space_obj_list = []
    # формируем список пространств для бэкапа
    for space_id, space_config_obj in space_config_obj_dict.items():
            need_space_obj_list.append(space_config_obj)

    # начинаем бэкап пространств
    unlock_backup(need_space_obj_list)


# выполняем unlock для выбранных бд
def unlock_backup(db_list: list[DbConfig]):
    client = docker.from_env()

    # SQL-команда для гарантированного убийства сессии, держащей лок
    kill_sql = (
        "SELECT ID FROM information_schema.processlist "
        "WHERE ID = IS_USED_LOCK('backup_lock') INTO @lock_id; "
        "SET @s = IF(@lock_id IS NOT NULL, CONCAT('KILL ', @lock_id), 'SELECT 1'); "
        "PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;"
    )

    for db in db_list:
        print(f"--- Проверка блокировок для: {db.space_id or 'MONOLITH'} (Port: {db.port}) ---")

        if db.driver == "host":
            try:
                conn = mysql.connector.connect(
                    host=db.host, port=db.port,
                    user=db.root_user, password=db.root_password,
                    connect_timeout=5
                )
                cursor = conn.cursor()
                cursor.execute(kill_sql)
                conn.commit()
                conn.close()
                print(f"[OK] Лок на хосте {db.host}:{db.port} проверен/снят.")
            except Exception as e:
                print(f"[ERROR] Не удалось подключиться к хосту {db.host}: {e}")
        else:
            try:
                container = prepare_db(db)
                if container:
                    cmd = f"mysql -h localhost -u {db.root_user} -p{db.root_password} -e \"{kill_sql}\""
                    result = container.exec_run(cmd)
                    if result.exit_code == 0:
                        print(f"[OK] Команда очистки выполнена в контейнере {container.name}")
                    else:
                        print(f"[FAIL] Ошибка выполнения в контейнере: {result.output.decode()}")
                else:
                    print(f"[SKIP] Контейнер для {db.space_id} не найден.")
            except Exception as e:
                print(f"[ERROR] Ошибка при работе с контейнером {db.space_id}: {e}")


# готовим БД для unlock
def prepare_db(db: DbConfig) -> docker.models.containers.Container | None:
    if db.driver == "host":
        return None

    container_list = client.containers.list(filters={"name": db.container_name})
    if len(container_list) < 1:
        scriptutils.die(
            "Пространство %d не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения." % db.space_id)

    space_container: docker.models.containers.Container = container_list[0]

    return space_container


# сформировать список конфигураций пространств
def get_space_dict(current_values: dict, stack_name_domino: str) -> dict[int: DbConfig]:
    # получаем название домино
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]
    domino_id = domino["label"]

    # формируем список пространств, доступных для бэкапа
    # пространства выбираются по наличию их конфига
    space_config_obj_dict = {}
    for space_config in glob.glob("%s/*_company.json" % space_config_dir):

        s = re.search(r'([0-9]+)_company', space_config)

        if s is None:
            continue

        space_id = s.group(1)
        f = open(space_config, "r")
        space_config_dict = json.loads(f.read())
        f.close()
        if space_config_dict["status"] not in [1, 2]:
            continue

        db_root_password = \
            current_values["database_connection"]["driver_data"]["company_mysql_hosts"][int(space_id) - 1][
                "root_password"] if \
                current_values["database_connection"]["driver"] == "host" else \
                "root"

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            domino_id,
            int(space_id),
            space_config_dict["mysql"]["host"],
            space_config_dict["mysql"]["port"],
            "root",
            db_root_password,
            current_values["backup_user"],
            current_values["backup_user_password"],
            current_values["database_connection"]["driver"],
            "%s-%s-company_mysql-%d" % (stack_name_domino, domino_id, space_config_dict["mysql"]["port"])
        )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
    return space_config_obj_dict


# получить данные окружение из values
def get_values() -> dict:
    default_values_file_path = Path("%s/../src/values.yaml" % script_dir)
    values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


def merge(a: dict, b: dict, path=[]):
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] != b[key]:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a


start()