#!/usr/bin/env python3
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse, re, yaml, json, glob, os, tarfile, shutil
import docker
import docker.errors, docker.models, docker.models.containers, docker.types
from math import ceil
from utils import scriptutils
from pathlib import Path
from loader import Loader
from time import sleep
from datetime import datetime

scriptutils.assert_root()

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
parser.add_argument('-y', '--yes', required=False, action='store_true', help='Согласиться на все')
args = parser.parse_args()

values_name = args.values
environment = args.environment
stack_name_prefix = environment + '-' + values_name

need_backup_spaces =True
need_backup_monolith = True

client = docker.from_env()

script_dir = str(Path(__file__).parent.resolve())

XTRABACKUP_IMAGE="docker.getcompass.ru/backend_compass/xtrabackup"
XTRABACKUP_VERSION="8.0.28-21"
NEED_APP_VERSION = "4.1.0"

# класс конфига пространства
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str, backup_user: str, backup_password: str, db_path: str, backup_path: str, container_name : str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password
        self.backup_user = backup_user
        self.backup_password = backup_password
        self.db_path = db_path
        self.backup_path = backup_path
        self.backup_name = os.path.basename(os.path.normpath(self.backup_path))
        self.container_name = container_name

# точка входа в скрипт бэкапа
def start():

    # получаем значения для выбранного окружения
    current_values = get_values()
    
    loader = Loader("Загружаем образ Percona Xtrabackup", "Загрузили образ Percona Xtrabackup").start()
    client.images.pull(repository=XTRABACKUP_IMAGE, tag=XTRABACKUP_VERSION)
    loader.success()

    backup_path_str = "%s/backups/%s" % (current_values["root_mount_path"], datetime.today().strftime('%d.%m.%Y_%H:%M:%S'))
    Path(backup_path_str).mkdir(parents=True,exist_ok=True)

    # начинаем бэкап конфигов
    if "production" in current_values["server_tag_list"]:
        start_configs_backup(current_values, backup_path_str)
    
    # начинаем бэкап монолита
    start_monolith_backup(current_values, backup_path_str)

    # начинаем бэкап пространств
    start_space_backup(current_values, backup_path_str)

# записать данные в контрольный файл
def write_control_file(backup_path_str: str, data: dict) -> None:

    if not Path("%s/control.json" % backup_path_str).exists():
        f = open("%s/control.json" % backup_path_str, "x")
        f.close()
        
    with open("%s/control.json" % backup_path_str, "r") as file:
        json_str = file.read()
        json_dict = json.loads(json_str) if json_str != "" else {}

    with open("%s/control.json" % backup_path_str, "w") as file:
        json_dict = merge(json_dict, data)
        file.write(json.dumps(json_dict))

def start_configs_backup(current_values: dict, backup_path_str: str):

    backup_name = "configs"

    config_archive_path = "%s/%s.tgz" % (backup_path_str, backup_name)

    with tarfile.open(config_archive_path, "w:gz") as tar:
        tar.add("%s/security.yaml" % current_values["root_mount_path"], arcname="security.yaml")
        tar.add("%s/deploy_configs" % current_values["root_mount_path"], arcname="deploy_configs")

    control_data = {"config_archive_name": "%s.tgz" % backup_name}
    write_control_file(backup_path_str, control_data)

# делаем бэкап монолита
def start_monolith_backup(current_values: dict, backup_path_str: str):

    if not need_backup_monolith:
        print(scriptutils.error("БД монолита не выбрана, как необходимая для бэкапа"))
        return
    
    monolith_backup_path_str = "%s/mysql" % (backup_path_str)
    Path(monolith_backup_path_str).mkdir(exist_ok=True, parents=True)

    monolith = DbConfig(
        "",
        0,
        current_values["projects"]["monolith"]["service"]["mysql"]["host"],
        current_values["projects"]["monolith"]["service"]["mysql"]["port"],
        current_values["projects"]["monolith"]["service"]["mysql"]["user"],
        current_values["projects"]["monolith"]["service"]["mysql"]["password"],
        current_values["backup_user"],
        current_values["backup_user_password"],
        "%s/monolith/database" % current_values["root_mount_path"],
        monolith_backup_path_str,
        "%s-monolith_mysql-monolith" % (stack_name_prefix)
    )   

    backup_db_list([monolith], backup_path_str)

# запускаем бэкап пространств
def start_space_backup(current_values: dict, backup_path_str: str):
    
    if not need_backup_spaces:
        print(scriptutils.error("БД пространств не выбраны, как необходимые для бэкапа"))
        return
    
    # формируем список активных пространств
    space_config_obj_dict = get_space_dict(current_values, backup_path_str)

    if len(space_config_obj_dict) < 1:
        scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

    # даем пользователю выбрать, какие пространства надо бэкапить
    input_space_list = ['']
    
    need_backup_space_obj_list = []
    
    # формируем список пространств для бэкапа
    for space_id, space_config_obj in space_config_obj_dict.items():

        if str(space_id) in input_space_list or input_space_list == ['']:
            need_backup_space_obj_list.append(space_config_obj)
    
    # начинаем бэкап пространств
    backup_db_list(need_backup_space_obj_list, backup_path_str)

# формируем бэкапы для выбранных пространств
def backup_db_list(db_list: list[DbConfig], backup_path_str: str):

    # для каждого пространства выполняем бэкап и его архивирование
    for db in db_list:
        db_container = prepare_db(db)

        try:

            print(scriptutils.warning("#-----ПРОСТРАНСТВО %d-----#" % db.space_id if db.space_id != 0 else "#-----ОСНОВНАЯ БАЗА-----#"))
            run_xtrabackup_container(db, db_container)

            loader = Loader("Архивируем бэкап...", "Архив с бэкапом готов", "Не смогли заархивировать бэкап").start()
            db_archive_path = archive_backup(db)
            loader.success()
            print(scriptutils.warning("Путь до архива бэкапа: %s" % (db_archive_path)))

            if db.space_id > 0:
                control_data = {"space_backups": {"%s::%s" % (db.domino_id, db.space_id): os.path.basename(os.path.normpath(db_archive_path))}}
            else:
                control_data = {"monolith_backup_name": os.path.basename(os.path.normpath(db_archive_path))}

            write_control_file(backup_path_str, control_data)
        # финиш бэкапа выполнять надо всегда - чтобы удалить временного пользователя с правами бэкапа
        finally:
            finish_backup(db_container, db)

# формируем архив для бэкапа
def archive_backup(db: DbConfig) -> str:

    space_archive_path = str(Path(db.backup_path + "/../%s.tgz" % db.backup_name).resolve())
    with tarfile.open(space_archive_path, "w:gz") as tar:
        tar.add(db.backup_path, arcname=os.path.basename(os.path.normpath(db.db_path)))
    
    # удаляем заархивированные данные
    shutil.rmtree(db.backup_path, ignore_errors=True)
    
    return space_archive_path

# готовим БД для бэкапа
def prepare_db(db: DbConfig) -> docker.models.containers.Container:

    container_list = client.containers.list(filters= {"name": db.container_name})

    if len(container_list) < 1:
        scriptutils.die("Пространство %d не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения." % db.space_id)
    
    space_container : docker.models.containers.Container = container_list[0]

    # создаем временного пользователя в БД, от имени которого будет проводиться бэкап
    mysql_command = "CREATE USER IF NOT EXISTS '%s'@'%%' IDENTIFIED WITH mysql_native_password BY '%s';" % (db.backup_user, db.backup_password) +\
        "GRANT RELOAD, BACKUP_ADMIN, LOCK TABLES, REPLICATION CLIENT, CREATE TABLESPACE, PROCESS, SUPER, CREATE, INSERT, SELECT ON * . * TO '%s'@'%%';" % db.backup_user +\
        "FLUSH PRIVILEGES;"
    
    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
    result = space_container.exec_run(cmd=cmd)

    if result.exit_code != 0:
        print(result.output)
        scriptutils.die("Не смогли создать mysql пользователя для бэкапа в пространстве %d" % db.space_id)

    return space_container

# действия, необходимые совершить после бэкапа
def finish_backup(db_container: docker.models.containers.Container, db: DbConfig):

    # удаляем временного пользователя, которого создавали для бэкапа
    mysql_command = "DROP USER '%s'@'%%';" % (db.backup_user) +\
    "FLUSH PRIVILEGES;"

    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)

    result = db_container.exec_run(cmd=cmd)

    if result.exit_code != 0:
        scriptutils.die("Не смогли удалить mysql пользователя для бэкапа в пространстве %d" % db.space_id)

# запускаем контейнер и выполняем команду бэкапа
def run_xtrabackup_container(db_config_obj: DbConfig, db_container: docker.models.containers.Container):
    
    # формируем точки монтирования
    data_mount = docker.types.Mount(
        "/var/lib/mysql",
        db_config_obj.db_path,
        "bind",
    )

    backup_mount = docker.types.Mount(
        "/backup_data",
        db_config_obj.backup_path,
        "bind",
    )

    # находим сеть, к которой мы можем подключить контейнер xtrabackup
    if db_container.attrs.get("NetworkSettings") is None or len(db_container.attrs["NetworkSettings"].get("Networks")) < 1:
        scriptutils.die("Не смогли найти ни одну подключенную сеть у контейнера mysql. Окружение поднято корректно?")

    # нужна именно attachable сеть, чтобы к ней можно было подключить внешний контейнер
    attach_network_name = ""
    for network_name, network_attrs in db_container.attrs["NetworkSettings"]["Networks"].items():
        
        network = client.networks.get(network_attrs["NetworkID"])

        if network is None:
            continue
        
        if network.attrs.get("Attachable"):
            attach_network_name = network_name
    
    if attach_network_name == "":
        scriptutils.die("У контейнера mysql нет сети, к которой можно подключить контейнер xtrabackup. Обновите приложение Compass до версии %s" % NEED_APP_VERSION)

    # формируем команду для бэкапа
    backup_command = [
        "bash",
        "-c",
        ' '.join(["xtrabackup",
            "--backup",
            "--target-dir=/backup_data",
            "--host=%s" % db_config_obj.host,
            "--port=%s" % str(db_config_obj.port),
            "--datadir=/var/lib/mysql",
            "--user=%s" % db_config_obj.backup_user,
            "--password=%s" % db_config_obj.backup_password,
            "&&",
            "xtrabackup",
            "--prepare",
            "--target-dir=/backup_data",
            ])]
    loader = Loader("Создаем бэкап...", "Создали бэкап", "Не смогли создать бэкап").start()
    
    # бэкапим пространство
    try:
        result = client.containers.run(
            detach=False,
            image="%s:%s" % (XTRABACKUP_IMAGE, XTRABACKUP_VERSION), 
            mounts=[data_mount, backup_mount],
            network=attach_network_name,
            auto_remove=False,
            command=backup_command,
            stderr=True,
            stdout=True
            )
        loader.success()
        
        print(scriptutils.warning("Команда, которая использовалась для бэкапа: %s" % (' '.join(backup_command))))
    except docker.errors.ContainerError as e:
        loader.error()
        print(e.stderr)
        print(e.exit_status)
        print(scriptutils.error("Не смогли выполнить бэкап"))
        raise e

# сформировать список опций для выбора пространств пользователем
def build_option_list(space_dict: dict[int: DbConfig]) -> str:

    option_list_str = '''
Выберите пространства через запятую, для которых нужно сделать бэкап Например 1,2,4.
По умолчанию будет сделан бэкап всех пространств.
Список доступных пространств: '''

    for space_id, space in space_dict.items():
        option_list_str += "%s, " % (space_id)

    return option_list_str[:-2] + "\n"

# получить путь до папки с бэкапом пространства
def get_space_backup_dir_path(space_id: str, backup_path_str: str) -> str:

    path_str = "%s/mysql_company_%s" % (backup_path_str, space_id)
    Path(path_str).mkdir(exist_ok=True, parents=True)
    return path_str

# получить путь до данных БД пространства
def get_space_data_dir_path(current_values: dict, domino_id: str, space: str) -> str:

    space_db_path = current_values["company_db_path"]

    return "%s/%s/mysql_company_%s/" % (space_db_path, domino_id, space)

# сформировать список конфигураций пространств
def get_space_dict(current_values: dict, backup_path_str: str) -> dict[int: DbConfig]:

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
            current_values["backup_user"],
            current_values["backup_user_password"],
            get_space_data_dir_path(current_values, domino_id, space_id),
            get_space_backup_dir_path(space_id, backup_path_str),
            "%s-%s-company_mysql-%d" % (stack_name_prefix, domino_id, space_config_dict["mysql"]["port"])
            )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
    return space_config_obj_dict

# получить данные окружение из values
def get_values() -> dict:

    default_values_file_path = Path("%s/../src/values.yaml" % (script_dir))
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

# точка входа в скрипт
start()
