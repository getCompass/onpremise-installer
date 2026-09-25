#!/usr/bin/env python3

import sys
sys.dont_write_bytecode = True

from pathlib import Path
import argparse, yaml

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

parser = argparse.ArgumentParser()
parser.add_argument("-v", "--values", required=False, type=str)
parser.add_argument("-e", "--environment", required=False, type=str)
args = parser.parse_args()

INSTRUCTION_URL = "https://doc-onpremise.getcompass.ru/high-availability-update.html"
YELLOW = "\033[93m"
RED = "\033[91m"
END = "\033[0m"

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

values_file_path = Path('%s/../../src/values.%s.yaml' % (script_dir, values_arg))
if not values_file_path.exists():
    exit(0)

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values


if not scriptutils.is_replication_enabled(current_values):
    exit(0)

if not scriptutils.is_replication_master_server(current_values):
    exit(0)

print(
    YELLOW
    + "\n".join(
        [
            "!!!Перед обновлением до версии 6.9.0 необходимо пройти инструкцию по переходу на новую отказоустойчивость!!!",
            "Ссылка на инструкцию:",
            INSTRUCTION_URL,
            "",
        ]
    )
    + END
)

confirmation = ""
try:
    confirmation = input(
        "Инструкция по переходу на новую отказоустойчивость пройдена? "
        "Продолжить обновление? [y/N]\n"
    ).strip().lower()
except (EOFError, UnicodeDecodeError):
    confirmation = ""

if confirmation != "y":
    print(RED + "Обновление приложения отменено" + END)
    sys.exit(1)
