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

def change_comment(file_content:str, attr: str, new_comment:str) -> str:

    # парсим значение поля
    content_lines = file_content.splitlines()
    unique_attribute_line = content_lines[len(content_lines) -1]
    before_lines = []
    after_lines = []
    found_comment = False

    for index, line in enumerate(content_lines):

        if attr in line:

            # извлекаем значение из строки
            unique_attribute_line = content_lines[index] 
            before_lines = content_lines[:index]
            after_lines = content_lines[index+1:]

            break

    # удаляем строки комментариев
    for i in range(len(before_lines) - 1, -1, -1):

        line = str(before_lines[i])

        # если коммент закончился, то завершаем выполнение
        if not (line.startswith("#") or (line == "" and not found_comment)):
            break

        # устанавливаем флаг, что нашли коммент
        if line.startswith("#") and not found_comment:
            found_comment = True
        before_lines.pop(i)
    
    new_content = ""
    for line in before_lines:
        new_content += line + "\n"
    
    new_content += new_comment
    new_content += unique_attribute_line + "\n"

    for line in after_lines:
        new_content += line + "\n"
    
    return new_content

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

user_unique_attribute_comment = '''# Название уникального атрибута учетной записи LDAP, значение которого будет использоваться в качестве однозначного определения пользователя в системе. 
#
# Тип данных: строка 
# Рекомендуется использовать следующие параметры:
# Для Active Directory – "objectGUID"
# Для FreeIPA – "ipaUniqueID"
#
'''
content = change_comment(content, "ldap.user_unique_attribute:", user_unique_attribute_comment)

user_login_attribute_comment = '''# Название атрибута учетной записи LDAP, значение которого будет использоваться для логина пользователя
#
# Тип данных: строка, пример:
# Для Active Directory – "sAMAccountName"
# Для FreeIPA – "uid"
#
'''

content = change_comment(content, "ldap.user_login_attribute:", user_login_attribute_comment)

with open(auth_config_path, 'w') as file:
    file.write(content)