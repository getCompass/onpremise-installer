#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import yaml, argparse, os, json, glob, re
import subprocess
import docker
from time import sleep

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

# папка, где находятся конфиги
config_path = current_script_path.parent.parent / 'configs'

# если отсутствуют файлы-конфиги
if len(os.listdir(config_path)) == 0:
    print(
        scriptutils.warning(
            "Отсутствуют конфиг-файлы в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# --- если в global.protected.yaml есть поля - выходим, делать ничего не нужно ---

global_protected_config_path = str(config_path) + "/global.protected.yaml"
if not os.path.exists(global_protected_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл global.protected.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг уже содержит свежие поля
with open(global_protected_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "backup_user_password" in content:
        print(scriptutils.success("Конфиг-файл global.protected.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

values_file_path = Path('%s/../../src/values.%s.yaml' % (script_dir, values_arg))
if not values_file_path.exists():
    print(scriptutils.success("Конфиг-файл global.protected.yaml выглядит актуальным, миграция не требуется."))
    exit(0)

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

if current_values["database_connection"]["driver"] == "host":

    # обязательно уточняем установлен ли mysqlsh при использовании внешних баз данных
    print(
        scriptutils.warning(
            "!!!У вас используются внешние базы данных. Перед установкой обновления убедитесь, что на сервере с compass установлен mysqlsh по инструкции!!!\n"
        )
    )

    try:
        if input("Выполняем обновление приложения? [Y/n]\n").lower() != "y":
            scriptutils.die("Обновление приложения было отменено")
    except UnicodeDecodeError as e:
        print("Не смогли декодировать ответ. Error: ", e)
        exit(1)

# --- иначе генерируем пароль и кладем в global.protected.yaml ---

protected_config = {}
protected_config_path = Path(global_protected_config_path)
if protected_config_path.exists():
    with protected_config_path.open("r") as config_file:
        protected_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)
    protected_config.update(protected_config_values)

backup_user_password = scriptutils.generate_random_password(32)
backup_archive_password = scriptutils.generate_random_password(32)
protected_config["backup_user_password"] = backup_user_password
protected_config["backup_archive_password"] = backup_archive_password

with protected_config_path.open("w+t") as f:
    yaml.dump(protected_config, f, sort_keys=False)

backup_protected_config_path = Path(current_values.get("root_mount_path") + "/deploy_configs/global.protected.yaml")
with backup_protected_config_path.open("w+t") as f:
    yaml.dump(protected_config, f, sort_keys=False)

# экранированный пароль для SQL
backup_user_password_sql = backup_user_password.replace("'", "''")

# класс конфига пространства
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password


keys_list = list(current_values["projects"]["domino"].keys())
domino = current_values["projects"]["domino"][keys_list[0]]
space_config_dir = domino["company_config_dir"]
domino_id = domino["label"]

# если используются внутренние базы данных
if current_values["database_connection"]["driver"] != "host":

    # --- меняем пароль у каждой компании ---
    client = docker.from_env()

    timeout = 60
    n = 0
    while n <= timeout:

        # формируем список пространств
        # пространства выбираются по наличию их конфига
        space_config_obj_dict = {}
        space_id_list = []
        for space_config in glob.glob("%s/*_company.json" % space_config_dir):

            s = re.search(r'([0-9]+)_company', space_config)

            if s is None:
                continue

            space_id = s.group(1)
            with open(space_config, "r") as f:
                space_config_dict = json.loads(f.read())
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
        space_config_obj_dict = dict(sorted(space_config_obj_dict.items()))
        if len(space_config_obj_dict) > 0:
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die("Не найдено ни одного пространства на сервере. Окружение поднято?")

    for space_id, space_config_obj in space_config_obj_dict.items():
        found_container = scriptutils.find_container_mysql_container(
            client, scriptutils.TEAM_MYSQL_TYPE, domino_id, space_config_obj.port
        )
        mysql_host = "localhost"
        mysql_user = "root"
        mysql_pass = "root"

        def exec_sql(sql, parse_output=False):
            cmd = [
                "mysql",
                "-h", mysql_host,
                "-u", mysql_user,
                f"-p{mysql_pass}",
                "-Nse", sql
            ]
            try:
                # demux=True -> output: (stdout_bytes, stderr_bytes)
                result = found_container.exec_run(cmd, demux=True)
            except docker.errors.NotFound:
                print("\nНе нашли mysql контейнер для компании")
                return None

            if result.exit_code != 0:
                print(f"Не удалось сменить пароль backup_user в компании {space_id}, driver: docker")
                out = b""
                if result.output:
                    out = (result.output[0] or b"") + (result.output[1] or b"")
                if out:
                    print("Результат выполнения:\n", out.decode("utf-8", errors="ignore"))
                sys.exit(result.exit_code)

            if parse_output:
                stdout = (result.output[0] or b"").decode("utf-8", errors="ignore").strip()
                return stdout
            return None

        exists_backup_user_on_127 = int(exec_sql(
            "SELECT COUNT(*) FROM mysql.user WHERE user='backup_user' AND host='127.0.0.1';",
            parse_output=True
        ) or "0")

        # только меняем пароль у 127.0.0.1
        if exists_backup_user_on_127 > 0:
            exec_sql(f"ALTER USER 'backup_user'@'127.0.0.1' IDENTIFIED BY '{backup_user_password_sql}';")
        else:
            exists_backup_user_on_localhost = int(exec_sql(
                "SELECT COUNT(*) FROM mysql.user WHERE user='backup_user' AND host='localhost';",
                parse_output=True
            ) or "0")

            if exists_backup_user_on_localhost > 0:
                # переносим localhost -> 127.0.0.1 и меняем пароль
                exec_sql("RENAME USER 'backup_user'@'localhost' TO 'backup_user'@'127.0.0.1';")
                exec_sql(f"ALTER USER 'backup_user'@'127.0.0.1' IDENTIFIED BY '{backup_user_password_sql}';")
            else:
                exec_sql(f"CREATE USER 'backup_user'@'127.0.0.1' IDENTIFIED BY '{backup_user_password_sql}';")
    exit(0)

# --- меняем пароль у каждой компании ---

# формируем список пространств
# пространства выбираются по наличию их конфига
for space_config in glob.glob("%s/*_company.json" % space_config_dir):
    s = re.search(r'([0-9]+)_company', space_config)
    if s is None:
        continue

    space_id = s.group(1)
    with open(space_config, "r") as f:
        space_config_dict = json.loads(f.read())
    if space_config_dict["status"] not in [1, 2]:
        continue

    company_db_host = space_config_dict["mysql"]["host"]
    company_db_port = space_config_dict["mysql"]["port"]
    company_db_root_password = \
        current_values["database_connection"]["driver_data"]["company_mysql_hosts"][int(space_id) - 1][
            "root_password"]

    def run_mysqlsh(sql, parse_output=False):

        proc = subprocess.run([
            "mysqlsh",
            "--user=root",
            f"--password={company_db_root_password}",
            f"--host={company_db_host}",
            f"--port={company_db_port}",
            "--sql",
            "-e",
            sql
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        if parse_output:
            m = re.search(r'(\d+)\s*$', proc.stdout.strip())
            return m.group(1) if m else "0"
        return None

    try:
        exists_backup_user_on_127 = int(run_mysqlsh(
            "SELECT COUNT(*) FROM mysql.user WHERE user='backup_user' AND host='127.0.0.1';",
            parse_output=True
        ) or "0")

        if exists_backup_user_on_127 > 0:
            # только меняем пароль у 127.0.0.1
            run_mysqlsh(f"ALTER USER 'backup_user'@'127.0.0.1' IDENTIFIED BY '{backup_user_password_sql}';")
        else:
            exists_backup_user_on_localhost = int(run_mysqlsh(
                "SELECT COUNT(*) FROM mysql.user WHERE user='backup_user' AND host='localhost';",
                parse_output=True
            ) or "0")

            # переносим localhost -> 127.0.0.1 и меняем пароль
            if exists_backup_user_on_localhost > 0:
                run_mysqlsh("RENAME USER 'backup_user'@'localhost' TO 'backup_user'@'127.0.0.1';")
                run_mysqlsh(f"ALTER USER 'backup_user'@'127.0.0.1' IDENTIFIED BY '{backup_user_password_sql}';")
            else:
                run_mysqlsh(f"CREATE USER 'backup_user'@'127.0.0.1' IDENTIFIED BY '{backup_user_password_sql}';")

    except subprocess.CalledProcessError as e:
        print(e.stderr)
        print(scriptutils.error(f"Не удалось сменить пароль backup_user в компании {space_id}, driver: host"))
        raise e
