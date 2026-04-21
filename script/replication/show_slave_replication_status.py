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

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для проверки статуса репликации mysql-изменений с master сервера.",
    usage="python3 script/replication/show_slave_replication_status.py [-v VALUES] [-e ENVIRONMENT] [--type monolith|team] [--all-teams] [--all-types] [--log-level LOG_LEVEL] [--monitoring] [--userbot-notice-path USERBOT_NOTICE_PATH] [--userbot-notice-test]",
    epilog="Пример: python3 script/replication/show_slave_replication_status.py -v compass -e production --all-teams --all-types --log-level 1 --monitoring --userbot-notice-path /etc/compass_userbot/userbot_config.json --userbot-notice-test",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument(
    "-t", "--type", required=False, default="monolith", type=str,
    help="На каком типе mysql запускаем (monolith или team)",
    choices=["monolith", "team"]
)
parser.add_argument("--all-teams", required=False, action="store_true",
                    help="Выбрать все созданные команды для выполнения скрипта")
parser.add_argument("--all-types", required=False, action="store_true",
                    help="Выбрать все типы mysql для выполнения скрипта")
parser.add_argument("--log-level", required=False, default=1, type=int,
                    help="Уровень логирования статуса репликации")
parser.add_argument("--monitoring", required=False, action="store_true",
                    help="Флаг для мониторинга статуса репликации")
parser.add_argument('--userbot-notice-path', required=False, default='/etc/compass_userbot/userbot_config.json', type=str,
                    help='Путь к файлу с данными бота для уведомления в случае переключения vip')
parser.add_argument('--userbot-notice-test', required=False, action='store_true',
                    help='Проверка отправки ботом уведомления')

args = parser.parse_args()
values_name = args.values
mysql_type = args.type.lower()
is_all_teams = args.all_teams
is_all_types = args.all_types
log_level = args.log_level
is_replica_monitoring = args.monitoring
userbot_notice_config_str = args.userbot_notice_path
is_userbot_notice_test = args.userbot_notice_test

values_file_name = f"values.{values_name}.yaml"

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

    replica_success_result = [] # список проверок, что все реплики работают корректно

    if is_replica_monitoring and is_userbot_notice_test:
        message = f"Проверка уведомления от бота для скрипта проверки статуса репликации."
        send_userbot_replica_notice(message)
        return

    if is_replica_monitoring == False and log_level > 3:
        log_text = ("Детали статуса репликации:\n" +
        "- Slave_IO_State - текущее состояние репликации,\n" +
        "- Slave_IO_Running - работает ли поток IO (получение данных с мастера),\n" +
        "- Slave_SQL_Running - работает ли поток SQL (применение изменений),\n" +
        "- Last_IO_Error, Last_SQL_Error - последние ошибки репликации,\n" +
        "- Seconds_Behind_Master - отставание реплики от мастера в секундах\n")
        print(log_text)

    mysql_host = "localhost"

    if is_all_types or mysql_type == scriptutils.MONOLITH_MYSQL_TYPE:
        if is_replica_monitoring == False:
            loader = Loader("Статус репликации для типа monolith:", "Статус репликации для типа monolith:").start()
        mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
        mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

        found_container = scriptutils.find_container_mysql_container(client, scriptutils.MONOLITH_MYSQL_TYPE, domino_id)
        if not found_container:
            print("Не удалось найти контейнер pivot mysql.")
            sys.exit(1)

        is_monolith_success, status_text = mysql_show_slave_replication_status(
                                               found_container, mysql_host, mysql_user, mysql_pass)

        replica_success_result.append(is_monolith_success)
        if is_replica_monitoring == False:
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

            if (not chosen_space_index.isdigit()) or int(chosen_space_index) < 0 or int(chosen_space_index) > (
                    len(space_id_list) + 1):
                scriptutils.die("Выбран некорректный вариант")

        # проходимся по каждому пространству
        if is_all_teams or int(chosen_space_index) == (len(space_id_list) + 1):
            for space_id, space_config_obj in space_config_obj_dict.items():
                if is_replica_monitoring == False:
                    loader = Loader("Статус репликации в команде %s:" % space_id,
                                    "Статус репликации в команде %s:" % space_id).start()
                found_container = scriptutils.find_container_mysql_container(client, scriptutils.TEAM_MYSQL_TYPE,
                                                                             domino_id, space_config_obj.port)
                is_space_success, status_text = mysql_show_slave_replication_status(found_container, mysql_host, mysql_user,
                                                                              mysql_pass)

                replica_success_result.append(is_space_success)
                if is_replica_monitoring == False:
                    loader.success()
                    print(status_text)

        else:
            space_id = space_id_list[int(chosen_space_index) - 1]
            space_config_obj = space_config_obj_dict[space_id]
            if is_replica_monitoring == False:
                loader = Loader("Статус репликации в команде %s:" % space_id,
                                "Статус репликации в команде %s:" % space_id).start()
            found_container = scriptutils.find_container_mysql_container(client, scriptutils.TEAM_MYSQL_TYPE, domino_id,
                                                                         space_config_obj.port)
            is_space_success, status_text = mysql_show_slave_replication_status(found_container, mysql_host, mysql_user,
                                                                          mysql_pass)

            replica_success_result.append(is_space_success)
            if is_replica_monitoring == False:
                loader.success()
                print(status_text)

    # уведомляем, если у реплики провальный статус
    notice_replica_failed_status(replica_success_result)

    if not all(replica_success_result):
        print(scriptutils.warning("\nРепликация не может завершиться корректно!"))
        log_text = "Проверьте следующие моменты:\n"
        log_text += "- верно ли указан Master_Host (если репликация запущена на reserve сервере, то Master_Host должен иметь в названии лейбл primary),\n"
        log_text += "- был ли ранее создан mysql-пользователь, имя которого используется в поле Master_User,\n"
        log_text += "- проверьте ошибки в полях Last_IO_Error и Last_SQL_Error.\n"
        print(log_text)


def notice_replica_failed_status(replica_success_result: list):
    is_replicas_success = all(replica_success_result)
    if is_replica_monitoring and not all(replica_success_result) and not is_master_server(current_values):
        send_userbot_replica_notice("Проблема с репликацией MySQL - проверьте статус реплики на сервере.")
        exit(1)


# получить статус репликации в полученном контейнере
def mysql_show_slave_replication_status(found_container: docker.models.containers.Container, mysql_host: str,
                                        mysql_user: str, mysql_pass: str):
    cmd = f"mysql -h {mysql_host} -u {mysql_user} -p{mysql_pass} -e \"SHOW SLAVE STATUS\\G\""

    try:
        result = found_container.exec_run(cmd)
    except docker.errors.NotFound:
        print("\nНе нашли mysql контейнер для компании")
        return false, ""

    if result.exit_code != 0:
        scriptutils.die("Ошибка при получении статуса репликации")

    output = result.output.decode("utf-8", errors="ignore")

    # парсим ответ статуса реплики
    result = slave_status_parsing(output)

    # подготавливаем текст статуса для вывода
    is_success, slave_status_text = prepare_status_text(result)

    return is_success, slave_status_text


# парсим ответ статуса реплики
def slave_status_parsing(output):
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

    return result

# подготавливаем текст статуса для вывода
def prepare_status_text(result: Dict):

    io_running = str(result.get("Slave_IO_Running"))
    prepare_io_running = scriptutils.error(io_running) if io_running != "Yes" else io_running
    sql_running = str(result.get("Slave_SQL_Running"))
    prepare_sql_running = scriptutils.error(sql_running) if sql_running != "Yes" else sql_running
    seconds_behind_master = result.get("Seconds_Behind_Master")

    is_success = io_running == "Yes" and sql_running == "Yes"

    if log_level == 1:
        if is_success:
            if seconds_behind_master == 0:
                return True, "Репликация работает корректно"
            else:
                return True, f"Репликация запущена, но отстаёт на {seconds_behind_master} seconds"
        else:
            return False, scriptutils.error(
                f"Репликация не запущена: Slave_IO_Running = {io_running}; Slave_SQL_Running = {sql_running}")
    elif log_level == 2:
        return is_success, (f"""Slave_IO_Running: {prepare_io_running}
Slave_SQL_Running: {prepare_sql_running}
Seconds_Behind_Master: {seconds_behind_master} seconds\n""")
    else:

        slave_status_text = (f"""Master_Host: {result.get("Master_Host")}
Master_User: {result.get("Master_User")}
Master_Port: {result.get("Master_Port")}

Slave_IO_State: {result.get("Slave_IO_State")}
Slave_IO_Running: {prepare_io_running}
Slave_SQL_Running: {prepare_sql_running}
Seconds_Behind_Master: {seconds_behind_master} seconds

Last_IO_Error: {result.get("Last_IO_Error")}
Last_SQL_Error: {result.get("Last_SQL_Error")}\n""")

    return is_success, slave_status_text


# отправка уведомления ботом о статусе реплики
def send_userbot_replica_notice(message: str):

    hostname = scriptutils.get_hostname()
    message = f"⚠️ *{hostname}*: {message}"

    # проверяем наличие конфига с настройками бота
    userbot_notice_path = Path(userbot_notice_config_str)
    if len(userbot_notice_config_str) < 1 or not userbot_notice_path.exists():
        print(f"Не найден файл-конфиг с данными бота: {userbot_notice_config_str}")
        return

    # получаем настройки
    with open(userbot_notice_path, 'r') as file:
        json_str = file.read()
        userbot_data = json.loads(json_str) if json_str != "" else {}

    is_need_response = True if is_userbot_notice_test else False
    scriptutils.send_userbot_notice(userbot_data["userbot_token"], userbot_data["notice_chat_id"],
        userbot_data["notice_domain"], message, userbot_data["userbot_version"], is_need_response)


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


def is_master_server(current_values: Dict):

    company_config_mount_path = current_values.get("company_config_mount_path")
    if company_config_mount_path is None or company_config_mount_path == "":
        scriptutils.die("В файле для деплоя %s отсутствует значение для company_config_mount_path" % values_file_name)
        return

    servers_companies_relationship_file = current_values.get("servers_companies_relationship_file")
    if servers_companies_relationship_file is None or servers_companies_relationship_file == "":
        print(scriptutils.error("В файле для деплоя %s отсутствует значение для servers_companies_relationship_file" % values_file_name))
        return

    # получаем путь к файлу для связи компаний между серверами
    servers_companies_relationship_file_path = f"{company_config_mount_path}/{servers_companies_relationship_file}"

    if not Path(servers_companies_relationship_file_path).exists():
        print(scriptutils.error("Не найден файл для связи компаний между серверами: %s" % servers_companies_relationship_file_path))
        return

    if current_values.get("service_label") is None or current_values.get("service_label") == "":
        print(scriptutils.error("В файле для деплоя %s отсутствует значение для service_label" % values_file_name))
        return
    service_label = current_values.get("service_label")

    with open(servers_companies_relationship_file_path, "r") as file:
        reserve_relationship_str = file.read()
        reserve_relationship_dict = json.loads(reserve_relationship_str) if reserve_relationship_str != "" else {}

    # получаем флаг master = true/false
    if reserve_relationship_dict.get(service_label) is not None:
        current_server_data = reserve_relationship_dict.get(service_label)
        if current_server_data["master"] is not None and current_server_data["master"] == True:
            return True
    return False


# точка входа в скрипт
start()
