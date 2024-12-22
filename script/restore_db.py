#!/usr/bin/env python3
from __future__ import annotations
import sys

sys.dont_write_bytecode = True

import argparse, re, yaml, json, glob, os, tarfile, shutil, subprocess
import docker
import docker.errors, docker.models, docker.models.containers, docker.types
from math import ceil
from utils import scriptutils
from pathlib import Path
from loader import Loader
from time import sleep
from datetime import datetime
import ipaddress

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

# загружаем конфиг
script_path = Path(__file__).parent
config_path = Path(str(script_path) + "/../configs/global.yaml")

config = {}

if not config_path.exists():
    print(scriptutils.error("Отсутствует файл конфигурации %s." % str(config_path.resolve())) +  "Запустите скрипт create_configs.py и заполните конфигурацию")
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.safe_load(config_file)
try:
    ipaddress.ip_address(config_values["host_ip"])
except ValueError:
    scriptutils.die("Указан неверный ip адрес хоста в аргументах")

host_ip = config_values["host_ip"]

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
    def __init__(self, domino_id: str,space_id: str, db_path: str, backup_path: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.db_path = db_path
        self.backup_path = backup_path
        self.archive_backup_name = os.path.basename(os.path.normpath(self.backup_path))
        self.backup_name, _ = os.path.splitext(self.archive_backup_name)

class SpaceBackupInfo:
    def __init__(self, domino_id: str, space_id :str, backup_name: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.backup_name = backup_name


# точка входа в скрипт бэкапа
def start():

    # получаем значения для выбранного окружения
    current_values = get_values()
    
    loader = Loader("Загружаем образ Percona Xtrabackup", "Загрузили образ Percona Xtrabackup").start()
    client.images.pull(repository=XTRABACKUP_IMAGE, tag=XTRABACKUP_VERSION)
    loader.success()

    backup_path = choose_backup(current_values)

    monolith_backup_name, space_backup_info_list, config_archive_name = validate_backup_contents(current_values, backup_path)

    # останавливаем окружение
    stop_environment()

    # восстанавливаем конфигурацию
    if "production" in current_values["server_tag_list"]:
        start_config_restore(current_values, backup_path, config_archive_name)

    # начинаем бэкап монолита
    start_monolith_restore(current_values, backup_path, monolith_backup_name)

    # начинаем бэкап пространств
    start_space_restore(current_values, backup_path, space_backup_info_list)

    # запускаем окружение
    start_environment(current_values)

    monolith_container: docker.models.containers.Container = wait_monolith_container()

    # если передали ip - меняем
    if host_ip != "":
        update_host_ip(monolith_container, host_ip, current_values["root_mount_path"])
    
    # обновляем конфиги пространств
    update_space_configs(monolith_container)

# останавливаем окружение
def stop_environment() -> None:

    result = input(scriptutils.error("Перед восстановлением необходимо завершить работу приложения Compass и удалить текущие данные БД. Согласны?[Y/n]"))

    if result.lower() != "y":
        scriptutils.die("Восстановление отменено")

    # Добавляем проверку перед удалением стеков
    remove_stack_if_exists(stack_name_prefix)

    loader = Loader("Ждем остановки приложения...", "Приложение остановлено", "Не смогли остановить приложение").start()
    while True:
        docker_monolith_network_list = client.networks.list(names=["%s-monolith-private" % stack_name_prefix])
        if len(docker_monolith_network_list) < 1:
            break
    loader.success()

# Функция для удаления стека с проверкой
def remove_stack_if_exists(stack_name):

    # Выполняем команду 'docker stack ls' и проверяем, существует ли стек
    result = subprocess.run(f"docker stack ls | grep {stack_name}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Если стек найден, удаляем его
    if result.stdout:
        print(f"Удаление стека {stack_name}...")
        subprocess.run("docker stack ls | grep %s | awk '{print $1}' | xargs docker stack rm" % (stack_name), shell=True)
    # Если стек не найден, ничего не делаем и не выводим сообщение

# обновить хостовый ip
def update_host_ip(monolith_container: docker.models.containers.Container, host_ip: str, root_mount_path: str) -> None:
    
    # обновляем ip в базе
    result = monolith_container.exec_run([
        "bash",
        "-c",
        f'mysql -h "$MYSQL_HOST" -p"$MYSQL_ROOT_PASS" -D pivot_company_service -e "UPDATE domino_registry SET \`database_host\` = \'{host_ip}\', \`code_host\` = \'{host_ip}\';"'
    ])
    if result.exit_code != 0:

        print(result.output)
        scriptutils.die("Не смогли обновить конфигурацию пространств. Убедитесь, что окружение поднялось корректно.")

    # обновляем айпи в конфиге домино хостов
    domino_hosts_file = f"{root_mount_path}/company_configs/.domino_hosts.json"

    with open(domino_hosts_file, "r") as file:
        json_str = file.read()
        json_dict = json.loads(json_str) if json_str != "" else {}
    
    json_dict["d1"] = host_ip

    with open(domino_hosts_file, "w") as file:
        file.write(json.dumps(json_dict))
    
# дождаться контейнера монолита
def wait_monolith_container() -> docker.models.containers.Container:

    # получаем контейнер monolith
    timeout = 600
    n = 0
    loader = Loader("Ждем поднятия окружения...", "Подняли окружение", "Не смогли поднять окружение").start()
    while n <= timeout:

        docker_container_list = client.containers.list(
            filters={
                "name": "%s-monolith_php-monolith" % (stack_name_prefix),
                "health": "healthy",
            }
        )
        
        if len(docker_container_list) > 0:
            monolith_container: docker.models.containers.Container = docker_container_list[0]
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            loader.error()
            scriptutils.die(
                "Не был найден необходимый docker-контейнер для обновления конфигурации пространств. Убедитесь, что окружение поднялось корректно."
            )
    loader.success()

    return monolith_container

# обновить конфиги пространств
def update_space_configs(monolith_container: docker.models.containers.Container) -> None:

    loader = Loader("Запускаем пространства...", "Запустили пространства", "Не смогли запустить пространства").start()
    
    result = monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php src/Compass/Pivot/sh/php/domino/force_update_company_db.php",
        ],
    )

    # форсированный апдейт конфигов идет каждые 180 секунд
    sleep(180)
    if result.exit_code != 0:

        loader.error()
        scriptutils.die("Не смогли обновить конфигурацию пространств. Убедитесь, что окружение поднялось корректно.")
    loader.success()

# запускаем окружение
def start_environment(current_values: dict) -> None:

    # возвращаем значения из ранее забекапленных конфигов
    if "production" in current_values["server_tag_list"]:
        
        result = subprocess.run([
            "python3",
            "%s/update.py" % script_dir,
            ])
        
        if result.returncode != 0:
            scriptutils.die("Не смогли поднять окружение после восстановления. Проверьте конфигурацию приложения и запустите скрипт restore_db.py заново.")
        
        return
    
    # если это тестовое окружение, то поднимаем окружение по другому
    start_dev_environment(current_values)

# запускаем тестовое окружение    
def start_dev_environment(current_values: dict):

    result = subprocess.run([
        "python3",
        "%s/deploy.py" % script_dir,
        "-e",
        environment,
        "-v",
        values_name,
        "-p",
        "monolith",
    ])

    if result.returncode != 0:
        print(result.stderr)
        print(result.stdout)
        scriptutils.die("Иди чини")
    

# восстанавливаем базу монолита
def start_monolith_restore(current_values: dict, backup_path: str, monolith_backup_name: str):

    monolith = DbConfig(
        "",
        0,
        "%s/monolith/database" % current_values["root_mount_path"],
        "%s/%s" % (backup_path, monolith_backup_name),
    )

    restore_db_list(backup_path, [monolith])

# восстанавливаем базы пространств
def start_space_restore(current_values: dict, backup_path: str, space_backup_info_list: list[SpaceBackupInfo]):
    
    # формируем список активных пространств
    space_config_obj_dict = get_space_dict(current_values, backup_path, space_backup_info_list)

    if len(space_config_obj_dict) < 1:
        scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")
    
    need_backup_space_obj_list = []
    
    # формируем список пространств для восстановления
    for key, space_config_obj in space_config_obj_dict.items():
        need_backup_space_obj_list.append(space_config_obj)
    
    # начинаем восстановление пространств
    restore_db_list(backup_path, need_backup_space_obj_list)

# восстанавливаем конфиги
def start_config_restore(current_values: dict, backup_path: str, config_archive_name: str):

    file = tarfile.open("%s/%s" % (backup_path, config_archive_name)) 
    print(file.getnames()) 
    file.extractall(current_values["root_mount_path"]) 
    file.close()

    if Path(current_values["root_mount_path"] + "/security.yaml").exists():
        shutil.copyfile(current_values["root_mount_path"] + "/security.yaml", script_dir + "/../src/security.yaml")

def choose_backup(current_values: dict) -> str: 

    backup_path_dict = {}
    backup_option_list = []

    backup_path_str = "%s/backups" % (current_values["root_mount_path"])

    for backup_archive_path in glob.glob("%s/*" % backup_path_str):

        backup_name = os.path.basename(os.path.normpath(backup_archive_path))
        backup_path_dict[backup_name] = backup_archive_path
        backup_option_list.append(backup_name)
    
    if len(backup_archive_path) < 1:
        scriptutils.die("Не найдено ни одного бэкапа в папке %s" % backup_path_str)
    
    backup_option_str = "Выберите бэкап, который хотите восстановить:\n"

    for index, option in enumerate(backup_option_list):
        backup_option_str += "%d) %s\n" % (index + 1, option)
    
    chosen_backup_index = input(backup_option_str)

    if (not chosen_backup_index.isdigit()) or int(chosen_backup_index) < 0 or int(chosen_backup_index) > len(backup_option_list):
        scriptutils.die("Выбран некорректный вариант")
    
    return backup_path_dict[backup_option_list[int(chosen_backup_index) - 1]]

def validate_backup_contents(current_values: dict, backup_path: str):

    with open("%s/control.json" % backup_path, "r") as control_file:
        control_dict = json.load(control_file)

    monolith_backup_path = Path("%s/%s" % (backup_path, control_dict["monolith_backup_name"]))

    if not monolith_backup_path.exists():
        scriptutils.die("В бэкапе нет архива с основной БД")
    
    space_backup_info_list = []

    for domino_space_id, backup_name in control_dict["space_backups"].items():

        domino_space_id_arr = domino_space_id.split("::")

        if len(domino_space_id_arr) != 2:
            scriptutils.die("Контрольный конфиг бэкапа некорректен!")
        
        domino_id = domino_space_id_arr[0]
        space_id = domino_space_id_arr[1]

        space_backup_path = Path("%s/%s" % (backup_path, backup_name))

        if not space_backup_path.exists():
            scriptutils.die("В бэкапе нет архива с БД пространства %d" % space_id)
    
        space_backup_info_list.append(SpaceBackupInfo(domino_id, space_id, backup_name))
    
    if "production" in current_values["server_tag_list"]:
        config_archive_path = Path("%s/%s" % (backup_path, control_dict["config_archive_name"]))

        if not config_archive_path.exists():
            scriptutils.die("В бэкапе отсутствуют конфиги с секретами сервера")
        
    return control_dict["monolith_backup_name"], space_backup_info_list, control_dict.get("config_archive_name", "")

# восстанавливаем выбранные БД
def restore_db_list(backup_path: str, db_list: list[DbConfig]):

    # для каждой БД выполняем восстановление
    for db in db_list:

        print(scriptutils.warning("#-----ПРОСТРАНСТВО %s-----#" % db.space_id if db.space_id != 0 else "#-----ОСНОВНАЯ БАЗА-----#"))

        loader = Loader("Удаляем текущие данные из БД...", "Успешно удалили текущие данные", "Не смогли удалить текущие данные").start()
        shutil.rmtree(db.db_path, ignore_errors=True)
        path = Path(db.db_path)
        path.mkdir(exist_ok=True, parents=True, mode = 0o755)

        loader.success()

        loader = Loader("Разархивируем бэкап...", "Успешно разархивировали бэкап", "Не смогли разархивировать бэкап").start()
        file = tarfile.open("%s/%s" % (backup_path, db.archive_backup_name))
        file.extractall(backup_path) 
        file.close()
        #recursive_chown(backup_path, "lxd", "docker")
        loader.success()

        run_xtrabackup_container(backup_path, db)

# запускаем контейнер и выполняем команду бэкапа
def run_xtrabackup_container(backup_path: str, db_config_obj: DbConfig):
    
    # формируем точки монтирования
    data_mount = docker.types.Mount(
        "/var/lib/mysql",
        db_config_obj.db_path,
        "bind",
    )

    backup_mount = docker.types.Mount(
        "/backup_data",
        "%s/%s" % (backup_path, os.path.basename(os.path.normpath(db_config_obj.db_path))),
        "bind",
    )

    # формируем команду для бэкапа
    restore_command = ["xtrabackup",
            "--move-back",
            "--target-dir=/backup_data",
            "--datadir=/var/lib/mysql",
            ]
    loader = Loader("Восстанавливаем бэкап...", "Восстановили бэкап", "Не смогли восстановить бэкап").start()
    
    # восстанавливаем бэкап
    try:
        client.containers.run(
            detach=False,
            image="%s:%s" % (XTRABACKUP_IMAGE, XTRABACKUP_VERSION), 
            mounts=[data_mount, backup_mount],
            auto_remove=False,
            command=restore_command
            )
        loader.success()
        print(scriptutils.warning("Команда, которая использовалась для восстановления бэкапа: %s" % (' '.join(restore_command))))
    except docker.errors.ContainerError as e:
        loader.error()
        print(e.stderr)
        print(e.exit_status)
        print(scriptutils.error("Не смогли выполнить восстановление бэкапа"))
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
def get_space_backup_dir_path(current_values: dict, domino_id: str, space_id: str) -> str:

    space_db_path = current_values["company_db_path"]
    path_str = "%s/backups/%s/%s/mysql_company_%s" % (space_db_path, datetime.today().strftime('%d.%m.%Y_%H:%M:%S'), domino_id, space_id)
    Path(path_str).mkdir(mode=644, exist_ok=True, parents=True)
    return path_str

# получить путь до данных БД пространства
def get_space_data_dir_path(current_values: dict, domino_id: str, space: str) -> str:

    space_db_path = current_values["company_db_path"]

    return "%s/%s/mysql_company_%s/" % (space_db_path, domino_id, space)

# сформировать список конфигураций пространств
def get_space_dict(current_values:dict, backup_path:str, space_backup_info_list: list[SpaceBackupInfo]) -> dict[int: DbConfig]:

    # формируем список пространств, доступных для бэкапа
    # пространства выбираются по наличию их конфига
    space_config_obj_dict = {}
    for space_backup_info in space_backup_info_list:

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            space_backup_info.domino_id,
            space_backup_info.space_id,
            get_space_data_dir_path(current_values, space_backup_info.domino_id, space_backup_info.space_id),
            "%s/%s" % (backup_path, space_backup_info.backup_name),
            )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
    return space_config_obj_dict

# получить данные окружение из values
def get_values() -> dict:

    values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values
    
    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values

def recursive_chown(path, owner, group):
    for dirpath, dirnames, filenames in os.walk(path):
        shutil.chown(dirpath, owner)
        for filename in filenames:
            shutil.chown(os.path.join(dirpath, filename), owner, group)
        for dirname in dirname:
            shutil.chown(os.path.join(dirpath, filename), owner, group)
# точка входа в скрипт
start()
