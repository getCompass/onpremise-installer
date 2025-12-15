#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, pwd, json
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
from utils.interactive import InteractiveValue, IncorrectValueException

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для создания главного пользователя.",
    usage="python3 script/create_root_user.py [-v VALUES] [-e ENVIRONMENT] [--validate-only] [--installer-output] [--service-label SERVICE_LABEL]",
    epilog="Пример: python3 script/create_root_user.py -v compass -e production --validate-only --installer-output --service-label primary",
)

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument("--validate-only", required=False, action="store_true",
                    help='Запуск скрипта в режиме read-only, без применения изменений')
parser.add_argument("--installer-output", required=False, action="store_true",
                    help='Вывод ошибок в формате JSON')
parser.add_argument('--service-label', required=False, default="", type=str,
                    help='Метка сервисов, к которому закреплен контейнер php-monolith')
args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#


# ---СКРИПТ---#

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())
# загружаем конфиги
config_path = Path(script_dir + "/../configs/team.yaml")
auth_config_path = Path(script_dir + "/../configs/auth.yaml")

config = {}
validation_errors = []
if not config_path.exists():
    print(
        scriptutils.error(
            "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию"
            % str(config_path.resolve())
        )
    )
    exit(1)

if not auth_config_path.exists():
    print(
        scriptutils.error(
            "Отсутствует файл конфигурации %s. Запустите скрипт create_configs.py и заполните конфигурацию"
            % str(auth_config_path.resolve())
        )
    )
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)
with auth_config_path.open("r") as config_file:
    auth_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(config_values)
config.update(auth_config_values)

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
service_label = args.service_label if args.service_label else ''
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"
validate_only = args.validate_only
installer_output = args.installer_output

QUIET = (validate_only and installer_output)

values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_arg))

if not values_file_path.exists() and (not validate_only):
    scriptutils.die(
        (
            "Не найден файл со сгенерированными значениями. Убедитесь, что приложение развернуто"
        )
    )

current_values = {}
if not validate_only:
    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

        if current_values == {}:
            scriptutils.die(
                "Не найден файл со сгенерированными значениями. Убедитесь, что приложение развернуто"
            )

        domain = str(current_values["domain"]).encode().decode('idna')

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label


def handle_exception(field, message: str):
    if validate_only:
        if installer_output:
            validation_errors.append(field)
        else:
            validation_errors.append(message)
        return

    print(message)
    exit(1)


# необходимые пользователи для окружения
required_user_list = ["www-data"]

# проверяем наличие необходимых пользователей
for user in required_user_list:
    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die("Необходимо создать пользователя окружения" + user)

# получаем имя для root-пользователя
try:
    full_name = InteractiveValue(
        "root_user.full_name",
        "Введите имя создаваемого root-пользователя",
        "str",
        config=config,
        is_required=True,
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)

# получаем доступные методы для регистрации root-пользователя
try:
    available_method_list = InteractiveValue(
        "available_methods", "Доступные способы аутентификации", "arr", config=config,
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)

# получаем значение номера телефона пользователя для регистрации
try:
    phone_number = InteractiveValue(
        "root_user.phone_number",
        "Введите номер телефона в международном формате",
        "str",
        validation="phone",
        config=config,
        is_required=("phone_number" in available_method_list),  # если среди доступных методов указан "phone_number"
        default_value=""
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)
    phone_number = ""

# получаем значение почты пользователя для регистрации
try:
    mail = InteractiveValue(
        "root_user.mail",
        "Введите почту",
        "str",
        validation="mail",
        config=config,
        is_required=("mail" in available_method_list),  # если среди доступных методов указан "mail"
        default_value=""
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)
    mail = ""

try:
    mail_allowed_domain_list = InteractiveValue(
        "mail.allowed_domains",
        "Получаем доступные домены для почты",
        "arr",
        config=config,
        is_required=False,
        default_value=[]
    ).from_config()

    mail_allowed_domains = "[%s]" % ', '.join(mail_allowed_domain_list)
except IncorrectValueException as e:
    handle_exception(e.field, e.message)
    mail_allowed_domains = "[]"

# если это проверка на валидацию, требуется почта и домен почты root-пользователя нет среди доступных доменов
if validate_only and ("mail" in available_method_list) and mail_allowed_domains != "[]" and (
        mail[mail.rfind('@') + 1:] not in mail_allowed_domains):
    scriptutils.die(
        "Домен почты root-пользователя не совпадает ни с одним из доступных доменов поля mail.allowed_domains"
    )

# получаем значение пароля для почты
try:
    password = InteractiveValue(
        "root_user.password",
        "Введите пароль для почты",
        "str",
        config=config,
        is_required=("mail" in available_method_list),  # если среди доступных методов указан "mail"
        default_value="",
        validation="mail_password"
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)
    password = ""

# получаем значение логина для аутентификации через SSO
try:
    sso_login = InteractiveValue(
        "root_user.sso_login",
        "Введите логин используемый для аутентификации через SSO (почтовый адрес или номер телефона в международном формате)",
        "str",
        config=config,
        is_required=("sso" in available_method_list),  # если среди доступных методов указан "sso"
        default_value=""
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)
    sso_login = ""

if (len(phone_number) == 0 and len(mail) == 0 and len(sso_login) == 0):
    if not QUIET:
        scriptutils.die(
            "Необходимо заполнить в конфигурации номер телефона или почту, или логин от sso пользователя"
        )

if validate_only:

    if installer_output:
        if len(validation_errors) > 0:
            print(json.dumps(validation_errors, ensure_ascii=False))
            exit(1)
        print("[]")
    else:
        if len(validation_errors) > 0:
            print("Ошибка в конфигурации %s" % str(config_path.resolve()))
            for error in validation_errors:
                print(error)
            exit(1)
    exit(0)

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
        found_pivot_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для создания пользователя. Убедитесь, что окружение поднялось корректно"
        )

output = found_pivot_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php src/Compass/Pivot/sh/php/domino/create_root_user.php --dry=0 --is-root --full-name=\"%s\" --phone-number=\"%s\" --mail=\"%s\" --password=\"%s\" --sso_login=\"%s\""
        % (full_name, phone_number, mail, password, sso_login),
    ],
)

if output.exit_code == 0:
    print(output.output.decode("utf-8"))
    print(scriptutils.warning(
        "Чтобы получить ключ аутентификации для входа в приложение, необходимо пройти авторизацию на сайте https://%s" % (
            domain)))
else:
    print(output.output.decode("utf-8"))
    scriptutils.error(
        "Что то пошло не так. Не смогли создать пользователя. Проверьте, что окружение поднялось корректно"
    )
