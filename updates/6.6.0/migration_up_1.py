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

# удаляет:
# - строки с полями
# - комментарии/пустые строки над полем
# - пустые строки сразу после поля
def remove_fields_with_comments(file_content, attrs):

    lines = file_content.splitlines()
    result = []

    # паттерн
    attr_patterns = [
        re.compile(r'^\s*' + re.escape(attr) + r'\s*:')
        for attr in attrs
    ]

    i = 0
    while i < len(lines):
        line = lines[i]

        # проверяем, является ли строка одним из удаляемых полей
        is_attr_line = any(patt.match(line) for patt in attr_patterns)

        if is_attr_line:

            # удаляем комментарии/пустые строки над полем
            while result and (
                    result[-1].lstrip().startswith("#") or result[-1].strip() == ""
            ):
                result.pop()

            # пропускаем саму строку с полем
            i += 1

            # удаляем пустые строки сразу после поля (косметика)
            while i < len(lines) and lines[i].strip() == "":
                i += 1

            continue

        # обычная строка — просто добавляем
        result.append(line)
        i += 1

    return "\n".join(result) + "\n"


# папка, где находятся конфиги
config_path = current_script_path.parent.parent / "configs"

# если отсутствуют файлы-конфиги
if len(os.listdir(config_path)) == 0:
    print(
        scriptutils.warning(
            "Отсутствуют конфиг-файлы в директории configs/.. - миграция не требуется. "
            "Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    sys.exit(0)

global_config_path = str(config_path / "global.yaml")
if not os.path.exists(global_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл global.yaml в директории configs/.. - миграция не требуется. "
            "Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    sys.exit(0)

# читаем содержимое global.yaml
with open(global_config_path, "r") as file:
    content = file.read()

# список полей, которые нужно удалить вместе с их комментариями
fields_to_remove = [
    "janus.service.janus.port",
    "janus.service.janus.admin_port",
    "janus.service.janus.rtp_port_from",
    "janus.service.janus.rtp_port_to",
    "janus.service.coturn.external_port",
    "janus.service.coturn.external_tls_port",
    "janus.service.coturn.exchange_port_from",
    "janus.service.coturn.exchange_port_to",
    "janus.service.nginx.external_https_port",
]

content = remove_fields_with_comments(content, fields_to_remove)

# сохраняем изменения
with open(global_config_path, "w") as file:
    file.write(content)
