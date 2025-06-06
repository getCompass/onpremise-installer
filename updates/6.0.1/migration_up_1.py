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
    if "ldap.profile_update_enabled" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем новые поля для протокола LDAP
content += """
# Включен ли мониторинг обновления учетной записи LDAP для запуска автоматического
# обновления связанного пользователя в Compass.
#
# Тип данных: булево значение, пример: true\\false
ldap.profile_update_enabled: false

# Временной интервал между проверками мониторинга обновления пользователя LDAP.
# Обязателен к заполнению в случае включенного параметра ldap.profile_update_enabled
#
# Тип данных: строка формата:
# Nm – интервал каждые N минут
# Nh – интервал каждые N часов
# Минимальное значение - 1m
# Пример: 5m – интервал каждые 5 минут
ldap.profile_update_interval: "5m"
"""

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()