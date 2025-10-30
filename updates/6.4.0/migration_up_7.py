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

team_config_path = str(config_path) + "/team.yaml"
if not os.path.exists(team_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл team.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг team.yaml уже содержит свежие поля
with open(team_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "file_auto_deletion.is_enabled" in content:
        print(scriptutils.success("Конфиг-файл team.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем поля автоудаления файлов
content += '''

# Разрешено ли автоматическое удаление файлов с сервера.
# Тип данных: булево значение true/false
file_auto_deletion.is_enabled: false

# Время хранения файлов на сервере перед удалением, если к ним не было обращений от клиентской платформы.
# Обязателен к заполнению в случае включенного параметра file_auto_deletion.is_enabled.
#
# Тип данных: число, пример: 30 – удаление файлов старше 30 дней
file_auto_deletion.file_ttl: 0

# Временной интервал запуска проверки на удаление файлов с сервера.
# Обязателен к заполнению в случае включенного параметра file_auto_deletion_enabled.
#
# Тип данных: число, пример: 2 – интервал каждые 2 дня
file_auto_deletion.check_interval: 0

# Тип удаляемых файлов с сервера.
# Обязателен к заполнению, значение параметра по умолчанию all – удаляются все типы файлов. 
# Его используют для указания типа удаляемого файла или списка типов удаляемых файлов (через запятую), например "audio, voice".
#
# Возможные значения:
# audio – аудиофайлы
# voice – голосовые сообщения
# image – изображения
# video – видео
# archive – архивы (zip, rar, 7z, tar, gz)
# document  – документы (doc, xls, ppt и т.д.)
# file – файлы (прочие, что не является документом или архивом)
#
# Тип данных: строка, пример: "video" – удаление только видео
file_auto_deletion.need_delete_file_type_list: "all"
'''

# сохраняем изменения
team_config = open(team_config_path, "w")
team_config.write(content)
team_config.close()