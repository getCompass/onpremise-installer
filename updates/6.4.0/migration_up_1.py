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

team_config_path = str(config_path) + "/team.yaml"
if False == os.path.exists(team_config_path):
    print(
        scriptutils.warning(
            "Отсутствует конфиг-файл team.yaml в директории configs/.. - миграция не требуется. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# читаем содержимое файла
content = open(team_config_path, encoding="utf-8").read().rstrip()

# если поле уже присутствует (и не закомментировано) — ничего не делаем
if re.search(r'(?m)^[ \t]*(?!#)profile\.deletion_enabled[ \t]*:', content):
    print(scriptutils.success("Конфиг-файл team.yaml выглядит актуальным, миграция не требуется."))
    exit(0)

# регулярка для строки-анкера (не закомментированная)
regex = r'(?m)^([ \t]*(?!#)profile\.status_change_enabled[ \t]*:.*)$'

# вставляем после найденной строки: сама строка + пустая строка + нужный блок
paste_content = (
    r"\g<1>\n\n"
    "# Разрешено ли пользователям удалять свой профиль\n"
    "profile.deletion_enabled: true"
)

new_content = re.sub(regex, paste_content, content, count=1)

# если якорь не найден — добавляем блок в конец файла
if new_content == content:
    if not content.endswith("\n"):
        content += "\n"
    new_content = (
            content
            + "\n"
            + "# Разрешено ли пользователям удалять свой профиль\n"
            + "profile.deletion_enabled: true"
    )

team_config = open(team_config_path, "w", encoding="utf-8")
team_config.write(new_content)
team_config.close()