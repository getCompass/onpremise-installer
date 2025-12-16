#!/usr/bin/env python3
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse, re, yaml, json, glob, os, tarfile, shutil
import docker
import docker.errors, docker.models, docker.models.containers, docker.types
from utils import scriptutils
from pathlib import Path
from loader import Loader
from datetime import datetime
from math import ceil
import subprocess
import mysql.connector
import socket

scriptutils.assert_root()

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для бэкапов баз данных.",
    usage="python3 script/backup_db.py [-v VALUES] [-e ENVIRONMENT] [--backups-folder BACKUPS_FOLDER] [--backup-name-format BACKUP_NAME_FORMAT] [--free-threshold-percent FREE_THRESHOLD_PERCENT] [--auto-cleaning-limit AUTO_CLEANING_LIMIT] [--userbot-notice-chat-id USERBOT_NOTICE_CHAT_ID] [--userbot-notice-token USERBOT_NOTICE_TOKEN] [--userbot-notice-domain USERBOT_NOTICE_DOMAIN] [--userbot-notice-text USERBOT_NOTICE_TEXT]",
    epilog="Пример: python3 script/backup_db.py -v compass -e production --backups-folder backups --backup-name-format %d_%m_%Y --free-threshold-percent 10 --auto-cleaning-limit 15 --userbot-notice-chat-id PEHneUlL7nM... --userbot-notice-token f47f9384-sk4f-4d1c-8193-7a9b9384952e --userbot-notice-domain https://example.com/ --userbot-notice-text \"Ошибка при создании бэкапа на сервере!\"",
)

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument("--backups-folder", required=False, default="", type=str, help="Название директории для хранения бэкапов")
parser.add_argument("--backup-name-format", required=False, default="%d_%m_%Y", type=str,
                    help="Формат названия папки бэкапа")
parser.add_argument("--free-threshold-percent", required=False, default=0, type=int,
                    help="Минимальное значение свободного места в процентах, при котором будут создаваться бэкапы")
parser.add_argument("--auto-cleaning-limit", required=False, default=0, type=int,
                    help="Максимальное количество хранимых бэкапов, при превышении значения самые старые бэкапы будут автоматически удаляться")
parser.add_argument("--userbot-notice-chat-id", required=False, default="", type=str,
                    help="ID чата, в который будут отправляться уведомления")
parser.add_argument("--userbot-notice-token", required=False, default="", type=str,
                    help="Токен бота, который будет отправлять уведомления")
parser.add_argument("--userbot-notice-domain", required=False, default="", type=str,
                    help="Домен приложения compass, на который отправляются уведомления")
parser.add_argument("--userbot-notice-text", required=False, default="", type=str,
                    help="Текст отправляемого уведомления, когда не смогли создать бэкап")
parser.add_argument("--need-backup-configs", required=False, default=1, type=int,
                    help="0 если не нужно бекапить конфиги")
parser.add_argument("--need-backup-spaces", required=False, default=1, type=int,
                    help="0 если не нужно бекапить mysql пространств")
parser.add_argument("--need-backup-monolith", required=False, default=1, type=int,
                    help="0 если не нужно бекапить mysql монолита")
parser.add_argument("--need-backup-space-id-list", required=False, type=str, default="",
                    help="ID пространств через запятую, которые необходимо забекапить, например: 1,2,4. Если не указано — бэкапим все")
args = parser.parse_args()

values_name = args.values
environment = args.environment
backups_folder = args.backups_folder
backup_name_format = args.backup_name_format
threshold_percent = args.free_threshold_percent
auto_cleaning_limit = args.auto_cleaning_limit
userbot_notice_chat_id = args.userbot_notice_chat_id
userbot_notice_token = args.userbot_notice_token
userbot_notice_domain = args.userbot_notice_domain
userbot_notice_text = args.userbot_notice_text
need_backup_configs = args.need_backup_configs
need_backup_spaces = args.need_backup_spaces
need_backup_monolith = args.need_backup_monolith

if args.need_backup_space_id_list.strip():
    input_space_list = [int(x) for x in args.need_backup_space_id_list.split(",") if x.strip()]
else:
    input_space_list = None

stack_name_prefix = f"{environment}-{values_name}"

client = docker.from_env()
script_dir = str(Path(__file__).parent.resolve())

hostname = socket.gethostname()

XTRABACKUP_IMAGE = "docker.getcompass.ru/backend_compass/xtrabackup"
XTRABACKUP_VERSION = "8.0.28-21"
NEED_APP_VERSION = "4.1.0"


# класс конфига пространства
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str,
                 backup_user: str, backup_password: str, db_path: str, backup_path: str, driver: str,
                 container_name: str) -> None:
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
        self.driver = driver
        self.container_name = container_name


# точка входа в скрипт бэкапа
def start():
    # получаем значения для выбранного окружения
    current_values = get_values()

    if backups_folder == "":
        backup_dir_str = "%s/backups" % current_values.get("root_mount_path")
    else:
        backup_dir_str = "%s" % backups_folder

    if not Path(backup_dir_str).exists():
        Path(backup_dir_str).mkdir(exist_ok=True, parents=True)

    # проверяем свободное место на диске
    check_disk_usage(backup_dir_str)

    # добавляем к префиксу stack-name также пометку сервиса, если такая имеется
    stack_name_monolith = stack_name_prefix + "-monolith"
    stack_name_domino = stack_name_prefix
    service_label = current_values.get("service_label") if current_values.get("service_label") else ""
    if service_label != "":
        stack_name_monolith = stack_name_monolith + "-" + service_label
        stack_name_domino = stack_name_domino + "-" + service_label

    if current_values["database_connection"]["driver"] != "host":
        loader = Loader("Загружаем образ Percona Xtrabackup", "Загрузили образ Percona Xtrabackup").start()
        client.images.pull(repository=XTRABACKUP_IMAGE, tag=XTRABACKUP_VERSION)
        loader.success()

    backup_path_str = create_backup_folder(backup_dir_str)

    # начинаем бэкап конфигов
    if "production" in current_values["server_tag_list"] and need_backup_configs == 1:
        start_configs_backup(current_values, backup_path_str)

    # начинаем бэкап монолита
    start_monolith_backup(current_values, backup_path_str, stack_name_monolith)

    # начинаем бэкап пространств
    start_space_backup(current_values, backup_path_str, stack_name_domino)

    # выполняем автоматическую очистку старых бэкапов
    old_backups_auto_clean(backup_dir_str)


# создаём директорию бэкапа
def create_backup_folder(backup_dir_str: str):
    backup_name = datetime.today().strftime(backup_name_format)
    backup_full_path_str = "%s/%s" % (backup_dir_str, backup_name)

    # если бэкап с таким именем существует, то добавляем постфикс
    if Path(backup_dir_str).exists():

        max_counter = None
        for item in Path(backup_dir_str).iterdir():
            # ищем бэкапы с таким же именем
            if item.is_dir() and item.name.startswith(backup_name):
                if item.name == backup_name:
                    max_counter = max_counter if max_counter else 0
                else:
                    # пробуем получить номер после дефиса
                    try:
                        counter_num = int(item.name.split('-')[-1])
                        max_counter = max_counter if max_counter else 0
                        max_counter = max(max_counter, counter_num)
                    except ValueError:
                        continue

        if max_counter is not None:
            counter = max_counter + 1
            backup_full_path_str = f"{backup_full_path_str}-{counter}"

    Path(backup_full_path_str).mkdir(parents=True, exist_ok=True)
    return backup_full_path_str


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
def start_monolith_backup(current_values: dict, backup_path_str: str, stack_name_monolith: str):
    if need_backup_monolith == 0:
        print(scriptutils.error("БД монолита не выбрана, как необходимая для бэкапа"))
        return

    monolith_backup_path_str = "%s/mysql" % backup_path_str
    Path(monolith_backup_path_str).mkdir(exist_ok=True, parents=True)

    db_host = current_values["database_connection"]["driver_data"]["project_mysql_hosts"]["monolith"]["host"] if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["host"]

    db_port = current_values["database_connection"]["driver_data"]["project_mysql_hosts"]["monolith"]["port"] if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["port"]

    db_root_user = "root" if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["user"]

    db_root_password = current_values["database_connection"]["driver_data"]["project_mysql_hosts"]["monolith"][
        "root_password"] if \
        current_values["database_connection"]["driver"] == "host" else \
        current_values["projects"]["monolith"]["service"]["mysql"]["password"]

    monolith = DbConfig(
        "",
        0,
        db_host,
        db_port,
        db_root_user,
        db_root_password,
        current_values["backup_user"],
        current_values["backup_user_password"],
        "%s/monolith/database" % current_values["root_mount_path"],
        monolith_backup_path_str,
        current_values["database_connection"]["driver"],
        "%s_mysql-monolith" % stack_name_monolith
    )

    backup_db_list([monolith], backup_path_str)


# запускаем бэкап пространств
def start_space_backup(current_values: dict, backup_path_str: str, stack_name_domino: str):
    if need_backup_spaces == 0:
        print(scriptutils.error("БД пространств не выбраны, как необходимые для бэкапа"))
        return

    # формируем список активных пространств
    space_config_obj_dict = get_space_dict(current_values, backup_path_str, stack_name_domino)

    if len(space_config_obj_dict) < 1:
        scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

    allowed_id_list = set(input_space_list) if input_space_list else None

    need_backup_space_obj_list = []

    # формируем список пространств для бэкапа
    for space_id, space_config_obj in space_config_obj_dict.items():

        if allowed_id_list is None or space_id in allowed_id_list:
            need_backup_space_obj_list.append(space_config_obj)

    # начинаем бэкап пространств
    backup_db_list(need_backup_space_obj_list, backup_path_str)


# формируем бэкапы для выбранных пространств
def backup_db_list(db_list: list[DbConfig], backup_path_str: str):
    # для каждого пространства выполняем бэкап и его архивирование
    for db in db_list:
        db_container = prepare_db(db)

        try:
            header = f"#----- ПРОСТРАНСТВО {db.space_id or 'MONOLITH'} -----#"
            print(scriptutils.warning(header))

            if db.driver == "host":
                # бэкапим с помощью mysqlsh
                backup_with_mysqlsh(db)
            else:
                # бэкапим через контейнер XtraBackup
                run_xtrabackup_container(db, db_container)

            loader = Loader("Архивируем бэкап...", "Архив с бэкапом готов", "Не смогли заархивировать бэкап").start()
            db_archive_path = archive_backup(db)
            loader.success()
            print(scriptutils.warning("Путь до архива бэкапа: %s" % db_archive_path))

            if db.space_id > 0:
                control_data = {"space_backups": {
                    "%s::%s" % (db.domino_id, db.space_id): os.path.basename(os.path.normpath(db_archive_path))}}
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
def prepare_db(db: DbConfig) -> docker.models.containers.Container | None:
    if db.driver == "host":
        try:
            conn = mysql.connector.connect(
                host=db.host,
                port=db.port,
                user=db.root_user,
                password=db.root_password,
            )
            cursor = conn.cursor()
            # несколько отдельных команд, чтобы корректно сработал FLUSH PRIVILEGES
            stmts = [
                f"CREATE USER IF NOT EXISTS '{db.backup_user}'@'%'"
                f" IDENTIFIED WITH mysql_native_password BY '{db.backup_password}'",
                f"GRANT RELOAD, BACKUP_ADMIN, LOCK TABLES, REPLICATION CLIENT,"
                f" CREATE TABLESPACE, PROCESS, SUPER, CREATE, INSERT, SELECT"
                f" ON *.* TO '{db.backup_user}'@'%'",
                "FLUSH PRIVILEGES"
            ]
            for sql in stmts:
                cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(err)
            scriptutils.die(
                f"Не удалось создать backup-пользователя на хосте для пространства {db.space_id}"
            )
        return None

    container_list = client.containers.list(filters={"name": db.container_name})
    if len(container_list) < 1:
        scriptutils.die(
            "Пространство %d не имеет рабочего контейнера, хотя отмечена как активная. Проверьте корректность поднятого окружения." % db.space_id)

    space_container: docker.models.containers.Container = container_list[0]

    # создаем временного пользователя в БД, от имени которого будет проводиться бэкап
    mysql_command = "CREATE USER IF NOT EXISTS '%s'@'%%' IDENTIFIED WITH mysql_native_password BY '%s';" % (
        db.backup_user, db.backup_password) + \
                    "GRANT RELOAD, BACKUP_ADMIN, LOCK TABLES, REPLICATION CLIENT, CREATE TABLESPACE, PROCESS, SUPER, CREATE, INSERT, SELECT ON * . * TO '%s'@'%%';" % db.backup_user + \
                    "FLUSH PRIVILEGES;"

    cmd = "mysql -h %s -u %s -p%s -e \"%s\"" % ("localhost", db.root_user, db.root_password, mysql_command)
    result = space_container.exec_run(cmd=cmd)

    if result.exit_code != 0:
        print(result.output)
        scriptutils.die("Не смогли создать mysql пользователя для бэкапа в пространстве %d" % db.space_id)

    return space_container


# действия, необходимые совершить после бэкапа
def finish_backup(db_container: docker.models.containers.Container | None, db: DbConfig):
    drop_stmts = [
        f"DROP USER '{db.backup_user}'@'%'",
        "FLUSH PRIVILEGES"
    ]

    if db.driver == "host":
        try:
            conn = mysql.connector.connect(
                host=db.host,
                port=db.port,
                user=db.root_user,
                password=db.root_password,
            )
            cursor = conn.cursor()
            for sql in drop_stmts:
                cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(err)
            scriptutils.die(
                f"Не удалось удалить backup-пользователя на хосте для пространства {db.space_id}"
            )
    else:
        drop_sql = "; ".join(drop_stmts)
        result = db_container.exec_run(
            cmd=f'mysql -h localhost -u {db.root_user} -p{db.root_password} -e "{drop_sql}"'
        )
        if result.exit_code != 0:
            scriptutils.die("Не смогли удалить mysql пользователя для бэкапа в пространстве %d" % db.space_id)


def backup_with_mysqlsh(db: DbConfig) -> None:
    backup_dir = db.backup_path

    # на всякий случай создаём папку
    Path(backup_dir).mkdir(parents=True, exist_ok=True)

    cpu_count = os.cpu_count() or 1
    threads = max(1, ceil(cpu_count * 0.3))

    mysqlsh_cmd = [
        "mysqlsh",
        f"--user={db.root_user}",
        f"--password={db.root_password}",
        f"--host={db.host}",
        f"--port={db.port}",
        "--js",
        "-e",
        f"util.dumpInstance('{backup_dir}', {{threads: {threads}}})"
    ]
    loader = Loader("Создаем бэкап...", "Создали бэкап", "Не смогли создать бэкап").start()

    try:
        subprocess.run(mysqlsh_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        loader.success()
    except subprocess.CalledProcessError as e:
        loader.error()
        print(e.stderr)
        print(scriptutils.error("Не смогли выполнить бэкап"))
        raise e


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
    if db_container.attrs.get("NetworkSettings") is None or len(
            db_container.attrs["NetworkSettings"].get("Networks")) < 1:
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
        scriptutils.die(
            "У контейнера mysql нет сети, к которой можно подключить контейнер xtrabackup. Обновите приложение Compass до версии %s" % NEED_APP_VERSION)

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
                  "--password=\"%s\"" % db_config_obj.backup_password,
                  "&&",
                  "xtrabackup",
                  "--prepare",
                  "--target-dir=/backup_data",
                  ])]
    loader = Loader("Создаем бэкап...", "Создали бэкап", "Не смогли создать бэкап").start()

    # бэкапим пространство
    try:
        client.containers.run(
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
        option_list_str += "%s, " % space_id

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
def get_space_dict(current_values: dict, backup_path_str: str, stack_name_domino: str) -> dict[int: DbConfig]:
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
        f = open(space_config, "r")
        space_config_dict = json.loads(f.read())
        f.close()
        if space_config_dict["status"] not in [1, 2]:
            continue

        db_root_password = \
            current_values["database_connection"]["driver_data"]["company_mysql_hosts"][int(space_id) - 1][
                "root_password"] if \
                current_values["database_connection"]["driver"] == "host" else \
                "root"

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            domino_id,
            int(space_id),
            space_config_dict["mysql"]["host"],
            space_config_dict["mysql"]["port"],
            "root",
            db_root_password,
            current_values["backup_user"],
            current_values["backup_user_password"],
            get_space_data_dir_path(current_values, domino_id, space_id),
            get_space_backup_dir_path(space_id, backup_path_str),
            current_values["database_connection"]["driver"],
            "%s-%s-company_mysql-%d" % (stack_name_domino, domino_id, space_config_dict["mysql"]["port"])
        )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
    return space_config_obj_dict


# получить данные окружение из values
def get_values() -> dict:
    default_values_file_path = Path("%s/../src/values.yaml" % script_dir)
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


# проверка свободного места на диске
def check_disk_usage(backup_dir_str: str):
    total, used, free = shutil.disk_usage(backup_dir_str)
    free_percent = round(free / total * 100)
    if threshold_percent > 0 and free_percent < threshold_percent:
        print(scriptutils.warning("Свободное место на диске превышает указанный порог для создания бэкапа."))
        print(f"(свободное место: {free_percent}%, указанный порог для создания бэкапа: {threshold_percent}%)")

        scriptutils.die(f"Прервано создание бэкапа с указанным порогом свободного места.")


# автоматическая очистка старых бэкапов
def old_backups_auto_clean(backup_dir_str: str):
    if auto_cleaning_limit <= 0:
        return

    # считаем сколько у нас папок с бэкапами
    backups_list = []
    backups_folders_count = 0
    with os.scandir(backup_dir_str) as entries:
        for entry in entries:

            if not entry.is_dir():
                continue

            backups_folders_count += 1

            try:
                backups_list.append((entry, entry.stat().st_mtime))
            except ValueError as e:
                try:
                    current_name = '-'.join(entry.name.split('-')[:-1])
                    backups_list.append((entry, entry.stat().st_mtime))
                except ValueError as e:
                    continue

    # проверяем, что требуется очистка
    if backups_folders_count > 0 and backups_folders_count > auto_cleaning_limit:

        # сортируем по дате (от старых к новым)
        backups_list.sort(key=lambda x: x[1])

        current_time = datetime.now()
        delete_count = 0

        for folder_path, folder_created_at in backups_list:

            if len(backups_list) - delete_count <= auto_cleaning_limit:
                break

            # удаляем старые бэкапы
            age_seconds = current_time.timestamp() - folder_created_at
            age_days = int(age_seconds / (24 * 3600))
            delete_text = f"Автоматически удален старый бэкап: {folder_path.name} ({age_days} дней)"
            try:
                shutil.rmtree(folder_path)
                delete_count += 1
                print(delete_text)
            except Exception as e:
                print(f"Ошибка удаления {folder_path.name}: {e}")

            message_text = f"*{hostname}*: {userbot_notice_text if userbot_notice_text.strip() else delete_text}"
            scriptutils.send_userbot_notice(userbot_notice_token, userbot_notice_chat_id, userbot_notice_domain,
                                            message_text)


# точка входа в скрипт
try:
    start()
except Exception as e:
    message_text = f"*{hostname}*: {userbot_notice_text if userbot_notice_text.strip() else 'Ошибка при создании бэкапа на сервере!'}"
    scriptutils.send_userbot_notice(userbot_notice_token, userbot_notice_chat_id, userbot_notice_domain, message_text)
    raise
except SystemExit as e:
    message_text = f"*{hostname}*: {userbot_notice_text if userbot_notice_text.strip() else 'Ошибка при создании бэкапа на сервере!'}"
    scriptutils.send_userbot_notice(userbot_notice_token, userbot_notice_chat_id, userbot_notice_domain, message_text)
    raise
