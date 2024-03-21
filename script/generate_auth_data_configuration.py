#!/usr/bin/env python3

import os, argparse, json
import re
from pathlib import Path
from subprocess import Popen
import yaml
from utils import scriptutils
from utils import interactive
import imaplib

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
    "--auth-output-path",
    required=False,
    default=root_path + "/src/pivot/config/pivot_auth.gophp",
    help="Путь до выходного файла auth конфига для авторизации/регистрации",
)

parser.add_argument(
    "--smtp-output-path",
    required=False,
    default=root_path + "/src/pivot/config/pivot_mail.gophp",
    help="Путь до выходного файла smtp конфига для почты",
)

parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)

args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

validate_only = args.validate_only

# пути для конфигов
auth_conf_path = args.auth_output_path
smtp_conf_path = args.smtp_output_path
auth_conf_path = Path(auth_conf_path)
smtp_conf_path = Path(smtp_conf_path)
validation_errors = []


class AuthMainConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            require_after: int,
            available_method_list: str,
    ):
        self.require_after = require_after
        self.available_method_list = available_method_list

    def input(self):

        # получаем значение количества попыток из конфига
        try:
            require_after = interactive.InteractiveValue(
                "captcha.require_after", "Кол-во попыток аутентификации, после которых запрашивается разгадывание капчи.", "int", config=config,
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        # получаем значение доступных методов из конфига
        try:
            available_method_list = interactive.InteractiveValue(
                "available_methods", "Доступные способы аутентификации", "arr", config=config,
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        return self.init(require_after, available_method_list)

    # заполняем содержимым
    def make_output(self):
        available_method_list_output = '"available_method_list" => %s' % (self.available_method_list)
        captcha_require_after_output = '"captcha_require_after" => %d' % (self.require_after)

        output = "\n%s,\n %s\n" % (available_method_list_output, captcha_require_after_output)
        return output.encode().decode()

class AuthMailConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            allowed_domain_list: str,
            registration_2fa_enabled: int,
            authorization_2fa_enabled: int,
    ):
        self.allowed_domain_list = allowed_domain_list
        self.registration_2fa_enabled = registration_2fa_enabled
        self.authorization_2fa_enabled = authorization_2fa_enabled

    def input(self):

        # получаем значение доступных доменов из конфига
        allowed_domain_list = interactive.InteractiveValue(
            "mail.allowed_domains",
            "Введите список доменов почтовых адресов, для которых разрешена аутентификация в приложении (через запятую, формата \"example.com\", \"domain.ru\")",
            "arr",
            config=config,
            is_required=False,
            default_value=[]
        ).from_config()

        # проверяем количество доменов почтовых адресов
        if len(allowed_domain_list.split(",")) > 3:
            scriptutils.die(
               "Превышено количество доступных доментов почтовых адресов: не более 3"
            )

        # проверяем, что список содержит только ENG домены
        for domain in allowed_domain_list.split(","):

            domain = domain.replace('"', "")
            domain = domain.replace('[', "")
            domain = domain.replace(']', "")
            if re.search(r'[^a-z\W\d]', domain.lower()) is not None:
                scriptutils.die(
                   "Разрешены только ENG домены"
                )

        # получаем значение опции подтверждения почты
        try:
            registration_2fa_enabled = interactive.InteractiveValue(
                "mail.registration_2fa_enabled", "Включена ли опция подтверждения почты при регистрации через проверочный код", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            authorization_2fa_enabled = interactive.InteractiveValue(
                "mail.authorization_2fa_enabled", "Включена ли опция подтверждения почты при авторизации через проверочный код", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        return self.init(allowed_domain_list, registration_2fa_enabled, authorization_2fa_enabled)

    # заполняем содержимым
    def make_output(self):
        allowed_domain_list_output = '"allowed_domain_list" => %s' % (self.allowed_domain_list)
        mail_registration_2fa_enabled_output = '"registration_2fa_enabled" => %s' % (str(self.registration_2fa_enabled).lower())
        mail_authorization_2fa_enabled_output = '"authorization_2fa_enabled" => %s' % (str(self.authorization_2fa_enabled).lower())

        output = "\n%s,\n %s,\n %s\n" % (allowed_domain_list_output, mail_registration_2fa_enabled_output, mail_authorization_2fa_enabled_output)
        return output.encode().decode()

class MailSmtpConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            smtp_host: str,
            smtp_port: str,
            smtp_username: str,
            smtp_password: str,
            smtp_encryption: str,
            smtp_from: str,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_encryption = smtp_encryption
        self.smtp_from = smtp_from

    def input(self):

        # получаем значение опции подтверждения почты
        try:
            registration_2fa_enabled = interactive.InteractiveValue(
                "mail.registration_2fa_enabled", "Включена ли опция подтверждения почты при регистрации через проверочный код", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            authorization_2fa_enabled = interactive.InteractiveValue(
                "mail.authorization_2fa_enabled", "Включена ли опция подтверждения почты при авторизации через проверочный код", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        # получаем значение доступных методов для авторизации
        available_methods = interactive.InteractiveValue(
            "available_methods", "Получаем доступные методы для авторизации", "arr", [], config=config, is_required=False
        ).from_config()

        # если указан mail в качестве доступного метода авторизации, то данные для smtp должны быть заполнены
        is_mail_smtp_required = False
        if "mail" in available_methods:
            is_mail_smtp_required = True

        try:
            smtp_host = interactive.InteractiveValue(
                "smtp.host", "Хост для отправки писем по SMTP", "str", config=config, default_value="", is_required=is_mail_smtp_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            smtp_host = ""

        try:
            smtp_port = interactive.InteractiveValue(
                "smtp.port", "Порт для отправки писем по SMTP", "int", config=config, default_value=0, is_required=is_mail_smtp_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            smtp_port = 0

        try:
            smtp_username = interactive.InteractiveValue(
                "smtp.username", "Имя пользователя для отправки писем по SMTP", "str", config=config, default_value="", is_required=False, validation="mail"
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            smtp_username = ""

        try:
            smtp_password = interactive.InteractiveValue(
                "smtp.password", "Пароль для отправки писем по SMTP", "str", config=config, default_value="", is_required=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            smtp_password = ""

        try:
            smtp_encryption = interactive.InteractiveValue(
                "smtp.encryption", "Тип шифрования соединения по SMTP", "str", config=config, default_value="", is_required=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            smtp_encryption = ""

        try:
            smtp_from = interactive.InteractiveValue(
                "smtp.from", "Электронный адрес отправителя", "str", config=config, default_value="", is_required=is_mail_smtp_required, validation="mail"
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            smtp_from = ""

        return self.init(smtp_host, smtp_port, smtp_username, smtp_password, smtp_encryption, smtp_from)

    # заполняем содержимым
    def make_output(self):
        smtp_host_output = '"host" => "%s"' % (self.smtp_host)
        smtp_port_output = '"port" => %d' % (self.smtp_port)
        smtp_username_output = '"username" => "%s"' % (self.smtp_username)
        smtp_password_output = '"password" => "%s"' % (self.smtp_password)
        smtp_encryption_output = '"encryption" => "%s"' % (self.smtp_encryption)
        smtp_from_output = '"from" => "%s"' % (self.smtp_from)

        output = "\n%s,\n %s,\n %s,\n %s,\n %s,\n %s\n" % (smtp_host_output, smtp_port_output, smtp_username_output, smtp_password_output, smtp_encryption_output, smtp_from_output)
        return output.encode().decode()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def handle_exception(field, message: str):
    if validate_only:
        validation_errors.append(message)
        return

    print(message)
    exit(1)


# начинаем выполнение
def start():
    generate_config()
    exit(0)

# записываем содержимое в файл
def write_file(output: str, conf_path: Path):
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
        scriptutils.warning(str(conf_path.resolve()))
    )

# генерируем конфиг
def generate_config():

    # генерируем данные для аутентификации
    auth_config_list = generate_auth_config()
    auth_output = make_auth_output(auth_config_list)

    # генерируем данные для smtp почты
    smtp_config_list = generate_smtp_config()
    smtp_output = make_smtp_output(smtp_config_list)

    # если только валидируем данные, то файлы не пишем
    if validate_only:

        if len(validation_errors) > 0:
            print("Ошибка в конфигурации %s" % str(config_path.resolve()))
            for error in validation_errors:
                print(error)
            exit(1)
        exit(0)

    if len(validation_errors) == 0:
        print(
            scriptutils.success(
                "Файлы с настройками аутентификации сгенерированы по следующему пути: "
            )
        )

    write_file(auth_output, auth_conf_path)
    write_file(smtp_output, smtp_conf_path)

# получаем содержимое конфига для аутентификации
def make_auth_output(auth_config_list: list):

    # получаем конфиг для главной информации аутентификации
    auth_main_config = auth_config_list[0]
    auth_main_config_head = """<?php

namespace Compass\Pivot;

/**
 * основные параметры аутентификации
 */
$CONFIG["AUTH_MAIN"] = [
"""
    auth_main_output = auth_main_config.make_output()
    auth_main_config_end = """];
"""

    # получаем конфиг для информации по почте
    auth_mail_config = auth_config_list[1]
    auth_mail_config_head = """

/**
 * параметры аутентификации через почту
 */
$CONFIG["AUTH_MAIL"] = [
"""
    auth_mail_output = auth_mail_config.make_output()
    auth_mail_config_end = """];

return $CONFIG;"""

    return auth_main_config_head + auth_main_output + auth_main_config_end + auth_mail_config_head + auth_mail_output + auth_mail_config_end

# получаем содержимое конфига для smtp почты
def make_smtp_output(smtp_config_list: list):

    smtp_main_config = smtp_config_list[0]

    smtp_main_config_head = """<?php

namespace Compass\Pivot;

$CONFIG["MAIL_SMTP"] = [
"""
    smtp_main_output = smtp_main_config.make_output()

    smtp_main_config_end = """];
return $CONFIG;"""

    return smtp_main_config_head + smtp_main_output + smtp_main_config_end

# генерируем данные для аутентификации
def generate_auth_config() -> dict:

    result = [AuthMainConfig(), AuthMailConfig()]

    return result

# генерируем данные для smtp почты
def generate_smtp_config() -> dict:

    result = [MailSmtpConfig()]

    return result


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
