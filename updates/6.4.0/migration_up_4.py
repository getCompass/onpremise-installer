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
if not os.path.exists(auth_config_path):
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
    if "ldap.user_login_attribute" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# по умолчанию считаем, значение пустым как если ldap не используется
user_login_attribute = ""

# парсим значение поля user_unique_attribute
content_lines = content.splitlines()
unique_attribute_line = len(content_lines)
before_lines = []
after_lines = []

for index, line in enumerate(content_lines):

    if "ldap.user_unique_attribute:" in line:

        # извлекаем значение из строки
        match = re.search(r'ldap\.user_unique_attribute:\s*"([^"]+)"', line)
        if match:
            user_login_attribute = match.group(1)
        unique_attribute_line = index 
        before_lines = content_lines[:index+1]
        after_lines = content_lines[index+2:]

        break

insert_content = """
# Название атрибута учетной записи LDAP, значение которого будет использоваться для логина пользователя
#
# Тип данных: строка, пример:
# Для Active Directory – "objectGUID"
# Для FreeIPA – "ipaUniqueID"
#
ldap.user_login_attribute: "{}"
""".format(user_login_attribute)

with open(auth_config_path, 'w') as file:

    file.writelines(map(lambda x: x + "\n", before_lines))
    file.write("\n")
    file.writelines(insert_content.strip("\n"))
    file.write("\n\n")
    file.writelines(map(lambda x: x + "\n", after_lines))