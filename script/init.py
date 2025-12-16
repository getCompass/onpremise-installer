#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
from utils import scriptutils
import collections.abc
import socket, yaml, argparse, string, random, pwd, os, json
from utils.interactive import InteractiveValue, IncorrectValueException
import uuid
from base64 import b64encode

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиги
config_path = Path(script_dir + "/../configs/global.yaml")
database_config_path = Path(script_dir + "/../configs/database.yaml")
replication_config_path = Path(script_dir + "/../configs/replication.yaml")
team_config_path = Path(script_dir + "/../configs/team.yaml")
dlp_config_path = Path(script_dir + "/../configs/dlp.yaml")

validation_errors = {}
config_path_errors = []

config = {}
protected_config = {}
database_config = {}
replication_config = {}
team_config = {}
dlp_config = {}

if not config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию" % str(
            config_path.resolve())))
    exit(1)

if not database_config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию" % str(
            database_config_path.resolve())))
    exit(1)

if not replication_config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию" % str(
            replication_config_path.resolve())))
    exit(1)

if not team_config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию" % str(
            team_config_path.resolve())))
    exit(1)

if not dlp_config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию" % str(
            dlp_config_path.resolve())))
    exit(1)
with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

with database_config_path.open("r") as database_config_file:
    database_config_values = yaml.load(database_config_file, Loader=yaml.BaseLoader)

with replication_config_path.open("r") as replication_config_file:
    replication_config_values = yaml.load(replication_config_file, Loader=yaml.BaseLoader)

with team_config_path.open("r") as team_config_file:
    team_config_values = yaml.load(team_config_file, Loader=yaml.BaseLoader)

with dlp_config_path.open("r") as dlp_config_file:
    dlp_config_values = yaml.load(dlp_config_file, Loader=yaml.BaseLoader)

config.update(config_values)
config.update(team_config_values)
dlp_config.update(dlp_config_values)
database_config.update(database_config_values)
replication_config.update(replication_config_values)
team_config.update(team_config_values)

protected_config_path = Path(script_dir + "/../configs/global.protected.yaml")

if (config.get("root_mount_path") is not None) and Path(
        config.get("root_mount_path") + "/deploy_configs/global.protected.yaml").exists():
    protected_config_path = Path(config.get("root_mount_path") + "/deploy_configs/global.protected.yaml")

if protected_config_path.exists():
    with protected_config_path.open("r") as config_file:
        protected_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

    protected_config.update(protected_config_values)

domino_template_subdomain = "c{company_id}-{domino_url}"
domino_template_path = "{domino_url}/{company_id}"

deploy_project_list = [
    "monolith",
    "pivot",
    "userbot",
    "domino",
    "file",
    "announcement",
    "federation",
    "join_web",
    "integration",
    "jitsi_web",
    "jitsi",
    "license",
]

deploy_saas_project_list = [
    "intercom",
    "test",
    "analytic",
]

nested_project_list = ["file", "domino"]

project_ports = {
    "pivot": 31000,
    "analytic": 31600,
    "userbot": 31200,
    "domino": 31100,
    "file": 31300,
    "announcement": 31500,
    "federation": 32400,
    "join_web": 31900,
    "monolith": 32100,
    "intercom": 32200,
    "test": 32300,
    "integration": 32500,
    "jitsi_web": 32600,
    "license": 32700,
}

domino_ports = {
    "go_database_controller_port": 31101,
    "service.manticore.external_port": 31102,
}

jitsi_ports = {
    "service.web.https_port": 35000,
    "service.jvb.media_port": 10000,
    "service.jicofo.port": 35001,
    "service.prosody.serve_port": 35002,
    "service.prosody.v0.serve_port": 35003,
    "service.prosody.v1.serve_port": 35004,
    "service.prosody.v2.serve_port": 35005,
}

database_driver_data_fields = {
    "predefined": ["database_definition_path"],
    "docker": [],
}

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для генерации values.",
    usage="python3 script/init.py [-v VALUES] [-p PROJECT] [-e ENVIRONMENT] [--project-name-override PROJECT_NAME_OVERRIDE] [--use-default-values] [--install-integration] [--validate-only] [--installer-output]",
    epilog="Пример: python3 script/init.py -v compass -p monolith -e production --project-name-override public --use-default-values --install-integration --validate-only --installer-output",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument(
    "-p", "--project", required=False, type=str, help="Название проекта, который разворачиваем (например: monolith)"
)
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument("--project-name-override", required=False, type=str, help="Название для перезаписи имени проекта")
parser.add_argument("--use-default-values", required=False, action='store_true',
                    help="Использовать значения из дефолтного values.yaml")
parser.add_argument("--install-integration", required=False, action='store_true',
                    help="Установка модуля интеграций с внешним сервисом")
parser.add_argument("--validate-only", required=False, action="store_true",
                    help='Запуск скрипта в режиме read-only, без применения изменений')
parser.add_argument("--installer-output", required=False, action="store_true",
                    help='Вывод ошибок в формате JSON')
args = parser.parse_args()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#


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

values_name = args.values
project = args.project
environment = args.environment
use_default_values = args.use_default_values
validate_only = args.validate_only
installer_output = args.installer_output
install_integration = args.install_integration
project_name_override = (
    args.project_name_override if args.project_name_override is not False else ""
)

values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))

default_values_file_path = Path("%s/../src/values.yaml" % (script_dir))

if values_file_path.exists():
    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

else:
    current_values = {}

if default_values_file_path.exists():
    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

else:
    default_values = {}

hostname = socket.gethostname()
local_ip = socket.gethostbyname(hostname)
unique_dict = {}


def deep_get(dictionary: dict, keys: str, default={}):
    keys = keys.split(".")
    my_dict = dictionary.get(keys[0], default)

    if len(keys) > 1:
        for key in keys[1:]:
            my_dict = my_dict.get(key, default)

    return my_dict


def nested_set(dic, keys, value, create_missing=True):
    keys = keys.split(".")
    d = dic
    for key in keys[:-1]:
        if key in d:
            d = d[key]
        elif create_missing:
            d = d.setdefault(key, {})
        else:
            return dic
    if keys[-1] in d or create_missing:
        d[keys[-1]] = value
    return dic


def handle_exception(field: str, message: str, config_path: str):
    if validate_only:
        if installer_output:
            if validation_errors.get(config_path) is None:
                validation_errors[config_path] = []

            validation_errors[config_path].append(field)
        else:
            if validation_errors.get(config_path) is None:
                validation_errors[config_path] = []

            validation_errors[config_path].append(message)
        return

    print(message)
    exit(1)


### VALUE FUNCTIONS ###

def server_uid(
        project_name: str, label: str, project_values: dict, global_values: dict
):
    return str(uuid.uuid4())


def project_port(
        project_name: str, label: str, project_values: dict, global_values: dict
) -> int:
    return project_ports[project_name]


def get_domino_template(
        project_name: str, label: str, project_values: dict, global_values: dict
) -> str:
    subdomain_enabled = global_values.get("subdomain_enabled")
    ''
    if bool(subdomain_enabled):
        return domino_template_subdomain

    return domino_template_path


def random_string(
        project_name: str, label: str, project_values: dict, global_values: dict, size: int
) -> int:
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
    return "".join(random.choice(characters) for i in range(size))


# генерируем пароль длиной size, содержащий минимум:
# - 1 цифру
# - 1 строчную букву
# - 1 прописную букву
# - 1 спецсимвол
def random_password(
        project_name: str, label: str, project_values: dict, global_values: dict, size: int
) -> str:
    return scriptutils.generate_random_password(size)


def get_subnet_number(subnet_mask: str) -> int:
    for part in subnet_mask.split():
        address, network = part.split("/")
        a, b, c, d = address.split(".")
    return c


def get_free_subnet(
        project_name: str, label: str, project_values: dict, global_values: dict
) -> int:
    min_subnet_number = global_values["start_octet"] + 1
    max_subnet_number = 254

    subnet_mask = "172.39.%s.0/24"

    if current_values.get("projects") is None:
        return subnet_mask % min_subnet_number

    occupied_subnet_number_list = []

    for project, project_values in current_values["projects"].items():
        if project in nested_project_list:
            for nested_project, nested_project_values in project_values.items():
                if not isinstance(nested_project_values, collections.abc.Mapping):
                    continue
                project_subnet = deep_get(nested_project_values, "network.subnet")

                if project_subnet != {}:
                    break
        else:
            project_subnet = deep_get(project_values, "network.subnet")

        if project_subnet != {}:
            occupied_subnet_number_list.append(int(get_subnet_number(project_subnet)))

    s = set(occupied_subnet_number_list)
    free_subnet_number_list = [
        x for x in [*range(min_subnet_number, max_subnet_number)] if x not in s
    ]

    return subnet_mask % min(free_subnet_number_list)


def copy(
        project_name: str, label: str, project_values: dict, global_values: dict, keys: str
):
    keys = keys.split(".", 1)

    if keys[0] == "_project":
        return deep_get(project_values, ".".join(keys[1:]))
    else:
        return deep_get(global_values, ".".join(keys[1:]))


def secret_key(
        project_name: str, label: str, project_values: dict, global_values: dict, size: int
):
    return b64encode(os.urandom(size)).decode('utf-8')


def copy_with_postfix(
        project_name: str,
        label: str,
        project_values: dict,
        global_values: dict,
        keys: str,
        postfix: str,
):
    keys = keys.split(".", 1)

    if keys[0] == "_project":
        temp = deep_get(project_values, ".".join(keys[1:]))
        return (str(temp) if temp == {} else temp) + postfix
    else:
        temp = deep_get(global_values, ".".join(keys[1:]))
        return (str(temp) if temp == {} else temp) + postfix


def copy_with_custom_postfix(
        project_name: str,
        label: str,
        project_values: dict,
        global_values: dict,
        keys: str,
        postfix: str,
):
    keys = keys.split(".", 1)
    if keys[0] == "_project":
        temp = deep_get(project_values, ".".join(keys[1:]))
        return (str(temp) if temp == {} else temp) + "_" + postfix
    else:
        temp = deep_get(global_values, ".".join(keys[1:]))
        return (str(temp) if temp == {} else temp) + postfix


def get_project_name(
        project_name: str, label: str, project_values: dict, global_values: dict
):
    return label


def get_project_subdomain(
        project_name: str, label: str, project_values: dict, global_values: dict
):
    return label.replace("_", "-")


### END VALUE FUNCTIONS###
### POST FUNCTIONS ###
def create_dir(value: str, owner: str = None, mode: int = 0o755):
    path = Path(value)
    path.mkdir(exist_ok=True, parents=True)

    # проверяем, что указанный пользователь существует
    if owner is not None:
        try:
            user = pwd.getpwnam(owner)
            # проверяем существование UID и GID, если они есть
            if user.pw_uid is not None and user.pw_gid is not None:
                os.chown(str(path.resolve()), user.pw_uid, user.pw_gid)
        except KeyError:
            if scriptutils.is_rpm_os():
                print(f"Пользователь '{owner}' не существует, пропускаем смену владельца.")
            else:
                raise KeyError(f"Пользователь '{owner}' не существует и это не RPM.")

    os.chmod(str(path.resolve()), mode)

    return str(path.resolve())


def strtolower(value):
    if isinstance(value, str):
        return value.lower()

    if isinstance(value, list):
        output = []
        for item in value:
            output.append(str(item).lower())

        return output

    return None


def convert_idn(value: str):
    return value.strip().encode("idna").decode()


def onpremise_domain(
        project_name: str, label: str, project_values: dict, global_values: dict, _4=None
):
    return global_values.get("domain")


### END POST FUNCTIONS ###
### SKIP FUNCTIONS ###
def skip_subdomain(
        project_name: str, label: str, project_values: dict, global_values: dict, _4=None
):
    return not bool(global_values.get("subdomain_enabled"))


def skip_url_path(
        project_name: str, label: str, project_values: dict, global_values: dict, _4=None
):
    return bool(global_values.get("subdomain_enabled"))


### END SKIP FUNCTIONS ###
nginx_fields = [
    {
        "name": "ssl_key",
        "comment": "Укажите имя ключа для домена с расширением (example.key). Ключ должен быть помещен в папку /etc/nginx/ssl",
        "default_value": None,
        "type": "str",
        "ask": True,
    },

    {
        "name": "ssl_crt",
        "comment": "Укажите имя сертификата для домена с расширением (example.crt). Сертификат должен быть помещен в папку /etc/nginx/ssl",
        "default_value": None,
        "type": "str",
        "ask": True,
    },

    {
        "name": "directio_alignment",
        "comment": "Значение для nginx.directio_alignment",
        "default_value": 512,
        "type": "int",
        "ask": True,
    },
]

database_connection_fields = [
    {
        "name": "driver",
        "comment": "Укажите драйвер, с помощью которого будет выполняться подключение к базе (docker, host)",
        "default_value": "docker",
        "type": "str",
        "ask": True,
    },
    {
        "name": "driver_data",
        "comment": "Параметры драйвера подключения к БД",
        "default_value": None,
        "type": "dict_or_none",
        "ask": True,
    }
]

database_encryption_fields = [
    {
        "name": "mode",
        "comment": "Режим работы шифрования БД (none, read_write, read)",
        "default_value": "none",
        "type": "str",
        "ask": True,
    },
    {
        "name": "master_key",
        "comment": "Мастер ключ шифрования БД",
        "default_value": "",
        "type": "str",
        "ask": True,
        "is_required": False,
    }
]

icap_fields = [
    {
        "name": "is_enabled",
        "comment": "Включен ли ICAP",
        "default_value": None,
        "type": "bool",
        "ask": True,
        "is_required": True
    },
    {
        "name": "host",
        "comment": "Хост сервера ICAP",
        "default_value": None,
        "type": "str",
        "ask": True,
        "is_required": False,
        "depends_on": "is_enabled",
        "validation": "host"
    },
    {
        "name": "port",
        "comment": "Порт сервера ICAP",
        "default_value": 1433,
        "type": "int",
        "ask": True,
        "is_required": False,
        "depends_on": "is_enabled",
        "validation": "port"
    },
    {
        "name": "url_path",
        "comment": "Путь до сервиса ICAP",
        "default_value": "",
        "type": "str",
        "ask": True,
        "is_required": False,
    },
    {
        "name": "control_entity_list",
        "comment": "Список контролируемых сущностей, отправляемые в LDAP",
        "default_value": None,
        "type": "arr",
        "ask": True,
        "is_required": False,
        "depends_on": "is_enabled",
        "options": ["text", "file"],
    },
    {
        "name": "file_extension_list",
        "comment": "Список контролируемых расширений файлов, отправляемые в LDAP",
        "default_value": "",
        "type": "arr",
        "ask": True,
        "is_required": False,
        "post_function": strtolower,
        "post_args": [],
    }
]

file_auto_deletion_fields = [
    {
        "name": "is_enabled",
        "comment": "Включено ли автоудаление файлов",
        "default_value": None,
        "type": "bool",
        "ask": True,
    },
    {
        "name": "file_ttl",
        "comment": "Время жизни файлов",
        "default_value": None,
        "type": "int",
        "ask": True,
        "is_required": False,
        "depends_on": "is_enabled",
        "validation": "positive_int"
    },
    {
        "name": "check_interval",
        "comment": "Временной интервал запуска проверки на удаление файлов с сервера",
        "default_value": None,
        "type": "int",
        "ask": True,
        "is_required": False,
        "depends_on": "is_enabled",
        "validation": "positive_int"
    },
    {
        "name": "need_delete_file_type_list",
        "comment": "Тип удаляемых файлов с сервера",
        "default_value": None,
        "type": "arr",
        "ask": True,
        "is_required": False,
        "depends_on": "is_enabled",
        "options": ["audio", "voice", "image", "video", "archive", "document", "file"]
    }
]

team_fields = [
    {
        "name": "file_access_restriction_mode",
        "comment": "Режим доступа к файлам",
        "default_value": "none",
        "type": "str",
        "ask": True,
    },
]

required_root_fields = [
    {
        "name": "subdomain_enabled",
        "comment": "Включены ли поддомены",
        "default_value": 0,
        "type": "int",
        "ask": False,
        "post_function": None,
        "post_args": [],
    },
    {
        "name": "server_uid",
        "comment": "Уникальный идентификатор сервера",
        "default_value": None,
        "value_function": server_uid,
        "args": [],
        "type": "str",
        "ask": False,
        "post_function": None,
        "post_args": [],
    },
    {
        "name": "root_mount_path",
        "comment": "Укажите место хранения файлов проекта",
        "default_value": str(Path(script_dir + "/../../../compass/mount").resolve()),
        "type": "str",
        "ask": True,
        "post_function": create_dir,
        "post_args": [],
    },
    {
        "name": "root_password",
        "comment": "Введите пароль от mysql сервера",
        "default_value": None,
        "value_function": random_string,
        "args": [32],
        "type": "password",
        "ask": False,
        "is_protected": True,
    },
    {
        "name": "monolith_nginx_port",
        "comment": "Введите порт для nginx монолита",
        "default_value": 32100,
        "value_function": None,
        "type": "int",
        "ask": True,
    },
    {
        "name": "company_db_path",
        "comment": "Укажите место хранения баз данных команд",
        "default_value": None,
        "value_function": copy_with_postfix,
        "args": ["_global.root_mount_path", "/db_company"],
        "type": "str",
        "ask": False,
        "post_function": create_dir,
        "post_args": [],
    },
    {
        "name": "company_config_mount_path",
        "comment": "Укажите место хранения конфигурационных файлов команд",
        "default_value": None,
        "value_function": copy_with_postfix,
        "args": ["_global.root_mount_path", "/company_configs"],
        "type": "str",
        "ask": False,
        "post_function": create_dir,
        "post_args": ["www-data"],
    },
    {
        "name": "default_file_path",
        "comment": "Укажите место хранения дефолтных файлов",
        "default_value": None,
        "value_function": copy_with_postfix,
        "args": ["_global.root_mount_path", "/default_file"],
        "type": "str",
        "ask": False,
        "post_function": create_dir,
        "post_args": [],
    },
    {
        "name": "license_mount_path",
        "comment": "Укажите место хранения локальных лицензий",
        "default_value": None,
        "value_function": copy_with_postfix,
        "args": ["_global.root_mount_path", "/license"],
        "type": "str",
        "ask": False,
        "post_function": create_dir,
        "post_args": [],
    },
    {
        "name": "host_ip",
        "comment": "Укажите хост, на котором будет разворачиваться проект. Указывайте ip в локальной сети, если проекты находятся в ее пределах. Не используйте адрес 127.0.0.1 или localhost!",
        "default_value": None,
        "type": "str",
        "validation": "ip",
        "ask": True,
    },
    {
        "name": "domain",
        "comment": "Укажите домен, на котором будет разворачиваться проект",
        "default_value": None,
        "type": "str",
        "ask": True,
        "validation": "idna",
        "post_function": convert_idn,
        "post_args": [],
    },
    {
        "name": "stack_name_prefix",
        "comment": "Префикс стака проекта",
        "default_value": environment + "-" + values_name,
        "type": "str",
        "ask": False,
    },
    {
        "name": "sentry_dsn_key_electron",
        "comment": "Sentry DSN ключ для electron",
        "default_value": "",
        "type": "str",
        "ask": True,
        "is_required": False,
        "skip_current_value": True,
    },
    {
        "name": "sentry_dsn_key_android",
        "comment": "Sentry DSN ключ для android",
        "default_value": "",
        "type": "str",
        "ask": True,
        "is_required": False,
        "skip_current_value": True,
    },
    {
        "name": "sentry_dsn_key_ios",
        "comment": "Sentry DSN ключ для ios",
        "default_value": "",
        "type": "str",
        "ask": True,
        "is_required": False,
        "skip_current_value": True,
    },
    {
        "name": "is_need_index_web",
        "comment": "Разрешено ли поисковикам индексировать страницу авторизации",
        "default_value": False,
        "type": "bool",
        "ask": True,
        "is_required": False
    },
    {
        "name": "is_portable_calls_disabled",
        "comment": "Включено ли ограничение на звонки на сервере",
        "default_value": False,
        "type": "bool",
        "ask": True,
        "is_required": False
    },
    {
        "name": "backup_user_password",
        "comment": "Введите пароль пользователя mysql для бекапов баз данных команд",
        "default_value": None,
        "type": "password",
        "value_function": random_password,
        "args": [32],
        "ask": False,
        "is_protected": True,
    },
    {
        "name": "backup_archive_password",
        "comment": "Введите пароль для архивов бекапов",
        "default_value": None,
        "type": "password",
        "value_function": random_password,
        "args": [32],
        "ask": False,
        "is_protected": True,
    },
    {
        "name": "websocket_port",
        "comment": "Укажите порт, через который клиентски приложения будут подключаться по websocket протоколу",
        "default_value": 0,
        "type": "int",
        "ask": True,
    },
    {
        "name": "local_license",
        "comment": "Включены ли локальные лицензии",
        "default_value": False,
        "type": "bool",
        "ask": True,
        "is_required": False
    }
]

common_project_fields = [
    {
        "name": "host",
        "comment": "IP-адрес, на котором будет располагаться проект. Указывайте ip в локальной сети, если проекты находятся в ее пределах. Не используйте адрес 127.0.0.1 или localhost!",
        "default_value": None,
        "type": "str",
        "validation": "ip",
        "value_function": copy,
        "args": ["_global.host_ip"],
        "ask": False,
    },
    {
        "name": "service.nginx.external_https_port",
        "comment": "Внешний порт для nginx",
        "default_value": None,
        "value_function": copy,
        "args": ["_global.monolith_nginx_port"],
        "type": "int",
        "ask": False,
        "except": ["join_web", "jitsi", "jitsi_web"],
    },
    {
        "name": "label",
        "comment": "Название стака для проекта",
        "default_value": None,
        "value_function": get_project_name,
        "args": [],
        "type": "str",
        "ask": False,
    },
    {
        "name": "subdomain",
        "comment": "Поддомен проекта",
        "default_value": "",
        "value_function": None,
        "args": [],
        "skip_function": skip_subdomain,
        "type": "str",
        "validation": "idna",
        "ask": True,
        "except": ["join_web", "pivot", "monolith"],
        "post_function": convert_idn,
        "post_args": [],
    }
]

common_specific_project_fields = {
    "join_web": [
        {
            "name": "service.join_web.external_port",
            "comment": "Порт для сайта",
            "default_value": None,
            "value_function": project_port,
            "args": [],
            "type": "int",
            "ask": True,
        }
    ],
    "jitsi_web": [
        {
            "name": "service.jitsi_web.external_port",
            "comment": "Порт для сайта",
            "default_value": None,
            "value_function": project_port,
            "args": [],
            "type": "int",
            "ask": True,
        }
    ]
}

required_project_fields = [
    {
        "name": "service.mysql.root_password",
        "comment": "Введите пароль от mysql сервера",
        "default_value": None,
        "value_function": copy,
        "args": ["_global.root_password"],
        "type": "password",
        "ask": False,
        "except": ["join_web", "jitsi", "jitsi_web"],
    },
    {
        "name": "service.mysql.password",
        "comment": "Введите пароль от mysql сервера",
        "default_value": None,
        "value_function": copy,
        "args": ["_project.service.mysql.root_password"],
        "type": "password",
        "ask": False,
        "except": ["join_web", "jitsi", "jitsi_web"],
    },
    {
        "name": "service.mysql.user",
        "comment": "Введите ользователя mysql сервера",
        "default_value": "root",
        "type": "str",
        "ask": False,
        "except": ["join_web", "jitsi", "jitsi_web"],
    },
    {
        "name": "network.subnet",
        "comment": "Укажите подсеть в сети docker",
        "default_value": None,
        "value_function": get_free_subnet,
        "args": [],
        "ask": False,
    },
]

required_specific_project_fields = {

    "domino": [
        {
            "name": "company_config_dir",
            "comment": "Введите путь до папки, где будут храниться конфиги команд",
            "default_value": None,
            "value_function": copy_with_custom_postfix,
            "args": ["_global.company_config_mount_path"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": ["www-data"],
        },
        {
            "name": "code_host",
            "comment": "Введите IP-адрес, на котором будет располагаться кодовая база домино",
            "default_value": None,
            "value_function": copy,
            "args": ["_project.host"],
            "type": "str",
            "ask": False,
        },
        {
            "name": "domino_secret_key",
            "comment": "Введите секретный ключ домино",
            "default_value": None,
            "value_function": secret_key,
            "args": [32],
            "type": "str",
            "ask": False,
            "is_protected": True,
        },
        {
            "name": "mysql_host",
            "comment": "Введите IP-адрес, на котором будет располагаться базы данных компаний",
            "default_value": None,
            "value_function": copy,
            "args": ["_project.code_host"],
            "type": "str",
            "ask": False,
        },
        {
            "name": "tier",
            "comment": "Укажите ранг домино",
            "default_value": 1,
            "type": "int",
            "ask": False,
        },
        {
            "name": "manticore_path",
            "comment": "Укажите путь до папки, где будут храниться данные для поиска",
            "default_value": None,
            "value_function": copy_with_custom_postfix,
            "args": ["_global.root_mount_path"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": [],
        },
        {
            "name": "company_mysql_user",
            "comment": "Введите имя пользователя mysql для баз данных команд",
            "default_value": "user",
            "type": "str",
            "ask": False,
            "is_protected": True,
        },
        {
            "name": "company_mysql_password",
            "comment": "Введите пароль пользователя mysql для баз данных команд",
            "default_value": None,
            "type": "password",
            "value_function": random_password,
            "args": [32],
            "ask": False,
            "is_protected": True,
        },
        {
            "name": "go_database_controller_port",
            "comment": "Укажите порт для контроллера баз данных команд",
            "default_value": domino_ports["go_database_controller_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.manticore.host",
            "comment": "Укажите IP-адрес базы поиска",
            "default_value": None,
            "value_function": copy,
            "args": ["_project.code_host"],
            "type": "str",
            "ask": False,
        },
        {
            "name": "service.manticore.external_port",
            "comment": "Укажите внешний порт для базы поиска",
            "default_value": domino_ports["service.manticore.external_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.manticore.port",
            "comment": "Укажите порт для базы поиска",
            "default_value": 9306,
            "type": "int",
            "ask": False,
        },
        {
            "name": "company_db_path",
            "comment": "Укажите папку с файлами БД",
            "default_value": None,
            "value_function": copy_with_custom_postfix,
            "args": ["_global.company_db_path"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": [],
        },
        {
            "name": "template_public_company_url",
            "comment": "Шаблон URL для домино",
            "default_value": None,
            "value_function": get_domino_template,
            "args": [],
            "type": "str",
            "ask": False
        },
    ],
    "pivot": [
        {
            "name": "service.go_pusher.is_push_mock_enable",
            "comment": "Должен ли быть включен ли мок для пушей?",
            "default_value": "false",
            "type": "str",
            "ask": False,
        }
    ],
    "file": [
        {
            "name": "tmp_files_dir",
            "comment": "Укажите папку с временными файлами",
            "default_value": None,
            "value_function": copy_with_postfix,
            "args": ["_global.root_mount_path", "/tmp_files"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": ["www-data", 0o777],
        },
        {
            "name": "files_dir",
            "comment": "Укажите папку с файлами",
            "default_value": None,
            "value_function": copy_with_custom_postfix,
            "args": ["_global.root_mount_path"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": ["www-data", 0o777],
        },
        {
            "name": "default_files_dir",
            "comment": "Укажите папку со стандартными файлами приложения",
            "default_value": None,
            "value_function": copy_with_custom_postfix,
            "args": ["_global.root_mount_path"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": ["www-data", 0o777],
        },
        {
            "name": "custom_files_dir",
            "comment": "Укажите папку с пользовательскими файлами приложения",
            "default_value": None,
            "value_function": copy_with_custom_postfix,
            "args": ["_global.root_mount_path"],
            "type": "str",
            "ask": False,
            "post_function": create_dir,
            "post_args": ["www-data", 0o777],
        },
    ],
    "jitsi": [
        {
            "name": "domain",
            "comment": "Домен, на котором будет разворачиваться jitsi нода",
            "default_value": None,
            "type": "str",
            "ask": False,
            "validation": "idna",
            "value_function": onpremise_domain,
            "args": [],
        },
        {
            "name": "jwt.app_secret",
            "comment": "Введите секретный ключ для подписи JWT токена",
            "default_value": None,
            "value_function": random_string,
            "args": [32],
            "type": "password",
            "is_protected": True,
            "ask": False,
        },
        {
            "name": "secrets.jicofo_auth_password",
            "comment": "Введите пароль для авторизации компонента jicofo",
            "default_value": None,
            "value_function": random_string,
            "args": [32],
            "type": "password",
            "is_protected": True,
            "ask": False,
        },
        {
            "name": "secrets.jvb_auth_password",
            "comment": "Введите пароль для авторизации компонента jvb",
            "default_value": None,
            "value_function": random_string,
            "args": [32],
            "type": "password",
            "is_protected": True,
            "ask": False,
        },
        {
            "name": "secrets.event_plugin_token",
            "comment": "Введите секретный ключ для подписи событий отправляемых от Jitsi ноды",
            "default_value": None,
            "value_function": random_string,
            "args": [32],
            "type": "password",
            "is_protected": True,
            "ask": False,
        },
        {
            "name": "secrets.rest_api_token",
            "comment": "Введите токен для запросов к rest api Jitsi ноды",
            "default_value": None,
            "value_function": random_string,
            "args": [32],
            "type": "password",
            "is_protected": True,
            "ask": False,
        },
        {
            "name": "service.web.https_port",
            "comment": "Укажите порт для https запросов к веб-интерфейсу jitsi",
            "default_value": jitsi_ports["service.web.https_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.jvb.media_advertise_ips",
            "comment": "Укажите IP-адрес или список IP-адресов (через запятую), по которым клиенты будут подключаться к медиа-серверу",
            "default_value": None,
            "type": "arr",
            "ask": True,
            "is_required": False,
            "validation": "ip"
        },
        {
            "name": "service.jvb.media_port",
            "comment": "Укажите порт, на который участники конференции будут отправлять медиа-трафик",
            "default_value": jitsi_ports["service.jvb.media_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.jicofo.port",
            "comment": "Укажите порт для компонента jicofo",
            "default_value": jitsi_ports["service.jicofo.port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.prosody.serve_port",
            "comment": "Укажите порт для компонента prosody",
            "default_value": jitsi_ports["service.prosody.serve_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.prosody.v0.serve_port",
            "comment": "Укажите порт для компонента prosody",
            "default_value": jitsi_ports["service.prosody.v0.serve_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.prosody.v1.serve_port",
            "comment": "Укажите порт для компонента prosody",
            "default_value": jitsi_ports["service.prosody.v1.serve_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.prosody.v2.serve_port",
            "comment": "Укажите порт для компонента prosody",
            "default_value": jitsi_ports["service.prosody.v2.serve_port"],
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.turn.host",
            "comment": "Укажите адрес TURN сервера, который будет использоваться для соединения в ВКС",
            "default_value": None,
            "type": "str",
            "ask": True,
        },
        {
            "name": "service.turn.port",
            "comment": "Укажите порт TURN сервера, который принимает входящие UDP/TCP соединения клиентов",
            "default_value": None,
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.turn.tls_port",
            "comment": "Укажите порт TURN сервера, который принимает входящие соединения клиентов, использующие протокол TLS",
            "default_value": None,
            "type": "int",
            "ask": True,
        },
        {
            "name": "service.turn.secret",
            "comment": "Укажите секретный ключ TURN сервера",
            "default_value": None,
            "type": "str",
            "ask": True,
        },
        {
            "name": "service.turn.use_protocols",
            "comment": "Укажите список используемых протоколов для соединения клиентов с TURN сервером",
            "default_value": None,
            "type": "arr_join",
            "ask": True,
        },
        {
            "name": "service.turn.force_relay",
            "comment": "Укажите использовать ли принудительно TURN сервер для соединения в видеоконференция",
            "default_value": None,
            "type": "bool",
            "ask": True,
        },
    ],
    "integration": [
        {
            "name": "service.nginx.external_https_port",
            "comment": "Внешний порт для nginx",
            "default_value": None,
            "value_function": project_port,
            "args": [],
            "type": "int",
            "ask": False
        }
    ],
}

found_external_ports = {}


def process_post_value(value, field: dict):
    post_value = None
    if field.get("post_function") is not None:
        post_value = field["post_function"](value, *field["post_args"])

        if post_value is not None:
            value = post_value

    return value


def process_field(
        field: dict, project: str, label: str, project_values: dict, new_values: dict, config: dict, config_path: str
):
    use_default = use_default_values

    # если для этого проекта не надо - пропускаем
    if (field.get("except") is not None) and (project in field["except"]):
        return None, None

    if field.get("skip_function") is not None:
        if field["skip_function"](
                project, label, {}, new_values, field["skip_args"] if field.get("skip_args") is not None else []
        ):
            return None, None

    prefix = ""
    if project != "":
        prefix = project + "."

    if (value := protected_config.get(prefix + field["name"])) is not None:
        process_post_value(value, field)
        return value, field

    if field["ask"]:
        if field.get("value_function") is not None:
            field["default_value"] = field["value_function"](
                project, label, {}, new_values, *field["args"]
            )

        if (field.get("force_default") == True):
            use_default = True

        if field.get("is_required") is False:
            is_required = False
        else:
            is_required = True

        validation = field.get("validation")

        # если поле, от которого зависим, True, заполнение становится обязательным
        if field.get("depends_on") is not None:

            need_field = field["depends_on"]
            if project_values.get(need_field) is True:
                is_required = True
            else:
                validation = None

        options = [] if field.get("options") is None else field["options"]
        try:
            new_value = InteractiveValue(
                prefix + field["name"],
                "[%s] " % project + field["comment"],
                field["type"],
                field["default_value"],
                validation=validation,
                force_default=use_default,
                config=config,
                is_required=is_required,
                options=field.get("options", [])
            ).from_config()
        except IncorrectValueException as e:
            handle_exception(e.field, e.message, config_path)
            return None, field["name"]

    else:

        new_value = (
            field["default_value"]
            if field["default_value"] is not None
            else field["value_function"](project, label, {}, new_values, *field["args"])
        )

        if field.get("is_protected"):
            protected_config[prefix + field["name"]] = new_value

    new_value = process_post_value(new_value, field)

    return new_value, field["name"]


def write_to_file(new_values: dict):
    if validate_only:
        if installer_output:
            if len(validation_errors) > 0:
                failed_fields = []
                for _, error_list in validation_errors.items():
                    failed_fields.extend(error_list)
                print(json.dumps(failed_fields, ensure_ascii=False))
                exit(1)
            print("[]")
        else:
            if len(validation_errors) > 0:
                for config_path, error_list in validation_errors.items():
                    print(scriptutils.error("Ошибка в конфигурации %s" % str(config_path.resolve())))
                    for error in error_list:
                        print(error)
                exit(1)
        return
    new_path = Path(str(values_file_path.resolve()))
    with new_path.open("w+t") as f:
        yaml.dump(new_values, f, sort_keys=False)

    print("Файл конфигурации обновлен: " + scriptutils.warning(str(new_path.resolve())))

    with protected_config_path.open("w+t") as f:
        yaml.dump(protected_config, f, sort_keys=False)

    # записываем бэкапы в папку маунта на всякий случай
    root_mount_path = new_values["root_mount_path"]
    backup_config_dir = Path(root_mount_path + "/deploy_configs")
    backup_config_dir.mkdir(exist_ok=True)

    backup_config_path = Path(root_mount_path + "/deploy_configs/global.yaml")
    backup_protected_config_path = Path(root_mount_path + "/deploy_configs/global.protected.yaml")

    with backup_config_path.open("w+t") as f:
        yaml.dump(config, f, sort_keys=False)

    with backup_protected_config_path.open("w+t") as f:
        yaml.dump(protected_config, f, sort_keys=False)

    print("Файл с секретами обновлен: " + scriptutils.warning(str(protected_config_path.resolve())))


def start():
    values_initial_dict = {
        "protocol": "https",
        "auth_bot_user_id": 1001,
        "remind_bot_user_id": 1002,
        "support_bot_user_id": 1003,
        "begin_increment_user_id": 160000,
        "need_company_hibernate": False,
        "is_local": False,
        "billing_protocol": "https",
        "billing_domain": "payment.getcompass.com",
        "dev_server": False,
        "server_type": "production",
        "start_octet": 10,
        "server_tag_list": ["production", "on-premise", "monolith"],
        "environment": "production",
        "domino_mysql_innodb_flush_method": "O_DIRECT",
        "domino_mysql_innodb_flush_log_at_timeout": 1,
        "triggers": {"before": ["triggers/check_security.py"]},
        "manticore_cluster_name": "compass_cluster",
        "servers_companies_relationship_file": "reserve_servers_companies_relationship.json",
    }

    # если имеется флаг установки интеграции, то добавляем тег integration
    if install_integration:
        values_initial_dict["server_tag_list"] += ["integration"]

    if scriptutils.is_yandex_cloud_marketplace_product():
        values_initial_dict["server_tag_list"] += ["yandex_cloud_marketplace"]

    new_values = init_global(values_initial_dict, values_file_path, environment)
    new_values = init_nginx(new_values)
    new_values = init_database(new_values)
    new_values = init_replication(new_values)
    new_values = init_team(new_values)
    new_values = init_file_auto_deletion(new_values)
    new_values = init_icap(new_values)

    if new_values.get("local_license"):
        new_values["server_tag_list"] += ["local_license"]

    if not project:
        write_to_file(new_values)
        return

    new_values = init_all_projects(new_values)
    if default_values["projects"][project].get("deploy_units") is not None:
        deploy_units = default_values["projects"][project]["deploy_units"] + [project]
    else:
        deploy_units = [project]

    for du in deploy_units:
        new_values = init_project(
            new_values, values_file_path, environment, du, project_name_override
        )

    write_to_file(new_values)


def process_postfix(label: str, field: dict) -> str:
    if field["name"] == "manticore_path":
        return "/manticore/%s_domino" % label

    if field["name"] == "company_db_path":
        return "/%s" % label

    if field["name"] == "default_files_dir":
        return "/default_files"

    if field["name"] == "custom_files_dir":
        return "/custom_files"

    if field["name"] == "files_dir":
        return "/files"

    return "/%s_domino" % label


def update_environment(environment: str, values_initial_dict: dict) -> dict:
    if environment == "dev":
        values_initial_dict["dev_server"] = True
        values_initial_dict["server_type"] = "test-server"
        values_initial_dict["server_tag_list"] = ["dev", "onpremise"]

    return values_initial_dict


def init_global(values_initial_dict: dict, values_path: Path, environment: str) -> dict:
    new_values = {}
    if values_path.exists():
        new_values.update(current_values)

    values_initial_dict = update_environment(environment, values_initial_dict)
    new_values.update(values_initial_dict)
    new_values["environment"] = environment

    for required_root_field in required_root_fields:
        if (value := protected_config.get(required_root_field["name"])) is not None:
            new_values[required_root_field["name"]] = value
            continue

        if required_root_field.get("skip_function") is not None:
            if required_root_field["skip_function"](
                    project, "", {}, new_values,
                    required_root_field["skip_args"] if required_root_field.get("skip_args") is not None else []
            ):
                continue

        if new_values != values_initial_dict:
            required_root_field["default_value"] = (
                current_values[required_root_field["name"]]
                if current_values.get(required_root_field["name"]) is not None and (
                        required_root_field.get("skip_current_value") is None or required_root_field[
                    "skip_current_value"] == False)
                else required_root_field["default_value"]
            )

        if required_root_field["ask"]:
            if required_root_field.get("value_function") is not None:
                required_root_field["default_value"] = required_root_field[
                    "value_function"
                ]("", "", {}, new_values, *required_root_field["args"])

            is_required = True
            if required_root_field.get("is_required") is not None:
                is_required = required_root_field.get("is_required")

            try:
                new_value = InteractiveValue(
                    required_root_field["name"],
                    required_root_field["comment"],
                    required_root_field["type"],
                    required_root_field["default_value"],
                    validation=required_root_field.get("validation"),
                    force_default=use_default_values,
                    config=config,
                    is_required=is_required
                ).from_config()
            except IncorrectValueException as e:
                handle_exception(e.field, e.message, config_path)
                new_value = None

        else:
            new_value = (
                required_root_field["default_value"]
                if required_root_field["default_value"] is not None
                else required_root_field["value_function"](
                    project, project, {}, new_values, *required_root_field["args"]
                )
            )

            if required_root_field.get("is_protected"):
                protected_config[required_root_field["name"]] = new_value
        if new_value is not None:
            new_value = process_post_value(new_value, required_root_field)
            new_values[required_root_field["name"]] = new_value

    return new_values


def init_nginx(new_values: dict):
    if new_values.get("nginx") is None:
        new_values["nginx"] = {}

    for nginx_field in nginx_fields:
        new_value, field_name = process_field(
            nginx_field.copy(), "nginx", "nginx", new_values["nginx"], new_values, config, config_path
        )

        if new_value is None:
            continue

        new_values = nested_set(new_values, "nginx.%s" % field_name, new_value)

    return new_values


def init_file_auto_deletion(new_values: dict):
    if new_values.get("file_auto_deletion") is None:
        new_values["file_auto_deletion"] = {}

    for file_auto_deletion_field in file_auto_deletion_fields:
        new_value, field_name = process_field(
            file_auto_deletion_field.copy(), "file_auto_deletion", "file_auto_deletion",
            new_values["file_auto_deletion"], new_values, config, team_config_path
        )

        if new_value is None:
            continue

        new_values = nested_set(new_values, "file_auto_deletion.%s" % field_name, new_value)

    return new_values


def init_icap(new_values: dict):
    if new_values.get("icap") is None:
        new_values["icap"] = {}

    for icap_field in icap_fields:
        new_value, field_name = process_field(
            icap_field.copy(), "icap", "icap", new_values["icap"], new_values, dlp_config, dlp_config_path
        )

        if new_value is None:
            continue

        new_values = nested_set(new_values, "icap.%s" % field_name, new_value)

    return new_values


def init_team(new_values: dict):
    """инициализируем конфигурацию команды"""

    file_access_restriction_mode = team_config.get("file.access_restriction_mode", None)

    if file_access_restriction_mode is None:
        scriptutils.die("Не заполнен параметр file.access_restriction_mode")

    if file_access_restriction_mode != "none" and file_access_restriction_mode != "auth":
        scriptutils.die("Параметр file.access_restriction_mode должен иметь значение none или auth")

    # выполняем наполнение конфигурации полями
    config["file_access_restriction_mode"] = file_access_restriction_mode
    new_values = nested_set(new_values, "file_access_restriction_mode", file_access_restriction_mode)

    # проверяем максимальный размер загружаемого
    max_file_size_mb = team_config.get("max_file_size_mb", None)
    try:
        max_file_size_mb = int(max_file_size_mb)
    except:
        scriptutils.die("Параметр max_file_size_mb в team.yaml должен быть числом от 20 до 2048")
    if max_file_size_mb is None:
        scriptutils.die("Не заполнен параметр max_file_size_mb в team.yaml")

    if not (20 <= max_file_size_mb <= 2048):
        scriptutils.die("Параметр max_file_size_mb в team.yaml должен иметь значение от 20 до 2048")

    # выполняем наполнение конфигурации полями
    config["max_file_size_mb"] = max_file_size_mb
    new_values = nested_set(new_values, "max_file_size_mb", max_file_size_mb)
    return new_values


def init_database(new_values: dict):
    """инициализируем конфигурацию БД"""

    # первый делом вольем конфиг БД в обычный конфиг —
    # обычный не включается в себя yaml в привычном его виде,
    # но конфигурации БД объявлять построчно неудобно, поэтому
    # они лежат отдельный файлом, который уже для advanced пользователей
    # должен быть понятен и они его не сломают. Вливаем полностью перезаписывая
    # имеющийся, чтобы избежать возможных конфликтов
    config["database_connection.driver"] = database_config.get("database_connection", {}).get("driver", "")
    config["database_connection.driver_data"] = database_config.get("database_connection", {}).get("driver_data", None)

    # создаем пустой набор полей в итоговом values, если он не был объявлен
    if new_values.get("database_connection") is None:
        new_values["database_connection"] = {}

    # выполняем наполнение конфигурации полями
    for field in database_connection_fields:

        new_value, field_name = process_field(
            field.copy(), "database_connection", "database_connection",
            new_values["database_connection"], new_values, config, database_config_path
        )

        if new_value is None:
            continue

        new_values = nested_set(new_values, "database_connection.%s" % field_name, new_value)

    # повторяем то же самое для параметров шифрования
    config["database_encryption.mode"] = database_config.get("database_encryption", {}).get("mode", "none")
    config["database_encryption.master_key"] = database_config.get("database_encryption", {}).get("master_key", "")

    if new_values.get("database_encryption") is None:
        new_values["database_encryption"] = {}

    # выполняем наполнение конфигурации полями
    for field in database_encryption_fields:

        new_value, field_name = process_field(
            field.copy(), "database_encryption", "database_encryption",
            new_values["database_encryption"], new_values, config, database_config_path
        )

        if new_value is None:
            continue

        new_values = nested_set(new_values, "database_encryption.%s" % field_name, new_value)

    return new_values


def init_replication(new_values: dict):
    """инициализируем конфигурацию репликаций"""

    service_label = replication_config.get("service_label", None)
    if service_label is None:
        scriptutils.die("Не заполнен параметр service_label")

    if service_label != "" and len(service_label) > 8:
        scriptutils.die("Параметр service_label не должен быть длинее 12 символов")

    mysql_server_id = replication_config.get("mysql_server_id", None)
    try:
        mysql_server_id = int(mysql_server_id)
    except:
        scriptutils.die("Параметр mysql_server_id в replication.yaml должен быть числом")
    if mysql_server_id is None:
        scriptutils.die("Не заполнен параметр mysql_server_id")

    if mysql_server_id < 0:
        scriptutils.die("Параметр mysql_server_id не должен быть меньше 0")

    if service_label != "" and mysql_server_id == 0:
        scriptutils.die("Параметр mysql_server_id не должен быть равен 0, если заполнен service_label")

    start_octet = replication_config.get("start_octet", None)
    try:
        start_octet = int(start_octet)
    except:
        scriptutils.die("Параметр start_octet в replication.yaml должен быть числом")
    if start_octet is None:
        scriptutils.die("Не заполнен параметр start_octet")

    if (start_octet == 17 or start_octet == 18):
        scriptutils.die("Параметр start_octet не должен быть равен 17 или 18")

    if start_octet < 1:
        scriptutils.die("Параметр start_octet не должен быть меньше 1")

    # выполняем наполнение конфигурации полями
    config["service_label"] = service_label
    new_values = nested_set(new_values, "service_label", service_label)
    config["mysql_server_id"] = mysql_server_id
    new_values = nested_set(new_values, "mysql_server_id", mysql_server_id)
    config["start_octet"] = start_octet
    new_values = nested_set(new_values, "start_octet", start_octet)

    master_service_label = service_label
    if service_label != "":
        # получаем путь к файлу для связи компаний между серверами
        servers_companies_relationship_file_path = new_values.get("company_config_mount_path") + "/" + new_values.get(
            "servers_companies_relationship_file")

        # проверяем, есть ли файл
        if not Path(servers_companies_relationship_file_path).exists():

            # если нет, создаём и указываем текущий service_label как мастер
            f = open(servers_companies_relationship_file_path, "w")
            reserve_relationship_write_object = {service_label: {"master": True}}
            f.write(json.dumps(reserve_relationship_write_object))
            f.close()

            # устанавливаем пользователя
            user = pwd.getpwnam("www-data")
            os.chown(servers_companies_relationship_file_path, user.pw_uid, user.pw_gid)
        else:
            # если файл есть, читаем содержимое
            with open(servers_companies_relationship_file_path, "r") as file:
                reserve_relationship_str = file.read()
                reserve_relationship_dict = json.loads(
                    reserve_relationship_str) if reserve_relationship_str != "" else {}

                if reserve_relationship_dict.get(service_label) is None:
                    data = {"master": False}
                    reserve_relationship_dict[service_label] = data

                master_service_label = ""
                for label, data in reserve_relationship_dict.items():

                    # получаем service_label мастера
                    if "master" in data and data["master"] == True:
                        master_service_label = label

                    # если текущий service_label и не master_service_label
                    if label == new_values.get("service_label") and master_service_label != label:
                        data["master"] = False
                        reserve_relationship_dict[label] = data

            # записываем новое содержимое
            f = open(servers_companies_relationship_file_path, "w")
            f.write(json.dumps(reserve_relationship_dict))
            f.close()

    config["master_service_label"] = master_service_label
    new_values = nested_set(new_values, "master_service_label", master_service_label)

    return new_values


def init_all_projects(new_values: dict):
    if new_values.get("projects") is None:
        new_values["projects"] = {}

    for project in deploy_project_list:
        label = project

        if project == "file":
            label = "file1"
        elif project == "file_default_nodes":
            label = "file_default"
        elif project == "domino":
            label = "d1"

        project_values = new_values.get("projects", {}).get(project, {})

        if project in nested_project_list:
            project_values = project_values.get(label, {})

        for common_field in common_project_fields:
            new_value, field_name = process_field(
                common_field.copy(), project, label, project_values, new_values, config, config_path
            )

            if new_value is None:
                continue

            project_values = nested_set(project_values, field_name, new_value)

            if project in nested_project_list:
                new_values = nested_set(
                    new_values, "projects.%s.%s" % (project, label), project_values
                )
            else:
                new_values["projects"][project] = project_values

        if common_specific_project_fields.get(project) is None:
            continue

        for extra_field in common_specific_project_fields[project]:
            new_value, field_name = process_field(
                extra_field.copy(), project, label, project_values, new_values, config, config_path)

            if new_value is None:
                continue

            project_values = nested_set(project_values, field_name, new_value)
            if project in nested_project_list:
                new_values = nested_set(
                    new_values, "projects.%s.%s" % (project, label), project_values
                )
            else:
                new_values["projects"][project] = project_values

    return new_values


def init_project(
        new_values: dict,
        values_path: Path,
        environment: str,
        project: str,
        label: str = None,
):
    if project == "":
        return

    if new_values.get("projects") is None:
        new_values["projects"] = {}

    project_values = new_values["projects"].get(project, {})
    label = project if label is None else label

    if project == "file":
        label = "file1"
    elif project == "file_default_nodes":
        label = "file_default"
    elif project == "domino":
        label = "d1"
    if project in nested_project_list:
        if label == project:
            print(scriptutils.error("Передан проект без явного указания имени"))
            exit(1)

        project_values = project_values.get(label, {})

    for required_field in required_project_fields:
        # если для этого проекта не надо - пропускаем
        if (required_field.get("except") is not None) and (
                project in required_field["except"]
        ):
            continue
        if (value := protected_config.get(project + "." + required_field["name"])) is not None:
            new_value = process_post_value(value, required_field)
            project_values = nested_set(
                project_values, required_field["name"], new_value
            )
            continue

        if deep_get(project_values, required_field["name"]) == {}:
            if (
                    required_field.get("default_value") is not None
                    and required_field["ask"] == False
            ):
                new_value = required_field["default_value"]

            if (
                    required_field.get("value_function") is not None
                    and required_field["ask"] == False
            ):
                new_value = required_field["value_function"](
                    project, label, project_values, new_values, *required_field["args"]
                )

            if required_field["ask"] == True:
                if required_field.get("value_function") is not None:
                    required_field["default_value"] = required_field["value_function"](
                        project,
                        label,
                        project_values,
                        new_values,
                        *required_field["args"]
                    )
                try:
                    new_value = InteractiveValue(
                        project + "." + required_field["name"],
                        "[%s]" % project + required_field["comment"],
                        required_field["type"],
                        required_field["default_value"],
                        validation=required_field.get("validation"),
                        force_default=use_default_values,
                        config=config
                    ).from_config()
                except IncorrectValueException as e:
                    handle_exception(e.field, e.message, config_path)
                    new_value = None

            elif required_field.get("is_protected"):
                protected_config[project + "." + required_field["name"]] = new_value

            if new_value is not None:
                new_value = process_post_value(new_value, required_field)

                project_values = nested_set(
                    project_values, required_field["name"], new_value
                )

    extra_fields = required_specific_project_fields.get(project)
    if extra_fields is not None:
        for extra_field in extra_fields:
            # если для этого проекта не надо - пропускаем
            if (extra_field.get("except") is not None) and (
                    project in extra_field["except"]
            ):
                continue

            if extra_field.get("skip_function") is not None:
                if extra_field["skip_function"](
                        project, label, {}, new_values,
                        extra_field["skip_args"] if extra_field.get("skip_args") is not None else []
                ):
                    continue

            if (value := protected_config.get(project + "." + extra_field["name"])) is not None:
                new_value = process_post_value(value, extra_field)
                project_values = nested_set(project_values, extra_field["name"], new_value)
                continue

            if (
                    extra_field.get("default_value") is not None
                    and extra_field["ask"] == False
            ):
                new_value = extra_field["default_value"]

            if (
                    extra_field.get("value_function") is not None
                    and extra_field["value_function"].__name__
                    == copy_with_custom_postfix.__name__
            ):
                extra_field["args"].append(process_postfix(label, extra_field))

            if (
                    extra_field.get("value_function") is not None
                    and extra_field["ask"] == False
            ):
                new_value = extra_field["value_function"](
                    project, label, project_values, new_values, *extra_field["args"]
                )

            if extra_field["ask"] == True:
                if extra_field.get("value_function") is not None:
                    extra_field["default_value"] = extra_field["value_function"](
                        project, label, project_values, new_values, *extra_field["args"]
                    )

                # обязательный ли к заполнению параметр
                is_required = True
                if extra_field.get("is_required") is not None:
                    is_required = extra_field.get("is_required")

                try:
                    new_value = InteractiveValue(
                        project + "." + extra_field["name"],
                        "[%s]" % project + extra_field["comment"],
                        extra_field["type"],
                        extra_field["default_value"],
                        validation=extra_field.get("validation"),
                        force_default=use_default_values,
                        config=config,
                        is_required=is_required,
                    ).from_config()
                except IncorrectValueException as e:
                    handle_exception(e.field, e.message, config_path)
                    new_value = None

            elif extra_field.get("is_protected"):
                protected_config[project + "." + extra_field["name"]] = new_value

            if new_value is not None:
                new_value = process_post_value(new_value, extra_field)
                project_values = nested_set(project_values, extra_field["name"], new_value)

    if project in nested_project_list:
        new_values = nested_set(
            new_values, "projects.%s.%s" % (project, label), project_values
        )
    else:
        new_values["projects"][project] = project_values

    project_database_path = Path(
        "%s/%s/database" % (new_values["root_mount_path"], label)
    )
    project_database_path.mkdir(exist_ok=True, parents=True)

    # для аналитики создаем clickhouse папку
    if project == "analytic":
        project_clickhouse_path = Path(
            "%s/%s/clickhouse" % (new_values["root_mount_path"], label)
        )
        project_clickhouse_path.mkdir(exist_ok=True, parents=True)

    return new_values


try:
    start()
except KeyboardInterrupt:
    print("Вышли из скрипта")
