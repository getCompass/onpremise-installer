#!/usr/bin/env python3
import sys

sys.dont_write_bytecode = True

import argparse, re, yaml, json, glob
import os
import logging
import docker, subprocess
import docker.errors, docker.models, docker.models.containers, docker.types

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path
from time import sleep
from typing import Dict, List

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument(
    "-e",
    "--environment",
    required=False,
    default="production",
    type=str,
    help="окружение",
)

parser.add_argument(
    "-v",
    "--values",
    required=False,
    default="compass",
    type=str,
    help="название файла со значениями для деплоя",
)
parser.add_argument("--state", required=True, type=str, help="состояние сервера")
args = parser.parse_args()

values_name = args.values
environment = args.environment
state = args.state
stack_name_prefix = environment + '-' + values_name
stack_name_monolith = stack_name_prefix + "-monolith"

client = docker.from_env()

# класс конфига БД
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str, container_name : str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password
        self.container_name = container_name

# настройка логирования
logging.basicConfig(filename='/var/log/keepalived-state.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# путь до директории с инсталятором
installer_dir = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

default_values_file_path = Path("%s/../src/values.yaml" % (installer_dir))
values_file_path = Path("%s/../src/values.%s.yaml" % (installer_dir, values_name))

def start(state):

    logging.info(f"--- Keepalived state changed to: {state} ---")

    current_values = get_values()

    service_label = ""
    if current_values.get("service_label") is not None and current_values.get("service_label") != "":
        service_label = current_values.get("service_label")

    # конфиг бд для монолита
    monolith = DbConfig(
        "",
        0,
        current_values["projects"]["monolith"]["service"]["mysql"]["host"],
        current_values["projects"]["monolith"]["service"]["mysql"]["port"],
        current_values["projects"]["monolith"]["service"]["mysql"]["user"],
        current_values["projects"]["monolith"]["service"]["mysql"]["password"],
        "%s-%s_mysql" % (stack_name_monolith, service_label)
    )

    # формируем список активных пространств
    space_config_obj_dict = get_space_dict(current_values)

    # действия при переходе в MASTER
    if state == "MASTER":

        logging.info("This server is now MASTER")

        # меняем master_service_label
        change_master_service_label(current_values, current_values.get("service_label"))
        logging.info("Changed master_service_label on Master")

        # запускаем lsyncd файлов и конфигов
        try:
            subprocess.run(["sudo", "systemctl", "restart", "lsyncd"], check=True)
        except subprocess.CalledProcessError as e:
            logging.info(f"Ошибка при рестарте службы lsyncd: {e}")

        # отключаем автозапуск lsyncd
        try:
            subprocess.run(["sudo", "systemctl", "disable", "lsyncd"], check=True)
        except subprocess.CalledProcessError as e:
            logging.info(f"Ошибка при остановке автозапуска lsyncd: {e}")

        logging.info("Restarted lsyncd on Master")

        # останавливаем репликацию
        stop_replication_db_list([monolith])
        stop_replication_db_list(space_config_obj_dict)
        logging.info("Stopped replication on Master")

    # действия при переходе в BACKUP
    elif state == "BACKUP":

        logging.info("This server is now BACKUP")

        # останавливаем lsyncd файлов и конфигов
        try:
            subprocess.run(["sudo", "systemctl", "stop", "lsyncd"], check=True)
        except subprocess.CalledProcessError as e:
            logging.info(f"Ошибка при остановке службы lsyncd: {e}")

        logging.info("Stopped lsyncd on Backup")

        # блочим запись в бд
        lock_write_db_list([monolith])
        lock_write_db_list(space_config_obj_dict)

        logging.info("Locked tables in DB")

        # меняем master_service_label
        change_master_service_label(current_values)
        logging.info("Changed master_service_label on Backup")

    elif state == "FAULT":

        logging.info("This server is now FAULT")

        # останавливаем lsyncd файлов и конфигов
        try:
            subprocess.run(["sudo", "systemctl", "stop", "lsyncd"], check=True)
        except subprocess.CalledProcessError as e:
            logging.info(f"Ошибка при остановке службы lsyncd: {e}")

        logging.info("Stopped lsyncd on Fault")

        # меняем master_service_label
        change_master_service_label(current_values)
        logging.info("Changed master_service_label on Fault")
    else:
        scriptutils.die("Некорректное значение state")

# сформировать список конфигураций пространств
def get_space_dict(current_values: Dict) -> List[DbConfig]:

    # получаем название домино
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]
    domino_id = domino["label"]

    service_label = ""
    if current_values.get("service_label") is not None and current_values.get("service_label") != "":
        service_label = current_values.get("service_label")

    # формируем список пространств
    # пространства выбираются по наличию их конфига
    space_config_obj_dict = []
    for space_config in glob.glob("%s/*_company.json" % space_config_dir):

        s = re.search(r'([0-9]+)_company', space_config)

        if s is None:
            continue

        space_id = s.group(1)
        f = open (space_config, "r")
        space_config_dict = json.loads(f.read())
        f.close()
        if space_config_dict["status"] not in [1,2]:
            continue

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            domino_id,
            int(space_id),
            space_config_dict["mysql"]["host"],
            space_config_dict["mysql"]["port"],
            "root",
            "root",
            "%s-%s-%s-company_mysql-%d" % (stack_name_prefix, service_label, domino_id, space_config_dict["mysql"]["port"])
        )

        space_config_obj_dict.append(space_config_obj)

    return space_config_obj_dict

# получить данные окружения из values
def get_values() -> Dict:

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

def merge(a: Dict, b: Dict, path=[]):

    for key in b:
        if key in a:
            if isinstance(a[key], Dict) and isinstance(b[key], Dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] != b[key]:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a

def change_master_service_label(current_values: Dict, master_service_label: str = ""):

    # получаем путь к файлу для связи компаний между серверами
    servers_companies_relationship_file_path = current_values.get("company_config_mount_path") + "/" + current_values.get("servers_companies_relationship_file")

    # получаем текущий service_label
    current_service_label = current_values.get("service_label")

    if master_service_label == "":

        # читаем содержимое файла
        timeout = 600
        n = 0
        while n <= timeout:

            with open(servers_companies_relationship_file_path, "r") as file:

                reserve_relationship_str = file.read()
                reserve_relationship_dict = json.loads(reserve_relationship_str) if reserve_relationship_str != "" else {}

                for label, data in reserve_relationship_dict.items():
                    if "master" in data and data["master"] == True and label != current_service_label:
                        logging.info("set \"master\" = true for %s" % label)
                        master_service_label = label
                        data["master"] = True
                        reserve_relationship_dict[label] = data
                    if current_service_label == label and label != master_service_label:
                        logging.info("set \"master\" = false for %s" % label)
                        data["master"] = False
                        reserve_relationship_dict[label] = data

            # если определили master_service_label, то останавливаем цикл
            if master_service_label != "":
                f = open(servers_companies_relationship_file_path, "w")
                f.write(json.dumps(reserve_relationship_dict))
                f.close()
                break

            n = n + 5
            sleep(5)
            if n == timeout:
                logging.info("Got empty master_service_label")
                exit(0)
    else:

        with open(servers_companies_relationship_file_path, "r") as file:
            reserve_relationship_str = file.read()
            reserve_relationship_dict = json.loads(reserve_relationship_str) if reserve_relationship_str != "" else {}

            # меняем флаг master = true/false для серверов
            if reserve_relationship_dict.get(current_service_label) is None:
                logging.info("Changed \"master\" = true in current-values for %s" % current_service_label)
                data = {"master": True}
                reserve_relationship_dict[current_service_label] = data
            for label, data in reserve_relationship_dict.items():
                if label == master_service_label and ("master" not in data or data["master"] != True):
                    logging.info("Changed \"master\" = true in current-values for %s" % label)
                    data["master"] = True
                if label != master_service_label:
                    logging.info("Changed \"master\" = false in current-values for %s" % label)
                    data["master"] = False
                reserve_relationship_dict[label] = data

        f = open(servers_companies_relationship_file_path, "w")
        f.write(json.dumps(reserve_relationship_dict))
        f.close()

    logging.info("Changed \"master_service_label\" = %s in current-values" % master_service_label)

    with values_file_path.open("r") as values_file:
        new_values = yaml.safe_load(values_file)
        new_values = {} if new_values is None else new_values
    new_values["master_service_label"] = master_service_label

    write_to_file(new_values)

def write_to_file(new_values: Dict):
    new_path = Path(str(values_file_path.resolve()))
    with new_path.open("w+t") as f:
        yaml.dump(new_values, f, sort_keys=False)

# останавливаем репликацию БД
def stop_replication_db_list(db_list: list[DbConfig]):

    for db in db_list:

        container_list = client.containers.list(filters= {"name": db.container_name})

        if len(container_list) < 1:
            scriptutils.die("Пространство %d не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения." % db.space_id)

        space_container : docker.models.containers.Container = container_list[0]

        # mysql команда для выполнения
        mysql_command = "STOP SLAVE; SET GLOBAL super_read_only = OFF; SET GLOBAL read_only = OFF; UNLOCK TABLES;"

        cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
        result = space_container.exec_run(cmd=cmd)

        if result.exit_code != 0:
            print(result.output)
            scriptutils.die("Не смогли выполнить mysql команду в mysql пространства %d" % db.space_id)

# лочим запись в БД
def lock_write_db_list(db_list: list[DbConfig]):

    for db in db_list:

        container_list = client.containers.list(filters= {"name": db.container_name})

        if len(container_list) < 1:
            scriptutils.die("Пространство %d не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения." % db.space_id)

        space_container : docker.models.containers.Container = container_list[0]

        # mysql команда для выполнения
        mysql_command = "SET GLOBAL read_only = ON; SET GLOBAL super_read_only = ON; FLUSH TABLES WITH READ LOCK;"

        cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
        result = space_container.exec_run(cmd=cmd)

        if result.exit_code != 0:
            print(result.output)
            scriptutils.die("Не смогли выполнить mysql команду в mysql пространства %d" % db.space_id)

start(state)