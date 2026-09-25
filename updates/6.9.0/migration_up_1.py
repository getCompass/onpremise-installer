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
    replication_config = yaml.safe_load(file) or {}

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "peer_host" in replication_config:
        print(scriptutils.success("Конфиг-файл replication.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
with open(replication_config_path, "r") as file:
    content = file.read().rstrip()

# добавляем актуальный параметр в конец конфига
content += f"""

# Внутренний IP-адрес или hostname второго сервера отказоустойчивости
# значение обязательно, если заполнен service_label
# порт и протокол указывать не нужно
#
# Тип данных: строка
# Пример: peer_host: "192.168.1.5"
peer_host: ""

"""

# сохраняем изменения
replication_config = open(replication_config_path, "w")
replication_config.write(content)
replication_config.close()
