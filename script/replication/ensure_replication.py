#!/usr/bin/env python3
import sys

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, re, glob, json
import docker
import logging
import subprocess

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from utils import mysql_ssl
from replication.monitor_utils import acquire_single_instance_lock, read_keepalived_last_state, release_single_instance_lock
from replication.reconcile_utils import plan_configure_only_action, plan_replication_action
from replication.configure_replication_firewall import ensure_firewall
from pathlib import Path
from time import sleep

scriptutils.assert_replication_available()
scriptutils.assert_root()

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для проверки и автоматического восстановления репликации mysql.",
    usage="python3 script/replication/ensure_replication.py [-v VALUES] [-e ENVIRONMENT] [--monitoring] [--userbot-notice-path USERBOT_NOTICE_PATH] [--userbot-notice-test]",
    epilog="Пример: python3 script/replication/ensure_replication.py -v compass -e production --monitoring",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument('--monitoring', required=False, action="store_true",
                    help='Флаг для отправки уведомлений ботом о восстановлении и ошибках репликации')
parser.add_argument('--userbot-notice-path', required=False, default='/etc/compass_userbot/userbot_config.json', type=str,
                    help='Путь к файлу с данными бота для уведомлений')
parser.add_argument('--userbot-notice-test', required=False, action='store_true',
                    help='Проверка отправки ботом уведомления')
args = parser.parse_args()

values_name = args.values
environment = args.environment
is_monitoring = args.monitoring
userbot_notice_config_str = args.userbot_notice_path
is_userbot_notice_test = args.userbot_notice_test

script_dir = str(Path(__file__).parent.resolve())

RECONCILER_PID_FILE = "/var/run/mysql_replication_ensure.pid"
MASTER_STATE_BLOCK_FILE_PATH = "/etc/keepalived/block_master"
RESTART_RECHECK_DELAY_SEC = 5

logging.basicConfig(filename='/var/log/ensure-replication.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


# класс конфига БД
class DbConfig:
    def __init__(self, space_id: int, port: str, root_user: str, root_password: str, container_name: str) -> None:
        self.space_id = space_id
        self.port = port
        self.root_user = root_user
        self.root_password = root_password
        self.container_name = container_name


# получить данные окружение из values
def get_values() -> dict:
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


# сформировать список конфигураций пространств
def get_db_list(current_values: dict) -> list:
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    domino_id = domino["label"]
    space_config_dir = domino["company_config_dir"]

    service_label = ""
    if current_values.get("service_label") is not None and current_values.get("service_label") != "":
        service_label = current_values.get("service_label")

    stack_name_prefix = current_values.get("stack_name_prefix")

    db_list = [
        DbConfig(
            0,
            current_values["projects"]["monolith"]["service"]["mysql"]["port"],
            current_values["projects"]["monolith"]["service"]["mysql"]["user"],
            current_values["projects"]["monolith"]["service"]["mysql"]["password"],
            "%s-monolith-%s_mysql" % (stack_name_prefix, service_label),
        )
    ]

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

        db_list.append(
            DbConfig(
                int(space_id),
                space_config_dict["mysql"]["port"],
                "root",
                "root",
                "%s-%s-%s-company_mysql-%s" % (stack_name_prefix, service_label, domino_id,
                                               space_config_dict["mysql"]["port"]),
            )
        )

    return db_list


# проверяем, что текущий сервер является мастером
def is_local_master(current_values: dict) -> bool:
    if read_keepalived_last_state() == "master":
        return True

    return scriptutils.is_replication_master_server(current_values)


# отправка уведомления ботом
def send_userbot_notice(message: str):
    hostname = scriptutils.get_hostname()
    message = f"⚠️ *{hostname}*: {message}"

    userbot_notice_path = Path(userbot_notice_config_str)
    if len(userbot_notice_config_str) < 1 or not userbot_notice_path.exists():
        logging.info("Не найден файл-конфиг с данными бота: %s" % userbot_notice_config_str)
        return

    with open(userbot_notice_path, 'r') as file:
        json_str = file.read()
        userbot_data = json.loads(json_str) if json_str != "" else {}

    is_need_response = True if is_userbot_notice_test else False
    is_onprem_endpoint = userbot_data.get("is_onprem_endpoint", True)
    is_sent = scriptutils.send_userbot_notice(userbot_data["userbot_token"], userbot_data["notice_chat_id"],
                                              userbot_data["notice_domain"], message, userbot_data["userbot_version"],
                                              is_need_response, is_onprem_endpoint)

    if not is_sent:
        logging.warning("Не удалось отправить уведомление ботом: %s" % message)


# получить статус репликации в контейнере базы
def fetch_slave_status(container, db: DbConfig):
    cmd = "mysql -h %s -u %s -p%s -e \"SHOW SLAVE STATUS\\G\"" % ("localhost", db.root_user, db.root_password)

    # demux=True: stderr не должен попадать в вывод - mysql всегда пишет
    # туда warning о пароле в командной строке, из-за него пустой статус
    # (ненастроенная репликация) выглядел бы непустым
    result = container.exec_run(cmd=cmd, demux=True)

    if result.exit_code != 0:
        return None

    return (result.output[0] or b"").decode("utf-8", errors="ignore")


# выполняем mysql команду в контейнере базы
def exec_mysql_command(container, db: DbConfig, mysql_command: str):
    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)

    return container.exec_run(cmd=cmd)


# запускаем полную настройку репликации для базы
def run_start_replication_script(db: DbConfig, configure_only: bool = False) -> bool:
    command = [
        sys.executable,
        script_dir + "/start_slave_replication.py",
        "-v", values_name,
        "-e", environment,
        "--is-logs", "0",
        "--is-choice-space", "0",
    ]

    if db.space_id > 0:
        command.extend(["--type", "team", "--space-id", str(db.space_id)])
    else:
        command.extend(["--type", "monolith"])

    if configure_only:
        command.append("--no-start")

    result = subprocess.run(command)

    return result.returncode == 0


# проверяем и при необходимости восстанавливаем репликацию одной базы
def ensure_db_replication(client, db: DbConfig, configure_only: bool = False) -> str:
    db_label = str(db.space_id) if db.space_id > 0 else "monolith"

    container_list = client.containers.list(filters={"name": db.container_name})

    if len(container_list) < 1:
        logging.error("Не найден рабочий контейнер mysql для %s" % db_label)
        return "missing-container"

    container = container_list[0]

    status_output = fetch_slave_status(container, db)

    if status_output is None:
        logging.error("Не удалось получить статус репликации для %s" % db_label)
        return "error"

    if configure_only:
        action = plan_configure_only_action(status_output)

        if action == "ok":
            return "ok"

        if action == "stop-threads":
            logging.warning("Потоки репликации работают на мастере для %s - останавливаем" % db_label)
            exec_mysql_command(container, db, "STOP SLAVE;")
            return "stopped-threads"

        logging.info("Репликация не настроена для %s - выполняем преднастройку" % db_label)

        if run_start_replication_script(db, configure_only=True):
            return "configured"

        logging.error("Не удалось выполнить преднастройку репликации для %s" % db_label)
        return "configure-failed"

    action = plan_replication_action(status_output)

    if action == "ok":
        return "ok"

    if action == "start":
        logging.info("Репликация не настроена для %s - запускаем настройку" % db_label)

        if run_start_replication_script(db):
            return "started"

        logging.error("Не удалось запустить репликацию для %s" % db_label)
        return "start-failed"

    logging.info("Потоки репликации остановлены для %s - пробуем START SLAVE" % db_label)
    exec_mysql_command(container, db, "START SLAVE;")
    sleep(RESTART_RECHECK_DELAY_SEC)

    status_output = fetch_slave_status(container, db)

    if status_output is not None and plan_replication_action(status_output) == "ok":
        return "restarted"

    logging.error("Не удалось восстановить потоки репликации для %s" % db_label)
    return "restart-failed"


# перезагружаем tls контекст репликации manticore без перезапуска контейнера
def reload_manticore_tls(client, current_values: dict) -> bool:
    manticore_cluster_name = current_values.get("manticore_cluster_name")
    if manticore_cluster_name is None or manticore_cluster_name == "":
        return False

    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    manticore_host = "manticore-%s" % domino["label"]
    manticore_port = domino["service"]["manticore"]["port"]

    stack_name = "%s-monolith-%s" % (current_values["stack_name_prefix"], current_values.get("service_label") or "")
    container_list = client.containers.list(
        filters={
            "name": "%s_php-monolith" % stack_name,
            "health": "healthy",
        }
    )

    if len(container_list) < 1:
        logging.warning("Не найден рабочий контейнер monolith для перезагрузки tls репликации manticore")
        return False

    mysql_command = "SET CLUSTER %s GLOBAL 'socket.ssl_reload'='1';" % manticore_cluster_name
    cmd = "mariadb --skip-ssl -h %s -P %s -e \"%s\"" % (manticore_host, manticore_port, mysql_command)
    result = container_list[0].exec_run(cmd)

    return result.exit_code == 0


# проверяем и при необходимости перевыпускаем ssl сертификат текущего хоста
def ensure_host_mysql_ssl_certificate(client, current_values: dict):
    if current_values.get("mysql_server_id") is None or current_values["mysql_server_id"] == 0:
        return

    ssl_dir = Path("%s/mysql_ssl" % current_values["root_mount_path"])

    if not ssl_dir.exists():
        logging.warning("Отсутствует директория с ssl сертификатами mysql: %s" % str(ssl_dir))
        return

    cert_prefix = mysql_ssl.get_host_cert_prefix(current_values)
    cert_path, key_path = mysql_ssl.get_host_cert_paths(ssl_dir, cert_prefix)

    if not mysql_ssl.is_certificate_expiring(cert_path, key_path):
        return

    logging.info("Сертификат mysql текущего хоста истекает - выполняем перевыпуск: %s" % str(cert_path))

    try:
        mysql_ssl.generate_mysql_ssl("mysql-%s" % cert_prefix, ssl_dir)
    except Exception as e:
        logging.error("Не удалось перевыпустить сертификат mysql текущего хоста: %s" % e)

        if is_monitoring:
            send_userbot_notice("Не удалось перевыпустить сертификат mysql текущего хоста (%s): %s"
                                % (cert_path.name, e))
        return

    reloaded_list = []
    failed_list = []

    for db in get_db_list(current_values):
        db_label = str(db.space_id) if db.space_id > 0 else "monolith"

        container_list = client.containers.list(filters={"name": db.container_name})

        if len(container_list) < 1:
            continue

        result = exec_mysql_command(container_list[0], db, "ALTER INSTANCE RELOAD TLS;")

        if result.exit_code == 0:
            reloaded_list.append(db_label)
        else:
            failed_list.append(db_label)

    if reloaded_list:
        logging.info("Перезагружены ssl сертификаты mysql: %s" % ", ".join(sorted(reloaded_list)))

    if failed_list:
        logging.error("Не удалось перезагрузить ssl сертификаты mysql: %s" % ", ".join(sorted(failed_list)))

    if reload_manticore_tls(client, current_values):
        logging.info("Перезагружен tls контекст репликации manticore (socket.ssl_reload)")
    else:
        logging.warning("Не удалось перезагрузить tls контекст репликации manticore - применяется при перезапуске контейнера")

    if is_monitoring and (reloaded_list or failed_list):
        if failed_list:
            send_userbot_notice("Перевыпущен сертификат mysql текущего хоста, но не удалось перезагрузить TLS в: %s"
                                % ", ".join(sorted(failed_list)))
        else:
            send_userbot_notice("Перевыпущен сертификат mysql текущего хоста и перезагружен TLS в: %s"
                                % ", ".join(sorted(reloaded_list)))


# точка входа в скрипт
def start():

    if not acquire_single_instance_lock(RECONCILER_PID_FILE):
        return

    try:
        if is_userbot_notice_test:
            send_userbot_notice("Проверка уведомления от бота для скрипта восстановления репликации.")
            return

        current_values = get_values()

        # синхронизируем правила файрвола репликации (DOCKER-USER) до работы с базами:
        # порт новой команды должен быть открыт раньше настройки её репликации
        if not ensure_firewall(current_values):
            logging.error("Не удалось синхронизировать правила файрвола репликации (DOCKER-USER) - порты могут быть открыты")
            if is_monitoring:
                send_userbot_notice("Не удалось ограничить порты репликации на уровне файрвола (DOCKER-USER) - требуется внимание администратора")

        client = docker.from_env()

        ensure_host_mysql_ssl_certificate(client, current_values)

        if is_local_master(current_values):
            logging.info("Сервер является мастером - выполняем преднастройку репликации для новых баз")

            results = {}
            for db in get_db_list(current_values):
                db_label = str(db.space_id) if db.space_id > 0 else "monolith"
                results[db_label] = ensure_db_replication(client, db, configure_only=True)

            failed_results = {label: result for label, result in results.items()
                              if result not in ("ok", "configured", "stopped-threads")}
            healed_results = {label: result for label, result in results.items()
                              if result in ("configured", "stopped-threads")}

            if is_monitoring and (failed_results or healed_results):
                message_parts = []
                if healed_results:
                    message_parts.append("преднастроена репликация: %s" % ", ".join(sorted(healed_results)))
                if failed_results:
                    message_parts.append("не удалось преднастроить: %s" % ", ".join(sorted(failed_results)))
                send_userbot_notice("Проверка репликации на мастере: %s" % "; ".join(message_parts))

            if failed_results:
                sys.exit(1)

            return

        if os.path.exists(MASTER_STATE_BLOCK_FILE_PATH):
            logging.warning("Автовосстановление репликации пропущено: установлена блокировка перехода в Master")

            if is_monitoring:
                send_userbot_notice("Автовосстановление репликации пропущено: установлена блокировка block_master - требуется ручная пересинхронизация")

            sys.exit(1)

        results = {}
        for db in get_db_list(current_values):
            db_label = str(db.space_id) if db.space_id > 0 else "monolith"
            results[db_label] = ensure_db_replication(client, db)

        failed_results = {label: result for label, result in results.items()
                          if result not in ("ok", "started", "restarted")}
        healed_results = {label: result for label, result in results.items()
                          if result in ("started", "restarted")}

        if is_monitoring and (failed_results or healed_results):
            message_parts = []
            if healed_results:
                message_parts.append("восстановлена репликация: %s" % ", ".join(sorted(healed_results)))
            if failed_results:
                message_parts.append("не удалось восстановить: %s" % ", ".join(sorted(failed_results)))
            send_userbot_notice("Проверка репликации: %s" % "; ".join(message_parts))

        if failed_results:
            sys.exit(1)
    finally:
        release_single_instance_lock(RECONCILER_PID_FILE)


start()
