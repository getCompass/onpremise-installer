#!/usr/bin/env python3

import sys

import docker.models
import docker.models.containers
import docker.models.networks
from typing import List

sys.dont_write_bytecode = True

from pathlib import Path
import re, socket, yaml, argparse, readline, string, random, pwd, os, subprocess

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from loader import Loader
from utils import scriptutils
import docker
from time import sleep

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

need_update = False
client = docker.from_env()

container_list : List[docker.models.containers.Container] = client.containers.list(filters={"name": "company_mysql"})

# проверяем, есть ли мускулы на хостовой сети. Если есть - сервер надо апдейтить
for container in container_list:
    
    if container.attrs["NetworkSettings"].get("Networks") is not None and container.attrs["NetworkSettings"]["Networks"].get("host") is not None:
        need_update = True

if not need_update:
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

loader = Loader(
    "Обновляем приложение...",
    "Успешно обновили приложение",
    "Не смогли обновить приложение",
).start()

get_stack_command = ["docker", "stack", "ls"]
grep_command = ["grep", "-E", r'production-compass-integration|production-compass-monolith']
awk_command = ["awk", '{print $1}']
delete_command = ["xargs", "docker", "stack", "rm"]

try:

    get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
    grep_process = subprocess.Popen(
        grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
    )
    awk_process = subprocess.Popen(
        awk_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
    )
    delete_process = subprocess.Popen(
        delete_command, stdin=awk_process.stdout, stdout=subprocess.PIPE
    )
    output, _ = delete_process.communicate()
except Exception as e:
    print(f"{str(e)}")

# ждем удаления сетей
timeout = 1200
n = 0
while n <= timeout:
    docker_network_list = client.networks.list(names=["production-compass-monolith-private"])

    if len(docker_network_list) < 1:
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        loader.error()
        scriptutils.die("Миграция не выполнена")

sleep(10)
loader.success()

# регенерируем сертификаты
subprocess.run(
    [
        sys.executable,
        script_dir + "/../../script/generate_ssl_certificates.py",
        "--force"
    ]
).returncode == 0 or scriptutils.die("Ошибка при генерации сертификатов")