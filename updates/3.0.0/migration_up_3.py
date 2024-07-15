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
    if "jitsi_web.service.jitsi_web.external_port" in content:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем актуальные параметры в конец конфига
content += """

# Внешний порт для контейнера с сайтом вкс страницы, перед присоединением к конференции.
# Внутренний трафик сайта будет пересылаться на этот порт.
#
# Тип данных: число
# Пример: jitsi_web.service.jitsi_web.external_port: 31901
jitsi_web.service.jitsi_web.external_port: 31901

# Порт для https запросов к веб-интерфейсу Jitsi.
# Запросы к веб-интерфейсу будут пересылаться на этот порт.
#
# Тип данных: число
# Пример: jitsi.service.web.https_port: 35000
jitsi.service.web.https_port: 35000

# Порт для передачи мультимедиа-данных конференции в приложении.
# Порт будет выделен под RTP соединения участников в конференции.
#
# Тип данных: число
# Пример: jitsi.service.jvb.media_port: 10000
jitsi.service.jvb.media_port: 10000

# Порт для компонента jicofo, модуля для ВКС
# Запросы к компоненту будут отправлять на этот порт.
#
# Тип данных: число
# Пример: jitsi.service.jicofo.port: 35001
jitsi.service.jicofo.port: 35001

# Порт для компонента prosody, модуля для ВКС
# Запросы к компоненту будут отправлять на этот порт.
#
# Тип данных: число
# Пример: jitsi.service.prosody.port: 35002
jitsi.service.prosody.serve_port: 35002

# Адрес TURN сервера, который будет использоваться для соединения в ВКС
# По умолчанию указан публичный TURN сервер Compass
#
# Тип данных: строка
# Пример: jitsi.service.turn.host: "onpremise-turn.getcompass.ru"
jitsi.service.turn.host: "onpremise-turn.getcompass.ru"

# Порт TURN сервера, который принимает входящие UDP/TCP соединения клиентов
# По умолчанию указан порт от публичного TURN сервера Compass
#
# Тип данных: число
# Пример: jitsi.service.turn.port: 80
jitsi.service.turn.port: 80

# Порт TURN сервера, который принимает входящие соединения клиентов, использующие протокол TLS
# По умолчанию указан порт от публичного TURN сервера Compass
#
# Тип данных: число
# Пример: jitsi.service.turn.tls_port: 443
jitsi.service.turn.tls_port: 443

# Секретный ключ TURN сервера
# По умолчанию указан секретный ключ публичного TURN сервера Compass
#
# Тип данных: строка
# Пример: jitsi.service.turn.secret: "secret-key"
jitsi.service.turn.secret: "XKwpb9C2bMkhNCsWxxg2CxzGDrl3wZG6"

# Список используемых протоколов для соединения клиентов с TURN сервером
# По умолчанию используется только UDP протокол для повышения качества
# видеоконференций в нестабильных сетях
#
# Тип данных: массив строк, пример:
# ["udp"] – используется только UDP протокол
# ["tcp"] – используется только TCP протокол
# ["udp", "tcp"] – используются оба протокола
jitsi.service.turn.use_protocols: ["udp"]

# Использовать ли принудительно TURN сервер для соединения в видеоконференция
# По умолчанию флаг включен для повышения гарантии установления соединения
#
# Тип данных: булево значение, true\\false
jitsi.service.turn.force_relay: true"""

global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()
