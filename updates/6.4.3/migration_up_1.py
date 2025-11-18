#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import yaml, re

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

# читаем содержимое файла
content = open(global_config_path, encoding="utf-8").read().rstrip()

# если поле уже присутствует (и не закомментировано) — ничего не делаем
if re.search(r'(?m)^[ \t]*(?!#)websocket_port[ \t]*:', content):
    print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
    exit(0)

# регулярка для строки-анкера (не закомментированная)
regex = r'(?m)^([ \t]*(?!#)company\.end_port[ \t]*:.*)$'

new_block = (
    "# Необязательный параметр. Порт для подключения клиентских приложений к серверу по websocket протоколу\n"
    "# Если не заполнен, то по умолчанию используется 443\n"
    "# Не используйте порты 6660-6669, они исторически режутся провайдерами как подозрительные, из-за чего подключение не произойдет\n"
    "#\n"
    "# Тип данных: число\n"
    "# Пример: websocket_port: 9502\n"
    "websocket_port: 0"
)

# вставляем после найденной строки: сама строка + пустая строка + нужный блок
paste_content = (
        r"\g<1>\n\n"
        + new_block
)

new_content = re.sub(regex, paste_content, content, count=1)

# если якорь не найден — добавляем блок в конец файла
if new_content == content:
    if not content.endswith("\n"):
        content += "\n"
    new_content = (
            content
            + "\n"
            + new_block
    )

global_config = open(global_config_path, "w", encoding="utf-8")
global_config.write(new_content)
global_config.close()
