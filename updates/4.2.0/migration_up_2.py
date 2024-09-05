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
    # считываем конфиг
    auth_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "sso.compass_mapping.name" in auth_config:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# получаем значения старых параметров oidc.attribution_mapping.first_name и oidc.attribution_mapping.last_name
oidc_first_name_value = auth_config.get("oidc.attribution_mapping.first_name")
oidc_last_name_value = auth_config.get("oidc.attribution_mapping.last_name")

# получаем значения старого параметра ldap ldap.user_unique_attribute
ldap_user_uniq_attributevalue = auth_config.get("ldap.user_unique_attribute")

# получаем значение sso.protocol
sso_protocol_value = auth_config.get("sso.protocol")

# собираем параметр
sso_compass_mapping_name = ""
if sso_protocol_value == "ldap":
    sso_compass_mapping_name = "{" + str(ldap_user_uniq_attributevalue) + "}"
else:
    if len(str(oidc_first_name_value)) > 0:
        sso_compass_mapping_name = "{" + str(oidc_first_name_value) + "}"
    if len(str(oidc_last_name_value)) > 0:
        sso_compass_mapping_name += " {" + str(oidc_last_name_value) + "}"
sso_compass_mapping_name.strip()

# читаем содержимое файла
content = open(auth_config_path).read()

# добавляем новые параметры
content += """

# Сопоставление атрибутов учетной записи SSO с атрибутами профиля пользователя в Compass.
# Это необходимо для автоматического заполнения информации о пользователе при его регистрации
# через SSO.
#
# Поле "sso.compass_mapping.name:" обязательно к заполнению, остальные поля могут быть пустыми, если атрибут не требуется.
# Тип данных: строка
#
# Атрибуты, которые требуется подтягивать из SSO по протоколу OIDC/LDAP указываются в фигурных скобках {{attribute_name}},
# например, для ФИО в Compass можно сопоставить атрибуты следующим образом:
# "sso.compass_mapping.name: "{{first_name}} {{last_name}}"".

# В Compass максимальная длина для ФИО 40 символов, при подтягивании данных из SSO в это поле
# большего числа символов, лишние символы будут удалены с конца текста.
sso.compass_mapping.name: "{}"

# В Compass допустимы аватарки в формате JPEG и PNG, от 100 до 8000 px, от 10 Кбайт до 20 Мбайт.
# Не подходящие под ограничения аватарки не будут перенесены в Compass.
sso.compass_mapping.avatar: ""

# Максимальная длина для бейджа 8 символов, в это поле рекомендуется подтягивать
# сокращенное название отдела или должности.
sso.compass_mapping.badge: ""

# Максимальная длина для названия отдела или должности 40 символов, при подтягивании данных из SSO в это поле
# большего числа символов, лишние символы будут удалены с конца текста.
sso.compass_mapping.role: ""

# Максимальная длина для поля статуса 400 символов, при подтягивании из SSO в это поле
# большего числа символов, лишние символы будут удалены с конца текста. Для статуса можно указать
# любой кастомный текст, например, "sso.compass_mapping.bio: "Телефон: {{mobile}}; Код сотрудника: {{employee_number}}"".
# Для переноса строки необходимо использовать символ \\n, например, "sso.compass_mapping.bio: "Телефон: {{mobile}};\\nКод сотрудника: {{employee_number}}"".
sso.compass_mapping.bio: ""
""".format(sso_compass_mapping_name)

# сохраняем изменения
auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()
