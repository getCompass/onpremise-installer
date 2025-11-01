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
    if "ldap.authorization_2fa_enabled" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# добавляем контент
content += '''
# Включена ли двухфакторная аутентификация (2fa) через проверочный код, отправляемый на почту, при авторизации через LDAP.
# Требует обязательную конфигурацию доставки email писем в разделе "SMTP" выше в данном файле конфигурации.
#
# Тип данных: булево значение, true\\false
ldap.authorization_2fa_enabled: false

# Сопоставление атрибута почты для 2fa учетной записи LDAP с атрибутом почты для 2fa профиля пользователя в Compass.
# Это необходимо для автоматической привязки почты для 2fa, на которую будет отправляться проверочный код для входа.
# Атрибут указывается в фигурных скобках {attribute_name}, например: "ldap.compass_mapping.mail_2fa: "{mail}"".
# Если параметр пуст, то пользователям будет необходимо вручную ввести почту для 2fa при первой авторизации через LDAP.
#
# Тип данных: строка
ldap.compass_mapping.mail_2fa: ""

# Список доменов почтовых адресов, для которых разрешена 2fa через почту.
# Если список пуст, то 2fa разрешена для всех доменов.
# Данный параметр необходимо пропустить, если используется автоматическая привязка почты для 2fa из LDAP.
# Параметр игнорируется, если настроена автоматическая привязка почты из профиля LDAP
#
# Тип данных: массив строк, пример: ["example.com", "domain.ru"]
ldap.mail_2fa.allowed_domains: []
'''

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()