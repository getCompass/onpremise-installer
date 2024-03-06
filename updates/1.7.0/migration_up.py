#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
from utils import scriptutils
from loader import Loader
import collections.abc, shutil
import re, socket, yaml, argparse, readline, string, random, pwd, os
from utils.interactive import InteractiveValue, IncorrectValueException

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

config_files_dictionary = {
    "captcha.yaml": "auth.yaml",
    "sms.yaml": "auth.yaml",
}

config_replaces_dictionary = {
    "captcha.project_id": "project_id",
    "captcha.default_client_key": "default_client_key",
    "captcha.android_client_key": "android.client_key",
    "captcha.ios_client_key": "ios.client_key",
    "captcha.huawei_client_key": "huawei.client_key",
    "captcha.electron_client_key": "electron.client_key",
    "captcha.server_key": "server_key",
    "sms_agent.provide_phone_code_list": "sms_agent.provide_phone_code_list",
    "sms_agent.high_priority_phone_code_list": "sms_agent.high_priority_phone_code_list",
    "sms_agent.min_balance_value": "sms_agent.min_balance_value",
    "sms_agent.provider_gateway_url": "sms_agent.provider_gateway_url",
    "sms_agent.app_name": "sms_agent.app_name",
    "sms_agent.login": "sms_agent.login",
    "sms_agent.password": "sms_agent.password",
    "twilio.provide_phone_code_list": "twilio.provide_phone_code_list",
    "twilio.high_priority_phone_code_list": "twilio.high_priority_phone_code_list",
    "twilio.min_balance_value": "twilio.min_balance_value",
    "twilio.provider_gateway_url": "twilio.provider_gateway_url",
    "twilio.app_name": "twilio.app_name",
    "twilio.account_sid": "twilio.account_sid",
    "twilio.account_auth_token": "twilio.account_auth_token",
    "vonage.provide_phone_code_list": "vonage.provide_phone_code_list",
    "vonage.high_priority_phone_code_list": "vonage.high_priority_phone_code_list",
    "vonage.min_balance_value": "vonage.min_balance_value",
    "vonage.provider_gateway_url": "vonage.provider_gateway_url",
    "vonage.app_name": "vonage.app_name",
    "vonage.api_key": "vonage.api_key",
    "vonage.api_secret": "vonage.api_secret",
}

# папка, где находятся конфиги
config_path = Path(script_dir + "/../configs")

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
    config_tpl_path = Path(script_dir + "/../yaml_template/configs")

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

        # если значение в новом конфиге не пустое, то пропускаем его
        if new_config.get(config_replaces_dictionary[key]) is not None:
            continue

        # получаем значение из старого конфига и добавляем его в текст нового конфига
        old_value = old_config.get(config_replaces_dictionary[key])
        if old_value is not None:
            new_config_text = new_config_text.replace(key + ":", key + ": " + str(old_value))

    # записываем всё в файл
    new_config_file = open(str(config_path) + "/" + new_config_file_name, "w")
    new_config_file.write(new_config_text)
    new_config_file.close()


