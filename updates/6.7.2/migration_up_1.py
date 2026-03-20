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
content = open(auth_config_path, encoding="utf-8").read().rstrip()

# если поле уже присутствует (и не закомментировано) — ничего не делаем
if re.search(r'(?m)^[ \t]*(?!#)ldap\.authorization_2fa_method[ \t]*:', content):
    print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
    exit(0)

# регулярка для строки-анкера (не закомментированная)
regex = r'(?m)^([ \t]*(?!#)ldap\.authorization_2fa_enabled[ \t]*:.*)$'

new_block = (
    "# Какой метод используется при 2fa\n"
    "#\n"
    "# Тип данных: строка, пример:\n"
    "# \"mail\" – подтверждение через код на почту\n"
    "# \"totp\" – подтверждение через otp код\n"
    "ldap.authorization_2fa_method: \"mail\""
)

# вставляем после найденной строки: сама строка + пустая строка + нужный блок
paste_content = (
        r"\g<1>\n\n"
        + new_block
)

new_content = re.sub(regex, paste_content, content, count=1)

# если якорь не найден — добавляем блок в конец файла
if new_content == content:
    if not content.endswith("\n"):
        content += "\n"
    new_content = (
            content
            + "\n"
            + new_block
    )

# ищем второе поле
if re.search(r'(?m)^[ \t]*(?!#)ldap\.totp_2fa\.issuer[ \t]*:', new_content):
    print(scriptutils.success("Конфиг-файл auth.yaml выглядит актуальным, миграция не требуется."))
    exit(0)

# регулярка для строки-анкера (не закомментированная)
regex = r'(?m)^([ \t]*(?!#)ldap\.mail_2fa\.allowed_domains[ \t]*:.*)$'

new_block = (
    "# Issuer секретных кодов для TOTP\n"
    "#\n"
    "# Название сервиса или организации, которое пользователи будут видеть в мобильном приложении для одноразовых кодов.\n"
    "ldap.totp_2fa.issuer: \"Compass\"\n"
)

# вставляем после найденной строки: сама строка + пустая строка + нужный блок
paste_content = (
        r"\g<1>\n\n"
        + new_block
)

new_content = re.sub(regex, paste_content, new_content, count=1)

# если якорь не найден — добавляем блок в конец файла
if new_content == content:
    if not content.endswith("\n"):
        content += "\n"
    new_content = (
            content
            + "\n"
            + new_block
    )

auth_config = open(auth_config_path, "w", encoding="utf-8")
auth_config.write(new_content)
auth_config.close()
