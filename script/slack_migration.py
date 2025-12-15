#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# миграции данных из slack в Compass On-premise

import sys
import time

sys.dont_write_bytecode = True

import argparse, yaml, pwd, psutil, shutil
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
import socket
from loader import Loader


# получение свободного порта на сервере
def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('', 0))
        return sock.getsockname()[1]


# распаршивает строку с параметрами в словарь
def parse_string_to_dict(string):
    params = {}
    parts = string.split()
    current_key = None

    for part in parts:
        if '=' in part:
            key, value = part.split('=')
            params[key.strip()] = value.strip()
            current_key = key.strip()
        else:
            if current_key:
                params[current_key] += ' ' + part

    return params


# выводит список имен из массива данных
def print_options(data):
    for i, item in enumerate(data):
        print(f"{i + 1}. {item['name']}")


# получает выбор пользователя из консоли и возвращает выбранный элемент
def get_user_choice(data):
    print_options(data)
    choice = int(input("Введите company_id команды в Compass (в неё будет произведена миграция данных): "))
    return data[choice - 1]


def list_of_dicts_to_strings(data):
    result = []
    for item in data:
        if isinstance(item, str):
            item = parse_string_to_dict(item)
            result.append(dict_to_string(item))
        elif isinstance(item, dict):
            result.append(dict_to_string(item))
        else:
            raise ValueError(f"Expected a dictionary or string in the list, but got {type(item)}")
    return result


def list_of_strings_to_dicts(data):
    result = []
    for item in data:
        if isinstance(item, str):
            result.append(parse_string_to_dict(item))
        elif isinstance(item, dict):
            result.append(item)
        else:
            raise ValueError(f"Expected a dictionary or string in the list, but got {type(item)}")
    return result


def dict_to_string(params):
    # Проверяем, действительно ли params является словарем
    if not isinstance(params, dict):
        raise ValueError(f"Expected a dictionary, but got {type(params)}")

    # Преобразуем словарь в строку с параметрами
    parts = [f"{key}={value}" for key, value in params.items()]
    return ' '.join(parts)


# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
parser.add_argument('--manticore_host', required=False, default="", type=str, help='Введите ip хоста на котором будет поднята manticore (ip текущего сервера)')
parser.add_argument('--manticore_port', required=False, default="", type=str, help='Введите port на котором будет поднята manticore (например: 9315)')
parser.add_argument('--manticore_mount_workdir', required=True, type=str, help='Введите путь папки маунта manticore')
parser.add_argument('--slack_export_workdir', required=True, type=str, help='Введите путь до директории экспорта данных из slack')

args = parser.parse_args()

slack_export_workdir = args.slack_export_workdir
manticore_host = args.manticore_host
manticore_mount = args.manticore_mount_workdir

if args.manticore_port == "":
    # получаем свободный порт для мантикоры
    manticore_port = int(get_free_port())
else:
    manticore_port = int(args.manticore_port)

script_dir = str(Path(__file__).parent.resolve())
values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, args.values))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект'))

    nginx_company_port = current_values['projects']['domino']['d1']['service']['nginx']['external_https_port']
    company_host = current_values['projects']['domino']['d1']['code_host']
    domino_url = "https://" + company_host + ":" + str(nginx_company_port)

    # для onedomain
    if 'url_path' in current_values['projects']['domino']['d1'] and current_values['projects']['domino']['d1']['url_path']:
        domino_url = domino_url + "/" + current_values['projects']['domino']['d1']['url_path']

    # для production
    if args.environment == "production":
        domino_url = domino_url + "/" + current_values['projects']['domino']['d1']['label']

if manticore_host == "":
    # получаем ip тачки
    manticore_host = current_values['projects']['pivot']['host']

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

# необходимые пользователи для окружения
required_user_list = ['www-data']

# проверяем наличие необходимых пользователей
for user in required_user_list:

    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die('Необходимо создать пользователя окружения' + user)

client = docker.from_env()

# получаем контейнер monolith
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "%s_php-monolith" % stack_name,
            "health": "healthy",
        }
    )

    if len(docker_container_list) > 0:
        found_php_monolith_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для создания пользователя. Убедитесь, что окружение поднялось корректно"
        )

# получаем контейнер file_node
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "%s_php-file-node-file1" % stack_name,
            "health": "healthy",
        }
    )

    if len(docker_container_list) > 0:
        found_php_file_node_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для импорта файлов. Убедитесь, что окружение поднялось корректно"
        )

# ---Поднимаем контейнер мантикоры и мигратора---#

# Ставим loader для показа ожидания для пользователя
loader = Loader(
    "Ждем подготовки окружения для миграции из Slack...",
    "Подготовка окружения для миграции из Slack завершена",
    "Не удалось подготовить окружение для миграции из Slack",
)
loader.start()

# получаем контейнер поднятого manticore
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "compass-migration-manticore",
        }
    )

    if len(docker_container_list) > 0:
        manticore_container = docker_container_list[0]

        # Получаем информацию о контейнере
        container_info = manticore_container.attrs

        # Извлекаем порт из информации о контейнере
        ports = container_info['NetworkSettings']['Ports']

        # Находим порт, который нас интересует (например, порт 9308)
        for port_key, port_value in ports.items():
            if port_key == '9306/tcp':
                manticore_port = int(port_value[0]['HostPort'])
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        try:
            manticore_container = client.containers.run(
                "manticoresearch/manticore",
                name="compass-migration-manticore",
                volumes=["%s:/var/lib/manticore" % manticore_mount],
                ports={'9306/tcp': ('%s' % (manticore_host), manticore_port)},
                environment=["EXTRA=1", "MCL=1"],
                detach=True
            )
            print("\n Поднимаем контейнер мантикоры для миграции")
        except Exception as e:
            loader.error()
            print(scriptutils.error(f"Ошибка при запуске контейнера manticore: {e}"))
            sys.exit(0)

# получаем контейнер поднятого exporter
timeout = 10
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "compass-migration-exporter",
        }
    )

    if len(docker_container_list) > 0:
        exporter_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        try:
            exporter_container = client.containers.run(
                "docker.getcompass.ru/backend_compass/php_slack_migrator:v4.4.6",
                name="compass-migration-exporter",
                volumes=["%s:/app/exported" % slack_export_workdir],
                detach=True
            )
            exporter_container.exec_run(user="root", cmd=["bash", "-c", "mysql -h %s -P %i < /app/db_schema/schema.sql" % (manticore_host, manticore_port)])
            print("\n Поднимаем контейнер экспортера для миграции")
        except Exception as e:
            loader.error()
            print(scriptutils.error(f"Ошибка при запуске контейнера exporter: {e}"))
            sys.exit(0)

loader.success()


# ---проверяем что на диске достаточно места---#

# берем данные из экспорта - файлы
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=file --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
)

if output.exit_code != 0:
    print(scriptutils.warning("Не смогли подсчитать количество загружаемых файлов"))
    sys.exit(0)

# Считаем объем файлов
output = found_php_file_node_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/FileNode/sh/php/migration/get_all_file_size.php --local_manticore_host='%s' --local_manticore_port=%s"
        % (manticore_host, manticore_port),
    ],
)

if output.exit_code != 0:
    print(output.output.decode("utf-8"))
    scriptutils.error('Получение объема всех файлов закончилось неудачей')
    exit(1)

output_arrays = output.output.decode("utf-8").splitlines()
corrected_data = list_of_strings_to_dicts(output_arrays)
file_info = corrected_data[-1]


files_count = file_info["files_count"]
print("\nВсего файлов для загрузки: %s" % files_count)

files_size_bytes = int(file_info["files_size_bytes"])
files_size_gb = round(files_size_bytes / 1024 / 1024 / 1024, 2)
real_import_size = files_size_gb * 3+1
print("Место на диске необходимое для импорта: %s Gib" % real_import_size)

# получаем объем свободного дискового пространства
total, used, free = shutil.disk_usage("/")
print("\nОбъем диска")
print("Занято: %d GiB" % (used // (2**30)))
print("Свободно: %d GiB" % (free // (2**30)))

confirm = input('\nПродолжаем? [y/N]')
if confirm != 'y':
    exit(1)

# ---Получение списка компаний из pivot---#

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Pivot/sh/php/migration/get_active_company_list.php",
    ],
)

if output.exit_code != 0:
    print(output.output.decode("utf-8"))
    scriptutils.error('Получение списка компаний завершилось неудачей')
    exit(1)

output_arrays = output.output.decode("utf-8").splitlines()

# Исправьте данные предварительно
corrected_data = list_of_strings_to_dicts(output_arrays)

# Получаем выбор пользователя
selected_item = get_user_choice(corrected_data)

# Выводим выбранный элемент
print("Вы выбрали:", selected_item)

# ---Вешаем анонс технических работ на компанию---#

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Announcement/sh/php/migration/publish_technical_works_in_progress_company_announcement.php --company_id=%s"
        % selected_item["company_id"],
    ],
)

if output.exit_code == 0:
    print(output.output.decode("utf-8"))
    print(scriptutils.success("Установили анонс технических работ на команду"))
else:
    print(scriptutils.error("Ошибка - не удалось установить анонс технических работ на команду"))
    sys.exit(0)

output_array = output.output.decode("utf-8").splitlines()
announcement_parts = output_array[0].split("=")
announcement_id = int(announcement_parts[1])

# ---Файлы---#

# берем данные из экспорта - файлы
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=file --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
)

if output.exit_code == 0:
    print(output.output.decode("utf-8"))
    print(scriptutils.success("Экспорт файлов из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка при работе с экспортом файлов из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# загружаем файлы
output = found_php_file_node_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/FileNode/sh/php/migration/just_download_files.php --local_manticore_host='%s' --local_manticore_port=%s --save_file_path='/files/migration_files_company_%s/'"
        % (manticore_host, manticore_port, selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Загрузка файлов из Slack выполнена"))
else:
    print(scriptutils.error("Ошибка при работе загрузки файлов из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

current_timestamp = int(time.time())

# импортируем в compass
output = found_php_file_node_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/FileNode/sh/php/migration/just_upload_files.php --local_manticore_host='%s' --local_manticore_port=%s --company_url='%s' --domino_url='%s' --space_id=%s --sender_user_id='%s' --need_work=%i --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], domino_url, selected_item["company_id"], selected_item["created_by_user_id"], current_timestamp),
    ],
    stream=True,
)

for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Загрузка файлов из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка при загрузке файлов из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Пользователи---#

# берем данные из экспорта - пользователи
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=user --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
    stream=True,
)

for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Экпорт пользователей из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка при работе с экспортом пользователей из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Pivot/sh/php/migration/import_user.php --dry=0 --company-id=%s --local_manticore_host='%s' --local_manticore_port=%s --dry=0"
        % (selected_item["company_id"], manticore_host, manticore_port),
    ],
    stream=True,
)

for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция пользователей из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка при миграции пользователей из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Чаты---#

# берем данные из экспорта - чаты
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=channel --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Экспорт чатов из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка при работе с экспортом чатов из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Conversation/sh/php/migration/import_conversations.php --local_manticore_host='%s' --local_manticore_port=%s --company_url='%s' --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция чатов из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка импорта чатов из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Conversation/sh/php/migration/import_group_user.php --local_manticore_host='%s' --local_manticore_port=%s --dry=0 --company_id=%s --company_url='%s'"
        % (manticore_host, manticore_port, selected_item["company_id"], selected_item["url"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция пользователей в чаты из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка выполнения миграции пользователей в чаты из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Сообщения---#

# берем данные из экспорта - сообщения
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=message --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Экспорт сообщений из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка экспорта сообщений чатов из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass сообщения
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Conversation/sh/php/migration/import_messages.php --local_manticore_host='%s' --local_manticore_port=%s --company_url='%s' --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция сообщений чатов из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка при работе с миграцией сообщений чатов из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Треды---#

# берем данные из экспорта - треды
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=thread --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Экспорт тредов из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка при работе с экспортом тредов из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass треды
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Thread/sh/php/migration/import_threads.php --local_manticore_host='%s' --local_manticore_port=%s --company_url='%s' --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция тредов из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка при работе с импортом тредов из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Комментарии---#

# берем данные из экспорта - треды
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=comment --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Экспорт комментариев из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка при работе экспорта комментариев из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass треды
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Thread/sh/php/migration/import_comments.php --local_manticore_host='%s' --local_manticore_port=%s --company_url='%s' --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция сообщений в тредах из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка импорт сообщений в тредах из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Реакции---#

# берем данные из экспорта - реакции
output = exporter_container.exec_run(
    user="root",
    cmd=[
        "bash",
        "-c",
        "php -d display_errors=on /app/main.php --step=reaction --db='%s:%s' --workdir='/app/exported/' --dry=0"
        % (manticore_host, manticore_port),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Экспорт реакций из Slack выполнен"))
else:
    print(scriptutils.error("Ошибка при работе с экспортом реакций из Slack"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass реакции в чат
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Conversation/sh/php/migration/import_reactions.php --local_manticore_host='%s' --local_manticore_port=%s --company_url=%s --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция реакций в чате из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка импорта реакций в чате из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# импортируем в compass реакции в треды
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Thread/sh/php/migration/import_reactions.php --local_manticore_host='%s' --local_manticore_port=%s --company_url=%s --space_id=%s --dry=0"
        % (manticore_host, manticore_port, selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Миграция реакций в тредах из Slack в Compass выполнена"))
else:
    print(scriptutils.error("Ошибка импорта реакций в тредах из Slack в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# запускаем индексацию пространства
output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Conversation/sh/php/migration/start_full_reindex.php --company_url=%s --space_id=%s --dry=0"
        % (selected_item["url"], selected_item["company_id"]),
    ],
    stream=True,
)
for data in output.output:
    print(data.decode())

if output.exit_code == 0 or output.exit_code == None:
    print(scriptutils.success("Запущена индексация поиска"))
else:
    print(scriptutils.error("Ошибка индексации пространства в Compass"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

# ---Убираем анонс технических работ с компании---#

output = found_php_monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php /app/src/Compass/Announcement/sh/php/migration/disable_announcement.php --announcement_id=%s"
        % (announcement_id),
    ],
)

if output.exit_code == 0:
    print(output.output.decode("utf-8"))
    print(scriptutils.success("Убрали анонс технических работ с команды"))
else:
    print(scriptutils.error("Ошибка - не смогли убрать анонс технических работ с команды"))
    print("Для разблокировки команды %s запустите скрипт: " % selected_item["name"])
    print("python3 script/disable_announcement.py --announcement-id=%i" % announcement_id)
    sys.exit(0)

print(scriptutils.success("Миграция данных из Slack в Compass выполнена"))
print(scriptutils.success("Процесс завершен"))
