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
    if "ldap.user_search_filter" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем новое поле ldap.user_search_filter
content += """

# Фильтр для поиска учетной записи LDAP в момент авторизации пользователя в приложении.
# Параметр обязательно должен содержать уникальный атрибут, например (attribute_name={0}), где
# вместо attribute_name указывается название аттрибута, по которому будет осуществляться поиск учетной записи.
#
# Необязательный параметр. Используйте его при необходимости фильтрации пользователей по критериям.
#
# Например:
# Для Active Directory: "(&(objectClass=person)(sAMAccountName={0}))"
#
# Для Active Directory с проверкой на принадлежность учетной записи к группе CompassUsers:
# "(&(objectClass=person)(sAMAccountName={0})(memberOf=CN=CompassUsers,DC=example,DC=com))"
#
# Для FreeIPA: "(&(objectClass=person)(uid={0}))"
#
# Тип данных: строка
ldap.user_search_filter:
"""

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()