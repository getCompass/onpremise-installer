#!/usr/bin/env python3

# Скрипт выполняет задачи:
# – создает файлы с конфигами в папке configs

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import shutil
from utils import scriptutils

script_dir = str(Path(__file__).parent.resolve())

# папка, где находятся конфиги
config_path = Path(script_dir + "/../configs")

# папка, где находятся шаблоны конфигов
config_tpl_path = Path(script_dir + "/../yaml_template/configs")

# список шаблонов с конфигами
config_tpl_files = config_tpl_path.glob("*.tpl.yaml")

# создаем папку с конфигами, если ее нет
config_path.mkdir(exist_ok=True)

print("Созданы конфигурационные файлы:")

# копируем файлы в папку с конфигами
for tpl_file in config_tpl_files:
    
    basename = tpl_file.name
    new_basename = basename.replace(".tpl", "")
    dst = str(config_path.resolve()) + "/" + new_basename

    if Path(dst).exists():
        print(scriptutils.warning("В папке configs найдены действующие конфигурационные файлы, завершаю выполнение. Используйте либо удалите текущие конфиги в папке %s" % str(config_path.resolve())))
        exit(0)
    shutil.copy2(str(tpl_file.resolve()), dst)
    print(dst)
