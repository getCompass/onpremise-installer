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
    if "sso.client_id" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# заменяем комментарии по способам аутентификации
content = content.replace("""# Доступные способы аутентификации. Возможные варианты:
# phone_number – по номеру телефона, через подтверждение смс-кодом.
# Требует обязательную конфигурацию доставки смс в разделе «СМС АВТОРИЗАЦИЯ».
#
# mail – по электронной почте, через пароль и код подтверждения.
# Подтверждение через код по умолчанию включено, отключить можно в разделе «ПОЧТА».
# Требует обязательное заполнение SMTP протоколов в разделе «ПОЧТА».
#
# Тип данных: массив строк, пример:
# ["phone_number", "mail"] – аутентификация через номер телефона или почту
# ["phone_number"] – аутентификация только через номер телефона
# ["mail"] – аутентификация только через почту""", """# Доступные способы аутентификации. Возможные варианты:
# phone_number – по номеру телефона, через подтверждение смс-кодом.
# Требует обязательную конфигурацию доставки смс в разделе «СМС АВТОРИЗАЦИЯ».
#
# mail – по электронной почте, через пароль и код подтверждения.
# Подтверждение через код по умолчанию включено, отключить можно в разделе «ПОЧТА».
# Требует обязательное заполнение SMTP протоколов в разделе «ПОЧТА».
#
# sso – через SSO провайдер, с помощью корпоративной учетной записи сотрудника.
# Требует обязательную настройку SSO провайдера в разделе «SSO».
#
# Тип данных: массив строк, пример:
# ["phone_number", "mail", "sso"] – аутентификация через номер телефона, почту и SSO
# ["phone_number"] – аутентификация только через номер телефона
# ["mail"] – аутентификация только через почту
# ["sso"] – аутентификация только через SSO""")

# добавляем актуальные параметры в конец конфига
content += """

# ----------------------------------------------
# SSO АВТОРИЗАЦИЯ
# ----------------------------------------------

# ID и секретный ключ клиентского приложения, зарегистрированных в SSO провайдере
#
# Тип данных: строка
sso.client_id:
sso.client_secret:

# Ссылка на метаданные SSO провайдера
#
# Тип данных: строка, пример: "https://example/adfs/.well-known/openid-configuration"
sso.oidc_provider_metadata_link:

# Сопоставление названия атрибутов учетной записи SSO с атрибутами профиля пользователя в Compass.
# Это необходимо для автоматического заполнения информации о пользователе при его регистрации
# через SSO
#
# Поля могут быть пустыми, если атрибут не требуется
# Тип данных: строка
sso.attribution_mapping.first_name: "first_name"
sso.attribution_mapping.last_name: "last_name"
sso.attribution_mapping.mail: "mail"
sso.attribution_mapping.phone_number: "phone_number"

# Кастомизация текста кнопки для запуска аутентификации через SSO на веб-сайте On-Premise решения
#
# Тип данных: строка
sso.web_auth_button_text: "Войти через корп. портал (AD SSO)\""""

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()