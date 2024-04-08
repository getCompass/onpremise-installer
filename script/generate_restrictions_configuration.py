#!/usr/bin/env python3

import argparse
from pathlib import Path
import yaml
from utils import scriptutils
from utils import interactive

# ---АРГУМЕНТЫ СКРИПТА---#

script_dir = Path(__file__).parent.resolve()

# загружаем конфиги
config_path = script_dir.parent / "configs" / "team.yaml"

config = {}

if not config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

with config_path.open("r") as config_file:
    config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(config_values)

root_path = script_dir.parent.resolve()

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "--pivot-restrictions-output-path",
    required=False,
    default=root_path / "src" / "pivot" / "config" / "restrictions.gophp",
    help="Путь до выходного файла restrictions конфига для ограничений",
)
parser.add_argument(
    "--domino-restrictions-output-path",
    required=False,
    default=root_path / "src" / "domino" / "config" / "company_restrictions.gophp",
    help="Путь до выходного файла restrictions конфига для ограничений",
)
parser.add_argument(
    "--integration-restrictions-output-path",
    required=False,
    default=root_path / "src" / "integration" / "config" / "restrictions.gophp",
    help="Путь до выходного файла restrictions конфига для ограничений",
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
pivot_restrictions_conf_path = args.pivot_restrictions_output_path
pivot_restrictions_conf_path = Path(pivot_restrictions_conf_path)
domino_restrictions_conf_path = args.domino_restrictions_output_path
domino_restrictions_conf_path = Path(domino_restrictions_conf_path)
integration_restrictions_conf_path = args.integration_restrictions_output_path
integration_restrictions_conf_path = Path(integration_restrictions_conf_path)
validation_errors = []


class RestrictionsMainConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            phone_change_enabled: int,
            mail_change_enabled: int,
            name_change_enabled: int,
            avatar_change_enabled: int,
            badge_change_enabled: int,
            description_change_enabled: int,
            status_change_enabled: int,
    ):
        self.phone_change_enabled = phone_change_enabled
        self.mail_change_enabled = mail_change_enabled
        self.name_change_enabled = name_change_enabled
        self.avatar_change_enabled = avatar_change_enabled
        self.badge_change_enabled = badge_change_enabled
        self.description_change_enabled = description_change_enabled
        self.status_change_enabled = status_change_enabled

    def input(self):

        try:
            phone_change_enabled = interactive.InteractiveValue(
                "profile.phone_change_enabled",
                "Разрешено ли пользователям изменять номер телефона в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            mail_change_enabled = interactive.InteractiveValue(
                "profile.mail_change_enabled",
                "Разрешено ли пользователям изменять почтовый адрес в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            name_change_enabled = interactive.InteractiveValue(
                "profile.name_change_enabled",
                "Разрешено ли пользователям изменять Имя Фамилия в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            avatar_change_enabled = interactive.InteractiveValue(
                "profile.avatar_change_enabled",
                "Разрешено ли пользователям изменять аватар в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            badge_change_enabled = interactive.InteractiveValue(
                "profile.badge_change_enabled",
                "Разрешено ли пользователям изменять бейдж в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            description_change_enabled = interactive.InteractiveValue(
                "profile.description_change_enabled",
                "Разрешено ли пользователям изменять описание в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        try:
            status_change_enabled = interactive.InteractiveValue(
                "profile.status_change_enabled",
                "Разрешено ли пользователям изменять статус в профиле", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message)

        return self.init(phone_change_enabled, mail_change_enabled, name_change_enabled, avatar_change_enabled,
                         badge_change_enabled, description_change_enabled, status_change_enabled)

    # заполняем содержимым
    def make_output(self):
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

        output = "%s,\n %s,\n %s,\n %s,\n %s,\n %s,\n %s" % (
            phone_change_enabled_output, mail_change_enabled_output, name_change_enabled_output,
            avatar_change_enabled_output, badge_change_enabled_output, description_change_enabled_output,
            status_change_enabled_output)
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
    generate_config(pivot_restrictions_conf_path, "Compass\Pivot")
    generate_config(domino_restrictions_conf_path, "Compass\Company")
    generate_config(integration_restrictions_conf_path, "Compass\Integration")
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
def generate_config(restrictions_conf_path: Path, module_namespace: str):

    # генерируем данные
    config = RestrictionsMainConfig()
    output = make_output(config, module_namespace)

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
                "Файлы с настройками ограничений сгенерированы по следующему пути: "
            )
        )

    write_file(output, restrictions_conf_path)


# получаем содержимое конфига для аутентификации
def make_output(config: RestrictionsMainConfig, module_namespace: str):
    return """<?php

namespace {};

/**
 * все ограничения в приложении связанные с профилем
 */
$CONFIG["RESTRICTIONS_PROFILE"] = [
    {}
];

return $CONFIG;""".format(module_namespace, config.make_output())

# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
