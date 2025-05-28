#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import yaml, os, argparse, docker

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

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

global_config_path = str(config_path) + "/global.yaml"
if False == os.path.exists(global_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл global.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# подключаемся к докеру
client = docker.from_env()
php_migration_container_name = "%s-monolith_php-migration" % stack_name_prefix
need_update_migrations_after_deploy = True

container_list = client.containers.list(filters={'name': php_migration_container_name, 'health': 'healthy'})
if len(container_list) > 0:
    exit(0)

print(
    scriptutils.warning(
        "!!!Во время обновления приложение будет недоступно в течение ~10 минут!!!\n"
    )
)

try:
    if input("Выполняем обновление приложения? [Y/n]\n").lower() != "y":
        scriptutils.die("Обновление приложения было отменено")
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(1)