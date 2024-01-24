#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import argparse, yaml, pwd
from python_on_whales import docker, exceptions
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

config = {}
validation_errors = []
if not config_path.exists():
    print(
        scriptutils.error(
            "Отсутствует файл конфигурации %s. Запустите скрит create_configs.py и заполните конфигурацию"
            % str(config_path.resolve())
        )
    )
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(config_values)

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
validate_only = args.validate_only

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
try:
    phone_number = InteractiveValue(
        "root_user.phone_number",
        "Введите номер телефона в международном формате",
        "str",
        validation="phone",
        config=config,
        is_required=True,
    ).from_config()
except IncorrectValueException as e:
    handle_exception(e.field, e.message)

if validate_only:

    if len(validation_errors) > 0:
        print("Ошибка в конфигурации %s" % str(config_path.resolve()))
        for error in validation_errors:
            print(error)
        exit(1)
    exit(0)

# получаем контейнер monolith
timeout = 10
n = 0
while n <= timeout:
    if environment == "" or values_arg == "":
        docker_container_list = docker.container.list(
            filters={"name": "monolith_php-monolith", "health": "healthy"}
        )
    else:
        docker_container_list = docker.container.list(
            filters={
                "name": "%s-monolith_php-monolith" % (stack_name_prefix),
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

try:
    output = found_pivot_container.execute(
        user="www-data",
        command=[
            "bash",
            "-c",
            "php src/Compass/Pivot/sh/php/domino/create_root_user.php --dry-run=0 --is-root --full-name=\"%s\" --phone-number=\"%s\""
            % (full_name, phone_number),
        ],
        interactive=True,
        tty=True,
    )
    print(output)
    print(scriptutils.warning("Чтобы получить ключ аутентификации для входа в приложение, необходимо пройти авторизацию на сайте https://%s/." % domain))
except exceptions.DockerException as e:
    print(e.stdout)
    print(e.stderr)
    scriptutils.error(
        "Что то пошло не так. Не смогли создать пользователя. Проверьте, что окружение поднялось корректно"
    )
