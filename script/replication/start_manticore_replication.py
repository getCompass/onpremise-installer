#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, subprocess, re, json
import docker
import glob
import logging
from typing import Dict
from time import sleep

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path

scriptutils.assert_root()

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=True)

parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="окружение")
parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="название файла со значениями для деплоя")
parser.add_argument("-t", "--type", required=False, default="master", type=str, help="тип репликации (master|reserve)")
parser.add_argument("--master-mysql-server-id", required=False, default=1, type=int, help="server_id мастер сервера")
parser.add_argument('--need-update-company', required=False, default=0, type=int, help='нужно ли обновление для компаний')

args = parser.parse_args()
environment = args.environment
values_name = args.values
replication_type = args.type.lower()
master_mysql_server_id = args.master_mysql_server_id
need_update_company = args.need_update_company

script_dir = str(Path(__file__).parent.resolve())

# класс конфига пространства
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password


# получить данные окружение из values
def get_values() -> Dict:
    default_values_file_path = Path("%s/../../src/values.yaml" % (script_dir))
    values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_name))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = scriptutils.merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


def start():
    # получаем значения для выбранного окружения
    current_values = get_values()
    security = scriptutils.get_security(current_values)
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    domino_id = domino["label"]

    stack_name = current_values["stack_name_prefix"] + "-monolith"
    service_label = current_values["service_label"]
    if service_label is None or service_label == "":
        scriptutils.die("Пустое значение service_label в файле src/values.%s.yaml" % values_name)

    stack_name = stack_name + "-" + service_label

    manticore_cluster_name = current_values["manticore_cluster_name"]

    client = docker.from_env()

    # получаем контейнер monolith
    timeout = 30
    n = 0
    while n <= timeout:

        docker_container_list = client.containers.list(
            filters={
                "name": "%s_php-monolith" % (stack_name),
                "health": "healthy",
            }
        )

        if len(docker_container_list) > 0:
            found_monolith_container = docker_container_list[0]
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die(
                "Не был найден необходимый docker-контейнер manticore. Убедитесь, что окружение поднялось корректно"
            )

    manticore_host = domino["service"]["manticore"]["host"]
    manticore_external_port = domino["service"]["manticore"]["external_port"]

    # инициализируем кластер в контейнере manticore
    print("Инициализируем кластер в контейнере manticore")
    if replication_type == "master":
        mysql_command = "CREATE CLUSTER %s;" % manticore_cluster_name
    else:

        # пробуем удалить кластер, если ранее в мантикоре тот успел подняться
        try:
            mysql_command = "DELETE CLUSTER %s;" % manticore_cluster_name
            manticore_replication(found_monolith_container, mysql_command, manticore_host, manticore_external_port, 0)
        except:
            pass
        mysql_command = "JOIN CLUSTER %s AT 'manticore-%s:9312';" % (manticore_cluster_name, master_mysql_server_id)
    manticore_replication(found_monolith_container, mysql_command, manticore_host, manticore_external_port, 1)

    if need_update_company != 1:
        return

    # формируем список активных пространств
    timeout = 60
    n = 0
    while n <= timeout:
        space_config_obj_dict = get_space_dict(current_values)
        if len(space_config_obj_dict) > 0:
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

    print("Обновляем команды - прикрепляем созданные ранее таблицы manticore к кластеру")
    for space_id, space_config_obj in space_config_obj_dict.items():

        print("Прикрепляем к кластеру команду %s" % space_id)
        mysql_command = "ALTER CLUSTER %s ADD main_%s;" % (manticore_cluster_name, space_id)
        manticore_replication(found_monolith_container, mysql_command, manticore_host, manticore_external_port, 1)


# запускаем репликацию мантикоры
def manticore_replication(found_container: docker.models.containers.Container, mysql_command: str, manticore_host: str, manticore_external_port: int, is_need_log: int):

    cmd = "mariadb --skip-ssl -h %s -P %s -e \"%s\"" % (manticore_host, manticore_external_port, mysql_command)

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nНе смогли найти контейнер manticore")
        return

    if is_need_log == 1:
        if result.exit_code == 0:
            print("\nЗавершили запуск репликации для manticore")
        else:
            print("Ошибка при запуске репликации для manticore")
            if result.output:
                print("Результат выполнения:\n", result.output.decode("utf-8", errors="ignore"))
            sys.exit(result.exit_code)

# сформировать список конфигураций пространств
def get_space_dict(current_values: Dict) -> Dict[int, DbConfig]:
    # получаем название домино
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]
    domino_id = domino["label"]

    # формируем список пространств
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

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            domino_id,
            int(space_id),
            space_config_dict["mysql"]["host"],
            space_config_dict["mysql"]["port"],
            "root",
            "root",
        )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
    return space_config_obj_dict

# точка входа в скрипт
start()
