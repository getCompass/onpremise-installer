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
    if "jitsi.service.jvb.media_advertise_ips" in content:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем новое поле jitsi.service.jvb.media_advertise_ips
content += """

# Необязательный параметр. Используйте его для указания IP-адреса или списка IP-адресов (через запятую),
# по которым клиенты будут подключаться к вашему медиа-серверу Compass On-Premise.
# Этот параметр особенно полезен, если сервер находится за NAT. В этом случае укажите публичный IP-адрес,
# а затем через запятую — IP-адрес, указанный в параметре `host_ip` выше.
#
# Тип данных: строка
# Пример: jitsi.service.jvb.media_advertise_ips: "212.41.12.120,10.0.1.5"
jitsi.service.jvb.media_advertise_ips: ""
"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()