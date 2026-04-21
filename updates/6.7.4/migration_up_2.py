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
    global_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "jitsi.service.prosody.entrypoint" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# открываем файл для чтения
with open(global_config_path, "r") as file:
    content = file.read()

# если строка с prosody.v2.serve_port найдена, добавляем новые строки
target_line = "jitsi.service.prosody.v2.serve_port"
if target_line in content:
    # разбиваем файл по строкам
    lines = content.split("\n")

    # ищем строку с портом prosody
    for i, line in enumerate(lines):
        if target_line in line:

            # вставляем новые строки
            # вставляем новые строки
            new_lines = [
                "",
                "# Точка входа для api запросов к prosody, модуля для ВКС",
                "# Запросы для комнаты к компоненту будут отправлять на этот entrypoint.",
                "# ",
                "# Тип данных: строка",
                "# Пример: jitsi.service.prosody.entrypoint: \"http://prosody-jitsi:5280\"",
                "jitsi.service.prosody.entrypoint: \"http://prosody-jitsi:5280\""
            ]

            # вставляем новые строки после текущей
            lines[i+1:i+1] = new_lines

            break  # прерываем цикл после первой найденной строки

    # объединяем обратно в текст
    new_content = "\n".join(lines)

    # записываем в файл
    with open(global_config_path, "w") as file:
        file.write(new_content)
else:
    print(scriptutils.error("Строка с jitsi.service.prosody.v2.serve_port не найдена в конфиг-файле global.yaml"))