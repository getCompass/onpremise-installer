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
    if "outlook_add_in.is_enabled" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = open(global_config_path).read().rstrip()

spec = yaml.load(content, Loader=yaml.BaseLoader)
port_list = []
for k, v in spec.items():
    if str(k).endswith("_port") and not str(k).startswith("company") and not str(k).startswith("jitsi"):
        port_list.append(int(v))

max_port = max(port_list)

if max_port < 1:
    scriptutils.error("Не найден ни один порт в global.yaml, проверьте валидность конфигурации")
    exit(1)

# добавляем актуальный параметр в конец конфига
content += f"""

# Внешний порт для контейнера с API гейтвеем. 
# Все запросы к API приложения будут перенаправляться на этот порт.
#
# Тип данных: число
# Пример: api_gateway.service.go_api_gateway.external_https_port: 31103
api_gateway.service.go_api_gateway.external_https_port: {max_port + 1}

# Надстройка для Microsoft Outlook
#
# Надстройка позволяет управлять видеоконференциями Compass из календаря Outlook. 
# После включения файл с данными надстройки будет доступен по адресу: https://<ваше доменное имя>/outlook/manifest.xml
#
# Тип данных: булево значение, true\\false
outlook_add_in.is_enabled: false

# Внешний порт для контейнера с надстройкой outlook. 
# Запросы к надстройке outlook будут пересылаться на этот порт.
# Порт не используется, если надстройка отключена.
#
# Тип данных: число
# Пример: outlook_add_in.service.external_port: 31104
outlook_add_in.service.external_port: {max_port + 2}

# Внешний порт для контейнера с сервисом авторизации. 
# Все запросы к авторизации с помощью API токенов будут перенаправляться на этот порт.
#
# Тип данных: число
# Пример: auth.service.go_auth.external_grpc_port: 31105
auth.service.go_auth.external_grpc_port: {max_port + 3}
"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()
