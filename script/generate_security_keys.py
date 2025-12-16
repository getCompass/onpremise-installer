#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True
import string, random, yaml
from pathlib import Path
import collections.abc, argparse
from OpenSSL import crypto
from loader import Loader

from utils import scriptutils

script_dir = str(Path(__file__).parent.resolve())

parser = scriptutils.create_parser(
    description="Скрипт для генерации секретных ключей.",
    usage="python3 script/generate_security_keys.py [-v VALUES] [-e ENVIRONMENT]",
    epilog="Пример: python3 script/generate_security_keys.py -v compass -e production",
)

parser.add_argument('-v', '--values', required=True, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=True, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
args = parser.parse_args()

values_name = args.values
environment = args.environment

# длина ключа
key_size = 32
rsa_key_size = 768

# проверяем, что запустили от рута
scriptutils.assert_root()


# класс для того, чтобы отличать значения в кавычках
class quoted(str):
    pass


# добавляем кавычки
def quoted_presenter(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")


# добавляем знак | многострочным значениям
def str_presenter(dumper, data):
    if data.count("\n") > 0:  # check for multiline string
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


yaml.add_representer(quoted, quoted_presenter)
yaml.add_representer(str, str_presenter)


def start():
    values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))

    if not values_file_path.exists():
        print(scriptutils.error("Отсутствует файл конфигурации, не можем сгенерировать ключ безопасности"))
        exit(1)

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    root_mount_path = current_values.get("root_mount_path")

    if (root_mount_path is None) or (not Path(root_mount_path).exists()):
        print(scriptutils.error(
            "Не найдена папка root_mount_path, куда развертывается приложение Compass. Запустите скрипт init.py"))
        exit(1)

    security_file_path = Path(root_mount_path + "/security.yaml")
    security_tpl_file_path = Path(script_dir + "/../yaml_template/security.tpl.yaml")

    # если файл уже существует
    if security_file_path.exists():
        loader = Loader(
            "Файл с секретами уже сгенерирован. Добавляем новые значения, если есть",
            "Добавлены новые ключи по следующему пути: %s"
            % str(security_file_path.resolve()),
        ).start()

        with security_tpl_file_path.open("r") as security_tpl_file_contents:
            security_tpl_values = yaml.safe_load(security_tpl_file_contents)

        with security_file_path.open("r") as security_file_contents:
            security_values = yaml.safe_load(security_file_contents)

        security_values = update_new_security_values_for_exists_file(security_tpl_values, security_values)
    else:
        loader = Loader(
            "Генерируем ключи безопасности для проекта",
            "Ключи безопасности сгенерированы по следующему пути: %s"
            % str(security_file_path.resolve()),
        ).start()
        with security_tpl_file_path.open("r") as security_tpl_file_contents:
            security_tpl_values = yaml.safe_load(security_tpl_file_contents)

        security_values = update_security_values(security_tpl_values)

    security_file_path.open("wt").write(
        yaml.dump(security_values, default_flow_style=False)
    )

    loader.success()


def update_security_values(security_tpl_values: dict, security_values: dict = {}):
    for k, v in security_tpl_values.items():
        if isinstance(v, collections.abc.Mapping):
            if k == "ssl_keys":
                security_values["ssl_keys"] = {}

                for ssl_k, _ in v.items():
                    pub, priv = generate_ssl_key_pair()
                    security_values["ssl_keys"][ssl_k] = {}
                    security_values["ssl_keys"][ssl_k]["public_key"] = pub
                    security_values["ssl_keys"][ssl_k]["private_key"] = priv
                continue

            if k == "replication":
                security_values["replication"] = {}

                current_user = security_values["replication"].get("mysql_user")
                if not current_user:
                    security_values["replication"]["mysql_user"] = quoted("replicator_" + generate_random_string(8))

                current_pass = security_values["replication"].get("mysql_pass")
                if not current_pass:
                    security_values["replication"]["mysql_pass"] = quoted(generate_random_string(key_size))
                continue

            security_values[k] = update_security_values(v, security_values.get(k, {}))
        else:
            security_values[k] = quoted(generate_random_string(key_size))

    return security_values


# обновляем новые значения для существующего файла
def update_new_security_values_for_exists_file(security_tpl_values: dict, security_values: dict = {}):
    for k, v in security_tpl_values.items():

        # если это сложная структура
        if isinstance(v, collections.abc.Mapping):

            # если это ssl ключи, то ничего с ними не делаем, оставляем как есть
            if k == "ssl_keys":
                continue

            if k == "replication":
                if "replication" not in security_values:
                    security_values["replication"] = {}

                current_user = security_values["replication"].get("mysql_user")
                if not current_user:
                    security_values["replication"]["mysql_user"] = quoted("replicator_" + generate_random_string(8))

                current_pass = security_values["replication"].get("mysql_pass")
                if not current_pass:
                    security_values["replication"]["mysql_pass"] = quoted(generate_random_string(key_size))
                continue

            # обновляем всю его вложенность
            security_values[k] = update_new_security_values_for_exists_file(v, security_values.get(k, {}))
        else:

            # если поле уже существует и оно не равняется дефолтному значению
            if k in security_values and security_values[k] != v:
                # оставляем его как есть
                security_values[k] = quoted(security_values[k])
                continue

            # иначе заполняем новым значением
            security_values[k] = quoted(generate_random_string(key_size))

    return security_values


def generate_random_string(size: int):
    characters = (string.ascii_letters + string.digits).translate(
        {
            ord('"'): None,
            ord("'"): None,
            ord("\\"): None,
            ord("`"): None,
            ord("$"): None,
            ord("-"): None,
            ord("="): None,
            ord("{"): None,
            ord("}"): None,
            ord("|"): None,
            ord("%"): None,
            ord("@"): None,
        }
    )
    generated_string = "".join(random.choice(characters) for i in range(size))

    return generated_string


def generate_ssl_key_pair():
    priv_key = crypto.PKey()
    priv_key.generate_key(crypto.TYPE_RSA, rsa_key_size)

    pub = crypto.dump_publickey(crypto.FILETYPE_PEM, priv_key).decode("utf-8")
    priv = crypto.dump_privatekey(crypto.FILETYPE_PEM, priv_key).decode("utf-8")

    return pub, priv


start()
