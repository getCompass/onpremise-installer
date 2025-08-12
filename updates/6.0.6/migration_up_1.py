#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import yaml, os

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
    if "ldap.user_profile_update_filter:" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# меняем комментарий
content = content.replace("""# Название атрибута учетной записи LDAP, значение которого будет использоваться в качестве username в форме авторизации
# Значение этого атрибута должно быть уникальным для каждой учетной записи
#
# Тип данных: строка, пример:
# Для Active Directory – \"sAMAccountName\"
# Для FreeIPA – \"uid\"""", """# Название атрибута учетной записи LDAP, значение которого будет использоваться в качестве username в форме авторизации
# Значение этого атрибута должно быть уникальным для каждой учетной записи
#
# Тип данных: строка, пример:
# Для Active Directory – "sAMAccountName"
# Для FreeIPA – "uid"
#
# Если используется несколько контроллеров домена через глобальный каталог, то необходимо использовать userPrincipalName для AD или krbPrincipalName для FreeIPA,
# так как логин должен быть уникальным в обоих доменах.""")

# добавляем новые поля для протокола LDAP
content += """
# Фильтр для поиска учетных записей LDAP при обновлении данных пользователей.
# Параметр НЕ должен содержать уникальный атрибут.
#
# Необязательный параметр. Используйте его при необходимости фильтрации пользователей по критериям.
#
# В случае заполнения фильтр должен быть идентичным с ldap.user_search_filter, но не включать уникальный атрибут.
#
# Например:
# Для Active Directory: "(objectClass=person)"
#
# Для Active Directory с проверкой на принадлежность учетной записи к группе CompassUsers:
# "(&(objectClass=person)(memberOf:1.2.840.113556.1.4.1941:CN=CompassUsers,DC=example,DC=com))"
#
# Для FreeIPA: "(objectClass=person)"
#
# Для FreeIPA с проверкой на принадлежность учетной записи к группе CompassUsers:
# "(&(objectClass=person)(memberOf=cn=CompassUsers,cn=groups,cn=accounts,dc=example,dc=com))"
#
# Тип данных: строка
ldap.user_profile_update_filter:
"""

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()