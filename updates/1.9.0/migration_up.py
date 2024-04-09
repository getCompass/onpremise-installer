#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import re, socket, yaml, argparse, readline, string, random, pwd, os, subprocess

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils
from python_on_whales import docker, exceptions
from time import sleep

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

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

team_config_path = str(config_path) + "/team.yaml"
if False == os.path.exists(team_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл team.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг team.yaml уже содержит свежие поля
with open(team_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "profile.phone_change_enabled" in content:
        print(scriptutils.success("Конфиг-файл team.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

docker_monolith_network_list = docker.network.list(filters={"name": "production-compass-monolith_monolith-private"})
if len(docker_monolith_network_list) > 0:

    get_stack_command = ["docker", "stack", "ls"]
    grep_command = ["grep", "production-compass-monolith"]
    delete_command = ["xargs", "docker", "stack", "rm"]

    try:

        get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
        grep_process = subprocess.Popen(
            grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
        )
        delete_process = subprocess.Popen(
            delete_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
        )
        output, _ = delete_process.communicate()
    except Exception as e:
        print(f"{str(e)}")

    # ждем удаления сетей
    timeout = 1200
    n = 0
    while n <= timeout:
        docker_network_list = docker.network.list(filters={"name": "production-compass-monolith_monolith-private"})

        if len(docker_network_list) < 1:
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die("Миграция не выполнена")

    sleep(10)

# добавляем актуальные параметры в конец конфига
content += """

# ----------------------------------------------
# РЕДАКТИРОВАНИЕ ПРОФИЛЯ
# ----------------------------------------------

# Разрешено ли пользователям изменять номер телефона в профиле
profile.phone_change_enabled: true

# Разрешено ли пользователям изменять почтовый адрес в профиле
profile.mail_change_enabled: true

# Разрешено ли пользователям изменять Имя Фамилия в профиле
profile.name_change_enabled: true

# Разрешено ли пользователям изменять аватар в профиле
profile.avatar_change_enabled: true

# Разрешено ли пользователям изменять бейдж в профиле
profile.badge_change_enabled: true

# Разрешено ли пользователям изменять описание в профиле
profile.description_change_enabled: true

# Разрешено ли пользователям изменять статус в профиле
profile.status_change_enabled: true"""

team_config = open(team_config_path, "w")
team_config.write(content)
team_config.close()
