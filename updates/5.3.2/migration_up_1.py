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

auth_config_path = str(config_path) + "/auth.yaml"
if False == os.path.exists(auth_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл auth.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# читаем содержимое файла
content = open(auth_config_path).read().rstrip()

    # если в содержимом уже имеется новое поле, то ничего не делаем
if "[[manager:distinguishedName='{manager}']]" in content:
    print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
    exit(0)

regex = r'\nsso\.compass_mapping\.bio:'
paste_content = """

# Для протокола LDAP возможно использование атрибутов от других пользователей
# Необходимо связать ключ с уникальным атрибутом стороннего пользователя
# Выражения присваивания указываются в скобках [[выражение]],
# [[manager:distinguishedName='{manager}']]
# Расшифровка выражения присваивания:
# manager - ключ, к которому будет присвоен сторонний объект LDAP
# distinguishedName - атрибут, по которому будем искать в LDAP
# '{manager}' - значение атрибута, по которому ищем в LDAP. Значение может состоять из нескольких {атрибутов} текущего пользователя
# После чего можно использовать атрибуты стороннего пользователя с помощью конструкции {ключ=>атрибут}
# "sso.compass_mapping.bio: "[[manager:distinguishedName='{manager}']] Руководитель: {manager=>displayName} Номер телефона: {number}"".
sso.compass_mapping.bio:"""
content = re.sub(regex, paste_content, content)

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()
