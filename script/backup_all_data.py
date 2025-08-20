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
args = parser.parse_args()

values_name = args.values
environment = args.environment
dst = args.destination
stack_name_prefix = environment + '-' + values_name

# путь до директории с инсталятором
installer_dir = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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


# проверяем права доступа у пользователя к удаленой директории
def check_remote_folder():

    # разбиваем destination на user@host и удаленую директорию куда копируем файлы
    remote_host, remote_path = dst.split(":", 1)

    # проверяем, что у пользователя есть права для записи в директорию
    cmd = f'ssh {remote_host} "test -d {remote_path} && test -w {remote_path} || echo ERROR"'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    if "ERROR" in result.stdout or result.returncode != 0:
        scriptutils.die(f"Ошибка: У пользователя нет доступа к удаленой директории {remote_path}")


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
    cmd = ["python3", script_path]

    # запускаем команду
    try:

        start_time = time.time()
        loader = Loader("Делаем резервную копию базы данных", "Сделали резервную копию базы данных").start()
        subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        loader.success()
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Создание резервной копии базы данных заняло: {elapsed_time:.2f} sec")
    except subprocess.CalledProcessError as e:
        print(scriptutils.error("Не удалось сделать резервную копию базы данных, ошибка:"))
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

    # получим и выведем размер директории src для справки
    directory_size = get_directory_size(src)
    print(f"Размер директории с резервной копией {src}: {directory_size / (1024 * 1024):.2f} MB")

    # флаги rsync
    flags = "-avzu"

    # формируем команду
    cmd = ["rsync", flags, src, dst]

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
        print(scriptutils.error("Не удалось отправить резервную копию в указанное место, ошибка:"))
        print(e)
        print(e.stdout)
        print(e.stderr)
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
