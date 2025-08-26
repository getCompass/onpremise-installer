#!/usr/bin/env python3

import sys

import mysql.connector.errorcode

sys.dont_write_bytecode = True

import subprocess, yaml, os, shutil, argparse

from utils import scriptutils
from pathlib import Path
from loader import Loader
from time import sleep
import docker, json
import mysql.connector

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиг
config = {}
protected_config = {}

# загружаем конфиги
config_path = Path(script_dir + "/../configs/global.yaml")

if not config_path.exists():
    print(
        scriptutils.error(
            "Отсутствует файл конфигурации %s. Запустите скрит create_configs.py и заполните конфигурацию"
            % str(config_path.resolve())
        )
    )
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(config_values)

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="Окружение, в котором разворачиваем")
# ВНИМАНИЕ - в data передается json
parser.add_argument(
    "--data", required=False, type=json.loads, help="дополнительные данные для развертывания"
)
args = parser.parse_args()
override_data = args.data if args.data else {}
if not override_data:
    override_data = {}
product_type = override_data.get("product_type", "") if override_data else ""

environment = args.environment

# пишем константы
values_name = "compass"
stack_name_prefix = environment + "-" + values_name
stack_name_monolith = stack_name_prefix + "-monolith"

if Path(script_dir + "/../src/values." + environment + "." + values_name + ".yaml").exists():
    specified_values_file_name = str(
        Path(script_dir + "/../src/values." + environment + "." + values_name + ".yaml").resolve()
    )
elif (
        product_type
        and Path(script_dir + "/../src/values." + values_name + "." + product_type + ".yaml").exists()
):
    specified_values_file_name = str(
        Path(script_dir + "/../src/values." + values_name + "." + product_type + ".yaml").resolve()
    )
elif (Path(script_dir + "/../src/values." + values_name + ".yaml").exists()):
    specified_values_file_name = str(Path(script_dir + "/../src/values." + values_name + ".yaml").resolve())
else:
    specified_values_file_name = str(Path(script_dir + "/../src/values.yaml").resolve())

with open(specified_values_file_name, "r") as values_file:
    values_dict = yaml.safe_load(values_file)

scriptutils.assert_root()

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
stack_name_company = stack_name_prefix
service_label = values_dict.get("service_label") if values_dict.get("service_label") else ""
if service_label != "":
    stack_name_monolith = stack_name_monolith + "-" + service_label
    stack_name_company = stack_name_prefix + "-" + service_label

try:
    if input("Удаляем приложение Compass, продолжить? [y/N]\n").lower() != "y":
        scriptutils.die("Удаление приложения было отменено")
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(0)

# удаляем стаки компаний
get_stack_command = ["docker", "stack", "ls"]
grep_command = ["grep", stack_name_company]
grep_company_command = ["grep", r"\-company"]
delete_command = ["xargs", "docker", "stack", "rm"]

# сначала удаляем компанейские стаки
get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
grep_process = subprocess.Popen(
    grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
)
grep_company_process = subprocess.Popen(
    grep_company_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
)
delete_process = subprocess.Popen(
    delete_command, stdin=grep_company_process.stdout, stdout=subprocess.PIPE
)
output, _ = delete_process.communicate()

# удаляем остальные стаки
get_stack_command = ["docker", "stack", "ls"]
grep_command = ["grep", stack_name_monolith]
grep_monolith_command = ["grep", "-v", r"\-company"]
delete_command = ["xargs", "docker", "stack", "rm"]

# сначала удаляем компанейские стаки
get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
grep_process = subprocess.Popen(
    grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
)
grep_monolith_process = subprocess.Popen(
    grep_monolith_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
)
delete_process = subprocess.Popen(
    delete_command, stdin=grep_monolith_process.stdout, stdout=subprocess.PIPE
)
output, _ = delete_process.communicate()

loader = Loader(
    "Удаляем приложение...",
    "Успешно удалили приложение",
    "Не смогли удалить приложение",
).start()


# стереть все базы по указанному сокету
def drop_all_databases(host: str, port: str, user: str, password: str, need_drop_users: bool = False):
    restricted_db_list = [
        'information_schema',
        'mysql',
        'performance_schema',
        'sys'
    ]

    mydb = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
    )

    drop_users = "DROP USER 'user'@'%';DROP USER 'backup_user'@'127.0.0.1';FLUSH PRIVILEGES;"
    drop_command = 'DROP DATABASE'
    show_databases = 'SHOW DATABASES'
    my_cursor = mydb.cursor(buffered=True)
    my_cursor.execute(show_databases)

    db_for_deletion = []
    result = my_cursor.fetchall()
    for row in result:

        if row[0] in restricted_db_list:
            continue
        db_for_deletion.append(row[0])

    for db in db_for_deletion:
        my_cursor.execute('%s %s' % (drop_command, db))

    mydb.commit()

    if need_drop_users:
        my_cursor.execute('%s' % (drop_users))
    mydb.close()


# чистим базы
def clear_mysql_instances(database_config: dict):
    if database_config["database_connection"]["driver"] != "host":
        return

    monolith_mysql_root_password = database_config['database_connection']['driver_data']['project_mysql_hosts']['monolith']['root_password']
    monolith_mysql_host = database_config['database_connection']['driver_data']['project_mysql_hosts']['monolith']['host']
    monolith_mysql_port = database_config['database_connection']['driver_data']['project_mysql_hosts']['monolith']['port']

    loader = Loader('Чистим базы на хосте...', 'Базы очищены',
                    'Не получилось почистить базы').start()

    company_mysql_hosts: dict = database_config['database_connection']['driver_data']['company_mysql_hosts']

    # дропаем все, что только можно
    try:
        drop_all_databases(monolith_mysql_host, monolith_mysql_port, 'root', monolith_mysql_root_password)

        for v in company_mysql_hosts:
            drop_all_databases(v["host"], v["port"], 'root', v["root_password"], True)

    except mysql.connector.Error as err:

        if err.errno != mysql.connector.errorcode.ER_CANNOT_USER:
            loader.error()
            print(err)
            exit(1)

    loader.success()


client = docker.from_env()

# ждем, пока все контейнеры удалятся
timeout = 600
n = 0
while n <= timeout:
    docker_container_list = client.containers.list(filters={"name": stack_name_monolith}, sparse=True, ignore_removed=True)

    if len(docker_container_list) < 1:
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die("Приложение не было удалено")

# ждем удаления сетей
timeout = 120
n = 0
while n <= timeout:
    docker_network_list = client.networks.list(filters={"name": stack_name_monolith})

    if len(docker_network_list) < 1:
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die("Приложение не было удалено")

# удаляем network mysql-shared
shared_network_list = client.networks.list(filters={"name": "monolith-mysql-shared"})
for network in shared_network_list:
    try:
        network.remove()
    except docker.errors.NotFound:
        continue
    except docker.errors.APIError as e:
        continue

sleep(10)

# удаляем volumes jitsi
jitsi_volume_list = client.volumes.list(filters={"name": "%s_jitsi-custom-" % stack_name_monolith})
for volume in jitsi_volume_list:
    try:
        volume.remove()
    except docker.errors.NotFound:
        continue
    except docker.errors.APIError as e:
        print("Не удалось удалить один из jitsi volume: ", e)

loader.success()

root_mount_path = config.get("root_mount_path")

if root_mount_path is None:
    scriptutils.die(
        "В конфигурации %s не указан путь до данных приложения, поле root_mount_path"
        % str(config_path.resolve())
    )

root_mount_path = Path(root_mount_path)

if not root_mount_path.exists():
    scriptutils.die(
        "Путь, указанный в конфигурации %s в поле root_mount_path, не существует"
    )

try:
    if (
            input(
                "Удаляем все данные приложения по пути %s, продолжить? [y/N]\n"
                % str(root_mount_path.resolve())
            ).lower()
            != "y"
    ):
        scriptutils.die("Удаление данных было отменено")
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(0)

# Команда удаления (все, кроме инсталлятора)
root_path = Path(script_dir + "/../").resolve()
retain = [root_path.resolve()]

for item in root_mount_path.glob("*"):
    if item not in retain:
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

# спрашиваем, удалять ли базы
try:

    database_config_file_path = Path("%s/../configs/database.yaml" % (script_dir))

    if database_config_file_path.exists():

        with database_config_file_path.open() as database_config_file:
            database_config = yaml.load(database_config_file, Loader=yaml.BaseLoader)

        if (database_config["database_connection"]["driver"] == "host" and
                input(
                    "Очищаем инстансы mysql, которые использовались для приложения, продолжить? [y/N]\n"
                ).lower()
                == "y"
        ):
            clear_mysql_instances(database_config)
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(0)

# раз удалили данные, то и текущая конфигурация сервера больше не нужна
values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))

if values_file_path.exists():
    values_file_path.unlink()

# проверяем также файл для service_label, если имеется
service_label_file_path = Path("%s/../.service_label" % script_dir)
if service_label_file_path.exists():
    service_label_file_path.unlink()
