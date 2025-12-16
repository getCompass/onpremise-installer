#!/usr/bin/env python3

import argparse
from pathlib import Path

import yaml

from utils import scriptutils

# region АРГУМЕНТЫ СКРИПТА #
parser = scriptutils.create_parser(
    "Скрипт для валидации конфига team.yaml.",
    usage="python3 script/validate_team_configuration.py [--validate-only]",
    epilog="Пример: python3 script/validate_team_configuration.py --validate-only",
)

parser.add_argument("--validate-only", required=False, action="store_true",
                    help='Запуск скрипта в режиме read-only, без применения изменений')
args = parser.parse_args()

script_dir = str(Path(__file__).parent.resolve())
root_path = str(Path(script_dir + "/../").resolve())

validate_only = args.validate_only

# проверяем конфигурационный файл с глобальными параметрами
config_path = Path(script_dir + "/../configs/global.yaml")

if not config_path.exists():
    scriptutils.die(
        f"Отсутствует файл конфигурации {str(config_path.resolve())}. " +
        f"Запустите скрипт create_configs.py и заполните конфигурацию"
    )

# загружаем конфигурационный файл с глобальными параметрами
with config_path.open("r") as config_file:
    config: dict = yaml.load(config_file, Loader=yaml.BaseLoader)

# проверяем конфигурационный файл с параметрами команды
team_config_path = Path(script_dir + "/../configs/team.yaml")

if not team_config_path.exists():
    scriptutils.die(
        f"Отсутствует файл конфигурации {str(team_config_path.resolve())}. " +
        f"Запустите скрипт create_configs.py и заполните конфигурацию"
    )

try:
    # загружаем конфигурационный файл с параметрами команды
    with team_config_path.open("r") as team_config_file:
        team_config: dict = yaml.load(team_config_file, Loader=yaml.BaseLoader)
except:
    scriptutils.die("Не смогли прочитать конфигурацию %s. Поправьте её и запустите установку снова." % str(
        team_config_path.resolve()))


def start():
    file_access_mode = team_config.get("file.access_restriction_mode", None)
    if file_access_mode is None:
        scriptutils.die("не заполнен параметр file.access_restriction_mode")

    if file_access_mode != "none" and file_access_mode != "auth":
        scriptutils.die("параметр file.access_restriction_mode должен иметь значение none или auth")

    return


start()
print(scriptutils.success("Проверка конфигурации команды прошла успешно"))
