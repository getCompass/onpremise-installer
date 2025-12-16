#!/usr/bin/env python3

import sys
import time

sys.dont_write_bytecode = True

import argparse, yaml, sys, os, glob, re, json
import docker

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path
from time import sleep
from loader import Loader

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="Название values файла окружения")
parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="Окружение, в котором разворачиваем")

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

scriptutils.assert_root()

script_dir = str(Path(__file__).parent.resolve())

# ---СКРИПТ---#

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
stack_name_prefix = environment + "-" + values_arg
stack_name = stack_name_prefix + "-monolith"


# получить данные окружение из values
def get_values() -> dict:
    default_values_file_path = Path("%s/../../src/values.yaml" % (script_dir))
    values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_arg))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = scriptutils.merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values

def update_company_configs_timestamp(current_values):

    company_config_mount_path = current_values.get("company_config_mount_path")
    company_config_mount_file = company_config_mount_path + "/.timestamp.json"
    with open(company_config_mount_file, "r") as file:
        json_str = file.read()
        mount_json_dict = json.loads(json_str) if json_str != "" else {}

    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]
    domino_id = domino["label"]

    mount_json_dict[domino_id] = int(time.time())

    with open(company_config_mount_file, "w") as file:
        file.write(json.dumps(mount_json_dict))

    space_config_dir_file = space_config_dir + "/.timestamp.json"
    with open(space_config_dir_file, "r") as dir_file:
        json_str = dir_file.read()
        dir_json_dict = json.loads(json_str) if json_str != "" else {}

    dir_json_dict[domino_id] = int(time.time())

    with open(space_config_dir_file, "w") as dir_file:
        dir_file.write(json.dumps(dir_json_dict))


current_values = get_values()

service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

client = docker.from_env()

# получаем контейнер monolith
timeout = 30
n = 0
while n <= timeout:

    docker_container_list = client.containers.list(
        filters={
            "name": "%s_php-monolith" % (stack_name),
            "health": "healthy",
        }
    )

    if len(docker_container_list) > 0:
        found_pivot_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            "Не был найден необходимый docker-контейнер для создания команды. Убедитесь, что окружение поднялось корректно"
        )

print(scriptutils.warning("Восстанавливаю команды..."))
keys_list = list(current_values["projects"]["domino"].keys())
domino = current_values["projects"]["domino"][keys_list[0]]
space_config_dir = domino["company_config_dir"]
is_success = True
space_configs_count = len(glob.glob("%s/*_company.json" % space_config_dir))
space_iteration = 1
for space_config in glob.glob("%s/*_company.json" % space_config_dir):

    s = re.search(r'([0-9]+)_company', space_config)
    if s is None:
        continue

    space_id = s.group(1)

    f = open(space_config, "r")
    space_config_dict = json.loads(f.read())
    f.close()
    if space_config_dict["status"] not in [1, 2]:
        question_text = "Компания %s не в статусе active/vacant, продолжить её восстановление? [y/N]\n" % space_id
        if input(question_text).lower() != "y":
            continue

    log_text = "Восстанавливаем команду %s" % space_id
    if space_configs_count > 1:
        log_text = log_text + " (%s из %s)" % (space_iteration, space_configs_count)
    space_iteration += 1
    print(log_text)
    output = found_pivot_container.exec_run(
        user="www-data",
        cmd=[
            "bash",
            "-c",
            'php src/Compass/Pivot/sh/php/domino/repair_company.php --company-id="%s"' % space_id,
        ],
    )
    if output.exit_code != 0:
        output = found_pivot_container.exec_run(
            user="www-data",
            cmd=[
                "bash",
                "-c",
                'php src/Compass/Pivot/sh/php/domino/repair_company.php --company-id="%s"' % space_id,
            ],
        )
        if output.exit_code != 0:
            print(output.output.decode("utf-8", errors="ignore"))
            print(scriptutils.error("Не смог восстановить команду %s" % space_id))
            scriptutils.die(
                "Что то пошло не так. Не смогли восстановить команду %s. Проверьте, что окружение поднялось корректно" % space_id
            )

print(scriptutils.success("Команды восстановлены"))

# обновляем timestamp для конфигов компаний
update_company_configs_timestamp(current_values)