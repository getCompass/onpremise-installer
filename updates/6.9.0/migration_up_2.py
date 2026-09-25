#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import yaml
import re

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

global_config_path = str(config_path) + "/global.yaml"
if False == os.path.exists(global_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл global.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг global.yaml уже содержит свежие поля
with open(global_config_path, "r") as file:
    # считываем конфиг
    global_config = yaml.safe_load(file) or {}

    # если в содержимом уже имеются оба новых поля, то ничего не делаем
    if "web.is_enabled" in global_config and "web.service.external_port" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
with open(global_config_path, "r") as file:
    content = file.read().rstrip()

# добавляем только отсутствующие параметры в конец конфига
if "web.is_enabled" not in global_config:
    content += """

# Веб-версия приложения
#
# Позволяет работать в Compass из браузера без установки приложения.
# После включения веб-версия будет доступна по адресу: https://<domain>/web/
#
# Тип данных: булево значение, true\\false
web.is_enabled: true

"""

if "web.service.external_port" not in global_config:
    content = content.rstrip() + """

# Внешний порт для контейнера с веб-версией.
# Запросы к веб-версии будут пересылаться на этот порт.
#
# Тип данных: число
# Пример: web.service.external_port: 31107
web.service.external_port: 31107

"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()
