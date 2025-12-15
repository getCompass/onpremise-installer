#!/usr/bin/env python3

import sys
sys.dont_write_bytecode = True

import os, argparse
from dotenv import dotenv_values
from pathlib import Path

#---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-i', '--input-file', required=True, type=str, help='Путь до входного файла')
parser.add_argument('-o', '--output-file', required=True, type=str, help='Путь до выходного файла')
args = parser.parse_args()
#---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

#---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#
#---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

#---СКРИПТ---#

# получаем папку, где находится скрипт
script_dir = os.path.dirname(os.path.realpath(__file__))
root_path = os.path.abspath(script_dir + "/../")
os.chdir(root_path)

input_file_path = os.path.abspath(args.input_file)
output_file_path = os.path.abspath(args.output_file)

env_vars = {}

# парсим env
config = dotenv_values(input_file_path)

# открываем файл для записи
output_file_path = Path(output_file_path)
output_file_path.parent.mkdir(exist_ok=True)
f = output_file_path.open('w')
f.flush()

# записываем в новый файл
for name, value in config.items():

        # перед записью все переносы строк меняем на \n
        output = (str(name) + "=" + str(value)).encode('unicode_escape').decode('utf-8')
        
        f.write( output + "\n")

f.close()



