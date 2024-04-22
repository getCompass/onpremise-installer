#!/usr/bin/env python3
#pip3 install pyyaml pyopenssl python_on_whales mysql_connector_python python-dotenv psutil

import sys
sys.dont_write_bytecode = True

import argparse, yaml, psutil
from python_on_whales import docker, exceptions, Container
from pathlib import Path
from utils import scriptutils, interactive
from loader import Loader
from time import sleep

#---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором разворачиваем')

args = parser.parse_args()
#---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

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

#---СКРИПТ---#

def start():

    timeout = 10
    n = 0
    name = "%s-monolith_php-monolith" % (stack_name_prefix)

    while n <= timeout:

        docker_container_list = docker.container.list(filters={'name': name, 'health': 'healthy'})

        if len(docker_container_list) > 0:

            found_container = docker_container_list[0]
            break

        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die('Не был найден необходимый docker контейнер для активации сервера. Проверьте что окружение поднялось корректно')

    try:

        loader = Loader('Активирую сервер...', 'Сервер активирован', 'Не смог активировать сервер').start()
        output = found_container.execute(user='www-data', command=['bash', '-c', 'php src/Compass/Premise/sh/php/server/activate.php'])
        loader.success()
    except exceptions.DockerException as e:

        loader.error()
        print(e.stderr)
        print(e.stdout)

        scriptutils.error('Что то пошло не так. Не смогли активировать сервер')

start()