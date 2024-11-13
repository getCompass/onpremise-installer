#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import yaml

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
    # считываем конфиг
    auth_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "ldap.require_cert_strategy" in auth_config:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# получаем значение параметра ldap.use_ssl
ldap_use_ssl = auth_config.get("ldap.use_ssl")

# определяем значение для нового параметра
if ldap_use_ssl == True:
    ldap_require_cert_strategy = "demand"
else:
    ldap_require_cert_strategy = "never"

# читаем содержимое файла
content = open(auth_config_path).read()

# добавляем актуальный параметр в конец конфига
content += """

# Выбираем стратегию проверки сертификатов SSL/TLS при установлении безопасного соединения с LDAP-сервером
#
# Возможные значения:
# never   – проверка сертификата отключена
# allow   – проверка сертификата выполняется, но клиент все равно разрешает подключение даже в случае неудачной валидации
# try     – сертификат запрашивается, и если он не предоставлен, сессия продолжается нормально.
#           Если сертификат предоставлен, но не может быть проверен, сессия немедленно прерывается
# demand  – требует обязательной проверки сертификата сервера. Соединение не будет установлено, если сертификат не прошёл проверку
#
# Тип данных: строка, например: \"demand\"
ldap.require_cert_strategy: \"{}\"
""".format(ldap_require_cert_strategy)

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()