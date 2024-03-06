#!/usr/bin/env python3

import os, argparse, json
from pathlib import Path
from subprocess import Popen
import yaml
from utils import scriptutils
from utils import interactive

# ---АГРУМЕНТЫ СКРИПТА---#

script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиги
config_path = Path(script_dir + "/../configs/auth.yaml")

config = {}

if not config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрит create_configs.py и заполните конфигурацию" % str(
            config_path.resolve())))
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(config_values)

root_path = str(Path(script_dir + "/../").resolve())

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument(
    "--add-app-list",
    required=False,
    nargs="+",
    help="Список дополнительных приложений, для которых генерируем конфиг",
)
parser.add_argument(
    "--output-path",
    required=False,
    default=root_path + "/src/pivot/config/pivot_captcha.gophp",
    help="Путь до выходного файла",
)

parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

allowed_provider_list = ["enterprise_google"]

required_app_list = ["compass"]

# получаем список приложений, для которых дополнительно генерируем конфиг
added_app_list = args.add_app_list
app_list = required_app_list
validate_only = args.validate_only

# формируем финальный список приложений
if added_app_list:
    app_list += added_app_list

conf_path = args.output_path
conf_path = Path(conf_path)
validation_errors = []


class AppBlock:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            project_id: str,
            default_client_key: str,
            server_key: dict,
            require_after: int,
            additional_client_keys: dict = {},
    ):
        self.project_id = project_id
        self.client_keys = {"default": default_client_key}
        self.default_client_key = default_client_key
        self.client_keys.update(additional_client_keys)
        self.server_key = server_key
        self.require_after = require_after

    def input(self):
        try:
            project_id = interactive.InteractiveValue(
                "captcha.project_id", "Введите идентификатор проекта Google Recaptcha", "str", config=config,
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            project_id = ""

        try:
            default_client_key = interactive.InteractiveValue(
                "captcha.default_client_key", "Введите клиентский ключ для платформы", "str", config=config,
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            default_client_key = ""

        try:
            server_key = interactive.InteractiveValue(
                "captcha.server_key", "Введите серверный ключ", "str", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            server_key = ""

        try:
            require_after = interactive.InteractiveValue(
                "captcha.require_after", "Введите кол-во попыток аутентификации, после которых запрашивается разгадывание капчи.", "int", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            require_after = 0

        additional_client_keys = self.add_additional_client_keys()

        return self.init(project_id, default_client_key, server_key, require_after, additional_client_keys)

    def add_additional_client_keys(self, additional_client_keys: dict = {}) -> dict:

        for platform in ["electron", "android", "huawei", "ios"]:
            try:
                client_key = interactive.InteractiveValue(
                    "captcha.%s_client_key" % platform, "Введите клиентский ключ для платформы", "str", config=config,
                    is_required=(platform == "android" or platform == "ios")
                ).from_config()
            except interactive.IncorrectValueException as e:
                handle_exception(e.field, e.message)
                client_key = ""

            platform_key = '%s_key' % (platform)
            additional_client_keys.update({platform_key: client_key})
        return additional_client_keys

    def make_output(self):
        project_id_output = '"project_id" => "%s"' % (self.project_id)
        server_key_output = '"server_key" => "%s"' % (self.server_key)
        require_after_output = '"require_after" => %d' % (self.require_after)

        client_key_output = '"client_keys" => ['

        for platform_name, client_key in self.client_keys.items():

            print("Обработка платформы:", platform_name)  # Выводим лог platform_name

            # если не задали отдельные ключи
            if ((platform_name == "electron_key" or platform_name == "huawei_key")
                    and (client_key is None or len(client_key) < 1)):
                client_key = self.default_client_key
            elif client_key is None or len(client_key) < 1:
                continue

            client_key_output += '"%s" => "%s",' % (platform_name, client_key)

        # удаляем последнюю запятую для корректного вывода
        client_key_output = client_key_output.rstrip(',')

        output = "%s, %s, %s, %s]" % (project_id_output, server_key_output, require_after_output, client_key_output)
        return output.encode().decode()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def handle_exception(field, message: str):
    if validate_only:
        validation_errors.append(message)
        return

    print(message)
    exit(1)


def start():

    generate_config()
    exit(0)


def write_file(output: str):
    if validate_only:
        if len(validation_errors) > 0:
            print("Ошибка в конфигурации %s" % str(config_path.resolve()))
            for error in validation_errors:
                print(error)
            exit(1)
        exit(0)

    conf_path.unlink(missing_ok=True)
    f = conf_path.open("w")
    f.write(output)
    f.close()

    print(
        scriptutils.success(
            "Файл с настройками капчи сгенерирован по следующему пути: "
            + scriptutils.warning(str(conf_path.resolve()))
        )
    )


def generate_config():
    providers = {}

    provider = allowed_provider_list[0]
    providers[provider] = generate_provider_config(provider)

    output = make_output(providers)
    write_file(output)


def make_output(providers: dict):
    config_head = """<?php

namespace Compass\Pivot;

$CONFIG["CAPTCHA_PROVIDER_LIST"] = [
"""
    provider_output = ""
    for provider, provider_values in providers.items():
        app_output = "\n"
        for app, app_block in provider_values.items():
            app_output += '\t\t"%s" => [%s],\n' % (app, app_block.make_output())

        provider_output = '\t"%s" => [%s\t],\n' % (provider, app_output)
    config_end = """];
return $CONFIG;"""

    return config_head + provider_output + config_end


def generate_provider_config(provider: str) -> dict:
    result = {}
    for app in app_list:
        result[app] = AppBlock()

    return result


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
