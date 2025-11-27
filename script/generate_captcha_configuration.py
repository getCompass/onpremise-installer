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
config_path = Path(script_dir + "/../configs/captcha.yaml")

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

parser = argparse.ArgumentParser(add_help=True)

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

parser.add_argument(
    "--installer-output",
    required=False,
    action='store_true'
)
parser.add_argument("--confirm-all", required=False, action="store_true")

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

allowed_provider_list = ["enterprise_google", "yandex_cloud"]

required_app_list = ["compass"]

# получаем список приложений, для которых дополнительно генерируем конфиг
added_app_list = args.add_app_list
app_list = required_app_list
validate_only = args.validate_only
installer_output = args.installer_output
confirm_all = args.confirm_all

# формируем финальный список приложений
if added_app_list:
    app_list += added_app_list

conf_path = args.output_path
conf_path = Path(conf_path)
validation_errors = []
captcha_already_skipped = False
require_after_already_done = False


class AppBlock:
    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.input()

    def init(
            self,
            project_id: str,
            default_client_key: str,
            server_key: dict,
            yandex_default_client_key: str,
            yandex_server_key: str,
            additional_client_keys: dict = {},
    ):
        self.project_id = project_id
        self.client_keys = {"default": default_client_key}
        self.default_client_key = default_client_key
        self.client_keys.update(additional_client_keys)
        self.server_key = server_key
        self.yandex_default_client_key = yandex_default_client_key
        self.yandex_server_key = yandex_server_key

    def input(self):

        try:
            captcha_enabled = interactive.InteractiveValue(
                "captcha.enabled", "Включена ли опция для проверки капчи после неудачных попыток аутентификации.",
                "bool", config=config, is_required=False, default_value=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        # если ранее скипнули установку капчи
        global captcha_already_skipped
        if captcha_enabled == False and confirm_all:
            captcha_already_skipped = True

        if captcha_already_skipped == True:
            return self.init("", "", "", "", "", {})

        # если капча выключена и ранее вопрос по пропуску не задавали, то уточняем продолжим ли с пропуском капчи
        if captcha_enabled == False and captcha_already_skipped == False:

            if not validate_only:
                return self.init("", "", "", "", "", {})

            captcha_already_skipped = True
            skip_captcha = input(
                "Вы пытаетесь установить приложение без настройки CAPTCHA.\nЭто может привести к уязвимостям в безопасности и позволить автоматическим системам (ботам) получить доступ к вашему приложению.\nПродолжить установку [Y/n]?\n").lower()
            if skip_captcha == "y":
                return self.init("", "", "", "", "", {})
            else:
                exit(1)

        global require_after_already_done
        if require_after_already_done == False:

            require_after_already_done = True
            try:
                interactive.InteractiveValue(
                    "captcha.require_after",
                    "Введите кол-во попыток аутентификации, после которых запрашивается разгадывание капчи.", "int",
                    config=config
                ).from_config()
            except interactive.IncorrectValueException as e:
                handle_exception(e.field, e.message)

        default_client_key = interactive.InteractiveValue(
            "google_captcha.default_client_key", "Введите клиентский ключ для платформы", "str", config=config,
            is_required=False,
        ).from_config()

        server_key = interactive.InteractiveValue(
            "google_captcha.server_key", "Введите серверный ключ", "str", config=config, is_required=False,
        ).from_config()

        yandex_default_client_key = interactive.InteractiveValue(
            "yandex_captcha.default_client_key", "Введите клиентский ключ для платформы.", "str", config=config,
            is_required=False,
        ).from_config()

        yandex_server_key = interactive.InteractiveValue(
            "yandex_captcha.server_key", "Введите серверный ключ.", "str", config=config, is_required=False,
        ).from_config()

        enterprise_captcha_need = server_key is not None or default_client_key is not None
        yandex_captcha_need = yandex_server_key is not None or yandex_default_client_key is not None

        if (default_client_key is None and yandex_default_client_key is None) or (
                server_key is None and yandex_server_key is None):
            print(scriptutils.error("Данные по enterprise_google или yandex капче должны быть заполнены"))
            exit(1)

        try:
            project_id = interactive.InteractiveValue(
                "google_captcha.project_id", "Введите идентификатор проекта Google Recaptcha", "str", config=config,
                is_required=enterprise_captcha_need,
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        additional_client_keys = {}
        if self.provider == "enterprise_google":
            additional_client_keys = self.add_additional_client_keys(enterprise_captcha_need)

        return self.init(project_id, default_client_key, server_key, yandex_default_client_key, yandex_server_key,
                         additional_client_keys)

    def add_additional_client_keys(self, enterprise_captcha_need, additional_client_keys: dict = {}) -> dict:

        for platform in ["electron", "android", "huawei", "ios"]:
            try:
                client_key = interactive.InteractiveValue(
                    "google_captcha.%s_client_key" % platform, "Введите клиентский ключ для платформы", "str",
                    config=config,
                    is_required=(enterprise_captcha_need and (platform == "android" or platform == "ios"))
                ).from_config()
            except interactive.IncorrectValueException as e:
                handle_exception(e.field, e.message)
                client_key = ""

            platform_key = '%s_key' % (platform)
            additional_client_keys.update({platform_key: client_key})
        return additional_client_keys

    def make_output(self):

        project_id_output = ""
        if self.provider == "enterprise_google":
            project_id_output = '"project_id" => "%s"' % (self.project_id)
            server_key_output = '"server_key" => "%s"' % (self.server_key)
            default_client_key = self.default_client_key
            client_keys = self.client_keys
        else:
            server_key_output = '"server_key" => "%s"' % (self.yandex_server_key)
            default_client_key = self.yandex_default_client_key
            client_keys = {"default": default_client_key}

        client_key_output = ''

        for platform_name, client_key in client_keys.items():

            if not validate_only:
                print("Обработка платформы %s провайдера %s" % (platform_name,
                                                                self.provider))  # Выводим лог platform_name

            # если не задали отдельные ключи
            if ((platform_name == "electron_key" or platform_name == "huawei_key")
                    and default_client_key is not None and (client_key is None or len(client_key) < 1)):
                client_key = default_client_key
            elif platform_name == "default" and default_client_key is not None:
                client_key = default_client_key
            elif client_key is None or len(client_key) < 1:
                continue

            client_key_output += '"%s" => "%s",' % (platform_name, client_key)

        # удаляем последнюю запятую для корректного вывода
        client_key_output = client_key_output.rstrip(',')

        output = ""
        if len(client_key_output) < 1:
            return output

        client_key_output = '"client_keys" => [' + client_key_output

        if len(project_id_output) > 0:
            output += "%s," % project_id_output
        output += "%s, %s]" % (server_key_output, client_key_output)
        return output.encode().decode()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def handle_exception(field, message: str):
    if validate_only:
        if installer_output:
            validation_errors.append(field)
        else:
            validation_errors.append(message)
        return

    print(message)
    exit(1)


def start():
    generate_config()
    exit(0)


def write_file(output: str):
    if validate_only:
        if installer_output:
            if len(validation_errors) > 0:
                print(json.dumps(validation_errors, ensure_ascii=False))
                exit(1)
            print("[]")
        else:
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

    for provider in allowed_provider_list:
        providers[provider] = generate_provider_config(provider)

    output = make_output(providers)
    write_file(output)


def generate_provider_config(provider: str) -> dict:
    result = {}
    for app in app_list:
        result[app] = AppBlock(provider)

    return result


def make_output(providers: dict):
    config_head = r'''<?php

namespace Compass\Pivot;

$CONFIG["CAPTCHA_PROVIDER_LIST"] = [
'''
    provider_output = ""
    for provider, provider_values in providers.items():
        app_output = "\n"
        for app, app_block in provider_values.items():

            make_output = app_block.make_output()
            if len(make_output) > 0:
                app_output += '\t\t"%s" => [%s],\n' % (app, make_output)
                provider_output += '\t"%s" => [%s\t],\n' % (provider, app_output)
    config_end = r'''];
return $CONFIG;'''

    return config_head + provider_output + config_end


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
