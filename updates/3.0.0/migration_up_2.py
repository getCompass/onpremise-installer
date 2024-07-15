#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import re, socket, yaml, argparse, readline, string, random, pwd, os

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

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

auth_config_path = str(config_path) + "/team.yaml"
if False == os.path.exists(auth_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл team.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг team.yaml уже содержит свежие поля
with open(auth_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "root_user.sso_login" in content:
        print(scriptutils.success("Конфиг-файл team.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем актуальные параметры в конец конфига
content += """
# SSO логин используемый для авторизации через SSO.
# В поле необходимо указать почту или номер телефона, используемый при логине через SSO.
#
# Тип данных: строка, пример: "example@mail.example" или "+79220000000"
root_user.sso_login:"""

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()

# проверяем доступна ли сейчас авторизация через SSO
auth_config_path = str(config_path) + "/auth.yaml"
if False == os.path.exists(auth_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл auth.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# парсим файл
with open(auth_config_path, "r") as file:

    # читаем содержимое файла
    content = file.read()

    # ищем sso в available_methods
    match = re.search(r'available_methods.*sso', content)
    if match is not None:
        print(scriptutils.success('Если хотите авторизоваться в аккаунт root-пользователя через SSO, то заполните root_user.sso_login в configs/team.yaml и запустите script/add_root_user_sso_login.py для применения изменений'))

auth_config.close()