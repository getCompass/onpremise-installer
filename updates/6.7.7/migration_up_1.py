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
    if "nginx.proxy_protocol.is_enabled" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = open(global_config_path).read().rstrip()

# добавляем актуальный параметр в конец конфига
content += f"""

# Необязательный параметр. Включает обработку PROXY protocol для случая, когда перед
# приложением стоит внешний TCP-балансировщик (L4-proxy), терминирующий клиентские соединения.
# При значении true nginx начинает слушать дополнительный порт и извлекать реальный
# IP-адрес клиента из заголовка PROXY protocol, который присылает внешний proxy.
# Если параметр не используется, оставьте false.
#
# Тип данных: булево значение, true\\false
# Пример: nginx.proxy_protocol.is_enabled: true
nginx.proxy_protocol.is_enabled: false

# Необязательный параметр. Порт, на котором nginx принимает соединения от внешнего
# TCP-proxy с включенным PROXY protocol. Учитывается только если nginx.proxy_protocol.is_enabled:: true.
# Должен отличаться от основного порта приложения (443) и порта websocket.
#
# Тип данных: число
# Пример: nginx.proxy_protocol.port: 444
nginx.proxy_protocol.port: 444

# Необязательный параметр. Список доверенных адресов внешних proxy, от которых nginx
# принимает реальный IP клиента через PROXY protocol. Учитывается только если
# nginx.proxy_protocol.is_enabled: true. Допускаются одиночные IP-адреса и подсети в формате CIDR
# (IPv4 и IPv6). Запросы с других адресов не будут считаться доверенными.
#
# Тип данных: массив строк
# Пример: nginx.proxy_protocol.real_ip_from: ["10.0.0.1", "192.168.0.0/16"]
nginx.proxy_protocol.real_ip_from: []

"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()
