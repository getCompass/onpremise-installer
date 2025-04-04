#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import yaml

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
    global_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "is_need_index_web" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = open(global_config_path).read().rstrip()

# добавляем актуальный параметр в конец конфига
content += """

# Разрешено ли поисковикам индексировать страницу авторизации.
# По умолчанию индексация отключена.
#
# Тип данных: булево значение, true\\false
is_need_index_web: false

# Включено ли ограничение на звонки на сервере.
# По умолчанию выключено.
#
# Тип данных: булево значение, true\\false
is_portable_calls_disabled: false
"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()