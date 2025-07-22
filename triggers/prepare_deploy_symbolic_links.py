#!/usr/bin/env python3

# Скрипт для предварительной подготовки символьных ссылок.
# Нужен для реализации деплоя монолита без копипасты конфигов и переменных

import argparse
import os
from pathlib import Path

import yaml, shutil

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values-path', required=True, type=str, help='Путь до values файла')
parser.add_argument('-d', '--default-values-path', required=True, type=str, help='Путь до дефолтного values файла')
parser.add_argument('-p', '--project', required=True, type=str, help='Имя проекта')
args = parser.parse_args()

# ---ГЛОБАЛЬНЫЕ ШТУКИ
values_file_path = args.values_path
default_values_file_path = args.default_values_path
project = args.project
script_dir = os.path.dirname(os.path.realpath(__file__))
root_path = os.path.abspath(script_dir + "/../")
config_path = root_path + "/src/system/config/init_project_certificates.gojson"

# создает символьные ссылки для конфигурационных файлов деплой-юнитов
def make_temporary_symbolic_link_for_deploy_units(project:str, deploy_units:list):

    print("creating symbolic links for project " + project)

    # пути до директорий /config и /variable в деплой-проекте
    project_conf_dir = root_path + "/src/" + project + "/config/"
    project_var_dir = root_path + "/src/" + project + "/variable/"

    for deploy_unit in deploy_units:

        # пути, куда будем цеплять символьные ссылки
        symlink_conf_path = Path(project_conf_dir + deploy_unit)
        symlink_var_path = Path(project_var_dir + deploy_unit)

        # очищаем конфиги, если есть
        if symlink_conf_path.exists() or symlink_conf_path.is_symlink():
            try:
                symlink_conf_path.unlink()
            except IsADirectoryError:
                shutil.rmtree(symlink_conf_path)

        # очищаем переменные, если есть
        if symlink_var_path.exists() or symlink_var_path.is_symlink():
            try:
                symlink_var_path.unlink()
            except IsADirectoryError:
                shutil.rmtree(symlink_var_path)

        # пересоздаем символьные ссылки на директории деплой-юнита
        symlink_conf_path.symlink_to(Path(root_path + "/src/" + deploy_unit + "/config"))
        symlink_var_path.symlink_to(Path(root_path + "/src/" + deploy_unit + "/variable"))

        print("symbolic link for deploy unit " + deploy_unit + " created")


# ---СКРИПТ---#
# загружаем yaml файл со значениями
with open(values_file_path, 'r') as values_file:
    values = yaml.safe_load(values_file)

# загружаем yaml файл со значениями
with open(default_values_file_path, 'r') as values_file:
    default_values = yaml.safe_load(values_file)

values['projects'][project].update(default_values['projects'][project])

# ищем нужный ключ для указанного деплой-проекта
# если не нашли, то заканчиваем работу
if 'deploy_units' not in values['projects'][project]:
    exit(0)

project_values = values['projects']
deploy_units = project_values[project]['deploy_units']

make_temporary_symbolic_link_for_deploy_units(project, deploy_units)
exit(0)
