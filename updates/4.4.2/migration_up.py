#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os

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

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "sso.web_auth_ldap_description_text" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем актуальные параметры в конец конфига
content += """

# Кастомизация текста подсказки на экране авторизации через LDAP на веб-сайте On-Premise решения.
#
# Тип данных: строка
sso.web_auth_ldap_description_text: "Для авторизации введите username и пароль от вашей корпоративной учётной записи LDAP:\""""

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()