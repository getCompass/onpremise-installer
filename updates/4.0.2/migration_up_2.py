#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import re, socket, yaml, argparse, readline, string, random, pwd, os, subprocess

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from loader import Loader
from utils import scriptutils
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

auth_config_path = str(config_path) + "/auth.yaml"
if False == os.path.exists(auth_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл auth.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг auth.yaml уже содержит свежие поля
with open(auth_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "auth.is_desktop_prohibited" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем актуальные параметры в конец конфига
content += """

# ----------------------------------------------
# ЗАПРЕТ НА АВТОРИЗАЦИЮ С ПЛАТФОРМ
# ----------------------------------------------

# Запрещено ли пользователям с ПК авторизовываться в приложении.
#
# Тип данных: булево значение, true\\false
auth.is_desktop_prohibited: false

# Запрещено ли пользователям с ios авторизовываться в приложении.
#
# Тип данных: булево значение, true\\false
auth.is_ios_prohibited: false

# Запрещено ли пользователям с android авторизовываться в приложении.
#
# Тип данных: булево значение, true\\false
auth.is_android_prohibited: false"""

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()
