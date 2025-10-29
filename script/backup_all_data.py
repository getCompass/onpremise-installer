#!/usr/bin/env python3

# Скрипт выполняет резервное копирование всех данных окружения
# Может запускаться на горячую, без остановки приложения

import sys

sys.dont_write_bytecode = True

import argparse, yaml, os, shutil
from utils import scriptutils
from pathlib import Path
from loader import Loader
import subprocess
import time
import os
import socket

scriptutils.assert_root()

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument(
    "-dst",
    "--destination",
    required=True,
    type=str,
    help="место, куда будет отправлена резервная копия",
)

parser.add_argument(
    "-e",
    "--environment",
    required=False,
    default="production",
    type=str,
    help="окружение",
)

parser.add_argument(
    "-v",
    "--values",
    required=False,
    default="compass",
    type=str,
    help="название файла со значениями для деплоя",
)
parser.add_argument('-y', '--yes', required=False, action='store_true', help='Согласиться на все')
parser.add_argument("--backups-folder", required=False, default="", type=str, help="директория для хранения бэкапов")
parser.add_argument("--backup-name-format", required=False, default="%d_%m_%Y", type=str,
                    help="формат имени папки бэкапа")
parser.add_argument("--free-threshold-percent", required=False, default=0, type=int,
                    help="пороговое значение свободного места в процентах для возможности создания бэкапа")
parser.add_argument("--auto-cleaning-limit", required=False, default=0, type=int,
                    help="лимит для автоматической очистки бэкапов, если их количество превышает указанный лимит")
parser.add_argument("--userbot-notice-chat-id", required=False, default="", type=str,
                    help="id чата для отправки уведомления")
parser.add_argument("--userbot-notice-token", required=False, default="", type=str,
                    help="токен бота для отправки уведомления")
parser.add_argument("--userbot-notice-domain", required=False, default="", type=str,
                    help="домен, на который отправляется запрос уведомления")
parser.add_argument("--userbot-notice-text", required=False, default="", type=str,
                    help="текст уведомления от бота в случае, если не смогли создать бэкап")
args = parser.parse_args()

values_name = args.values
environment = args.environment
dst = args.destination
backups_folder = args.backups_folder
backup_name_format = args.backup_name_format
threshold_percent = args.free_threshold_percent
auto_cleaning_limit = args.auto_cleaning_limit
userbot_notice_chat_id = args.userbot_notice_chat_id
userbot_notice_token = args.userbot_notice_token
userbot_notice_domain = args.userbot_notice_domain
userbot_notice_text = args.userbot_notice_text

stack_name_prefix = environment + '-' + values_name

# путь до директории с инсталятором
installer_dir = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

hostname = socket.gethostname()

# точка входа в скрипт бэкапа всех данных
def start():
    # проверяем, что что установлен rsync
    if is_rsync_installed() == False:
        scriptutils.die("Для работы скрипта необходимо установить утилиту rsync")

    # проверяем права доступа у пользователя к удаленой директории
    check_remote_folder()

    # копируем инсталятор
    copy_installer()
    print(scriptutils.success("Скопировали инсталятор"))

    # бэкапим базу данных
    backup_db()

    # отправляем резервную копию
    transfer_data()


# проверяем, что что установлен rsync
def is_rsync_installed():
    try:
        # попытка выполнить команду rsync --version
        result = subprocess.run(['rsync', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # если код возврата равен 0, rsync установлен
        if result.returncode == 0:
            return True
        else:
            return False
    except FileNotFoundError:

        # команда rsync не найдена
        return False

def parse_destination(dst: str):
    # если строка содержит "user@host:/path" или "host:/path"
    # и не начинается с "/" (чтобы не спутать с локальным путём)
    if ":" in dst and not dst.startswith("/"):
        remote_host, remote_path = dst.split(":", 1)
        return True, remote_host, remote_path
    return False, None, dst

# проверяем права доступа у пользователя к удаленой директории
def check_remote_folder():

    is_remote, remote_host, path = parse_destination(dst)

    if is_remote:
        # проверяем, что у пользователя есть права для записи в директорию
        # сначала проверяем, существует ли директория. Если нет, создаем ее.
        cmd = f'ssh {remote_host} "if [ ! -d {path} ]; then mkdir -p {path}; fi && test -w {path}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if "ERROR" in result.stdout or result.returncode != 0:
            scriptutils.die(f"Ошибка: У пользователя нет доступа к удаленой директории {path}")
    else:
        # локальная директория
        if not os.path.exists(path):
            # создаем директорию, если ее нет
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                scriptutils.die(f"Не удалось создать локальную директорию {path}: {str(e)}")

        # проверяем право на запись
        if not os.path.exists(path):
            scriptutils.die(f"Локальная директория {path} не существует после попытки создания.")
        if not os.access(path, os.W_OK):
            scriptutils.die(f"Нет прав на запись в локальную директорию {path}")

# создаем директорию
def create_destination_directory(path, is_remote=False, remote_host=None):
    if is_remote:
        # Для удаленного пути используем SSH для создания директории
        cmd = f'ssh {remote_host} "mkdir -p {path}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            scriptutils.die(f"Не удалось создать удаленную директорию {path} через SSH")
    else:
        # Для локального пути используем os.makedirs
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            scriptutils.die(f"Не удалось создать локальную директорию {path}: {str(e)}")

# копируем инсталятор
def copy_installer():
    # получаем значения для выбранного окружения
    current_values = get_values()

    # путь куда копируем
    dst = "%s/installer" % (current_values["root_mount_path"])

    # копируем конфигурацию
    shutil.copytree(installer_dir, dst, dirs_exist_ok=True)


# бэкапим базу данных
def backup_db():
    # путь до скрипта
    script_path = "%s/script/backup_db.py" % (installer_dir)

    # формируем команду
    cmd = ["python3", script_path,
        "--backups-folder", backups_folder,
        "--backup-name-format", backup_name_format,
        "--free-threshold-percent", str(threshold_percent),
        "--auto-cleaning-limit", str(auto_cleaning_limit),
        "--userbot-notice-chat-id", userbot_notice_chat_id,
        "--userbot-notice-token", userbot_notice_token,
        "--userbot-notice-domain", userbot_notice_domain,
        "--userbot-notice-text", userbot_notice_text,
    ]

    # запускаем команду
    try:

        start_time = time.time()
        loader = Loader(
            "Делаем резервную копию базы данных",
            "Сделали резервную копию базы данных",
            "Не удалось сделать резервную копию базы данных").start()
        subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        loader.success()
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Создание резервной копии базы данных заняло: {elapsed_time:.2f} sec")
    except subprocess.CalledProcessError as e:
        loader.error()
        print(e)
        print(e.stdout)
        print(e.stderr)
        scriptutils.die("Исправьте проблему и выполните скрипт снова")


# отправляем резервную копию в указанное место
def transfer_data():
    # получаем значения для выбранного окружения
    current_values = get_values()

    # директорию, которую копируем
    src = current_values["root_mount_path"]
    src_dirs = [current_values["root_mount_path"]]

    # получим и выведем размер директории src для справки
    directory_size = get_directory_size(src)
    print(f"Размер директории с резервной копией {src}: {directory_size / (1024 * 1024):.2f} MB")

    if backups_folder != "":
        directory_size = get_directory_size(backups_folder)
        print(f"Размер директории с бэкапами баз данных {backups_folder}: {directory_size / (1024 * 1024):.2f} MB")
        src_dirs = [current_values["root_mount_path"], backups_folder]

    # флаги rsync
    flags = "-avzu"

    # формируем команду
    cmd = ["rsync", flags, *src_dirs, dst]

    # запускаем команду
    try:

        start_time = time.time()
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # выводим в рилтайме лог выполнения
        while True:
            output = process.stdout.readline()
            if output == b'' and process.poll() is not None:
                break
            if output:
                print(output.strip().decode())

        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Отправка резервной копии заняла: {elapsed_time:.2f} sec")
    except subprocess.CalledProcessError as e:
        error_text = "Не удалось отправить резервную копию в указанное место!"
        print(scriptutils.error(error_text))
        print(e)
        print(e.stdout)
        print(e.stderr)
        message_text = f"*{hostname}*: {userbot_notice_text if userbot_notice_text.strip() else error_text}"
        scriptutils.send_userbot_notice(userbot_notice_token, userbot_notice_chat_id, userbot_notice_domain, message_text)
        scriptutils.die("Исправьте проблему и выполните скрипт снова")


# функция для расчета размера директории
def get_directory_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)

            # пропускаем символические ссылки
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


# получить данные окружение из values
def get_values() -> dict:
    default_values_file_path = Path("%s/src/values.yaml" % (installer_dir))
    values_file_path = Path("%s/src/values.%s.yaml" % (installer_dir, values_name))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


def merge(a: dict, b: dict, path=[]):
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] != b[key]:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a


# точка входа в скрипт
start()
