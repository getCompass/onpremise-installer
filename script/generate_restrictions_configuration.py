#!/usr/bin/env python3

import argparse
from pathlib import Path
import yaml, json
from utils import scriptutils
from utils import interactive

# ---АРГУМЕНТЫ СКРИПТА---#

script_dir = Path(__file__).parent.resolve()

# загружаем конфиги
auth_config_path = script_dir.parent / "configs" / "auth.yaml"
team_config_path = script_dir.parent / "configs" / "team.yaml"

config = {}

if not auth_config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {auth_config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

if not team_config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {team_config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

with auth_config_path.open("r") as config_file:
    auth_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

with team_config_path.open("r") as config_file:
    team_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(auth_config_values)
config.update(team_config_values)

root_path = script_dir.parent.resolve()

parser = scriptutils.create_parser(
    "Скрипт для создания конфигурации ограничений.",
    usage="python3 script/generate_restrictions_configuration.py [--pivot-restrictions-output-path PIVOT_RESTRICTIONS_OUTPUT_PATH] [--domino-restrictions-output-path DOMINO_RESTRICTIONS_OUTPUT_PATH] [--integration-restrictions-output-path INTEGRATION_RESTRICTIONS_OUTPUT_PATH] [--validate-only] [--installer-output]",
    epilog="Пример: python3 script/generate_restrictions_configuration.py --pivot-restrictions-output-path /home/compass/src/pivot/config/restrictions.gophp --domino-restrictions-output-path /home/compass/src/domino/config/company_restrictions.gophp --integration-restrictions-output-path /home/compass/src/integration/config/restrictions.gophp --validate-only --installer-output",
)

parser.add_argument("--pivot-restrictions-output-path", required=False,
                    default=root_path / "src" / "pivot" / "config" / "restrictions.gophp",
                    help="Путь до выходного файла pivot конфига ограничений")
parser.add_argument("--domino-restrictions-output-path", required=False,
                    default=root_path / "src" / "domino" / "config" / "company_restrictions.gophp",
                    help="Путь до выходного файла domino конфига ограничений")
parser.add_argument("--integration-restrictions-output-path", required=False,
                    default=root_path / "src" / "integration" / "config" / "restrictions.gophp",
                    help="Путь до выходного файла integration конфига ограничений")
parser.add_argument("--validate-only", required=False, action="store_true",
                    help='Запуск скрипта в режиме read-only, без применения изменений')
parser.add_argument("--installer-output", required=False, action="store_true",
                    help='Вывод ошибок в формате JSON')
args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

validate_only = args.validate_only
installer_output = args.installer_output

# пути для конфигов
pivot_restrictions_conf_path = args.pivot_restrictions_output_path
pivot_restrictions_conf_path = Path(pivot_restrictions_conf_path)
domino_restrictions_conf_path = args.domino_restrictions_output_path
domino_restrictions_conf_path = Path(domino_restrictions_conf_path)
integration_restrictions_conf_path = args.integration_restrictions_output_path
integration_restrictions_conf_path = Path(integration_restrictions_conf_path)
validation_errors = []
validation_error_config_path = ""


class RestrictionsMainConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            is_desktop_prohibited: int,
            is_ios_prohibited: int,
            is_android_prohibited: int,
            phone_change_enabled: int,
            mail_change_enabled: int,
            name_change_enabled: int,
            avatar_change_enabled: int,
            badge_change_enabled: int,
            description_change_enabled: int,
            status_change_enabled: int,
            deletion_enabled: int,
    ):
        self.is_desktop_prohibited = is_desktop_prohibited
        self.is_ios_prohibited = is_ios_prohibited
        self.is_android_prohibited = is_android_prohibited
        self.phone_change_enabled = phone_change_enabled
        self.mail_change_enabled = mail_change_enabled
        self.name_change_enabled = name_change_enabled
        self.avatar_change_enabled = avatar_change_enabled
        self.badge_change_enabled = badge_change_enabled
        self.description_change_enabled = description_change_enabled
        self.status_change_enabled = status_change_enabled
        self.deletion_enabled = deletion_enabled

    def input(self):

        try:
            is_desktop_prohibited = interactive.InteractiveValue(
                "auth.is_desktop_prohibited",
                "Запрещено ли пользователям с ПК работать в приложении", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, auth_config_path)
            is_desktop_prohibited = ""

        try:
            is_ios_prohibited = interactive.InteractiveValue(
                "auth.is_ios_prohibited",
                "Запрещено ли пользователям с ios работать в приложении", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, auth_config_path)
            is_ios_prohibited = ""

        try:
            is_android_prohibited = interactive.InteractiveValue(
                "auth.is_android_prohibited",
                "Запрещено ли пользователям с android работать в приложении", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, auth_config_path)
            is_android_prohibited = ""

        try:
            phone_change_enabled = interactive.InteractiveValue(
                "profile.phone_change_enabled",
                "Разрешено ли пользователям изменять номер телефона в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            phone_change_enabled = ""

        try:
            mail_change_enabled = interactive.InteractiveValue(
                "profile.mail_change_enabled",
                "Разрешено ли пользователям изменять почтовый адрес в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            mail_change_enabled = ""

        try:
            name_change_enabled = interactive.InteractiveValue(
                "profile.name_change_enabled",
                "Разрешено ли пользователям изменять Имя Фамилия в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            name_change_enabled = ""

        try:
            avatar_change_enabled = interactive.InteractiveValue(
                "profile.avatar_change_enabled",
                "Разрешено ли пользователям изменять аватар в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            avatar_change_enabled = ""

        try:
            badge_change_enabled = interactive.InteractiveValue(
                "profile.badge_change_enabled",
                "Разрешено ли пользователям изменять бейдж в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            badge_change_enabled = ""

        try:
            description_change_enabled = interactive.InteractiveValue(
                "profile.description_change_enabled",
                "Разрешено ли пользователям изменять описание в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            description_change_enabled = ""

        try:
            status_change_enabled = interactive.InteractiveValue(
                "profile.status_change_enabled",
                "Разрешено ли пользователям изменять статус в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            status_change_enabled = ""

        try:
            deletion_enabled = interactive.InteractiveValue(
                "profile.deletion_enabled",
                "Разрешено ли пользователям удалять свой профиль", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, team_config_path)
            deletion_enabled = ""

        return self.init(is_desktop_prohibited, is_ios_prohibited, is_android_prohibited, phone_change_enabled,
                         mail_change_enabled, name_change_enabled, avatar_change_enabled, badge_change_enabled,
                         description_change_enabled, status_change_enabled, deletion_enabled)

    # заполняем содержимым
    def make_profile_output(self):
        phone_change_enabled_output = '"phone_change_enabled" => %s' % (
            str(self.phone_change_enabled).lower())
        mail_change_enabled_output = '"mail_change_enabled" => %s' % (
            str(self.mail_change_enabled).lower())
        name_change_enabled_output = '"name_change_enabled" => %s' % (
            str(self.name_change_enabled).lower())
        avatar_change_enabled_output = '"avatar_change_enabled" => %s' % (
            str(self.avatar_change_enabled).lower())
        badge_change_enabled_output = '"badge_change_enabled" => %s' % (
            str(self.badge_change_enabled).lower())
        description_change_enabled_output = '"description_change_enabled" => %s' % (
            str(self.description_change_enabled).lower())
        status_change_enabled_output = '"status_change_enabled" => %s' % (
            str(self.status_change_enabled).lower())
        deletion_enabled_output = '"deletion_enabled" => %s' % (
            str(self.deletion_enabled).lower())

        output = "%s,\n %s,\n %s,\n %s,\n %s,\n %s,\n %s,\n %s" % (
            phone_change_enabled_output, mail_change_enabled_output, name_change_enabled_output,
            avatar_change_enabled_output, badge_change_enabled_output, description_change_enabled_output,
            status_change_enabled_output, deletion_enabled_output)
        return output.encode().decode()

    # заполняем содержимым
    def make_platform_output(self):
        is_desktop_prohibited_output = '"is_desktop_prohibited" => %s' % (
            str(self.is_desktop_prohibited).lower())
        is_ios_prohibited_output = '"is_ios_prohibited" => %s' % (
            str(self.is_ios_prohibited).lower())
        is_android_prohibited_output = '"is_android_prohibited" => %s' % (
            str(self.is_android_prohibited).lower())

        output = "%s,\n %s,\n %s" % (
            is_desktop_prohibited_output, is_ios_prohibited_output, is_android_prohibited_output
        )
        return output.encode().decode()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def handle_exception(field, message: str, config_path):
    if validate_only:
        validation_error_config_path = str(config_path.resolve())
        if installer_output:
            validation_errors.append(field)
        else:
            validation_errors.append(message)
        return

    print(message)
    exit(1)


# начинаем выполнение
def start():
    generate_config(pivot_restrictions_conf_path, r"Compass\Pivot")
    generate_config(domino_restrictions_conf_path, r"Compass\Company")
    generate_config(integration_restrictions_conf_path, r"Compass\Integration")
    exit(0)


# записываем содержимое в файл
def write_file(output: str, conf_path: Path):
    if validate_only:
        if installer_output:
            if len(validation_errors) > 0:
                print(json.dumps(validation_errors, ensure_ascii=False))
                exit(1)
            print("[]")
        else:
            if len(validation_errors) > 0:
                print("Ошибка в конфигурации %s" % validation_error_config_path)
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
def generate_config(restrictions_conf_path: Path, module_namespace: str):
    # генерируем данные
    config = RestrictionsMainConfig()
    output = make_output(config, module_namespace)

    # если только валидируем данные, то файлы не пишем
    if validate_only:

        if installer_output:
            if len(validation_errors) > 0:
                print(json.dumps(validation_errors, ensure_ascii=False))
                exit(1)
            print("[]")
        else:
            if len(validation_errors) > 0:
                print("Ошибка в конфигурации %s" % validation_error_config_path)
                for error in validation_errors:
                    print(error)
                exit(1)
        exit(0)

    if len(validation_errors) == 0:
        print(
            scriptutils.success(
                "Файлы с настройками ограничений сгенерированы по следующему пути: "
            )
        )

    write_file(output, restrictions_conf_path)


# получаем содержимое конфига для аутентификации
def make_output(config: RestrictionsMainConfig, module_namespace: str):
    return r'''<?php

namespace {};

/**
 * все ограничения в приложении связанные с профилем
 */
$CONFIG["RESTRICTIONS_PROFILE"] = [
    {}
];

/**
 * все ограничения в приложении связанные с платформой
 */
$CONFIG["RESTRICTIONS_PLATFORM"] = [
    {}
];

return $CONFIG;'''.format(module_namespace, config.make_profile_output(), config.make_platform_output())


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
