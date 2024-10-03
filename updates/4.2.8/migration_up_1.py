#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import re, socket, yaml, argparse, readline, string, random, pwd, os

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

values_file_path = Path('%s/../../src/values.%s.yaml' % (script_dir, values_arg))

if not values_file_path.exists():
    exit(0)

# удаляем старое значение media_advertise_ips
with values_file_path.open('r') as values_file:

    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

if current_values.get("projects", {}).get("jitsi", {}).get("service", {}).get("jvb", {}).get("media_advertise_ips") is not None:
    del current_values["projects"]["jitsi"]["service"]["jvb"]["media_advertise_ips"]

# сохраняем изменения
with values_file_path.open("w+t") as f:
    yaml.dump(current_values, f, sort_keys=False)