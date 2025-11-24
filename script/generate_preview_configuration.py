#!/usr/bin/env python3

import argparse
from pathlib import Path
import yaml, json
from utils import scriptutils
from utils import interactive

# ---АРГУМЕНТЫ СКРИПТА---#

script_dir = Path(__file__).parent.resolve()

# загружаем конфиги
global_config_path = script_dir.parent / "configs" / "global.yaml"

config = {}

if not global_config_path.exists():
    print(scriptutils.error(
        f"Отсутствует файл конфигурации {global_config_path.resolve()}. Запустите скрипт create_configs.py и заполните конфигурацию"))
    exit(1)

with global_config_path.open("r") as config_file:
    global_config_values = yaml.load(config_file, Loader=yaml.BaseLoader)

config.update(global_config_values)

root_path = script_dir.parent.resolve()

parser = argparse.ArgumentParser(add_help=True)
parser.add_argument(
    "--domino-preview-output-path",
    required=False,
    default=root_path / "src" / "domino" / "config" / "preview_parsing.gophp",
    help="Путь до выходного файла preview конфига для превью ссылок",
)
parser.add_argument(
    "--validate-only",
    required=False,
    action='store_true'
)
parser.add_argument(
    "--installer-output",
    required=False,
    action="store_true"
)
args = parser.parse_args()

# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

validate_only = args.validate_only
installer_output = args.installer_output

# пути для конфигов
domino_preview_conf_path = args.domino_preview_output_path
domino_preview_conf_path = Path(domino_preview_conf_path)
validation_errors = []
validation_error_config_path = ""


class PreviewMainConfig:
    def __init__(self) -> None:
        self.input()

    def init(
            self,
            url_parsing_flag: bool,
            white_list: list,
            black_list: list,
    ):
        self.url_parsing_flag = url_parsing_flag
        self.white_list = white_list
        self.black_list = black_list
        self.redirect_black_list = []

    def input(self):
        try:
            url_parsing_flag = interactive.InteractiveValue(
                "url_parsing_flag",
                "Нужно ли парсить ссылки", "bool", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, global_config_path)
            url_parsing_flag = True

        try:
            white_list = interactive.InteractiveValue(
                "white_list",
                "Список доменов, что парсятся при любых условиях", "list", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, global_config_path)
            white_list = []

        try:
            black_list = interactive.InteractiveValue(
                "black_list",
                "Список доменов, что не парсятся при любых условиях", "list", config=config
            ).from_config()
        except interactive.IncorrectValueException as e:
            handle_exception(e.field, e.message, global_config_path)
            black_list = []

        return self.init(url_parsing_flag, white_list, black_list)

    # заполняем содержимым
    def make_preview_output(self):
        # Форматирование для url_parsing_flag
        url_parsing_flag_output = '"url_parsing_flag" => %s' % (
            str(self.url_parsing_flag).lower())

        # Форматирование для white_list
        white_list_formatted = []
        for domain in self.white_list:
            white_list_formatted.append(f'"{domain}"')
        white_list_output = '"white_list"       => [%s]' % (
            ", ".join(white_list_formatted))

        # Форматирование для black_list
        black_list_formatted = []
        for domain in self.black_list:
            black_list_formatted.append(f'"{domain}"')
        black_list_output = '"black_list"       => [%s]' % (
            ", ".join(black_list_formatted))

        # Форматирование для redirect_black_list
        redirect_black_list_output = '"redirect_black_list" => []'

        output = "%s,\n\n\t%s,\n\n\t%s,\n\n\t%s" % (
            url_parsing_flag_output, white_list_output, black_list_output, redirect_black_list_output)
        return output.encode().decode()


# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def handle_exception(field, message: str, config_path):
    if validate_only:
        if installer_output:
            validation_errors.append(field)
        else:
            validation_errors.append(message)
        validation_error_config_path = str(config_path.resolve())
        return

    print(message)
    exit(1)


# начинаем выполнение
def start():
    generate_config(domino_preview_conf_path)
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
def generate_config(preview_conf_path: Path):
    # генерируем данные
    config = PreviewMainConfig()
    output = make_output(config)

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
                "Файлы с настройками превью ссылок сгенерированы по следующему пути: "
            )
        )

    write_file(output, preview_conf_path)


# получаем содержимое конфига для превью
def make_output(config: PreviewMainConfig):
    return r'''<?php

/**
 * Конфиг превью
 */
$CONFIG["PREVIEW"] = [

	/**
	 * Включена ли опция парсинга ссылок
	 */
	{},

];

return $CONFIG;'''.format(config.make_preview_output())


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#
start()
