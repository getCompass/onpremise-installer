#!/usr/bin/env python3
import sys

sys.dont_write_bytecode = True

import argparse, re, yaml, json, glob, psutil
import signal
import os
import logging
import docker, subprocess
import docker.errors, docker.models, docker.models.containers, docker.types
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path
from time import sleep
from typing import Dict, List

script_dir = str(Path(__file__).parent.resolve())

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для переключения состояния сервера.",
    usage="python3 script/replication/keepalived_status_changed.py [-v VALUES] [-e ENVIRONMENT] [--state MASTER|BACKUP|FAULT] [--userbot-notice-path USERBOT_NOTICE_PATH] [--userbot-notice-test]",
    epilog="Пример: python3 script/replication/keepalived_status_changed.py -v compass -e production --state BACKUP --userbot-notice-path /etc/compass_userbot/userbot_config.json --userbot-notice-test",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument('--state', required=True, type=str,
                    help='Переключить сервер в указанное состояние. Возможные значения: MASTER|BACKUP|FAULT')
parser.add_argument('--userbot-notice-path', required=False, default='/etc/compass_userbot/userbot_config.json', type=str,
                    help='Путь к файлу с данными бота для уведомления в случае переключения vip')
parser.add_argument('--userbot-notice-test', required=False, action='store_true',
                    help='Проверка отправки ботом уведомления')
args = parser.parse_args()

values_name = args.values
environment = args.environment
state = args.state
userbot_notice_config_str = args.userbot_notice_path
is_userbot_notice_test = args.userbot_notice_test

stack_name_prefix = environment + '-' + values_name
stack_name_monolith = stack_name_prefix + "-monolith"

# сколько ожидаем переключения состояния сервера
MASTER_STATE_CHANGED_SLEEP = 10

# файл для блокировки перехода в Master состояние
MASTER_STATE_BLOCK_FILE_PATH = "/etc/keepalived/block_master"

# хранит текущее состояние keepalived
KEEPALIVED_STATE_FILE = "/etc/keepalived/last_state"

client = docker.from_env()


# класс конфига БД
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str,
                 container_name: str) -> None:
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

    if is_userbot_notice_test:
        message = f"Проверка уведомления от бота для скрипта переключения состояния серверов."
        send_userbot_keepalived_notice(message)
        return

    logging.info(f"--- Keepalived изменил состояние на {state} ---")

    current_values = get_values()

    service_label = ""
    if current_values.get("service_label") is not None and current_values.get("service_label") != "":
        service_label = current_values.get("service_label")

    # конфиг бд для монолита
    monolith = DbConfig(
        "", 0,
        current_values["projects"]["monolith"]["service"]["mysql"]["host"],
        current_values["projects"]["monolith"]["service"]["mysql"]["port"],
        current_values["projects"]["monolith"]["service"]["mysql"]["user"],
        current_values["projects"]["monolith"]["service"]["mysql"]["password"],
        "%s-%s_mysql" % (stack_name_monolith, service_label)
    )

    # формируем список активных пространств
    space_config_obj_dict = get_space_dict(current_values)
    logging.info(f"{state}: Получили конфиги пространства.")

    # действия при переходе в MASTER
    if state.lower() == "master":
        master_state_changed(current_values, monolith, space_config_obj_dict)

    # действия при переходе в BACKUP
    elif state.lower() == "backup":

        check_keepalived_life_time()

        # уведомляем об этом ботом
        message = f"Внимание! Сервер переключился в состояние {state}"
        send_userbot_keepalived_notice(message)

        backup_state_changed(current_values, monolith, space_config_obj_dict)

    # действия при переходе в FAULT
    elif state.lower() == "fault":
        # уведомляем об этом ботом
        message = f"Внимание! Сервер переключился в состояние {state}"
        send_userbot_keepalived_notice(message)

        fault_state_changed(current_values, monolith, space_config_obj_dict)

    else:
        logging.error(scriptutils.error(f"Некорректное значение состояния: {state}"))


# выполняем действия если state стал master
def master_state_changed(current_values: Dict, monolith: DbConfig, space_config_obj_dict: list[DbConfig]):
    logging.info(f"{state}: Выполняем действия для состояния MASTER")

    # убиваем все процессы keepalived_state_changed, которые не относятся к мастеру
    kill_keepalived_state_changed_process(["BACKUP", "FAULT"])

    change_master_flag(current_values, current_values.get("service_label"))
    logging.info(f"{state}: Успешно изменили master flag")

    # сохраняем текущее состояние в файл
    save_current_state(state)

    # меняем master_service_label, что текущий сервер стал master
    change_master_service_label(current_values, current_values.get("service_label"))
    logging.info(f"{state}: Успешно изменили master_service_label")

    # ждём некоторое время пока другой сервер станет backup/fault
    logging.info(f"{state}: Ждём, когда сервера изменят состояние")
    sleep(MASTER_STATE_CHANGED_SLEEP)

    # останавливаем репликацию
    stop_replication_db_list([monolith], "monolith")
    stop_replication_db_list(space_config_obj_dict)

    # выключаем read-only режим баз данных
    disable_read_mode_db_list([monolith])
    disable_read_mode_db_list(space_config_obj_dict)
    logging.info(f"{state}: Выключили read-only режим в базах данных")

    logging.info(f"{state}: --- Завершили работу изменения состояния ---")


# убиваем все процессы keepalived_state_changed
def kill_keepalived_state_changed_process(states: List[str]):

    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmd = " ".join(proc.info['cmdline'] or [])

            for item in states:
                if "keepalived_status_changed.py" in cmd and f"--state {item}" in cmd:
                    pid = proc.info['pid']

                    try:
                        os.kill(pid, signal.SIGTERM)

                        # Ждём немного, чтобы процесс завершился
                        sleep(0.5)

                        # Проверяем, завершился ли процесс
                        try:
                            os.kill(pid, 0)  # Проверка существования процесса
                            # Пробуем SIGKILL
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            break

                    except ProcessLookupError as e:
                        logging.info(f"{state}: Пропускаем - процесс {pid} переключения состояния уже отключён: {e}")
                    except PermissionError as e:
                        logging.error(f"{state}: Отсутствует права для отключения процесса переключения состояния {pid}: {e}")
                    except Exception as e:
                        logging.error(f"{state}: Неизвестная ошибка отключения процесса переключения состояния {pid}: {type(e).__name__} - {e}")

                    break  # Выходим из цикла по states для этого процесса

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logging.error(f"{state}: Ошибка доступа к процессу переключения состояния: {e}")
            continue
        except Exception as e:
            logging.error(f"{state}: Непредвиденная ошибка в итерации процесса: {e}")
            continue


# выполняем действия если state стал backup
def backup_state_changed(current_values: Dict, monolith: DbConfig, space_config_obj_dict: list[DbConfig]):
    logging.info(f"{state}: Выполняем действия для состояния BACKUP")

    change_master_flag(current_values)
    logging.info(f"{state}: Успешно изменили master flag")

    last_state = get_last_state()

    # сохраняем текущее состояние в файл
    save_current_state(state)

    # блочим запись в бд
    lock_write_db_list([monolith], "monolith")
    lock_write_db_list(space_config_obj_dict)
    logging.info(f"{state}: Закрыли запись для баз данных")

    # меняем master_service_label
    success = change_master_service_label(current_values)

    if not success:
        # добавляем блокировку, если стоит запрос на автопереход в Master состояние
        block_to_master_state_changed(current_values, last_state)

        # уведомляем об этом ботом
        message = f"Сервер не смог обновить master_service_label - проверьте работу sync файлов на Master сервере"
        send_userbot_keepalived_notice(message)

        logging.error(scriptutils.error(f"{state}: Изменение master_service_label провалилось - проверьте работу sync файлов на Master сервере"))
        exit(0)

    logging.info(f"{state}: Успешно изменили master_service_label")

    # стартуем репликацию на backup сервере
    start_replication(current_values, last_state)

    logging.info(f"{state}: --- Завершили работу изменения состояния ---")


# проверяем время работы keepalived
# для кейса первого поднятия keepalived
# в этом случае сначала устанавливается backup state, и через 10сек - master state
def check_keepalived_life_time():

    PID_FILE = '/var/run/keepalived.pid'
    try:
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())

        process = psutil.Process(pid)
        uptime = int(time.time() - process.create_time())

        if uptime < 15:
            sleep(10)
    except (psutil.NoSuchProcess, FileNotFoundError):
        pass


# выполняем старт репликации
def start_replication(current_values: Dict, last_state: str):
    result = subprocess.run(
        [
            "sudo",
            sys.executable,
            script_dir + "/reset_slave_replication.py",
            "--all-types",
            "--all-teams",
        ]
    ).returncode

    # если рестарт репликации закончился с ошибкой
    if result != 0:
        logging.error(scriptutils.error(f"{state}: Рестарт репликации провалился - проверьте статус репликации"))

        # добавляем блокировку, если стоит запрос на автопереход в Master состояние
        block_to_master_state_changed(current_values, last_state)

        # уведомляем об этом ботом
        message = f"Сервер не смог выполнить рестарт репликации - проверьте статус репликации"
        send_userbot_keepalived_notice(message)
        exit(0)

    result = subprocess.run(
        [
            "sudo",
            sys.executable,
            script_dir + "/start_slave_replication.py",
            "--all-types",
            "--all-teams",
        ]
    ).returncode

    # если старт репликации не завершился
    if result != 0:
        logging.error(scriptutils.error(f"{state}: Старт репликации провалился - проверьте статус репликации"))

        # добавляем блокировку, если стоит запрос на автопереход в Master состояние
        block_to_master_state_changed(current_values, last_state)

        # уведомляем об этом ботом
        message = f"Сервер не смог выполнить старт репликации - проверьте статус репликации"
        send_userbot_keepalived_notice(message)
        exit(0)

    logging.info(f"{state}: Успешно стартовали репликацию")


# выполняем действия если state стал fault
def fault_state_changed(current_values: Dict, monolith: DbConfig, space_config_obj_dict: list[DbConfig]):
    logging.info(f"{state}: Выполняем действия для состояния FAULT")

    change_master_flag(current_values)
    logging.info(f"{state}: Успешно изменили master flag")

    last_state = get_last_state()

    # сохраняем текущее состояние в файл
    save_current_state(state)

    # блочим запись в бд
    lock_write_db_list([monolith], "monolith")
    lock_write_db_list(space_config_obj_dict)
    logging.info(f"{state}: Закрыли запись для баз данных")

    # меняем master_service_label
    success = change_master_service_label(current_values)
    if not success:
        # добавляем блокировку, если стоит запрос на автопереход в Master состояние
        block_to_master_state_changed(current_values, last_state)

        # уведомляем об этом ботом
        message = f"Сервер не смог обновить master_service_label - проверьте работу sync файлов на Master сервере"
        send_userbot_keepalived_notice(message)

        logging.error(scriptutils.error(f"{state}: Изменение master_service_label провалилось - проверьте работу sync файлов на Master сервере"))
        exit(0)

    logging.info(f"{state}: Успешно изменили master_service_label")

    logging.info(f"{state}: --- Завершили работу изменения состояния ---")


# добавляем блокировку, если стоит запрос на автопереход в Master состояние
def block_to_master_state_changed(current_values: Dict, last_state: str):
    disable_flag = current_values.get("master_state_changed_disable", False)
    if disable_flag is None or not disable_flag:
        return

    if (last_state == "master" or last_state == "unknown") and (state.lower() == "backup" or state.lower() == "fault"):

        # создаём файл для блокировки перехода
        try:
            with open(MASTER_STATE_BLOCK_FILE_PATH, 'a'):
                os.utime(MASTER_STATE_BLOCK_FILE_PATH, None)
            print(f"{state}: Блокировка перехода в Master состояние установлена: {MASTER_STATE_BLOCK_FILE_PATH}")
        except IOError as e:
            print(f"{state}: Ошибка при создании файла блокировки перехода в Master состояние: {e}")
            return

        logging.info(f"{state}: Установили файл-блокировки для изменения состояния на Master")

        # отправляем уведомление о создании блокировки
        message = "Установлена блокировка перехода сервера в Master состояние"
        send_userbot_keepalived_notice(message)


# отправка уведомления ботом о смене состояния сервера
def send_userbot_keepalived_notice(message: str):

    hostname = scriptutils.get_hostname()
    message = f"⚠️ *{hostname}*: {message}"

    # проверяем наличие конфига с настройками бота
    userbot_notice_path = Path(userbot_notice_config_str)
    if len(userbot_notice_config_str) < 1 or not userbot_notice_path.exists():
        print(f"Не найден файл-конфиг с данными бота: {userbot_notice_config_str}")
        logging.info(f"{state}: Не найден файл-конфиг с данными бота: {userbot_notice_config_str}")
        return

    # получаем настройки
    with open(userbot_notice_path, 'r') as file:
        json_str = file.read()
        userbot_data = json.loads(json_str) if json_str != "" else {}

    is_need_response = True if is_userbot_notice_test else False
    scriptutils.send_userbot_notice(userbot_data["userbot_token"], userbot_data["notice_chat_id"],
        userbot_data["notice_domain"], message, userbot_data["userbot_version"], is_need_response)


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
            "%s-%s-%s-company_mysql-%d" % (stack_name_prefix, service_label, domino_id,
                                           space_config_dict["mysql"]["port"])
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

    current_values = scriptutils.merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


# меняем master flag в файле для связи между серверами
def change_master_flag(current_values: Dict, master_service_label: str = ""):
    # получаем путь к файлу для связи компаний между серверами
    servers_companies_relationship_file_path = current_values.get(
        "company_config_mount_path") + "/" + current_values.get("servers_companies_relationship_file")

    # получаем текущий service_label
    current_service_label = current_values.get("service_label")

    if master_service_label == "":

        # читаем содержимое файла
        logging.info(f"{state}: Пытаемся изменить master flag (циклично с таймаутом)...")
        with open(servers_companies_relationship_file_path, "r") as file:
            reserve_relationship_str = file.read()
            reserve_relationship_dict = json.loads(reserve_relationship_str) if reserve_relationship_str != "" else {}

            if reserve_relationship_dict.get(current_service_label) is None:
                logging.info(f"{state}: Отсутствовал флаг master - добавили \"master\" = false в current-values для %s" % current_service_label)
                data = {"master": False}
                reserve_relationship_dict[current_service_label] = data
            for label, data in reserve_relationship_dict.items():
                if "master" in data and data["master"] == True and label != current_service_label:
                    master_service_label = label
                    logging.info(f"{state}: Установили \"master\" = true для %s" % label)
                    data["master"] = True
                    reserve_relationship_dict[label] = data
                if current_service_label == label and label != master_service_label:
                    data["master"] = False
                    reserve_relationship_dict[label] = data
        f = open(servers_companies_relationship_file_path, "w")
        f.write(json.dumps(reserve_relationship_dict))
        f.close()
    else:

        with open(servers_companies_relationship_file_path, "r") as file:
            reserve_relationship_str = file.read()
            reserve_relationship_dict = json.loads(reserve_relationship_str) if reserve_relationship_str != "" else {}

            # меняем флаг master = true/false для серверов
            if reserve_relationship_dict.get(current_service_label) is None:
                logging.info(f"{state}: Отсутствовал флаг master - добавили \"master\" = false в current-values для %s" % current_service_label)
                data = {"master": False}
                reserve_relationship_dict[current_service_label] = data
            for label, data in reserve_relationship_dict.items():
                if label == master_service_label and ("master" not in data or data["master"] != True):
                    logging.info(f"{state}: Изменили \"master\" = true в current-values для %s" % label)
                    data["master"] = True
                if label != master_service_label:
                    logging.info(f"{state}: Изменили \"master\" = false в current-values для %s" % label)
                    data["master"] = False
                reserve_relationship_dict[label] = data

        f = open(servers_companies_relationship_file_path, "w")
        f.write(json.dumps(reserve_relationship_dict))
        f.close()


# меняем master_service_label в файле для связи между серверами
def change_master_service_label(current_values: Dict, master_service_label: str = ""):
    # получаем путь к файлу для связи компаний между серверами
    servers_companies_relationship_file_path = current_values.get(
        "company_config_mount_path") + "/" + current_values.get("servers_companies_relationship_file")

    # получаем текущий service_label
    current_service_label = current_values.get("service_label")

    if master_service_label == "":

        # читаем содержимое файла
        timeout = 300
        n = 0
        logging.info(f"{state}: Пытаемся изменить master_service_label (циклично с таймаутом)...")
        while n <= timeout:

            with open(servers_companies_relationship_file_path, "r") as file:

                reserve_relationship_str = file.read()
                reserve_relationship_dict = json.loads(
                    reserve_relationship_str) if reserve_relationship_str != "" else {}

                for label, data in reserve_relationship_dict.items():
                    if "master" in data and data["master"] == True and label != current_service_label:
                        master_service_label = label

            # если определили master_service_label, то останавливаем цикл
            if master_service_label != "":
                f = open(servers_companies_relationship_file_path, "w")
                f.write(json.dumps(reserve_relationship_dict))
                f.close()
                break

            n = n + 2
            sleep(2)
            if n == timeout:
                logging.warning(scriptutils.warning(f"{state}: Получили пустой master_service_label - проверьте работу sync файлов на серверах"))
                return False

    logging.info(f"{state}: Изменили \"master_service_label\" = %s в current-values" % master_service_label)

    with values_file_path.open("r") as values_file:
        new_values = yaml.safe_load(values_file)
        new_values = {} if new_values is None else new_values
    new_values["master_service_label"] = master_service_label

    write_to_file(new_values)

    return True


def write_to_file(new_values: Dict):
    new_path = Path(str(values_file_path.resolve()))
    with new_path.open("w+t") as f:
        yaml.dump(new_values, f, sort_keys=False)


# выключаем read-only режим баз данных
def disable_read_mode_db_list(db_list: list[DbConfig]):
    for db in db_list:

        container_list = client.containers.list(filters={"name": db.container_name})

        if len(container_list) < 1:
            logging.error(scriptutils.error(
                f"{state}: Пространство %d не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения." % db.space_id))

        space_container: docker.models.containers.Container = container_list[0]

        # mysql команда для выполнения
        mysql_command = "SET GLOBAL super_read_only = OFF; SET GLOBAL read_only = OFF; UNLOCK TABLES;"

        cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
        result = space_container.exec_run(cmd=cmd)

        if result.exit_code != 0:
            print(result.output)
            logging.error(scriptutils.error(f"{state}: Не смогли выполнить mysql команду в mysql пространства %d" % db.space_id))


# останавливаем репликацию БД
def stop_replication_db_list(db_list: list[DbConfig], db_type: str = ""):

    db_type_str = "monolith" if len(db_type) > 0 else "пространств"

    for db in db_list:

        timeout = 49
        n = 0
        while n <= timeout:

            container_list = client.containers.list(filters={"name": db.container_name})
            space_id = db.space_id if db.space_id > 0 else "monolith"

            if len(container_list) > 0:
                space_container: docker.models.containers.Container = container_list[0]

                # mysql команда для выполнения
                mysql_command = "STOP SLAVE;"

                cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
                result = space_container.exec_run(cmd=cmd)

                if result.exit_code != 0:
                    print(result.output)
                    logging.warning(scriptutils.error(
                        f"{state}: Не смогли выполнить mysql команду остановки репликации в mysql пространства {space_id}. (Пробуем ещё раз)"))
                else:
                    break
            else:
                logging.warning(scriptutils.warning(
                    f"{state}: Пространство {space_id} не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения. (Пробуем ещё раз)."))

            n = n + 7
            sleep(7)
            if n == timeout:
                logging.error(scriptutils.error(f"{state}: Не смогли остановить репликацию для {db_type_str} - проверьте статус репликации. (Цикл проверки закончился)."))
                return

    logging.info(f"{state}: Остановили репликацию баз данных для {db_type_str}")


# сохраняем текущее состояние в файл
def save_current_state(state):
    with open(KEEPALIVED_STATE_FILE, 'w') as f:
        f.write(state)


# получаем последнее состояние keepalived из файла
def get_last_state():
    if os.path.exists(KEEPALIVED_STATE_FILE):
        with open(KEEPALIVED_STATE_FILE, 'r') as f:
            return f.read().strip().lower()
    return "unknown"


# лочим запись в БД
def lock_write_db_list(db_list: list[DbConfig], db_type: str = ""):

    db_type_str = "monolith" if len(db_type) > 0 else "пространств"

    for db in db_list:

        timeout = 49
        n = 0
        while n <= timeout:

            container_list = client.containers.list(filters={"name": db.container_name})
            space_id = db.space_id if db.space_id > 0 else "monolith"

            if len(container_list) < 1:
                logging.error(scriptutils.error(
                    f"{state}: Пространство {space_id} не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения. (Пробуем ещё раз)."))
            else:
                space_container: docker.models.containers.Container = container_list[0]

                # mysql команда для выполнения
                mysql_command = "SET GLOBAL read_only = ON; SET GLOBAL super_read_only = ON; FLUSH TABLES WITH READ LOCK;"

                cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
                result = space_container.exec_run(cmd=cmd)

                if result.exit_code != 0:
                    print(result.output)
                    logging.warning(scriptutils.warning(f"{state}: Не смогли выполнить mysql команду write-lock в mysql пространства {space_id}. (Пробуем ещё раз)"))
                else:
                    break

            n = n + 7
            sleep(7)
            if n == timeout:
                logging.error(scriptutils.error(f"{state}: Не смогли заблочить запись баз данных для {db_type_str} - проверьте статус репликации. (Цикл проверки закончился)."))
                return


start(state)
