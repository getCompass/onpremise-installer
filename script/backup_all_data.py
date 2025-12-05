#!/usr/bin/env python3

# Скрипт выполняет резервное копирование всех данных окружения
# Может запускаться на горячую, без остановки приложения

import sys

sys.dont_write_bytecode = True

import argparse, yaml, shutil
from utils import scriptutils
from pathlib import Path
import subprocess
import os
import socket
from loader import Loader

scriptutils.assert_root()

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=True)

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
    scriptutils.check_remote_folder(dst)

    # копируем инсталятор
    copy_installer()
    print(scriptutils.success("Скопировали инсталятор"))

    loader = Loader(
        "Делаем резервную копию базы данных",
        "Сделали резервную копию базы данных",
        "Не удалось сделать резервную копию базы данных").start()

    # бэкапим базу данных
    try:
        scriptutils.backup_db(installer_dir, backups_folder, backup_name_format, threshold_percent, auto_cleaning_limit,
                              userbot_notice_chat_id, userbot_notice_token, userbot_notice_domain, userbot_notice_text)
        loader.success()
    except subprocess.CalledProcessError as e:
        loader.error()
        print(e)
        print(e.stdout)
        print(e.stderr)
        scriptutils.die("Исправьте проблему и выполните скрипт снова")

    # отправляем резервную копию
    scriptutils.transfer_data(get_values(), dst, hostname, backups_folder, userbot_notice_text, userbot_notice_token,
                              userbot_notice_chat_id, userbot_notice_domain)


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
