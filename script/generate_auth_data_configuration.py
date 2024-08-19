#!/usr/bin/env python3

import os, argparse, json
import re
from pathlib import Path
from subprocess import Popen
import yaml
from utils import scriptutils
from utils import interactive
from utils.scriptutils import bcolors
import imaplib
import requests
import json

# ---АГРУМЕНТЫ СКРИПТА---#

script_dir = str(Path(__file__).parent.resolve())

# загружаем конфиги
config_path = Path(script_dir + "/../configs/auth.yaml")
captcha_config_path = Path(script_dir + "/../configs/captcha.yaml")

config = {}

if not config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрит create_configs.py и заполните конфигурацию" % str(
            config_path.resolve())))
    exit(1)
if not captcha_config_path.exists():
    print(scriptutils.error(
        "Отсутствует файл конфигурации %s. Запустите скрит create_configs.py и заполните конфигурацию" % str(
            captcha_config_path.resolve())))
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)
config.update(config_values)

with captcha_config_path.open("r") as config_file:
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
    "--sso-output-path",
    required=False,
    default=root_path + "/src/federation/config/sso.gophp",
    help="Путь до выходного файла конфига для SSO",
)

parser.add_argument(
    "--ldap-output-path",
    required=False,
    default=root_path + "/src/federation/config/ldap.gophp",
    help="Путь до выходного файла конфига для LDAP",
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
sso_conf_path = args.sso_output_path
ldap_conf_path = args.ldap_output_path
auth_conf_path = Path(auth_conf_path)
smtp_conf_path = Path(smtp_conf_path)
sso_conf_path = Path(sso_conf_path)
ldap_conf_path = Path(ldap_conf_path)
validation_errors = []


class AuthMainConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            captcha_enabled: int,
            require_after: int,
            available_method_list: str,
    ):
        self.captcha_enabled = captcha_enabled
        self.require_after = require_after
        self.available_method_list = available_method_list

    def input(self):

        # получаем настройку включения проверки капчи
        try:
            captcha_enabled = interactive.InteractiveValue(
                "captcha.enabled", "Включена ли опция проверки капчи при достижении лимита попыток аутентификации.", "bool", config=config,
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        # получаем значение количества попыток из конфига
        try:
            require_after = interactive.InteractiveValue(
                "captcha.require_after",
                "Кол-во попыток аутентификации, после которых запрашивается разгадывание капчи.",
                "int",
                config=config,
                is_required=(captcha_enabled == True),
                default_value=0,
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

        return self.init(captcha_enabled, require_after, available_method_list)

    # заполняем содержимым
    def make_output(self):
        available_method_list_output = '"available_method_list" => %s' % (self.available_method_list)
        captcha_enabled_output = '"captcha_enabled" => %s' % (str(self.captcha_enabled).lower())
        captcha_require_after_output = '"captcha_require_after" => %d' % (self.require_after)

        output = "\n%s,\n %s,\n %s\n" % (available_method_list_output, captcha_enabled_output, captcha_require_after_output)
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

class AuthSsoConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            sso_protocol: str,
            sso_web_auth_button_text: str,
            authorization_alternative_enabled: bool,
            full_name_actualization_enabled: bool,
            auto_join_to_team: str,
    ):
        self.sso_protocol = sso_protocol
        self.sso_web_auth_button_text = sso_web_auth_button_text
        self.authorization_alternative_enabled = authorization_alternative_enabled
        self.full_name_actualization_enabled = full_name_actualization_enabled
        self.auto_join_to_team = auto_join_to_team

    def input(self):

        # получаем значение доступных методов для авторизации
        available_methods = interactive.InteractiveValue(
            "available_methods", "Получаем доступные методы для авторизации", "arr", [], config=config, is_required=False
        ).from_config()

        # если указан sso в качестве доступного метода авторизации, то данные должны быть заполнены
        is_required = False
        if "sso" in available_methods:
            is_required = True

        try:
            sso_protocol = interactive.InteractiveValue(
                "sso.protocol", "Укажите протокол, который будет использоваться для аутентификации", "str", config=config, default_value="", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_protocol = ""

        try:
            sso_web_auth_button_text = interactive.InteractiveValue(
                "sso.web_auth_button_text", "Кастомный текст кнопки для запуска аутентификации через SSO на веб-сайте On-Premise решения", "str", config=config, default_value="Войти через корп. портал (AD SSO)", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_web_auth_button_text = ""

        try:
            authorization_alternative_enabled = interactive.InteractiveValue(
                "sso.authorization_alternative_enabled", "Включена ли опция альтернативных способов аутентификации при аутентификации через SSO", "bool", config=config, is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            authorization_alternative_enabled = ""

        try:
            full_name_actualization_enabled = interactive.InteractiveValue(
                "sso.full_name_actualization_enabled", "Включена ли опция актуализации Имени Фамилии пользователей в Compass каждый раз, когда они успешно авторизуются в приложении через SSO", "bool", config=config, is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            full_name_actualization_enabled = ""

        try:
            auto_join_to_team = interactive.InteractiveValue(
                "sso.auto_join_to_team", "Автоматическое вступление пользователей после регистрации через SSO/LDAP в первую команду на сервере", "str", config=config, is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            auto_join_to_team = ""

        return self.init(sso_protocol, sso_web_auth_button_text, authorization_alternative_enabled, full_name_actualization_enabled, auto_join_to_team)

    # подготавливаем содержимое для $CONFIG["AUTH_SSO"]
    def make_output(self):
        return """"protocol" => "{}",\n\t"start_button_text" => "{}",\n\t"authorization_alternative_enabled" => {},\n\t"full_name_actualization_enabled" => {},\n\t"auto_join_to_team" => "{}",""".format(
            self.sso_protocol,
            self.sso_web_auth_button_text,
            self.authorization_alternative_enabled,
            self.full_name_actualization_enabled,
            self.auto_join_to_team,
        )

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

class SsoConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            sso_client_id: str,
            sso_client_secret: str,
            sso_oidc_provider_metadata: str,
            sso_attribution_mapping_first_name: str,
            sso_attribution_mapping_last_name: str,
            sso_attribution_mapping_mail: str,
            sso_attribution_mapping_phone_number: str,

    ):
        self.sso_client_id = sso_client_id
        self.sso_client_secret = sso_client_secret
        self.sso_oidc_provider_metadata = sso_oidc_provider_metadata
        self.sso_attribution_mapping_first_name = sso_attribution_mapping_first_name
        self.sso_attribution_mapping_last_name = sso_attribution_mapping_last_name
        self.sso_attribution_mapping_mail = sso_attribution_mapping_mail
        self.sso_attribution_mapping_phone_number = sso_attribution_mapping_phone_number

    def input(self):

        # получаем значение доступных методов для авторизации
        available_methods = interactive.InteractiveValue(
            "available_methods", "Получаем доступные методы для авторизации", "arr", [], config=config, is_required=False
        ).from_config()

        # получаем протокол sso
        sso_protocol = interactive.InteractiveValue(
            "sso.protocol", "Получаем доступные методы для авторизации", "str", config=config, is_required=False
        ).from_config()

        # проверяем, что указано корректное значение
        if "sso" in available_methods and sso_protocol not in ["oidc", "ldap"]:
            handle_exception("sso.protocol", bcolors.WARNING + "Некорректное значение для параметра sso.protocol в конфиг-файле auth.yaml" + bcolors.ENDC)

        # если указан sso в качестве доступного метода авторизации и протокол OIDC, то данные должны быть заполнены
        is_required = False
        if "sso" in available_methods and sso_protocol == "oidc":
            is_required = True

        try:
            sso_client_id = interactive.InteractiveValue(
                "oidc.client_id", "ID клиентского приложения", "str", config=config, default_value="", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_client_id = ""

        try:
            sso_client_secret = interactive.InteractiveValue(
                "oidc.client_secret", "Секретный ключ клиентского приложения", "str", config=config, default_value="", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_client_secret = ""

        try:

            sso_oidc_provider_metadata_link = interactive.InteractiveValue(
                "oidc.oidc_provider_metadata_link", "Ссылка на метаданные SSO провайдера", "str", config=config, default_value="", is_required=is_required
            ).from_config()

            # если SSO параметры обязательны к заполнению, то получаем содержимое по ссылке
            # иначе укажим дефолтные занчения
            if is_required:
                # загрузка содержимого страницы
                response = requests.get(sso_oidc_provider_metadata_link)

                # проверка на наличие ошибок при запросе
                response.raise_for_status()

                # Проверка, является ли содержимое JSON строкой
                sso_oidc_provider_metadata = json.dumps(response.json(), ensure_ascii=False)
            else:
                sso_oidc_provider_metadata = "{}"

        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_oidc_provider_metadata = "{}"

        except requests.RequestException:
            handle_exception("oidc.oidc_provider_metadata_link", "Не удалось получить содержимое ссылки с метаданными SSO провайдера")
            sso_oidc_provider_metadata = "{}"

        except json.decoder.JSONDecodeError:
            handle_exception("oidc.oidc_provider_metadata_link", "Содержимое ссылки не является JSON объектом с метаданными SSO провайдера")
            sso_oidc_provider_metadata = "{}"

        try:
            sso_attribution_mapping_first_name = interactive.InteractiveValue(
                "oidc.attribution_mapping.first_name", "Сопоставление атрибута first_name (имя) между учетной записью SSO и профилем пользователя Compass", "str", config=config, default_value="", is_required=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_attribution_mapping_first_name = ""

        try:
            sso_attribution_mapping_last_name = interactive.InteractiveValue(
                "oidc.attribution_mapping.last_name", "Сопоставление атрибута last_name (фамилия) между учетной записью SSO и профилем пользователя Compass", "str", config=config, default_value="", is_required=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_attribution_mapping_last_name = ""

        try:
            sso_attribution_mapping_mail = interactive.InteractiveValue(
                "oidc.attribution_mapping.mail", "Сопоставление атрибута mail (почта) между учетной записью SSO и профилем пользователя Compass", "str", config=config, default_value="", is_required=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_attribution_mapping_mail = ""

        try:
            sso_attribution_mapping_phone_number = interactive.InteractiveValue(
                "oidc.attribution_mapping.phone_number", "Сопоставление атрибута phone_number (номер телефона) между учетной записью SSO и профилем пользователя Compass", "str", config=config, default_value="", is_required=False
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            sso_attribution_mapping_phone_number = ""

        # проверяем, что одно из полей first_name или last_name заполнены и одно из полей mail или phone_number заполнены
        if is_required and sso_attribution_mapping_first_name == "" and sso_attribution_mapping_last_name == "" and sso_attribution_mapping_mail == "" and sso_attribution_mapping_phone_number == "":
            handle_exception("", scriptutils.warning("Для корректной работы SSO аутентификации необходимо заполнить хотя бы один из параметров в парах:\n– sso.attribution_mapping.first_name или sso.attribution_mapping.last_name\n– sso.attribution_mapping.mail или sso.attribution_mapping.phone_number"))
        elif is_required and sso_attribution_mapping_first_name == "" and sso_attribution_mapping_last_name == "":
            handle_exception("", scriptutils.warning("Для корректной работы SSO аутентификации необходимо заполнить хотя бы один из параметров:\nsso.attribution_mapping.first_name или sso.attribution_mapping.last_name"))
        elif is_required and sso_attribution_mapping_mail == "" and sso_attribution_mapping_phone_number == "":
            handle_exception("", scriptutils.warning("Для корректной работы SSO аутентификации необходимо заполнить хотя бы один из параметров:\nsso.attribution_mapping.mail или sso.attribution_mapping.phone_number"))

        return self.init(sso_client_id, sso_client_secret, sso_oidc_provider_metadata, sso_attribution_mapping_first_name, sso_attribution_mapping_last_name, sso_attribution_mapping_mail, sso_attribution_mapping_phone_number)

    # подготавливаем содержимое для $CONFIG["SSO_OIDC_CONNECTION"]
    def make_sso_oidc_connection_output(self):
        return """"client_id" => "{}",\n\t"client_secret" => "{}",""".format(self.sso_client_id, self.sso_client_secret)

    # подготавливаем содержимое для $CONFIG["SSO_ATTRIBUTION_MAPPING"]
    def make_sso_attribution_mapping_output(self):
        return """"first_name" => "{}",\n\t"last_name" => "{}",\n\t"mail" => "{}",\n\t"phone_number" => "{}",""".format(
            self.sso_attribution_mapping_first_name,
            self.sso_attribution_mapping_last_name,
            self.sso_attribution_mapping_mail,
            self.sso_attribution_mapping_phone_number,
        )

class LdapConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            server_host: str,
            server_port: int,
            user_search_base: str,
            user_unique_attribute: str,
            limit_of_incorrect_auth_attempts: int,
            account_disabling_monitoring_enabled: str,
            on_account_removing: str,
            on_account_disabling: str,
            user_search_account_dn: str,
            user_search_account_password: str,
            account_disabling_monitoring_interval: str,
            user_search_page_size: int,

    ):
        self.server_host = server_host
        self.server_port = server_port
        self.user_search_base = user_search_base
        self.user_unique_attribute = user_unique_attribute
        self.limit_of_incorrect_auth_attempts = limit_of_incorrect_auth_attempts
        self.account_disabling_monitoring_enabled = account_disabling_monitoring_enabled
        self.on_account_removing = on_account_removing
        self.on_account_disabling = on_account_disabling
        self.user_search_account_dn = user_search_account_dn
        self.user_search_account_password = user_search_account_password
        self.account_disabling_monitoring_interval = account_disabling_monitoring_interval
        self.user_search_page_size = user_search_page_size

    def input(self):

        # получаем значение доступных методов для авторизации
        available_methods = interactive.InteractiveValue(
            "available_methods", "Получаем доступные методы для авторизации", "arr", [], config=config, is_required=False
        ).from_config()

        # получаем протокол sso
        sso_protocol = interactive.InteractiveValue(
            "sso.protocol", "Получаем доступные методы для авторизации", "str", config=config, is_required=False
        ).from_config()

        # если указан sso в качестве доступного метода авторизации и протокол LDAP, то данные должны быть заполнены
        is_required = False
        if "sso" in available_methods and sso_protocol == "ldap":
            is_required = True

        try:
            ldap_server_host = interactive.InteractiveValue(
                "ldap.server_host", "Хост сервера LDAP", "str", config=config, default_value="", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_server_host = ""

        try:
            ldap_server_port = interactive.InteractiveValue(
                "ldap.server_port", "Порт сервера LDAP", "int", config=config, default_value=0, is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_server_port = 0

        try:
            ldap_user_search_base = interactive.InteractiveValue(
                "ldap.user_search_base", "Контекст поиска пользователей в LDAP каталоге", "str", config=config, default_value="", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_user_search_base = ""

        try:
            ldap_user_unique_attribute = interactive.InteractiveValue(
                "ldap.user_unique_attribute", "Название атрибута учетной записи LDAP, значение которого будет использоваться в качестве username в форме авторизации", "str", config=config, default_value="", is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_user_unique_attribute = ""

        try:
            ldap_limit_of_incorrect_auth_attempts = interactive.InteractiveValue(
                "ldap.limit_of_incorrect_auth_attempts", "Лимит неудачных попыток аутентификации, по достижению которых IP адрес пользователя получает блокировку на 15 минут", "int", config=config, default_value=7, is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_limit_of_incorrect_auth_attempts = 7

        try:
            ldap_account_disabling_monitoring_enabled = interactive.InteractiveValue(
                "ldap.account_disabling_monitoring_enabled", "Включен ли мониторинг удаления / блокировки учетной записи LDAP для запуска автоматической блокировки связанного пользователя в Compass", "bool", config=config, is_required=is_required
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_account_disabling_monitoring_enabled = False

        try:
            ldap_on_account_removing = interactive.InteractiveValue(
                "ldap.on_account_removing", "Уровень автоматической блокировки при полном удалении учетной записи LDAP связанной с пользователем Compass", "str", config=config, default_value="", is_required=ldap_account_disabling_monitoring_enabled
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_on_account_removing = ""

        # проверяем, что указано корректное значение
        if ldap_account_disabling_monitoring_enabled and ldap_on_account_removing not in ["light", "hard"]:
            handle_exception("ldap.on_account_removing", bcolors.WARNING + "Некорректное значение для параметра ldap.on_account_removing в конфиг-файле auth.yaml" + bcolors.ENDC)

        try:
            ldap_on_account_disabling = interactive.InteractiveValue(
                "ldap.on_account_disabling", "Уровень автоматической блокировки при помечании отключенной учетной записи LDAP связанной с пользователем Compass", "str", config=config, default_value="", is_required=ldap_account_disabling_monitoring_enabled
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_on_account_disabling = ""

        # проверяем, что указано корректное значение
        if ldap_account_disabling_monitoring_enabled and ldap_on_account_disabling not in ["light", "hard"]:
            handle_exception("ldap.on_account_disabling", bcolors.WARNING + "Некорректное значение для параметра ldap.on_account_disabling в конфиг-файле auth.yaml" + bcolors.ENDC)

        try:
            ldap_user_search_account_dn = interactive.InteractiveValue(
                "ldap.user_search_account_dn", "Полный DN (Distinguished Name) учетной записи LDAP, которая будет использоваться для поиска других учетных записей и мониторинга их удаления/блокировки в каталоге", "str", config=config, default_value="", is_required=ldap_account_disabling_monitoring_enabled
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_user_search_account_dn = ""

        try:
            ldap_user_search_account_password = interactive.InteractiveValue(
                "ldap.user_search_account_password", "Пароль учетной записи LDAP, которая будет использоваться для поиска других учетных записей и мониторинга их удаления/блокировки в каталоге", "str", config=config, default_value="", is_required=ldap_account_disabling_monitoring_enabled
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_user_search_account_password = ""

        try:
            ldap_account_disabling_monitoring_interval = interactive.InteractiveValue(
                "ldap.account_disabling_monitoring_interval", "Временной интервал между проверками мониторинга блокировки пользователя LDAP", "str", config=config, default_value="", is_required=ldap_account_disabling_monitoring_enabled
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_account_disabling_monitoring_interval = ""

        # проверяем, что указано корректное значение
        if ldap_account_disabling_monitoring_enabled and bool(re.match(r'^\d+[smh]$',ldap_account_disabling_monitoring_interval)) == False:
            handle_exception("ldap.account_disabling_monitoring_interval", bcolors.WARNING + "Некорректное значение для параметра ldap.account_disabling_monitoring_interval в конфиг-файле auth.yaml" + bcolors.ENDC)

        try:
            ldap_user_search_page_size = interactive.InteractiveValue(
                "ldap.user_search_page_size", "Количество подгружаемых учетных записей из LDAP за один запрос в механизме мониторинга удаления / блокировки учетной записи LDAP", "int", config=config, default_value=0, is_required=ldap_account_disabling_monitoring_enabled
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)
            ldap_user_search_page_size = 0

        # проверяем, что указано корректное значение
        if ldap_account_disabling_monitoring_enabled and ldap_user_search_page_size < 1:
            handle_exception("ldap.user_search_page_size", bcolors.WARNING + "Некорректное значение для параметра ldap.user_search_page_size в конфиг-файле auth.yaml" + bcolors.ENDC)

        return self.init(ldap_server_host, ldap_server_port, ldap_user_search_base, ldap_user_unique_attribute, ldap_limit_of_incorrect_auth_attempts, ldap_account_disabling_monitoring_enabled, ldap_on_account_removing, ldap_on_account_disabling, ldap_user_search_account_dn, ldap_user_search_account_password, ldap_account_disabling_monitoring_interval, ldap_user_search_page_size)

    # подготавливаем содержимое для $CONFIG["SSO_OIDC_CONNECTION"]
    def make_output(self):
        return """"host" => "{}",\n\t"port" => {},\n\t"user_search_base" => "{}",\n\t"user_search_page_size" => "{}",\n\t"user_unique_attribute" => "{}",\n\t"limit_of_incorrect_auth_attempts" => {},\n\t"account_disabling_monitoring_enabled" => {},\n\t"on_account_removing" => "{}",\n\t"on_account_disabling" => "{}",\n\t"user_search_account_dn" => "{}",\n\t"user_search_account_password" => "{}",\n\t"account_disabling_monitoring_interval" => "{}",\n\t""".format(
            self.server_host,
            self.server_port,
            self.user_search_base,
            self.user_search_page_size,
            self.user_unique_attribute,
            self.limit_of_incorrect_auth_attempts,
            self.account_disabling_monitoring_enabled,
            self.on_account_removing,
            self.on_account_disabling,
            self.user_search_account_dn,
            self.user_search_account_password,
            self.account_disabling_monitoring_interval,
        )

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

    # генерируем данные для sso
    sso_config_list = generate_sso_config()
    sso_output = make_sso_output(sso_config_list)

    # генерируем данные для ldap
    ldap_config_list = generate_ldap_config()
    ldap_output = make_ldap_output(ldap_config_list)

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
    write_file(sso_output, sso_conf_path)
    write_file(ldap_output, ldap_conf_path)

# получаем содержимое конфига для аутентификации
def make_auth_output(auth_config_list: list):

    # получаем конфиги
    auth_main_config = auth_config_list[0]
    auth_mail_config = auth_config_list[1]
    auth_sso_config = auth_config_list[2]

    return """<?php

namespace Compass\Pivot;

/**
 * основные параметры аутентификации
 */
$CONFIG["AUTH_MAIN"] = [

    {}
];


/**
 * параметры аутентификации через почту
 */
$CONFIG["AUTH_MAIL"] = [

    {}
];

/**
 * параметры аутентификации через sso
 */
$CONFIG["AUTH_SSO"] = [

    {}
];

return $CONFIG;""".format(auth_main_config.make_output(), auth_mail_config.make_output(), auth_sso_config.make_output())

# получаем содержимое конфига для smtp почты
def make_smtp_output(smtp_config_list: list):

    smtp_main_config = smtp_config_list[0]

    return """<?php

namespace Compass\Pivot;

$CONFIG["MAIL_SMTP"] = [
    {}
];
return $CONFIG;""".format(smtp_main_config.make_output())

# получаем содержимое конфига для sso аутентификации
def make_sso_output(sso_config_list: list):

    sso_main_config = sso_config_list[0]
    return """<?php

namespace Compass\Federation;

/** параметры подключения SSO провайдера по OpenID Connect протоколу */
$CONFIG["SSO_OIDC_CONNECTION"] = [
	{}
];

/** маппинг аттрибутов/полей SSO аккаунта, для их передачи в Compass */
$CONFIG["SSO_ATTRIBUTION_MAPPING"] = [
	{}
];

/** конфигуруация SSO провайдера */
$CONFIG["SSO_OIDC_PROVIDER_CONFIG"] = json_decode('{}', true, 512, JSON_BIGINT_AS_STRING);

return $CONFIG;""".format(
        sso_main_config.make_sso_oidc_connection_output(),
        sso_main_config.make_sso_attribution_mapping_output(),
        sso_main_config.sso_oidc_provider_metadata
    )

# получаем содержимое конфига для ldap аутентификации
def make_ldap_output(ldap_config_list: list):

    ldap_main_config = ldap_config_list[0]
    return """<?php

namespace Compass\Federation;

/** параметры подключения LDAP провайдера для аутентификации */
$CONFIG["LDAP"] = [
	{}
];

return $CONFIG;""".format(
        ldap_main_config.make_output(),
    )

# генерируем данные для аутентификации
def generate_auth_config() -> dict:

    result = [AuthMainConfig(), AuthMailConfig(), AuthSsoConfig()]

    return result

# генерируем данные для smtp почты
def generate_smtp_config() -> dict:

    result = [MailSmtpConfig()]

    return result

# генерируем данные для sso
def generate_sso_config() -> dict:

    result = [SsoConfig()]

    return result

# генерируем данные для ldap
def generate_ldap_config() -> dict:

    result = [LdapConfig()]

    return result


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
