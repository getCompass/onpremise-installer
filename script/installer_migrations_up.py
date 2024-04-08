#!/usr/bin/env python3

import os, argparse, json
from pathlib import Path
import yaml
from utils import scriptutils
from utils import interactive
import subprocess


# класс для сравнения версии инсталлятора
class Version(tuple):
    def __new__(cls, text):
        return super().__new__(cls, tuple(int(x) for x in text.split('.')))


# пробуем получить файл с версией инсталлятора
script_dir = str(Path(__file__).parent.resolve())
version_path = Path(script_dir + "/../.version")

# если файл с версией отсутствует, то накатываем все обновления директории /updates
if not version_path.exists():
    current_version = 0
else:
    current_version = version_path.open("r").read()

# получаем файлы с командами для обновления проекта
config_files_path = Path(script_dir + "/../updates")

version_list = []
for migration_folder in sorted(config_files_path.glob("*")):

    version = migration_folder.name

    # если текущая версия больше версии миграции, то пропускаем выполнение
    if current_version != 0 and Version(current_version) >= Version(version):
        continue

    # собираем полученные версии в список
    version_list.append(version)

    # проходимся по каждой директории версии
    if migration_folder.is_dir():

        # получаем данные из yaml файлов
        migration_files_path = Path(migration_folder.resolve())
        for item in migration_files_path.glob("*.yaml"):

            # получаем команды из файла
            config_values = yaml.load(item.open("r"), Loader=yaml.BaseLoader)
            migration_commands = config_values.get("migration_commands")

            # выполняем команды из yaml-конфига, если такие указаны
            if migration_commands is not None:

                for command in migration_commands:
                    # экранируем кавычки в командах для выполнения
                    command = command.replace('"', '\"')
                    exec(command)

            migration_scripts = config_values.get("migration_scripts")

            # выполняем скрипт для миграции, если такой указан
            if migration_scripts is not None:
                for script in migration_scripts:
                    print(f"Выполняю скрипт миграции {script} версии {version}")
                    script_path = str(migration_files_path.resolve() / script)

                    # Запуск скрипта в отдельном процессе
                    result = subprocess.run(['python3', script_path], text=True, capture_output=True)

                    # Вывод результата выполнения скрипта
                    print(result.stdout)
                    if result.stderr:
                        print(result.stderr)

# если список версий пуст, значит миграций не было
if len(version_list) == 0:
    exit(0)

# получаем последнюю версию
last_version = version_list[len(version_list) - 1]

# записываем последнюю установленную версию в файл
f = open(version_path, "w")
f.write(last_version)
f.close()
