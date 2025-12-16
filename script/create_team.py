#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

import sys

sys.dont_write_bytecode = True

import subprocess, argparse, yaml, json, psutil
import docker
from pathlib import Path
from utils import scriptutils, interactive
from time import sleep
from loader import Loader
import os
import socket
import re

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument(
    "-v",
    "--values",
    required=False,
    default="compass",
    type=str,
    help="Название values файла окружения",
)
parser.add_argument(
    "-e",
    "--environment",
    required=False,
    default="production",
    type=str,
    help="Окружение, в котором разворачиваем",
)

parser.add_argument(
    "-dst",
    "--destination",
    required=False,
    default=None,
    type=str,
    help="место, куда будет отправлена резервная копия созданной компании",
)

parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)

parser.add_argument(
    "--installer-output",
    required=False,
    action="store_true"
)
parser.add_argument("--init", required=False, action="store_true")

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())


class DBDriverConf:

    def __init__(self, driver: str, data: any):
        self.driver = driver
        self.data = data


# загружаем конфиги
config_path_list = [
    Path(script_resolved_path + "/../configs/team.yaml"),
    Path(script_resolved_path + "/../configs/global.yaml"),
    Path(script_resolved_path + "/../configs/database.yaml"),
]

config = {}
validation_errors = []

for config_path in config_path_list:
    if not config_path.exists():
        print(
            scriptutils.error(
                "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию"
                % str(config_path.resolve())
            )
        )
        exit(1)

    with config_path.open("r") as config_file:
        config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

    config.update(config_values)


def get_company_ports():
    default_company_start_port = 33150
    default_company_end_port = 33164

    try:
        start_company_port = interactive.InteractiveValue(
            "company.start_port",
            "Начальный порт для развертывания баз данных.",
            "int",
            default_company_start_port,
            config=config,
        ).from_config()
    except interactive.IncorrectValueException as e:
        handle_exception(e.field, e.message)
        start_company_port = 0

    try:
        end_company_port = interactive.InteractiveValue(
            "company.end_port",
            "Конечный порт для развертывания баз данных.",
            "int",
            default_company_end_port,
            config=config,
        ).from_config()
    except interactive.IncorrectValueException as e:
        handle_exception(e.field, e.message)
        end_company_port = 0

    if end_company_port < start_company_port:
        message = "Конечный порт не может быть меньше начального"
        handle_exception(e.field, message)

    return start_company_port, end_company_port


def handle_exception(field, message: str):
    if validate_only:
        if installer_output:
            validation_errors.append(field)
        else:
            validation_errors.append(message)
        return

    print(message)
    exit(1)


def create_domino(
        pivot_container: docker.models.containers.Container,
        domino_id: str,
        domino_url: str,
        database_host: str,
        code_host: str,
        database_user: str,
        database_pass: str,
        go_database_controller_port: str,
        db_driver: DBDriverConf,
):
    pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            "php src/Compass/Pivot/sh/php/domino/create_domino.php --domino-id=%s --tier=1 --database-host=%s --code-host=%s --url=%s --is-company-creating-allowed=1 --go-database-controller-port=%i"
            % (
                domino_id,
                database_host,
                code_host,
                domino_url,
                go_database_controller_port,
            ),
        ],
    )

    loader = Loader(
        "Создаю domino...", "Создал domino", "Не смог создать domino"
    ).start()

    if not scriptutils.is_replication_master_server(current_values):
        loader.success()
        return

    if db_driver.driver == "host":

        # если драйвер host, то порты нужно добавлять по одному, а не пачкой
        # проходимся по всем портам компаний из данных драйвера и склеиваем их
        host_list = []
        for instance in db_driver.data.get("company_mysql_hosts"):
            host_list.append(f"{instance['host']}:{instance['port']}")

        host_list_serialized = ",".join(host_list)

        output = pivot_container.exec_run(
            user="www-data",
            cmd=[
                "bash",
                "-c",
                f"php src/Compass/Pivot/sh/php/domino/add_predefined_host_to_domino.php --domino-id={domino_id} --mysql-user=\"{database_user}\" --mysql-pass=\"{database_pass}\" --host-list=[{host_list_serialized}] --type=common"
            ],
        )
    else:

        # остальные случаи пытаемся обработать стандартной логикой добавления портов
        # достаем данные о начальном и конечном порте диапазона
        drv_data = db_driver.data
        start_port = drv_data["start_company_port"]
        end_port = drv_data["end_company_port"]

        output = pivot_container.exec_run(
            user="www-data",
            cmd=[
                "bash",
                "-c",
                f"php src/Compass/Pivot/sh/php/domino/add_port_to_domino.php --domino-id={domino_id} --mysql-user=\"{database_user}\" --mysql-pass=\"{database_pass}\" --start-port={start_port} --end-port={end_port} --type=common"
            ],
        )

    if output.exit_code == 0:
        loader.success()
    else:
        loader.error()
        print(output.output.decode("utf-8"))


# ---СКРИПТ---#

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"
init = args.init
validate_only = args.validate_only
installer_output = args.installer_output
dst = args.destination

values_file_path = Path("%s/../src/values.%s.yaml" % (script_resolved_path, values_arg))

if not values_file_path.exists() and (not validate_only):
    scriptutils.die(
        (
            "Не найден файл со сгенерированными значениями. Убедитесь, что приложение развернуто"
        )
    )

current_values = {}
if not validate_only:
    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

        if current_values == {}:
            scriptutils.die(
                "Не найден файл со сгенерированными значениями. Убедитесь, что приложение развернуто"
            )

        if current_values.get("projects", {}).get("domino", {}) == {}:
            scriptutils.die(
                scriptutils.error("Не был развернут проект domino через скрипт deploy.py")
            )

        domino_project = current_values["projects"]["domino"]

        if len(domino_project) < 1:
            scriptutils.die(
                scriptutils.error("Не был развернут проект domino через скрипт deploy.py")
            )

service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

db_config = interactive.InteractiveValue(
    "database_connection", "Введите драйвер БД", "dict_or_none", config=config,
).from_config()

db_driver_name = db_config.get("driver")

if db_driver_name == "docker":
    start_company_port, end_company_port = get_company_ports()
    db_driver = DBDriverConf(db_driver_name,
                             {"start_company_port": start_company_port, "end_company_port": end_company_port})
else:
    db_driver = DBDriverConf(db_driver_name, db_config.get("driver_data", None))

if init:
    try:
        team_name = interactive.InteractiveValue(
            "team.init_name",
            "Введите название первой команды",
            "str",
            config=config,
        ).from_config()
    except interactive.IncorrectValueException as e:
        handle_exception(e.field, e.message)
        team_name = ""
else:
    team_name = interactive.InteractiveValue(
        "team.init_name",
        "Введите название команды",
        "str",
    ).input()

is_need_create_backup = True if (not init
                                 and scriptutils.is_replication_master_server(current_values)
                                 and scriptutils.is_replication_enabled(current_values)) else False

if is_need_create_backup and not dst:
    handle_exception("dst", "При включенной репликации необходимо передавать параметр -dst при создании команды")

if validate_only:
    if installer_output:
        if len(validation_errors) > 0:
            print(json.dumps(validation_errors, ensure_ascii=False))
            exit(1)
        print("[]")
    else:
        if len(validation_errors) > 0:
            print("Ошибка в конфигурации")
            for error in validation_errors:
                print(error)
            exit(1)
    exit(0)

# проверяем права доступа у пользователя к удаленой директории
if is_need_create_backup:
    scriptutils.check_remote_folder(dst)

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
        found_pivot_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для создания команды. Убедитесь, что окружение поднялось корректно"
        )

first_key = list(domino_project)[0]
first_domino = domino_project[first_key]
domino_url = first_domino["label"] + "." + current_values["domain"]

output = found_pivot_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php src/Compass/Pivot/sh/php/domino/check_domino_exists.php --domino-id=%s"
        % first_domino["label"],
    ],
)

if output.exit_code != 0:
    create_domino(
        found_pivot_container,
        first_domino["label"],
        domino_url,
        first_domino["mysql_host"],
        first_domino["code_host"],
        first_domino["company_mysql_user"],
        first_domino["company_mysql_password"],
        first_domino["go_database_controller_port"],
        db_driver,
    )

if init:

    output = found_pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            "php src/Compass/Pivot/sh/php/domino/check_team_exists.php",
        ]
    )

    if output.exit_code == 0:
        print(
            scriptutils.success(
                "Первая компания уже была создана. Если хотите создать еще одну команду, запустите скрипт create_team.py"
            )
        )
        exit(0)

if scriptutils.is_replication_master_server(current_values):
    if not init:
        loader = Loader(
            "Создаю команду...",
            "Команда создана",
            "Не смог создать команду",
        ).start()
else:
    if init:
        loader = Loader(
            "Начинаем процесс репликации в команде...",
            "Репликация завершена",
            "Не смогли завершить репликацию",
        ).start()

if scriptutils.is_replication_master_server(current_values):
    output = found_pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            "php src/Compass/Pivot/sh/php/domino/warm_up_company.php",
        ],
    )

if output.exit_code == 0:
    sleep(1)
else:
    print("\n%s" % output.output.decode("utf-8", errors="ignore"))

# настраиваем репликацию на mysql пространства
if scriptutils.is_replication_enabled(current_values):
    subprocess.run(
        [
            "python3",
            script_resolved_path + "/replication/create_mysql_user.py",
            "-e",
            environment,
            "-v",
            values_arg,
            "--type",
            "team",
            "--is-logs",
            str(0),
            "--is-create-team",
            str(1)
        ]
    )

if scriptutils.is_replication_master_server(current_values):
    result = found_pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            'php src/Compass/Pivot/sh/php/domino/create_team.php --name="%s"' % team_name
        ]
    )
    output_text = result.output.decode("utf-8", errors="ignore").strip()

    if result.exit_code == 0:
        if scriptutils.is_replication_master_server(current_values) and not init:
            loader.success()

        m = re.search(r"company_id=(\d+);port=(\d+)", output_text)
        company_id = None
        company_port = None
        if m:
            company_id = int(m.group(1))
            company_port = int(m.group(2))

        if company_id is None or company_port is None:
            print(scriptutils.success("\nУспешно создали команду"))
        else:
            print(scriptutils.success("\nУспешно создали команду %s с портом %s" % (company_id, company_port)))
    else:
        print("\n%s" % result.output.decode("utf-8", errors="ignore"))
        if init != False:
            scriptutils.die(
                "Что то пошло не так. Не смогли создать команду. Проверьте, что окружение поднялось корректно")
else:
    if init:
        subprocess.run(
            [
                "python3", script_resolved_path + "/replication/start_slave_replication.py",
                "-e", environment,
                "-v", values_arg,
                "--type", "team",
                "--is-logs", str(0),
                "--is-choice-space", str(0)
            ]
        )
        loader.success()

# создаем бекап поднятой компании и отправляем его на резервный сервер
if is_need_create_backup:
    # путь до директории с инсталятором
    installer_dir = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    hostname = socket.gethostname()

    backup_name_format = ("reserve_company_%s" % company_id)
    backup_folder = ("%s/backups/" % current_values.get("root_mount_path")) + backup_name_format

    loader = Loader(
        "Делаем резервную копию базы данных",
        "Сделали резервную копию базы данных",
        "Не удалось сделать резервную копию базы данных").start()

    # бэкапим базу данных
    try:
        scriptutils.backup_db(installer_dir, backup_name_format=backup_name_format, need_backup_configs=0,
                              need_backup_monolith=0, need_backup_space_id_list=str(company_id))
        loader.success()
    except subprocess.CalledProcessError as e:
        loader.error()
        print(e)
        print(e.stdout)
        print(e.stderr)
        scriptutils.die("Исправьте проблему и выполните скрипт снова")

    # отправляем резервную копию
    scriptutils.transfer_data(current_values, dst, hostname, backup_folder, need_send_root_mount_path=False)
