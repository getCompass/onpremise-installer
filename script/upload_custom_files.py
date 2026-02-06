#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl python-dotenv

import sys

sys.dont_write_bytecode = True

import argparse, yaml, subprocess, pwd
import docker
from pathlib import Path
from utils import scriptutils
from time import sleep
from loader import Loader

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором разворачиваем')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

values_name = "compass"
values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"

script_dir = str(Path(__file__).parent.resolve())

values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, values_arg))

if not values_file_path.exists():
    scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

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


# ---СКРИПТ---#

def start():
    # необходимые пользователи для окржуения
    required_user_list = ['www-data']

    # проверяем наличие необходимых пользователей
    for user in required_user_list:

        try:
            pwd.getpwnam(user)
        except KeyError:
            scriptutils.die('Необходимо создать пользователя окружения' + user)

    client = docker.from_env()

    loader = Loader("Загружаем файлы...", "Успешно загрузили файлы", "Не смогли загрузить файлы").start()
    subprocess.run(
        [
            sys.executable,
            script_dir + "/prepare_custom_files.py",
            "-e",
            environment,
            "-v",
            values_name
        ]
    ).returncode == 0 or scriptutils.die("Ошибка при подготовке файлов к загрузке")

    # получаем контейнер php-монолита
    timeout = 30
    n = 0
    while n <= timeout:

        docker_container_list = client.containers.list(
            filters={'name': '%s_php-monolith' % (stack_name), 'health': 'healthy'})

        if len(docker_container_list) > 0:
            found_php_monolith_container = docker_container_list[0]
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die(
                'Не был найден необходимый docker-контейнер для запуска скриптов. Убедитесь, что окружение поднялось корректно')

    exec_script_list = [
        'php src/Compass/Pivot/sh/php/service/upload_custom_file_list.php',
        'php src/Compass/Pivot/sh/php/service/check_custom_file_list.php',
    ]

    for script in exec_script_list:

        output = found_php_monolith_container.exec_run(user='www-data', cmd=['bash', '-c', script])

        if output.exit_code != 0:
            print(output.output.decode("utf-8"))
            scriptutils.error('Что-то пошло не так. Выполнение одного из скриптов завершилось неудачей')
            exit(1)

    loader.success()

start()
