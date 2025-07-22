#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import yaml
import re

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / "script"
sys.path.append(str(utils_path))

from utils import scriptutils

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

# папка, где находятся конфиги
config_path = current_script_path.parent.parent / "configs"

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
    if "jitsi.service.prosody.v0.serve_port" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# открываем файл для чтения
with open(global_config_path, "r") as file:
    content = file.read()

# если строка с prosody.serve_port найдена, добавляем новые порты после нее
target_line = "jitsi.service.prosody.serve_port:"
if target_line in content:
    # разбиваем файл по строкам
    lines = content.split("\n")

    # ищем строку с портом prosody
    for i, line in enumerate(lines):
        if target_line in line:
            # получаем текущий порт (35002 или другой)
            current_port = int(line.split(":")[-1].strip())

            # формируем новые строки
            new_lines = [
                f"jitsi.service.prosody.v0.serve_port: {current_port + 1}",
                f"jitsi.service.prosody.v1.serve_port: {current_port + 2}",
                f"jitsi.service.prosody.v2.serve_port: {current_port + 3}"
            ]

            # вставляем новые строки (учитываем, есть ли уже такие записи)
            if not any("prosody.v0.serve_port" in l for l in lines[i+1:i+4]):
                lines[i+1:i+1] = new_lines  # вставляем после текущей строки

            break  # прерываем цикл после первой найденной строки

    # объединяем обратно в текст
    new_content = "\n".join(lines)

    # записываем в файл
    with open(global_config_path, "w") as file:
        file.write(new_content)
else:
    print(scriptutils.error("Строка с jitsi.service.prosody.serve_port не найдена в конфиг-файле global.yaml"))