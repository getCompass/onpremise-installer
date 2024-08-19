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

auth_config_path = str(config_path) + "/auth.yaml"
if False == os.path.exists(auth_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл auth.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# если конфиг auth.yaml уже содержит свежие поля
with open(auth_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "sso.auto_join_to_team" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем новое поле sso.auto_join_to_team
content += """

# Автоматическое вступление пользователей после регистрации через SSO/LDAP в первую команду на сервере.
# От лица администратора будет создана бессрочная ссылка-приглашение с заданным параметром вступления в команду.
# Параметр принимает следующие значения:
# member – пользователи автоматически вступают как участники;
# guest – пользователи автоматически вступают как гости;
# moderation – отправляется заявка на вступление в команду, требующая подтверждение от администратора;
# disabled – опция автоматического вступления в первую команду выключена.
#
# Тип данных: строка
sso.auto_join_to_team: "member"
"""

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()