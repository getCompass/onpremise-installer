#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачи:
# – загружает/обновляет дефолтные файлы
# – обновляет аватары ботов
# – создает системных ботов (если они не были созданы ранее)
# Скрипт может быть запущен неоднократно

import sys

sys.dont_write_bytecode = True

import argparse, yaml, pwd, psutil
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')
parser.add_argument('--service_label', required=False, default="", type=str,
                    help='Метка сервиса, к которому закреплён стак')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

script_dir = Path(__file__).parent.resolve()

smart_apps_config_path = script_dir.parent / "configs" / "smart_apps.yaml"

if not smart_apps_config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {smart_apps_config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

with smart_apps_config_path.open("r") as config_file:
    smart_apps_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
service_label = args.service_label if args.service_label else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

if service_label != "":
    stack_name = stack_name + "-" + service_label

# необходимые пользователи для окржуения
required_user_list = ['www-data']

# проверяем наличие необходимых пользователей
for user in required_user_list:

    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die('Необходимо создать пользователя окружения' + user)

client = docker.from_env()

# получаем контейнер php-монолита
timeout = 30
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={'name': '%s_php-monolith' % stack_name, 'health': 'healthy'})

    if len(docker_container_list) > 0:
        found_php_monolith_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            'Не был найден необходимый docker-контейнер для запуска скриптов. Убедитесь, что окружение поднялось корректно')

# проверяем наличие default-файлов
output = found_php_monolith_container.exec_run(user='www-data',
    cmd=['bash', '-c', 'php src/Compass/Pivot/sh/php/service/wait_default_files.php'])
if output.exit_code != 0:

    print(output.output.decode("utf-8"))
    print(scriptutils.error('В docker-контейнере монолита отсутствуют default-файлы приложения'))

smart_app_catalog_id_list = []
for smart_app in smart_apps_config_values.get("smart_apps.catalog_config", []):
    if not isinstance(smart_app, dict):
        continue
    try:
        catalog_item_id = int(smart_app.get("catalog_item_id", -1))
        if catalog_item_id > 0:
            smart_app_catalog_id_list.append(catalog_item_id)
    except (ValueError, TypeError):
        continue

smart_app_catalog_id_str = ",".join(map(str, smart_app_catalog_id_list))
update_created_smart_apps_script = ""
if smart_app_catalog_id_list:
    update_created_smart_apps_script = f"php src/Compass/Pivot/sh/php/service/exec_company_update_script.php --script-name=UpdateCreatedSmartApps --dry=0 --log-level=1 --module-proxy=[php_company] --script-data=[{smart_app_catalog_id_str}] --y"

exec_script_list = [
    'php src/Compass/Pivot/sh/php/service/upload_default_file_list.php',
    'php src/Compass/Pivot/sh/php/service/check_default_file_list.php',
    'php src/Compass/Pivot/sh/php/service/upload_custom_file_list.php',
    'php src/Compass/Pivot/sh/php/service/check_custom_file_list.php',
    'php src/Compass/Pivot/sh/start/create_system_bot_list.php',
    'php src/Compass/Pivot/sh/php/update/update_notice_bot.php',
    'php src/Compass/Pivot/sh/php/update/update_remind_bot.php',
    'php src/Compass/Pivot/sh/php/update/update_support_bot.php',
    'php src/Compass/Pivot/sh/php/update/replace_userbot_avatar.php',
    'php src/Compass/Pivot/sh/php/update/replace_preview_for_welcome_video.php',
    update_created_smart_apps_script,
]

for script in exec_script_list:

    output = found_php_monolith_container.exec_run(user='www-data', cmd=['bash', '-c', script])

    if output.exit_code != 0:
        print(output.output.decode("utf-8"))
        scriptutils.error('Что-то пошло не так. Выполнение одного из скриптов завершилось неудачей')
        exit(1)

scriptutils.success('Pivot успешно инициализирован')
