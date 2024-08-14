#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import collections.abc, shutil
import re, socket, yaml, argparse, readline, string, random, pwd, os

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils
from loader import Loader
from utils.interactive import InteractiveValue, IncorrectValueException

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

config_files_dictionary = {
    "auth.yaml": "captcha.yaml",
}

config_replaces_dictionary = {
    "captcha.enabled": "captcha.enabled",
    "captcha.require_after": "captcha.require_after",
    "google_captcha.project_id": "captcha.project_id",
    "google_captcha.default_client_key": "captcha.default_client_key",
    "google_captcha.android_client_key": "captcha.android_client_key",
    "google_captcha.ios_client_key": "captcha.ios_client_key",
    "google_captcha.huawei_client_key": "captcha.huawei_client_key",
    "google_captcha.electron_client_key": "captcha.electron_client_key",
    "google_captcha.server_key": "captcha.server_key",
    "yandex_captcha.default_client_key": "yandex_captcha.default_client_key",
    "yandex_captcha.server_key": "yandex_captcha.server_key",
}

# папка, где находятся конфиги
config_path = current_script_path.parent.parent / 'configs'

# если отсутствуют файлы-конфиги
if len(os.listdir(config_path)) == 0:
    print(
        scriptutils.warning(
            "Отсутствуют конфиг-файлы в директории configs/.. - миграция невозможна. Запустите скрипт create_configs.py для создания конфиг-файлов и заполните поля"
        )
    )
    exit(0)

# скрипт для создания недостающих конфиг-файлов
try:
    # папка, где находятся шаблоны конфигов
    config_tpl_path = current_script_path.parent.parent / "yaml_template/configs"

    # список шаблонов с конфигами
    config_tpl_files = config_tpl_path.glob("*.tpl.yaml")

    # копируем файлы в папку с конфигами
    for tpl_file in config_tpl_files:

        basename = tpl_file.name
        new_basename = basename.replace(".tpl", "")
        dst = str(config_path.resolve()) + "/" + new_basename

        if Path(dst).exists():
            continue
        shutil.copy2(str(tpl_file.resolve()), dst)
except:
    pass

# список файл-конфигов с указанными значениями
config_files = config_path.glob("*.yaml")

# получаем содержимое значения из текущих yaml-файлов конфигов
config = {}
for item in config_files:

    # пропускаем, если такой файл отсутствует в списке для замены
    if config_files_dictionary.get(item.name) is None:
        continue

    # получаем значения из старого конфига
    with item.resolve().open("r") as config_file:
        old_config = yaml.safe_load(config_file)

    # получаем название нового конфига, в котором будем заменять значение
    new_config_file_name = config_files_dictionary.get(item.name)

    # получаем содержимое нового конфига
    new_config_path = Path(str(config_path) + "/" + new_config_file_name)

    # получаем значения из нового конфига
    with new_config_path.open("r") as config_file:
        new_config = yaml.safe_load(config_file)

    new_config_file = open(str(config_path) + "/" + new_config_file_name, "r")
    new_config_text = new_config_file.read()
    new_config_file.close()

    # заменяем значения в полях нового конфига
    for key in config_replaces_dictionary:

        # получаем значение из старого конфига и добавляем его в текст нового конфига
        old_value = old_config.get(config_replaces_dictionary[key])
        current_value = new_config.get(config_replaces_dictionary[key])
        if old_value is not None:

            if current_value is None:

                new_config_text = new_config_text.replace(key + ":", key + ": " + str(old_value))
                continue

            new_config_text = new_config_text.replace(key + ": %s" % current_value, key + ": " + str(old_value))

    # записываем всё в файл
    new_config_file = open(str(config_path) + "/" + new_config_file_name, "w")
    new_config_file.write(new_config_text)
    new_config_file.close()