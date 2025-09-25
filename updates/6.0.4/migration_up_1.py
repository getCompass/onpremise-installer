#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import yaml
import re

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

global_config_path = str(config_path) + "/global.yaml"
if False == os.path.exists(global_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл global.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
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

# если конфиг global.yaml уже содержит свежие поля
with open(global_config_path, "r") as file:
    # считываем конфиг
    global_config = yaml.safe_load(file)

    # если в содержимом уже имеется новое поле, то ничего не делаем
    if "is_need_index_web" in global_config:
        print(scriptutils.success("Конфиг-файл global.yaml выглядит актуальным, миграция не требуется."))
        exit(0)

# читаем содержимое файла
content = open(global_config_path).read().rstrip()

# добавляем актуальный параметр в конец конфига
content += """

# Разрешено ли поисковикам индексировать страницу авторизации.
# По умолчанию индексация отключена.
#
# Тип данных: булево значение, true\\false
is_need_index_web: false
"""

# сохраняем изменения
global_config = open(global_config_path, "w")
global_config.write(content)
global_config.close()

# если конфиг auth.yaml уже содержит свежие поля
with open(auth_config_path, "r") as file:
    # читаем содержимое файла
    content = file.read()

    # если в содержимом уже имеются новые поля, то ничего не делаем
    if "available_guest_methods:" in content:
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
# sso – через SSO провайдер, с помощью корпоративной учетной записи сотрудника.
# Требует обязательную настройку SSO провайдера в разделе «SSO».
#
# Тип данных: массив строк, пример:
# ["phone_number", "mail", "sso"] – аутентификация через номер телефона, почту и SSO
# ["phone_number"] – аутентификация только через номер телефона
# ["mail"] – аутентификация только через почту
# ["sso"] – аутентификация только через SSO""", """# Доступные способы аутентификации. Возможные варианты:
# phone_number – по номеру телефона, через подтверждение смс-кодом.
# Требует обязательную конфигурацию доставки смс в разделе «СМС АВТОРИЗАЦИЯ».
#
# mail – по электронной почте, через пароль и код подтверждения.
# Подтверждение через код по умолчанию включено, отключить можно в разделе «ПОЧТА».
# Требует обязательное заполнение SMTP протоколов в разделе «ПОЧТА».
#
# sso – через SSO провайдер, с помощью корпоративной учетной записи сотрудника.
# Требует обязательную настройку SSO провайдера в разделе «SSO».
# При использовании SSO как способа аутентификации одновременно для участников и гостей, в разделе "SSO АВТОРИЗАЦИЯ"
# установите параметру "sso.auto_join_to_team:" значение "disabled".
#
# Тип данных: массив строк, пример:
# ["phone_number", "mail", "sso"] – аутентификация через номер телефона, почту и SSO
# ["phone_number"] – аутентификация только через номер телефона
# ["mail"] – аутентификация только через почту
# ["sso"] – аутентификация только через SSO

# Настройка способов аутентификации для участников.""")

# заменяем комментарии по альтернативным методам авторизации
content = content.replace("""# Включена ли опция альтернативных способов аутентификации при аутентификации через SSO.
# При включенной опции у пользователей прошедших аутентификацию через SSO
# появляется возможность аутентификации через другие способы аутентификации,
# описанных в available_methods в текущем конфигурационном файле.
#
# Тип данных: булево значение, true\\false""", """# Включена ли опция альтернативных способов аутентификации при аутентификации через SSO.
# При включенной опции у пользователей прошедших аутентификацию через SSO
# появляется возможность аутентификации через другие способы аутентификации,
# описанные в available_methods и available_guest_methods в текущем конфигурационном файле.
# 
# Тип данных: булево значение, true\\false""")

# шаблон блока, который будем вставлять
guest_block_tpl = """# Настройка способов аутентификации для пользователей с гостевым доступом.
# Если способы аутентификации для участников и гостей отличаются, на экране авторизации
# будет доступна кнопка "Войти в гостевой аккаунт".
# Если для участников и гостей используются одинаковые способы аутентификации, экран авторизации будет
# общим для всех пользователей.
available_guest_methods: {methods}"""

# регулярка найдёт строку вида "available_methods: [ ... ]" во всех вариантах пробелов/методов
pattern = r'(?m)^(available_methods:\s*\[([^\]]*)\])$'

def repl(m):
    full_line = m.group(1)       # например "available_methods: [\"phone_number\", \"mail\"]"
    methods_list = m.group(2)    # например "\"phone_number\", \"mail\""
    methods = f"[{methods_list}]"
    guest_block = guest_block_tpl.format(methods=methods)
    return f"{full_line}\n\n{guest_block}"

new_content, count = re.subn(pattern, repl, content)

# записываем обновленный файл
auth_config = open(auth_config_path, "w")
auth_config.write(new_content)
auth_config.close()