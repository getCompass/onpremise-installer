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
    if "yandex_captcha.default_client_key" in content:
        print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# заменяем комментарии по способам аутентификации
content = content.replace("""# Кол-во попыток аутентификации, после которых запрашивается разгадывание капчи.
# При значении = 0 – каждая попытка аутентификации запрашивает разгадывание капчи.
#
# Тип данных: число
captcha.require_after""", """# Клиентский ключ Yandex SmartCaptcha. Данный ключ будет использоваться
# для всех клиентских платформ.
# В документации по подключению Yandex SmartCaptcha обозначено как ключ клиента.
#
# Тип данных: строка
yandex_captcha.default_client_key:

# Серверный ключ Yandex SmartCaptcha.
# Данный ключ используется приложением для идентификации в Yandex SmartCaptcha.
# В документации по подключению Yandex SmartCaptcha обозначено как ключ сервера.
#
# Тип данных: строка
yandex_captcha.server_key:

# Кол-во попыток аутентификации, после которых запрашивается разгадывание капчи.
# При значении = 0 – каждая попытка аутентификации запрашивает разгадывание капчи.
#
# Тип данных: число
captcha.require_after""")

auth_config = open(auth_config_path, "w")
auth_config.write(content)
auth_config.close()