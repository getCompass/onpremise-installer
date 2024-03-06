#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import os, argparse, yaml, pwd, json, psutil
from python_on_whales import docker, exceptions
from pathlib import Path
from utils import scriptutils
from subprocess import Popen
from time import sleep
import shutil
from loader import Loader
import mysql.connector

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument(
    "-v", "--values", required=False, type=str, help="Название values файла окружения"
)
parser.add_argument(
    "-e",
    "--environment",
    required=False,
    type=str,
    help="Окружение, в котором разворачиваем",
)

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()


user_fields = [
    {
        "name": "username",
        "comment": "Введите имя создаваемого пользователя",
        "default_value": "Ivan Ivanov",
        "type": "str",
        "ask": True,
    },
    {
        "name": "phone_number",
        "comment": "Введите номер телефона в международном формате",
        "default_value": "+7999999999",
        "type": "str",
        "ask": True,
    },
]

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg

# необходимые пользователи для окружения
required_user_list = ["www-data"]

# проверяем наличие необходимых пользователей
for user in required_user_list:
    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die("Необходимо создать пользователя окружения" + user)

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
            "php src/Compass/Pivot/sh/php/domino/create_user.php --dry=0",
        ],
        interactive=True,
        tty=True,
    )
    print(output)
except exceptions.DockerException:
    print(output)
    scriptutils.error(
        "Что то пошло не так. Не смогли создать пользователя. Проверьте, что окружение поднялось корректно"
    )
