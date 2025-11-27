#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, time, re, glob, json
import docker
from typing import Dict

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from loader import Loader
from pathlib import Path

scriptutils.assert_root()

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=True)

parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="окружение")
parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="название файла со значениями для деплоя")
parser.add_argument(
    "-t", "--type", required=False, default="monolith", type=str, help="тип mysql (monolith|team)", choices=["monolith", "team"]
)
parser.add_argument("--all-teams", required=False, action="store_true", help="выбрать все команды")
parser.add_argument("--all-types", required=False, action="store_true", help="выбрать все типы mysql")

args = parser.parse_args()
values_name = args.values
mysql_type = args.type.lower()
is_all_teams = args.all_teams
is_all_types = args.all_types


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
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    domino_id = domino["label"]

    stack_name = current_values["stack_name_prefix"] + "-monolith"
    if current_values.get("service_label") is None or current_values.get("service_label") == "":
        confirm = input("\nService_label в файле values оказался пустым. Продолжаем? (y/n): ").strip().lower()
        if confirm != "y":
            scriptutils.error("Завершаем выполнение скрипта")

    stack_name = stack_name + "-" + current_values.get("service_label")

    client = docker.from_env()

    log_text = "Детали статуса репликации:\n"
    log_text = log_text + "- Slave_IO_State - текущее состояние репликации,\n"
    log_text = log_text + "- Slave_IO_Running - работает ли поток IO (получение данных с мастера),\n"
    log_text = log_text + "- Slave_SQL_Running - работает ли поток SQL (применение изменений),\n"
    log_text = log_text + "- Last_IO_Error, Last_SQL_Error - последние ошибки репликации,\n"
    log_text = log_text + "- Seconds_Behind_Master - отставание реплики от мастера в секундах\n"
    print(log_text)

    mysql_host = "localhost"

    if is_all_types or mysql_type == scriptutils.MONOLITH_MYSQL_TYPE:
        loader = Loader("Статус репликации для типа monolith:", "Статус репликации для типа monolith:").start()
        mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
        mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

        found_container = scriptutils.find_container_mysql_container(client, scriptutils.MONOLITH_MYSQL_TYPE, domino_id)
        if not found_container:
            print("Не удалось найти контейнер pivot mysql.")
            sys.exit(1)

        is_success, status_text = mysql_show_slave_replication_status(found_container, mysql_host, mysql_user, mysql_pass)
        loader.success()
        print(status_text)

    if is_all_types or mysql_type == scriptutils.TEAM_MYSQL_TYPE or is_all_teams:
        mysql_user = "root"
        mysql_pass = "root"

        # формируем список активных пространств
        space_config_obj_dict, space_id_list = get_space_dict(current_values)

        if len(space_config_obj_dict) < 1:
            scriptutils.die("Не найдено ни одной команды на сервере. Окружение поднято?")

        chosen_space_index = 1
        if not is_all_teams and len(space_id_list) > 1:
            space_option_str = "Выберете команду, для которой получаем статус репликации:\n"
            for index, option in enumerate(space_id_list):
                space_option_str += "%d. ID команды = %s\n" % (index + 1, option)
            space_option_str += "%d. Все\n" % (len(space_id_list) + 1)

            chosen_space_index = input(space_option_str)

            if (not chosen_space_index.isdigit()) or int(chosen_space_index) < 0 or int(chosen_space_index) > (len(space_id_list) + 1):
                scriptutils.die("Выбран некорректный вариант")

        # проходимся по каждому пространству
        if is_all_teams or int(chosen_space_index) == (len(space_id_list) + 1):
            is_all_success = True
            for space_id, space_config_obj in space_config_obj_dict.items():
                loader = Loader("Статус репликации в команде %s:" % space_id, "Статус репликации в команде %s:" % space_id).start()
                found_container = scriptutils.find_container_mysql_container(client, scriptutils.TEAM_MYSQL_TYPE, domino_id, space_config_obj.port)
                is_success, status_text = mysql_show_slave_replication_status(found_container, mysql_host, mysql_user, mysql_pass)
                loader.success()
                print(status_text)
                if is_success == False:
                    is_all_success = False
        else:
            space_id = space_id_list[int(chosen_space_index) - 1]
            space_config_obj = space_config_obj_dict[space_id]
            loader = Loader("Статус репликации в команде %s:" % space_id, "Статус репликации в команде %s:" % space_id).start()
            found_container = scriptutils.find_container_mysql_container(client, scriptutils.TEAM_MYSQL_TYPE, domino_id, space_config_obj.port)
            is_success, status_text = mysql_show_slave_replication_status(found_container, mysql_host, mysql_user, mysql_pass)
            loader.success()
            print(status_text)

    if is_success == False:
        print(scriptutils.warning("\nРепликация не может завершиться корректно!"))
        log_text = "Проверьте следующие моменты:\n"
        log_text += "- верно ли указан Master_Host (если репликация запущена на reserve сервере, то Master_Host должен иметь в названии лейбл primary),\n"
        log_text += "- был ли ранее создан mysql-пользователь, имя которого используется в поле Master_User,\n"
        log_text += "- проверьте ошибки в полях Last_IO_Error и Last_SQL_Error.\n"
        print(log_text)

# получить статус репликации в полученном контейнере
def mysql_show_slave_replication_status(found_container: docker.models.containers.Container, mysql_host: str, mysql_user: str, mysql_pass: str):

    cmd = f"mysql -h {mysql_host} -u {mysql_user} -p{mysql_pass} -e \"SHOW SLAVE STATUS\\G\""

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nНе нашли mysql контейнер для компании")
        return false, ""

    if result.exit_code != 0:
        scriptutils.die("Ошибка при получении статуса репликации")

    output = result.output.decode("utf-8", errors="ignore")

    patterns = {
        "Master_Host": r"Master_Host:\s*([^\r\n]*)",
        "Master_User": r"Master_User:\s*([^\r\n]*)",
        "Master_Port": r"Master_Port:\s*(\d*)",
        "Slave_IO_State": r"Slave_IO_State:\s*([^\r\n]*)",
        "Slave_IO_Running": r"Slave_IO_Running:\s*(\w*)",
        "Slave_SQL_Running": r"Slave_SQL_Running:\s*(\w*)",
        "Last_IO_Error": r"Last_IO_Error:\s*([\s\S]*?)(?=\n\w+:|$)",
        "Last_SQL_Error": r"Last_SQL_Error:\s*([\s\S]*?)(?=\n\w+:|$)",
        "Seconds_Behind_Master": r"Seconds_Behind_Master:\s*(\d+|NULL)"
    }

    lines = [line.strip() for line in output.split('\n') if line.strip()]

    result = {}
    current_field = None
    accumulated_value = []
    is_success = True

    for line in lines:
        # проверяем, начинается ли строка с нового поля
        field_match = re.match(r'^(\w+):\s*(.*)', line)
        if field_match:
            # если нашли новое поле, сохраняем предыдущее накопленное значение
            if current_field:
                result[current_field] = '\n'.join(accumulated_value).strip() or None
                accumulated_value = []

            current_field = field_match.group(1)
            value_part = field_match.group(2)
            if value_part:
                accumulated_value.append(value_part)
        else:
            # если это продолжение предыдущего поля
            if current_field and current_field in ['Last_IO_Error', 'Last_SQL_Error', 'Slave_IO_State']:
                accumulated_value.append(line)

    # добавляем последнее накопленное значение
    if current_field:
        result[current_field] = '\n'.join(accumulated_value).strip() or None

    # приводим типы для специальных полей
    if 'Master_Port' in result and result['Master_Port']:
        result['Master_Port'] = int(result['Master_Port'])
    if 'Seconds_Behind_Master' in result:
        if result['Seconds_Behind_Master'] == 'NULL':
            result['Seconds_Behind_Master'] = None
        elif result['Seconds_Behind_Master']:
            result['Seconds_Behind_Master'] = int(result['Seconds_Behind_Master'])

    # формируем текст статуса репликации
    slave_status_text = "Master_Host: %s" % result.get("Master_Host")
    slave_status_text = slave_status_text + "\n" + "Master_User: %s" % result.get("Master_User")
    slave_status_text = slave_status_text + "\n" + "Master_Port: %s" % result.get("Master_Port")
    slave_status_text = slave_status_text + "\n\n" + "Slave_IO_State: %s" % result.get("Slave_IO_State")

    if result.get("Slave_IO_Running") != "Yes":
        is_success = False
        slave_io_running = scriptutils.error(str(result.get("Slave_IO_Running")))
    else:
        slave_io_running = result.get("Slave_IO_Running")
    slave_status_text = slave_status_text + "\n" + "Slave_IO_Running: %s" % slave_io_running

    if result.get("Slave_SQL_Running") != "Yes":
        is_success = False
        slave_sql_running = scriptutils.error(str(result.get("Slave_SQL_Running")))
    else:
        slave_sql_running = result.get("Slave_SQL_Running")
    slave_status_text = slave_status_text + "\n" + "Slave_SQL_Running: %s" % slave_sql_running
    slave_status_text = slave_status_text + "\n" + "Seconds_Behind_Master: %s seconds" % result.get("Seconds_Behind_Master")
    slave_status_text = slave_status_text + "\n\n" + "Last_IO_Error: %s" % result.get("Last_IO_Error")
    slave_status_text = slave_status_text + "\n" + "Last_SQL_Error: %s" % result.get("Last_SQL_Error") + "\n"

    return is_success, slave_status_text

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
    space_id_list = []
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
        space_id_list.append(space_config_obj.space_id)
    space_id_list.sort()
    return dict(sorted(space_config_obj_dict.items())), space_id_list

# точка входа в скрипт
start()
