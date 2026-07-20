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

# папка, где находятся конфиги
config_path = current_script_path.parent.parent / 'configs'

# если отсутствуют файлы-конфиги
if not config_path.exists() or len(os.listdir(config_path)) == 0:
    print(
        scriptutils.warning(
            "Отсутствуют конфиг-файлы в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

team_config_path = config_path / "team.yaml"
if not team_config_path.exists():
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл team.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг team.yaml уже содержит свежие поля
with team_config_path.open("r") as file:
    team_config = yaml.safe_load(file)
    team_config = {} if team_config is None else team_config

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "team_mysql_settings" in team_config:
        print(scriptutils.success("Конфиг-файл team.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = team_config_path.read_text().rstrip()

# добавляем актуальный параметр в конец конфига
content += """

# ----------------------------------------------
# MYSQL КОМАНД
# ----------------------------------------------

# Индивидуальные настройки MySQL для команд.
# Секция необязательная. Если для команды нет записи, используются настройки по умолчанию.
#
# Пример:
# team_mysql_settings:
#   team_1:
#     innodb_buffer_pool_size_mb: 128
#     innodb_thread_concurrency: 8
#     table_open_cache: 400
team_mysql_settings: {}
"""

# сохраняем изменения
team_config_path.write_text(content)
