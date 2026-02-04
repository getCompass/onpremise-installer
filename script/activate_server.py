#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

import sys

sys.dont_write_bytecode = True

import argparse, yaml, psutil, shlex, json
import docker
from pathlib import Path
from utils import scriptutils
from loader import Loader
from time import sleep

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором разворачиваем')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#
# === ПРОГРЕСС УСТАНОВКИ ===

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

STEPS_FILE = Path(script_dir).parent / ".install_completed_steps.json"

def ensure_steps_file():
    if not STEPS_FILE.exists():
        try:
            STEPS_FILE.write_text("[]", encoding="utf-8")
        except Exception:
            # трекинг не ломает установку
            pass
def append_step(step: str):
    try:
        ensure_steps_file()
        raw = STEPS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw.strip() or "[]")
        if not isinstance(data, list):
            data = []
        if step not in data:
            data.append(step)
            STEPS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # трекинг не ломает установку
        pass

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg
stack_name = stack_name_prefix + "-monolith"



values_file_path = Path('%s/../src/values.%s.yaml' % (script_dir, values_arg))

if not values_file_path.exists():
    scriptutils.die(('Не найден файл со сгенерированными значениями. Вы развернули приложение?'))

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

    if current_values == {}:
        scriptutils.die('Не найден файл со сгенерированными значениями. Вы развернули приложение?')

    if current_values.get('projects', {}).get('domino', {}) == {}:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

    domino_project = current_values['projects']['domino']

    if len(domino_project) < 1:
        scriptutils.die(scriptutils.error('Не был развернут проект domino через скрипт deploy.py'))

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = current_values.get("service_label") if current_values.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label


# ---СКРИПТ---#

def start():
    client = docker.from_env()

    timeout = 10
    n = 0
    name = "%s_php-monolith" % (stack_name)

    while n <= timeout:

        docker_container_list = client.containers.list(filters={'name': name, 'health': 'healthy'})

        if len(docker_container_list) > 0:
            found_container = docker_container_list[0]
            break

        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die(
                'Не был найден необходимый docker контейнер для активации сервера. Проверьте что окружение поднялось корректно')

    yc_identity_document, yc_identity_document_base64_signature = scriptutils.get_yc_params()

    # экранируем для шелла
    yc_identity_document_arg = shlex.quote(yc_identity_document)
    yc_identity_document_base64_signature_arg = shlex.quote(yc_identity_document_base64_signature)

    loader = Loader('Активирую сервер...', 'Сервер активирован', 'Не смог активировать сервер').start()
    cli = "php src/Compass/Premise/sh/php/server/activate.php"
    if len(yc_identity_document_arg) > 0 and len(yc_identity_document_base64_signature_arg) > 0:
        cli = cli + (" --yc-identity-document=%s" % yc_identity_document_arg)
        cli = cli + (" --yc-identity-document-base64-signature=%s" % yc_identity_document_base64_signature_arg)
    output = found_container.exec_run(
        user='www-data',
        cmd=[
            "bash",
            "-c",
            cli.strip()
        ]
    )

    if output.exit_code == 0:
        loader.success()
    else:
        loader.error()
        print(output.output.decode("utf-8"))

        scriptutils.die('Что то пошло не так. Не смогли активировать сервер')

    append_step("activate_server")

start()
