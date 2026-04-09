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

replication_config_path = str(config_path) + "/replication.yaml"
if False == os.path.exists(replication_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл replication.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг replication.yaml уже содержит свежие поля
with open(replication_config_path, "r") as file:
    # считываем конфиг
    replication_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "master_state_changed_disable" in replication_config:
        print(scriptutils.success("Конфиг-файл replication.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = open(replication_config_path).read().rstrip()

# добавляем актуальный параметр в конец конфига
content += f"""

# Запрет на отключение автоматического перехода сервера в Master состояние
# Используется в случае перехода сервера в Backup состояние,
# после чего приложение не позволит без ручного вмешательства администратора автоматическое переключение в Master состояние
#
# Тип данных: булево значение, true\\false
# Пример: master_state_changed_disable: true
master_state_changed_disable: true
"""

# сохраняем изменения
replication_config = open(replication_config_path, "w")
replication_config.write(content)
replication_config.close()
