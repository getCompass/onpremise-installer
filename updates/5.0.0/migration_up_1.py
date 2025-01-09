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

team_config_path = str(config_path) + "/team.yaml"
if False == os.path.exists(team_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл team.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг auth.yaml уже содержит свежие поля
with open(team_config_path, "r") as file:
    # считываем конфиг
    auth_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "file.access_restriction_mode" in auth_config:
        print(scriptutils.success("Конфиг-файл team.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = open(team_config_path).read()

# добавляем актуальный параметр в конец конфига
content += """

# ----------------------------------------------
# Авторизация перед загрузкой файла
# ----------------------------------------------

# Ограничение доступа к файлам, загруженным в команды, по прямой ссылке. Возможные варианты:
#   — none — проверка не производится, файл всегда доступен по прямой ссылке;
#   — auth — проверка авторизации перед загрузкой — только участник команды может загрузить файл.
file.access_restriction_mode: "none"
"""

auth_config = open(team_config_path, "w")
auth_config.write(content)
auth_config.close()
