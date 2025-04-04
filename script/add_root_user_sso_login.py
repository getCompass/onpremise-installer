#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, pwd
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
from utils.interactive import InteractiveValue, IncorrectValueException

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument(
    "-v", "--values", required=False, default="compass", type=str, help="Название values файла окружения"
)
parser.add_argument(
    "-e",
    "--environment",
    required=False,
    default="production",
    type=str,
    help="Окружение, в котором разворачиваем",
)

parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)

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
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"
validate_only = args.validate_only

script_dir = str(Path(__file__).parent.resolve())

values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, values_arg))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

    domino_project = current_values['projects']['domino']

    if len(domino_project) < 1:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label


def handle_exception(field, message: str):
    if validate_only:
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

# получаем доступные методы для регистрации root-пользователя
try:
    available_method_list = InteractiveValue(
        "available_methods", "Доступные способы аутентификации", "arr", config=config,
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)

# получаем значение логина для аутентификации через SSO
try:
    sso_login = InteractiveValue(
        "root_user.sso_login",
        "Заполните поле root_user.sso_login в configs/team.yaml, в котором нужно указать логин, используемый для аутентификации через SSO (uid, username, почтовый адрес или номер телефона в международном формате)",
        "str",
        config=config,
        is_required=("sso" in available_method_list),  # если среди доступных методов указан "sso"
        default_value=""
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)
    sso_login = ""

if (len(sso_login) == 0):
    scriptutils.die(
        "Необходимо заполнить поле root_user.sso_login в configs/team.yaml"
    )

if validate_only:

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
        "php src/Compass/Pivot/sh/php/migration/add_root_user_sso_login.php --dry=0 --is-root --sso_login=%s" % sso_login,
    ],
)

if output.exit_code == 0:
    print(output.output.decode("utf-8"))
    print(scriptutils.success("Успешно добавлены данные %s для авторизации через SSO" % sso_login))
elif output.exit_code == 1:
    print(scriptutils.warning("Повторное добавление данных невозможно. Используйте ранее привязанные данные для авторизации через SSO."))
elif output.exit_code == 2:
    print(scriptutils.warning("Не смогли применить данные из configs/team.yaml, некорректный формат заполнения поля root_user.sso_login"))
elif output.exit_code == 3:
    print(scriptutils.warning(
        "Не смогли применить данные из configs/team.yaml, возникла ошибка в выполнении скрипта добавления данных, попробуйте запустить скрипт напрямую из контейнера php_monolith - php src/Compass/Pivot/sh/php/migration/add_root_user_sso_login.php --dry=0 --is-root --sso_login=<значение>"))
else:
    print(scriptutils.warning(
        "Не смогли применить данные из configs/team.yaml, проверьте работоспособность системы, или попробуйте запустить скрипт напрямую из контейнера php_monolith - php src/Compass/Pivot/sh/php/migration/add_root_user_sso_login.php --dry=0 --is-root --sso_login=<значение>"))
