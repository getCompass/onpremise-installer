#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl python_on_whales mysql_connector_python python-dotenv psutil

import sys

sys.dont_write_bytecode = True

import os, argparse, yaml, pwd, json, psutil
from python_on_whales import docker, exceptions, Container
from pathlib import Path
from utils import scriptutils, interactive
from subprocess import Popen
from time import sleep
from loader import Loader

# ---АГРУМЕНТЫ СКРИПТА---#
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
    "--validate-only",
    required=False,
    action='store_true'
)
parser.add_argument("--init", required=False, action="store_true")

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиги
config_path_list = [
    Path(script_dir + "/../configs/team.yaml"),
    Path(script_dir + "/../configs/global.yaml"),
]

config = {}
validation_errors = []

for config_path in config_path_list:
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

def get_company_ports():
    default_company_start_port = 33150
    default_company_end_port = 33165

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
        validation_errors.append(message)
        return
    
    print(message)
    exit(1)
    
def create_domino(
    pivot_container: Container,
    domino_id: str,
    domino_url: str,
    database_host: str,
    code_host: str,
    database_user: str,
    database_pass: str,
    go_database_controller_port: str,
):

    pivot_container.execute(
        user="www-data",
        command=[
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

    try:
        loader = Loader(
            "Создаю domino...", "Создал domino", "Не смог создать domino"
        ).start()

        output = pivot_container.execute(
            user="www-data",
            command=[
                "bash",
                "-c",
                "php src/Compass/Pivot/sh/php/domino/add_port_to_domino.php --domino-id=%s --mysql-user=%s --mysql-pass=%s --start-port=%i --end-port=%i --type=common"
                % (
                    domino_id,
                    database_user,
                    database_pass,
                    start_company_port,
                    end_company_port,
                ),
            ],
        )
        loader.success()
        print(output)
    except exceptions.DockerException as e:
        loader.error()
        print(e.stdout)
        print(e.stderr)


# ---СКРИПТ---#

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
init = args.init
validate_only = args.validate_only

script_dir = str(Path(__file__).parent.resolve())

values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_arg))

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

start_company_port, end_company_port = get_company_ports()
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

if validate_only:
    if len(validation_errors) > 0:
        print("Ошибка в конфигурации")
        for error in validation_errors:
            print(error)
        exit(1)
    exit(0)


# получаем контейнер monolith
timeout = 10
n = 0
while n <= timeout:
    if environment == "" or values_arg == "":
        docker_container_list = docker.container.list(
            filters={"name": "monolith_php-monolith", "health": "healthy"}
        )
    else:
        docker_container_list = docker.container.list(
            filters={
                "name": "%s-monolith_php-monolith" % (stack_name_prefix),
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

try:
    output = found_pivot_container.execute(
        user="www-data",
        command=[
            "bash",
            "-c",
            "php src/Compass/Pivot/sh/php/domino/check_domino_exists.php --domino-id=%s"
            % first_domino["label"],
        ],
    )
except exceptions.DockerException:
    create_domino(
        found_pivot_container,
        first_domino["label"],
        domino_url,
        first_domino["mysql_host"],
        first_domino["code_host"],
        first_domino["company_mysql_user"],
        first_domino["company_mysql_password"],
        first_domino["go_database_controller_port"],
    )

team_name = ""
if init:
    try:
        team_name = interactive.InteractiveValue(
            "team.init_name",
            "Введите название первой команды",
            "str",
            config=config,
        ).from_config()
        output = found_pivot_container.execute(
            user="www-data",
            command=[
                "bash",
                "-c",
                "php src/Compass/Pivot/sh/php/domino/check_team_exists.php",
            ],
            interactive=True,
            tty=True,
        )
        print(
            scriptutils.success(
                "Первая компания уже была создана. Если хотите создать еще одну команду, запустите скрипт create_team.py"
            )
        )
        exit(0)
    except exceptions.DockerException:
        pass
try:
    loader = Loader(
        "Готовлю место под команду...",
        "Подготовил место под команду",
        "Не смог подготовить место под команду",
    ).start()
    output = found_pivot_container.execute(
        user="www-data",
        command=[
            "bash",
            "-c",
            "php src/Compass/Pivot/sh/php/domino/warm_up_company.php",
        ],
    )
    loader.success()
    sleep(1)

    command = ["bash", "-c", "php src/Compass/Pivot/sh/php/domino/create_team.php"]

    if team_name != "":
        command = [
            "bash",
            "-c",
            'php src/Compass/Pivot/sh/php/domino/create_team.php --name="%s"'
            % team_name,
        ]
    output = found_pivot_container.execute(
        user="www-data",
        command=command,
        interactive=True,
        tty=True,
    )

    print(output)
    print(scriptutils.success("Команда создана"))
except exceptions.DockerException as e:
    loader.error()
    print(e.stderr)
    print(e.stdout)
    scriptutils.error(
        "Что то пошло не так. Не смогли создать команду. Проверьте, что окружение поднялось корректно"
    )
