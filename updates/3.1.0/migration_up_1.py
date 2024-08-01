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
    if "sso.protocol" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# по умолчанию считаем, что SSO не включен, а значит никакой протокол не указываем
sso_protocol = ""

# проверяем, включен ли способ аутентификации через SSO
content_lines = content.splitlines()
for line in content_lines:
    if "available_methods:" in line:
        if "sso" in line:
            sso_protocol = "oidc"
        break

# добавляем новое поле sso.protocol и заполняем его, если нужно
content += """

# Укажите протокол, который будет использоваться для аутентификации. Возможные варианты:
# "oidc" – протокол OpenID Connect
# "ldap" – протокол Lightweight Directory Access Protocol
#
# Тип данных: строка
sso.protocol: "{}"
""".format(sso_protocol)

# переименовываем старые поля протокола LDAP из sso. в oidc.
content = content.replace("sso.client_id:", "oidc.client_id:")
content = content.replace("sso.client_secret:", "oidc.client_secret:")
content = content.replace("sso.oidc_provider_metadata_link:", "oidc.oidc_provider_metadata_link:")
content = content.replace("sso.attribution_mapping.first_name:", "oidc.attribution_mapping.first_name:")
content = content.replace("sso.attribution_mapping.last_name:", "oidc.attribution_mapping.last_name:")
content = content.replace("sso.attribution_mapping.mail:", "oidc.attribution_mapping.mail:")
content = content.replace("sso.attribution_mapping.phone_number:", "oidc.attribution_mapping.phone_number:")

# добавляем новые поля для протокола LDAP
content += """

# ----------------------------------------------
# SSO АВТОРИЗАЦИЯ ПО ПРОТОКОЛУ LDAP
# ----------------------------------------------

# Хост сервера LDAP.
#
# Тип данных: строка, пример: "example.com"
ldap.server_host:

# Порт сервера LDAP.
#
# Тип данных: число, пример: 636
ldap.server_port: 636

# Контекст поиска пользователей в LDAP каталоге.
#
# Тип данных: строка, пример: "ou=users,dc=example,dc=com"
ldap.user_search_base:

# Название атрибута учетной записи LDAP, значение которого будет использоваться в качестве username в форме авторизации
# Значение этого атрибута должно быть уникальным для каждой учетной записи
#
# Тип данных: строка, пример:
# Для Active Directory – "CN"
# Для FreeIPA – "uid"
ldap.user_unique_attribute:

# Лимит неудачных попыток аутентификации, по достижению которых IP адрес пользователя получает блокировку на 15 минут.
#
# Тип данных: число
ldap.limit_of_incorrect_auth_attempts: 5

# Включен ли мониторинг удаления / блокировки учетной записи LDAP для запуска автоматической
# блокировки связанного пользователя в Compass.
#
# Тип данных: булево значение, пример: true\false
ldap.account_disabling_monitoring_enabled: false

# Уровень автоматической блокировки при отключении учетной записи LDAP, связанной с пользователем Compass.
# Обязателен к заполнению в случае включенного параметра ldap.account_disabling_monitoring_enabled
# Возможные уровни:
# "light" – у связанного пользователя Compass закрываются все активные сессии, блокируется доступ к пространствам на вашем сервере.
# "hard"  – у связанного пользователя Compass закрываются все активные сессии, блокируется доступ к пространствам на вашем сервере,
#           пользователь покидает все команды.
ldap.on_account_disabling: "light"

# Уровень автоматической блокировки при полном удалении учетной записи LDAP, связанной с пользователем Compass.
# Обязателен к заполнению в случае включенного параметра ldap.account_disabling_monitoring_enabled
# Возможные уровни:
# "light" – у связанного пользователя Compass закрываются все активные сессии, блокируется доступ к пространствам на вашем сервере.
# "hard"  – у связанного пользователя Compass закрываются все активные сессии, блокируется доступ к пространствам на вашем сервере,
#           пользователь покидает все команды.
# Если использовались почта или номер телефона для авторизации одновременно с LDAP, то в случае удаления учетной записи в LDAP,
# привязанная почта и номер пользователя станут недоступны для повторной регистрации/авторизации.
ldap.on_account_removing: "light"

# Полный DN (Distinguished Name) учетной записи LDAP, которая будет использоваться
# для поиска других учетных записей и мониторинга их удаления/блокировки в каталоге.
# Обязателен к заполнению в случае включенного параметра ldap.account_disabling_monitoring_enabled
#
# Тип данных: строка, пример: "uid=compass_monitor,ou=users,dc=example,dc=com"
ldap.user_search_account_dn:

# Пароль учетной записи LDAP, которая будет использоваться
# для поиска других учетных записей и мониторинга их удаления/блокировки в каталоге.
# Обязателен к заполнению в случае включенного параметра ldap.account_disabling_monitoring_enabled
#
# Тип данных: строка, пример: "qwerty12345"
ldap.user_search_account_password:

# Временной интервал между проверками мониторинга блокировки пользователя LDAP.
# Обязателен к заполнению в случае включенного параметра ldap.account_disabling_monitoring_enabled
#
# Тип данных: строка формата:
# Ns – интервал каждые N секунд
# Nm – интервал каждые N минут
# Nh – интервал каждые N часов
# Пример: 5m – интервал каждые 5 минут
ldap.account_disabling_monitoring_interval: "5m"
"""

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()