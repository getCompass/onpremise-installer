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

database_config_path = str(config_path) + "/database.yaml"
if False == os.path.exists(database_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл database.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг database.yaml уже содержит свежие поля
with open(database_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "database_encryption:" in content:
        print(scriptutils.success("Конфиг-файл database.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем актуальные параметры в конец конфига
content += """

# Параметры шифрования базы данных. Приложение шифрует данные сообщений
# и комментариев до передачи данных в БД. Таким образом получение
# доступа к БД или к резервной копии не даст доступа к содержимому переписок.
#
# Compass On-premise может работать в следующих режимах:
#   — none — шифрование отключено;
#   — read_write — поддержка чтения зашифрованных данных, запись зашифрованных данных;
#   — read — поддержка чтения зашифрованных данных, запись незашифрованных данных.
#
# Важно! После первого включения режима read_write переключиться на режим none нельзя.
database_encryption:

  # Режим шифрования (none, read_write, read).
  mode: \"none\"

  # Мастер-ключ шифрования. Данные не будут зашифрованы этим ключом, данный ключ используется
  # для расшифровывания ключа-секрета во время исполнения.
  master_key: \"\"
"""

database_config = open(database_config_path, "w")
database_config.write(content)
database_config.close()