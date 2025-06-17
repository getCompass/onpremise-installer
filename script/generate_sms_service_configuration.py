#!/usr/bin/python
# -*- coding: utf-8 -*-
from operator import truediv
import os.path
import sys, yaml
from utils.interactive import InteractiveValue, IncorrectValueException
from pathlib import Path
from utils import scriptutils
import argparse


# -------------------------------------------------------
# константы
# -------------------------------------------------------


# цвета текста
class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("--validate-only", required=False, action="store_true")

args = parser.parse_args()
validate_only = args.validate_only

# путь к папке с проектом
main_dir = str(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиги
config_path = Path(script_dir + "/../configs/auth.yaml")

config = {}
validation_errors = []
if not config_path.exists():
    print(
        scriptutils.error(
            "Отсутствует файл конфигурации %s. Запустите скрит create_configs.py и заполните конфигурацию"
            % str(config_path.resolve())
        )
    )
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(config_values)

# путь, где будет располагаться файл
conf_path = main_dir + "/src/pivot/config/pivot_sms.gophp"

# путь к шаблону SMS провайдера
template_path = main_dir + "/src/pivot/config/sms_provider_template.gophp"


def get_provider_entrypoint(provider: str):
    return provider_entrypoints[provider]


# список доступных провайдеров
# !!! WARNING !!!
# При добавлении нового провайдера необходимо добавить в этот список
# Включая поля для логина/пароля для подключения
credential_provider_list = {
    "sms_agent_alphanumeric_v1": {
        "provider_login_field": "login",  # поле для логина
        "provider_password_field": "password",  # поле для пароля
    },
    "vonage_alphanumeric_v1": {
        "provider_login_field": "api_key",  # поле для логина
        "provider_password_field": "api_secret",  # поле для пароля
    },
    "twilio_alphanumeric_v1": {
        "provider_login_field": "account_sid",  # поле для логина
        "provider_password_field": "account_auth_token",  # поле для пароля
    },
}

provider_names = {
    "sms_agent_alphanumeric_v1": "sms_agent",
    "vonage_alphanumeric_v1": "vonage",
    "twilio_alphanumeric_v1": "twilio",
}

provider_entrypoints = {
    "sms_agent_alphanumeric_v1": "https://api3.sms-agent.ru/v2.0/",
    "vonage_alphanumeric_v1": "https://rest.nexmo.com/",
    "twilio_alphanumeric_v1": "https://api.twilio.com/2010-04-01/",
}

# переменные для генерации конфигурационного файла
conf_generated_values = {
    "name": "pivot_sms.gophp",
    "path": conf_path,
    "template": template_path,
    "values": {
        "provide_phone_code_list": {
            "type": "arr_phone_prefix",
            "comment": "Укажите список обслуживаемых кодов сотовых операторов (через запятую, формата +79, +7935)",
            "default_value": None,
            "is_required": True,
        },
        "high_priority_phone_code_list": {
            "type": "arr_phone_prefix",
            "comment": "Укажите список кодов сотовых операторов, которые провайдер обслуживает с повышенным приоритетом (через запятую, формата +79, +7935)",
            "default_value": [],
            "is_required": False,
        },
        "min_balance_value": {
            "type": "int",
            "comment": "Введите минимальный порог баланса провайдера для его дальнейшего отключения",
            "default_value": None,
            "is_required": True,
        },
        "provider_gateway_url": {
            "type": "str",
            "comment": "Укажите URL провайдера для подключения SMS",
            "default_value": None,
            "value_function": None,
            "args": [],
            "is_required": True,
        },
        "provider_login": {
            "type": "str",
            "comment": "Введите логин провайдера для подключения SMS",
            "default_value": None,
            "is_required": True,
        },
        "provider_password": {
            "type": "password",
            "comment": "Введите пароль провайдера для подключения SMS",
            "default_value": None,
            "is_required": True,
        },
        "app_name": {
            "type": "str",
            "comment": "Введите идентификатор отправителя",
            "default_value": None,
            "is_required": True,
        },
    },
}

# вспомогательное сообщение
help_message = (
    "Для запуска генерации скрипта выполните команду: \r\n"
    "python3 generate_sms_config.py"
)

generate_conf_message = (
        bcolors.OKGREEN
        + "Конфигурационный файл сгенерирован и находится по следующему пути: \r\n"
        + conf_generated_values["path"]
        + "\r\n"
        + bcolors.ENDC
)

exist_conf_message = (
        bcolors.OKGREEN
        + "Конфигурационный файл находится по следующему пути: \r\n"
        + conf_generated_values["path"]
        + "\r\n"
        + bcolors.ENDC
)

main_template_start = (
    '<?php\r\n\r\n'
    'namespace Compass\\Pivot;\r\n\r\n'
    '$CONFIG["SMS_PROVIDER_LIST"] = [\r\n\r\n'
)

main_template_end = '];\r\n\r\n' 'return $CONFIG;'
# -------------------------------------------------------

# проверяем количество переданных аргументов
if len(sys.argv) < 2:
    sys.argv.append("")


# начинаем выполнение
def start():
    # начинаем генерацию файла конфигурации
    if not generate_template_config(conf_generated_values):
        return 1

    return 0


# проверить файл конфигурации на его наличие
def check_config_file():
    # проверяем, был ли он сгенерирован ранее. Если нет, просим сгенерировать
    if not os.path.isfile(conf_generated_values["path"]):
        print(
            bcolors.WARNING
            + "Не был найден конфигурационный файл "
            + conf_generated_values["name"]
            + ", который требуется для работы SMS.\r\nНачинаем генерацию файла конфигурации SMS..."
            + bcolors.ENDC
            + "\r\n"
        )
        return False

    return True


def handle_exception(field, message: str):
    if validate_only:
        validation_errors.append(message)
        return

    print(message)
    exit(1)


# генерируем конфигурационный файл по шаблону
def generate_template_config(conf_values: dict):
    # проверяем, что есть шаблон, по которому генерируем конфигурационный файл
    if not os.path.isfile(conf_values["template"]):
        print(
            bcolors.FAIL
            + "Не удалось найти шаблон "
            + conf_values["template"]
            + " SMS провайдера для конфигурационного файла "
            + str(conf_values["name"])
            + bcolors.ENDC
        )
        return False

    template = get_config_provider(conf_values)
    conf_path = Path(conf_values["path"])

    if template == "" and conf_path.exists():
        exit(0)

    if validate_only:
        if len(validation_errors) > 0:
            print("Ошибка в конфигурации %s" % str(config_path.resolve()))
            for error in validation_errors:
                print(error)
            exit(1)
        exit(0)

    # сохраняем всё в файл конфигурации
    conf_file = open(conf_values["path"], "w")
    conf_file.write(main_template_start)
    conf_file.write(template)
    conf_file.write(main_template_end)
    conf_file.close()

    # сообщаем о завершении генерации
    print(generate_conf_message)

    return True


# получаем провайдеров для конфигурации
def get_config_provider(conf_values: dict, main_template=""):
    available_methods = InteractiveValue(
        "available_methods", "Получаем доступные методы для авторизации", "arr", [], config=config, is_required=False
    ).from_config()

    available_guest_methods = InteractiveValue(
        "available_guest_methods", "Получаем доступные методы для авторизации гостей", "arr", [], config=config,
        is_required=False
    ).from_config()

    if available_methods == "[]" and available_guest_methods == "[]":
        return main_template

    # если указан номер телефона, то смс провайдер должен быть заполнен
    is_sms_provider_required = False
    if "phone_number" in available_methods or "phone_number" in available_guest_methods:
        is_sms_provider_required = True

    uncompleted_provider_list = []
    for provider, name in provider_names.items():
        # открываем файл шаблона
        template_file = open(conf_values["template"], "r")
        template = template_file.read()
        input_values = {}
        # получаем поля для аутентификации провайдера
        credential = credential_provider_list[provider]
        current_provider = provider

        # для каждого значения присваиваем значение в конфигурации
        for key, conf_value in conf_values["values"].items():
            if (
                    conf_value["default_value"] is None
                    and conf_value.get("value_function") is not None
            ):
                conf_value["default_value"] = conf_value["value_function"](
                    current_provider
                )

            # принимаем значение от пользователя
            if key in ["provider_login", "provider_password"]:
                input_values[key + "_field"] = credential[key + "_field"]
                conf_key = "%s.%s" % (name, credential[key + "_field"])
            else:
                conf_key = "%s.%s" % (name, key)

            try:
                value = InteractiveValue(
                    conf_key,
                    conf_value["comment"],
                    conf_value["type"],
                    conf_value["default_value"],
                    config=config,
                    is_required=False,
                ).from_config()
            except IncorrectValueException as e:
                handle_exception(e.field, e.message)
                value = None

            if (value is None or value == "[]") and (conf_value["is_required"]):
                uncompleted_provider_list.append(provider)
                break

            input_values[key] = value

        if provider in uncompleted_provider_list:
            continue
        input_values["sms_provider_name"] = current_provider

        # ищем и подменяем значение в шаблоне
        for key, value in input_values.items():
            if key == "provider_gateway_url" and value[-1] != "/":
                value += "/"

            template = template.replace("%" + key + "%", str(value))

        # добавляем к остальному шаблону
        main_template += template + "\r\n\r\n"

    if is_sms_provider_required and len(uncompleted_provider_list) == len(provider_names):
        scriptutils.die(
            "В конфигурации нет достаточно данных ни для одного провайдера SMS"
        )

        if validate_only:
            if len(validation_errors) > 0:
                print("Ошибка в конфигурации %s" % str(config_path.resolve()))
                for error in validation_errors:
                    print(error)
                exit(1)
            exit(0)
        exit(1)
    return main_template


# начинаем выполнение

try:
    sys.exit(start())
except KeyboardInterrupt:
    print("\r\nЗаполнение конфигурации было прервано")
