#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import yaml, shutil

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

# папка, где находятся конфиги
config_path = Path(script_dir + "/../../configs/smart_apps.yaml")

# папка, где находятся шаблоны конфигов
config_tpl_path = Path(script_dir + "/../../yaml_template/configs/smart_apps.tpl.yaml")

# если конфиг существует, прекращаем выполнение
if config_path.exists():
    exit(0)

# копируем конфиг
shutil.copy2(str(config_tpl_path.resolve()), str(config_path.resolve()))