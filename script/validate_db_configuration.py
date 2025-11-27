#!/usr/bin/env python3

import argparse
from pathlib import Path

import docker
import docker.errors
import functools
import mysql.connector
import mysql.connector.errorcode
import yaml

from utils import scriptutils

# region АГРУМЕНТЫ СКРИПТА #
parser = argparse.ArgumentParser(add_help=True)
parser.add_argument("--validate-only", required=False, action="store_true")
parser.add_argument("--installer-output", required=False, action="store_true")
args = parser.parse_args()

script_dir = str(Path(__file__).parent.resolve())
root_path = str(Path(script_dir + "/../").resolve())

validate_only = args.validate_only
installer_output = args.installer_output

QUIET = (validate_only and installer_output)


def log(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)


# проверяем конфигурационный файл с глобальными параметрами
config_path = Path(script_dir + "/../configs/global.yaml")

if not config_path.exists():
    scriptutils.die(
        f"Отсутствует файл конфигурации {str(config_path.resolve())}. " +
        f"Запустите скрипт create_configs.py и заполните конфигурацию"
    )

# загружаем конфигурационный файл с глобальными параметрами
with config_path.open("r") as config_file:
    config: dict = yaml.load(config_file, Loader=yaml.BaseLoader)

# проверяем конфигурационный файл с глобальными параметрами
database_config_path = Path(script_dir + "/../configs/database.yaml")

if not database_config_path.exists():
    scriptutils.die(
        f"Отсутствует файл конфигурации {str(database_config_path.resolve())}. " +
        f"Запустите скрипт create_configs.py и заполните конфигурацию"
    )

try:
    # загружаем конфигурационный файл с параметрами БД
    with database_config_path.open("r") as database_config_file:
        database_config: dict = yaml.load(database_config_file, Loader=yaml.BaseLoader)
except:
    scriptutils.die("Не смогли прочитать конфигурацию %s. Поправьте её и запустите установку снова." % str(
        database_config_path.resolve()))

# известные базы данных, если используются predefined базы, нужно контролировать
# их изменение, чтобы приложение не начало смотреть куда-то не туда.
known_database_path = None
known_database_config = None

lock_file_rel_path = "deploy_configs/database.lock.yaml"

if config.get("root_mount_path") is not None:

    # загружаем конфиг c ранее объявленными настройками БД
    known_database_path = Path(config.get("root_mount_path") + "/" + lock_file_rel_path)

    if known_database_path.exists():
        with known_database_path.open("r") as known_database_file:
            known_database_config = yaml.load(known_database_file, Loader=yaml.BaseLoader)

# endregion АГРУМЕНТЫ СКРИПТА #

# известные виды драйверов
allowed_driver_list = ["docker", "host"]


class DBDriverConf:
    """Класс-экземпляра параметров драйвера подключения к БД"""

    def __init__(self, cnf: dict):
        self.known_instance_uniq_list = []
        self.cnf = cnf

    def try_conf(self):

        """Проверяет указанную конфигурацию БД"""
        driver = self.cnf.get("driver", None)

        # если драйвер не передан или неизвестен, считаем, что конфиг невалидный
        if driver is None or driver not in allowed_driver_list:
            return False, "Указан неподдерживаемый драйвер в параметрах подключения к БД"

        result = True
        message = ""

        # для хоста проверяем по правилам хоста
        if driver == "host":
            result, message = self._try_host(self.cnf.get("driver_data", None))

        # для докера проверяем по правилам докера
        if driver == "docker":
            result, message = self._try_docker(self.cnf.get("driver_data", None))

        if result is False:
            return False, message

        dupes = [x for n, x in enumerate(self.known_instance_uniq_list) if x in self.known_instance_uniq_list[:n]]
        if len(dupes) > 0:
            return False, "В конфигурации найдены дублирующиеся параметры подключения к БД: " + str(dupes)

        return True, ""

    def _try_docker(self, _: any):

        """Для конфигурации через докер нет ограничений"""
        return True, ""

    def _try_host(self, driver_data: any):

        """Проверяет настройку для подключения к хостовым БД"""
        if not isinstance(driver_data, dict):
            return False, "Неверный формат конфигурации для БД"

        projects_conf = driver_data.get("project_mysql_hosts", None)

        if projects_conf is None:
            return False, "Неверный формат конфигурации для БД"

        monolith_conf = driver_data.get("project_mysql_hosts", {}).get("monolith", None)
        company_conn_list = driver_data.get("company_mysql_hosts", None)

        if monolith_conf is None:
            project_check, message = self._try_multi_host(monolith_conf)
        else:
            project_check, message = self._try_monolith_host(projects_conf)

        if project_check is False:
            return False, message

        if company_conn_list is None or not isinstance(company_conn_list, list):
            return False, "Неверный формат конфигурации для БД"

        company_conn_count = 0

        for company_conn in company_conn_list:

            conn = DBConnConf(company_conn)
            result, message = conn.try_conf()

            if result is False:
                return False, message

            self.known_instance_uniq_list.append(conn.get_key())
            company_conn_count = company_conn_count + 1

        if company_conn_count <= 0 or company_conn_count > 15:
            return False, "Неверно указано число БД для команд"

        return True, ""

    def _try_monolith_host(self, projects_conf: any):

        """Проверяет подключения для БД монолита"""
        conn = DBConnConf(projects_conf.get("monolith", {}))
        result, message = conn.try_conf()

        if result is True:
            self.known_instance_uniq_list.append(conn.get_key())

        return result, message

    # noinspection PyMethodMayBeStatic
    def _try_multi_host(self, _: any):

        """Проверяет подключения для БД в рамках мультимодулей. Но сейчас такой реализации нет."""
        return False, "Not Implemented"

    def is_extender_for(self, existing: dict):

        """Сравнивает два конфига и определяет, является ли текущий расширением указанного"""


class DBConnConf:
    """Класс-экземпляра конфигурации подключения к БД"""

    def __init__(self, cnf: dict):
        self.cnf = cnf

    def try_conf(self):

        """Проверяет переданный набор настроек на валидность конфига подключения"""
        host = self.cnf.get("host", None)
        port = self.cnf.get("port", None)
        r_password = self.cnf.get("root_password", None)

        field_dict = {"host": host, "port": port, "root_password": r_password}

        # если какие-то из параметров не объявлены, то говорим, что конфиг невалидный
        if (host is None or host == "") or (port is None or port == "") or (r_password is None or r_password == ""):
            err_str = functools.reduce(
                lambda p, k: p + k + ", " if field_dict[k] is None or field_dict[k] == "" else p + "", field_dict, "")
            err_str = err_str[:-2]

            return False, f"В наборе присутствуют следующие некорректные значения для подключения к БД: {err_str}"

        # если данные имеют какой-то неправильный тип
        if not isinstance(host, str) or host == "" or not str(port).isnumeric():
            return False, f"Указан некорректный набор параметров для подключения к БД у следующего инстанса: {host}:{port}"

        # если база недоступна, значит ее использовать нельзя
        if not is_database_available(host, port, 'root', r_password):
            return False, f"Указанный инстанс MySQL в конфигурации недоступен: {host}:{port}"

        return True, ""

    def get_key(self) -> str:

        """Возвращает уникальный ключ-пару хост:порт"""
        return f"{self.cnf.get('host', None)}:{self.cnf.get('port', None)}"

    def get_uniq(self) -> str:

        """Возвращает уникальную строку подключения"""
        return f"{self.cnf.get('host', None)}:{self.cnf.get('port', None)}:{self.cnf.get('root_password', None)}"


class DBConfComparer:
    """Класс, проверяющий, является ли новый конфиг расширение имеющегося"""

    def __init__(self, passed: DBDriverConf, existing: DBDriverConf):
        self.passed = passed
        self.existing = existing

    def compare(self):

        """Сравнивает два блока конфигурации БД"""
        if self.passed.cnf.get("driver") != self.existing.cnf.get("driver"):
            return False, "Не совпадает драйвер БД в новой и имеющейся конфигурации"

        # для докера больше не делаем проверок
        if self.passed.cnf.get("driver") == "docker":
            return True, ""

        # получаем список БД для переданных параметров
        passed_driver_data = self.passed.cnf.get("driver_data")
        passed_monolith_conf = passed_driver_data.get("project_mysql_hosts", {}).get("monolith", None)

        if passed_monolith_conf is not None:

            result, message = self._compare_monolith()
            if result is False:
                return result, message

        return self._compare_companies()

    def _compare_monolith(self):

        """Сравниваем параметры подключения для монолита"""

        existing_driver_data = self.existing.cnf.get("driver_data", None)
        existing_monolith_conf = existing_driver_data.get("project_mysql_hosts", {}).get("monolith", None)

        # если в имеющемся конфигурационном файле нет параметров для монолита, то
        # считаем, что валидация пройдена, поскольку новый конфиг добавит поля
        if existing_monolith_conf is None:
            return True, ""

        passed_driver_data = self.passed.cnf.get("driver_data", None)
        passed_monolith_conf = passed_driver_data.get("project_mysql_hosts", {}).get("monolith", None)

        if DBConnConf(passed_monolith_conf).get_uniq() != DBConnConf(existing_monolith_conf).get_uniq():
            return False, "Не совпадает конфигурация БД в новой и имеющейся конфигурации для проекта monolith"

        return True, ""

    def _compare_companies(self):

        """Сравниваем параметры подключения для компаний"""

        existing_driver_data = self.existing.cnf.get("driver_data")
        existing_company_conn_list = existing_driver_data.get("company_mysql_hosts", None)

        # если в имеющемся конфигурационном файле нет параметров для компаний, то
        # считаем, что валидация пройден, поскольку новый конфиг добавит поля
        if existing_company_conn_list is None or len(existing_company_conn_list) == 0:
            return True, ""

        passed_driver_data = self.passed.cnf.get("driver_data")
        passed_company_conn_list = passed_driver_data.get("company_mysql_hosts", None)

        passed_uniq_list = {}

        for passed_company_conn in passed_company_conn_list:
            passed_uniq_list[DBConnConf(passed_company_conn).get_uniq()] = True

        for existing_company_conn in existing_company_conn_list:

            uniq = DBConnConf(existing_company_conn).get_uniq()
            if passed_uniq_list.get(uniq, None) is None:
                return False, f"Новая конфигурация БД команды не содержит уже имеющееся подключение {uniq}"

        return True, ""


def is_database_available(host: str, port: str, user: str, password: str) -> bool:
    """Проверить доступность базы данных"""

    try:
        db = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            connection_timeout=2
        )
        db.close()
    except mysql.connector.Error:
        return False

    return True


# известные режимы работы шифрования БД
allowed_encrypt_mode_list = ["none", "read_write", "read"]


class EncryptDBConf:
    """Класс-экземпляра параметров шифрования БД"""

    def __init__(self, cnf: dict):

        self.known_instance_uniq_list = []
        self.cnf = cnf

        if self.cnf.get("use_encryption", None) is None:

            if self.cnf.get("mode", None) == "none":
                self.cnf["use_encryption"] = False
            else:
                self.cnf["use_encryption"] = True
        elif self.cnf.get("use_encryption", None) == "true" or self.cnf.get("use_encryption", None) is True:
            self.cnf["use_encryption"] = True
        else:
            self.cnf["use_encryption"] = False

    def try_conf(self):

        """Проверяет конфиг на валидность"""

        # проверяем, что режим работы указан верно
        mode = self.cnf.get("mode", None)
        if mode is None or mode not in allowed_encrypt_mode_list:
            return False, "Указан неверный параметр «mode» конфигурации шифрования БД."

        use_encryption = self.cnf.get("use_encryption", None)
        if use_encryption is None:
            return False, "Неверная конфигурация шифрования БД."

        # при режиме none никаких дополнительных проверок не нужно проводить,
        # несовместимость с ранее включенным write/read дальше проверится
        if mode == "none":
            return True, ""

        # проверим, что мастер ключ на месте
        master_key = self.cnf.get("master_key", None)
        if master_key is None or master_key == "":
            return False, f"Мастер ключ конфигурации шифрования БД должен быть указан при включенном шифровании БД."

        client = docker.from_env()

        try:
            # проверяем наличие существующего секрета
            existing = client.secrets.get("compass_database_encryption_secret_key")
        except docker.errors.NotFound:
            return False, f"Docker-секрет «compass_database_encryption_secret_key» с ключом секретом должен существовать при включенном шифровании БД."

        return True, ""


class EncryptConfComparer:
    """Класс, проверяющий, совместим ли новый конфиг шифрования с имеющимся"""

    def __init__(self, passed: EncryptDBConf, existing: EncryptDBConf):
        self.passed = passed
        self.existing = existing

    def compare(self):
        """Проверяет две конфигурации на совместимость"""

        if self.existing.cnf.get("use_encryption") is True and self.passed.cnf.get("use_encryption") is False:
            return False, "Необходимо включить шифрование БД — ранее использовалась конфигурация с шифрованием."

        return True, ""


def write_known_database_config(cfg: dict):
    """Записывает конфигурацию БД в файл известных конфигураций"""

    if validate_only:
        return

    if known_database_path is None:
        raise FileNotFoundError("Не найден путь для записи конфигурации БД")

    with open(known_database_path, "w") as outfile:
        yaml.dump(cfg, outfile)


def compare_database_config(passed: dict, known: dict):
    """Сравнивает две конфигурации подключения к БД"""

    db_conf = passed.get("database_connection", None)
    if db_conf is None:
        scriptutils.die("Не найден блок параметров подключения к БД")

    db_driver_conf = DBDriverConf(db_conf)
    result, msg = db_driver_conf.try_conf()
    if result is False:
        scriptutils.die(msg)

    if known is None:
        return

    # небольшой костылик, при первом релизе поля лежали просто
    # в файле, не внутри объекта database_connection
    known_db_conf = known.get("database_connection", None)
    if known_db_conf is None:
        known_db_conf = known

    result, msg = DBConfComparer(db_driver_conf, DBDriverConf(known_db_conf)).compare()
    if result is False:
        scriptutils.die(msg)


def compare_encryption_config(passed: dict, known: dict):
    """Сравнивает две конфигурации шифрования БД"""

    db_conf = passed.get("database_encryption", None)
    if db_conf is None:
        scriptutils.die("Не найден блок параметров шифрования БД")

    db_driver_conf = EncryptDBConf(db_conf)
    result, msg = db_driver_conf.try_conf()
    if result is False:
        scriptutils.die(msg)

    if known is None:
        return

    # если в имеющемся конфигу нет блока с шифрованием бд
    # (такое будет при первом обновлении), то заканчиваем
    known_db_conf = known.get("database_encryption", None)
    if known_db_conf is None:
        return

    result, msg = EncryptConfComparer(db_driver_conf, EncryptDBConf(known_db_conf)).compare()
    if result is False:
        scriptutils.die(msg)


def start():
    # сравниваем текущую и имеющуюся конфигурации
    compare_database_config(database_config, known_database_config)
    compare_encryption_config(database_config, known_database_config)

    # записываем новую конфигурацию
    write_known_database_config(database_config)
    return


start()
log(scriptutils.success("Проверка конфигурации БД прошла успешно"))
