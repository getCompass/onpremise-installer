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
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "url_parsing_flag:" in content:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем новые поля sentry_dsn_key_*
content += """
# Включено ли ограничение на звонки на сервере.
# По умолчанию выключено.
#
# Тип данных: булево значение, true\\false
is_portable_calls_disabled: false

# ----------------------------------------------
# ПРЕДПРОСМОТР ССЫЛОК
# ----------------------------------------------

# Позволяет отображать в приложении информацию (превью) из мета-тегов сайта
# при отправке ссылки отдельным сообщением.
#
# true – предпросмотр ссылок активен, зависит от того, какие домены перечислены в белом и чёрном списках.
# Если оба списка пусты, превью отображается у всех ссылок без исключений.
# false – предпросмотр ссылок отключен, превью не отображается ни у одной из ссылок.
#
# Тип данных: булево значение, true\\false
url_parsing_flag: true

# Массивы ссылок
#
# Заполнен только список white_list - превью отображается только у ссылок с доменами,
# заполненными в списке white_list. Превью не отображается у ссылок с другими доменами.
# Заполнен только список black_list - превью НЕ отображается только у ссылок с доменами,
# заполненными в списке black_list. Превью отображается у ссылок с другими доменами.
# Заполнены оба списка white_list и black_list - превью отображается только у ссылок с доменами,
# заполненными в списке white_list.
# Пример: white_list: ["example.com", "my-domain.com"]
white_list: []
black_list: []
"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()