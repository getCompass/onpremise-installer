#!/usr/bin/env python3

import  sys
sys.dont_write_bytecode = True

import os, argparse, yaml
from utils import scriptutils
from loader import Loader
from subprocess import Popen, PIPE
from pathlib import Path

#---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values-path', required=True, type=str, help='Путь до values файла')
parser.add_argument('-t', '--trigger-type', required=True, type=str, help='Тип вызываемого триггера')
parser.add_argument('-p', '--project', required=True, type=str, help='Имя проекта')
args = parser.parse_args()
#---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

#---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

# функциия для проверки триггера
def process_trigger(trigger):

    error_msg = trigger + ' - FAIL'
    success_msg = trigger + ' - SUCCESS'

    # это для красивого анимированного лоадера
    loader = Loader(trigger, success_msg, error_msg)
    loader.start()

    # запускаем процесс со скриптом, перенаправляя его вывод
    p = Popen([root_path + "/" + trigger, '-v', values_file_path, '-d', default_values_file_path, '-p', project], stdout=PIPE, stderr=PIPE, stdin=PIPE)
    p.wait()
    err = p.stderr.read()
    out = p.stdout.read()
    
    # match с версии 3.11, поэтому не используем
    # если скрипт сказал окей - то просто говорим, что все окей
    # если нет - добавляем вывод
    if (p.returncode == 0):
        loader.success()
    else:
        loader.error_msg = error_msg + "\n" + err.decode() + "\n" + out.decode()
        loader.error()

#---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

#---СКРИПТ---#

script_dir = os.path.dirname(os.path.realpath(__file__))
root_path = str(Path(script_dir + "/../").resolve())
values_file_path = str(Path(args.values_path).resolve())
default_values_file_path = str(Path(script_dir + "/../src/values.yaml").resolve())

os.chdir(root_path)
project = args.project
trigger_type = args.trigger_type

with open(values_file_path, 'r') as values_file:
    values = yaml.safe_load(values_file)

try:
    project_values = values['projects'][project]
except KeyError:
    scriptutils.die('Проект с именем ' + project + ' не найден')

with open(default_values_file_path, 'r') as values_file:
    default_values = yaml.safe_load(values_file)

try:
    default_project_values = default_values['projects'][project]
except KeyError:
    default_project_values = {}

global_triggers = default_values.get('triggers', {})
global_triggers.update(values.get('triggers', {}))

project_triggers = default_project_values.get('triggers', {})
project_triggers.update(project_values.get('triggers', {}))

# выполняем глобальные триггеры
if (global_triggers != {}):

   if ((typed_global_triggers := global_triggers.get(trigger_type)) is not None):
       
        for typed_trigger in typed_global_triggers:
            process_trigger(typed_trigger)

# выполняем локальные для проекта триггеры
if (project_triggers != {}):
   
   if ((typed_project_triggers := project_triggers.get(trigger_type)) is not None):
        
        for typed_trigger in typed_project_triggers:
            process_trigger(typed_trigger)

exit(0)
