#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import subprocess, yaml, os, shutil

from utils import scriptutils
from pathlib import Path
from loader import Loader
from time import sleep
from python_on_whales import docker, exceptions

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиг
config = {}
protected_config = {}

# загружаем конфиги
config_path = Path(script_dir + "/../configs/global.yaml")

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

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())

# пишем константы
values_name = "compass"
environment = "production"
stack_name_prefix = environment + "-" + values_name

scriptutils.assert_root()

try:
    if input("Удаляем приложение Compass, продолжить? [y/N]\n") != "y":
        scriptutils.die("Удаление приложения было отменено")
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(0)

# удаляем стаки докера
get_stack_command = ["docker", "stack", "ls"]
grep_command = ["grep", stack_name_prefix]
delete_command = ["xargs", "docker", "stack", "rm"]

# Удаляем стаки
get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
grep_process = subprocess.Popen(
    grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
)
delete_process = subprocess.Popen(
    delete_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
)
output, _ = delete_process.communicate()

loader = Loader(
    "Удаляем приложение...",
    "Успешно удалили приложение",
    "Не смогли удалить приложение",
).start()

# ждем, пока все контейнеры удалятся
timeout = 600
n = 0
while n <= timeout:
    docker_container_list = docker.container.list(filters={"name": stack_name_prefix})

    if len(docker_container_list) < 1:
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die("Приложение не было удалено")

# ждем удаления сетей
timeout = 120
n = 0
while n <= timeout:
    docker_network_list = docker.network.list(filters={"name": stack_name_prefix})

    if len(docker_network_list) < 1:
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die("Приложение не было удалено")

sleep(10)
loader.success()

root_mount_path = config.get("root_mount_path")

if root_mount_path is None:
    scriptutils.die(
        "В конфигурации %s не указан путь до данных приложения, поле root_mount_path"
        % str(config_path.resolve())
    )

root_mount_path = Path(root_mount_path)

if not root_mount_path.exists():
    scriptutils.die(
        "Путь, указанный в конфигурации %s в поле root_mount_path, не существует"
    )

try:
    if (
        input(
            "Удаляем все данные приложения по пути %s, продолжить? [y/N]\n"
            % str(root_mount_path.resolve())
        )
        != "y"
    ):
        scriptutils.die("Удаление данных было отменено")
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(0)

# Команда удаления (все, кроме инсталлятора)
root_path = Path(script_dir + "/../").resolve()
retain = [root_path.resolve()]

for item in root_mount_path.glob("*"):
    if item not in retain:
        if item.is_file():
            item.unlink()
        elif item.is_dir():
            shutil.rmtree(item)

# раз удалили данные, то и текущая конфигурация сервера больше не нужна
values_file_path = Path("%s/../src/values.%s.yaml" % (script_dir, values_name))
values_file_path.unlink()
