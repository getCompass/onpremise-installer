#!/usr/bin/env python3
import argparse

import docker.models
import docker.models.containers
import yaml, subprocess, docker

from pathlib import Path
from utils import scriptutils
from time import sleep
from loader import Loader

# region АГРУМЕНТЫ СКРИПТА #
parser = argparse.ArgumentParser(add_help=False)
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
args = parser.parse_args()

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"

script_dir = str(Path(__file__).parent.resolve())

values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_arg))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

    domino_project = current_values['projects']['domino']

    if len(domino_project) < 1:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

script_dir = str(Path(__file__).parent.resolve())
root_path = str(Path(script_dir + "/../").resolve())

# проверяем конфигурационный файл с глобальными параметрами
config_path = Path(script_dir + "/../configs/database.yaml")

if not config_path.exists():
    scriptutils.die(
        f"Отсутствует файл конфигурации {str(config_path.resolve())}. " +
        f"Запустите скрипт create_configs.py и заполните конфигурацию"
    )

# загружаем конфигурационный файл с глобальными параметрами
with config_path.open("r") as config_file:
    db_config: dict = yaml.load(config_file, Loader=yaml.BaseLoader)

# если мы не на хосте, то делать нечего
if db_config.get("database_connection", {}).get("driver") != "host":
    scriptutils.die("Скрипт можно выполнить только для host драйвера")

class DBDriverConf:

    def __init__(self, driver: str, data: any):
        self.driver = driver
        self.data = data

class DominoCredentials:

    def __init__(self, domino_id: str, company_mysql_user: str, company_mysql_pass: str):
        self.domino_id = domino_id
        self.company_mysql_user = company_mysql_user
        self.company_mysql_pass = company_mysql_pass

def load_domino_credentials() -> DominoCredentials:
    """Загрузить информацию о домино, необходимую для создания порта"""

    # загружаем values
    values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_arg))
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

    first_key = list(domino_project)[0]
    first_domino = domino_project[first_key]

    return DominoCredentials(first_domino["label"], first_domino["company_mysql_user"], first_domino["company_mysql_password"])

def get_pivot_container() -> docker.models.containers.Container:
    """Получить контейнер пивота"""

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
            found_pivot_container : docker.models.containers.Container = docker_container_list[0]
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die(
                "Не был найден необходимый docker-контейнер для создания команды. Убедитесь, что окружение поднялось корректно"
            )
    
    return found_pivot_container

def add_ports(pivot_container: docker.models.containers.Container, db_driver: DBDriverConf) -> None:
    """Функция для добавления портов на домино"""

    host_list = []
    for instance in db_driver.data.get("company_mysql_hosts"):
        host_list.append(f"{instance['host']}:{instance['port']}")

    host_list_serialized = ",".join(host_list)

    domino_credentials = load_domino_credentials()

    loader = Loader("Применяем конфигурацию БД...", "Успешно применили конфигурацию БД", "Не смогли применить конфигурацию БД")
    output = pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            f"php src/Compass/Pivot/sh/php/domino/add_predefined_host_to_domino.php --domino-id={domino_credentials.domino_id} --mysql-user={domino_credentials.company_mysql_user} --mysql-pass={domino_credentials.company_mysql_pass} --host-list=[{host_list_serialized}] --type=common"
        ],
    )

    if output.exit_code == 0:
        loader.success()
    else:
        loader.error()
        print(output.output.decode("utf-8"))

def start() -> None:

    db_driver = DBDriverConf(db_config["database_connection"]["driver"], db_config["database_connection"].get("driver_data", None))

    # валидируем конфигурацию БД
    subprocess.run(
    [
        "python3",
        script_dir + "/validate_db_configuration.py",
        "--validate-only"
    ]
    ).returncode == 0 or scriptutils.die("Ошибка при валидации конфигурации БД")

    confirm = input(scriptutils.warning("Применяем конфигурацию БД, заданную в %s?[y/n]" % str(config_path.resolve())))

    if confirm != "y":
        scriptutils.die("Выполнение скрипта прервано")
    
    # применяем конфигурацию БД
    subprocess.run(
    [
        "python3",
        script_dir + "/validate_db_configuration.py",
    ]
    ).returncode == 0 or scriptutils.die("Ошибка при фиксировании конфигурации БД")

    print("Обновляем приложение")
    subprocess.run([
        "python3",
        "%s/update.py" % script_dir,
        ])
        
    # добавляем порты
    add_ports(get_pivot_container(), db_driver)

start()
print(scriptutils.success("Успешно обновили конфигурацию баз данных"))
