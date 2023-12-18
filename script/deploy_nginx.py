#!/usr/bin/env python3

import sys
sys.dont_write_bytecode = True

import os, argparse, json, yaml
from pathlib import Path
from utils import scriptutils
from subprocess import Popen, PIPE
import shutil
from typing import Union
from loader import Loader

#---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-e', '--environment', required=True, type=str, help='окружение, на котором разворачиваем')
parser.add_argument('-v', '--values', required=True, type=str, help='файл со значениями для подстановки')
parser.add_argument('-n', '--name', required=False, type=str, help='оверрайд для префикса имени развертывания')
parser.add_argument('--data', required=False, type=json.loads, help='дополнительные данные для развертывания')
args = parser.parse_args()
#---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

#---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#

def var_path_list_to_string(var_path_list:list) -> str:

    output = ''
    for var_path in var_path_list:

        output+= var_path + ' '

    if len(output) > 0:
        output = output[:-1]

    return output

# генерируем nginx конфигурацию для проекта
def generate_nginx_conf(project:str,project_values:dict, default_project_values:dict, parent_project: str = '', layer:int = 0) -> Union[Popen, None]:

    layer = layer + 1

    # пока что у нас два слоя подпроектов, незачем искать дальше
    if layer > 2:
        return None

    if not isinstance(project_values, dict):
        return None

    if parent_project == '':
        parent_project = project

    if project == 'pivot':
        project_values['subdomain'] = 'pivot'

    if (project_values.get('subdomain') is None) and (default_project_values.get('subdomain') is None):

        for project, nested_project_values in project_values.items():
            return generate_nginx_conf(project, nested_project_values, default_project_values.get(project, {}), parent_project, layer)

    add_args = []

    if parent_project in ['file_default_nodes', 'file']:
        add_args.append('file_node_id=' + project)
    elif parent_project == 'domino':
        add_args.append('domino_id=' + project)
    subdomain = project_values.get('subdomain')

    if subdomain is None:
        subdomain = default_project_values.get('subdomain')

    if not Path(root_path + '/nginx_template/' + parent_project + '.tmpl').exists():
        return None
    return Popen([template_bin, root_path + '/nginx_template/' + parent_project + '.tmpl', var_path_list_to_string(var_path_list), nginx_home_path + '/' + subdomain + '.' + domain + '.nginx'] + add_args)

#---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

#---СКРИПТ---#

environment = args.environment
values_name = args.values
name = args.name
data = args.data if args.data else {}

# получаем папку, где находится скрипт
script_dir = str(Path(__file__).parent.resolve())
root_path = str(Path(script_dir + '/../').resolve())
os.chdir(root_path)
template_bin = str(Path(script_dir + '/template.py').resolve())

var_path_list = []
product_type = data.get('product_type', '') if data else ''
default_values_path=Path('src/values.yaml')
environment_values_path = Path('src/values.' + environment + '.' + values_name + '.yaml')
product_values_path = Path('src/values.' + values_name + '.' + product_type + '.yaml')
values_path = Path('src/values.' + values_name + '.yaml')

var_path_list.append(str(default_values_path.resolve()))

if environment_values_path.exists():
    var_path_list.append(str(environment_values_path.resolve()))
elif product_values_path.exists():
    var_path_list.append(str(product_values_path.resolve()))
else:
    var_path_list.append(str(values_path.resolve()))

compose_file_name='.compose.yaml'
compose_override_file_name='.compose.override.yaml'

default_values_file_path = str(default_values_path.resolve())

if environment_values_path.exists():
    values_file_path = str(environment_values_path.resolve())
elif product_values_path.exists():
    values_file_path = str(product_values_path.resolve())
else:
    values_file_path = str(values_path.resolve())

nginx_home_path = Path('/home/compass/nginx/conf')

if Path('/src/nginx/conf/').exists():
    shutil.rmtree(root_path + '/src/nginx/conf/')

if not nginx_home_path.exists():
    nginx_home_path.mkdir(parents=True)

nginx_home_path = str(nginx_home_path.resolve())
with open(values_file_path, 'r') as values_file:
    values = yaml.safe_load(values_file)

with open(default_values_file_path, 'r') as values_file:
    default_values = yaml.safe_load(values_file)

domain = values['domain']

pipe_list = []

for project, project_values in dict(values['projects']).items():

    # у join_web нет отдельного nginx файла, он входит в pivot
    if project == "join_web":
        continue

    p = generate_nginx_conf(project, project_values, default_values['projects'][project])
    if p is Popen:
        pipe_list.append(p)

# удолить
Path(root_path + '/src/nginx/include/upstream_'+ values['stack_name_prefix'] +'.conf').unlink(missing_ok=True)
Path('/etc/nginx/include/upstream_'+ values['stack_name_prefix'] +'.conf').unlink(missing_ok=True)
pipe_list.append(Popen([template_bin, root_path + '/nginx_template/status.tmpl', var_path_list_to_string(var_path_list), nginx_home_path + '/status.nginx']))

for p in pipe_list:
    p.wait()

# копируем все
shutil.copytree(root_path + '/src/nginx/', '/etc/nginx/', dirs_exist_ok=True)

p = Popen(['rm', '-r', '/etc/nginx/sites-enabled'])
p.wait()
p = Popen(['ln', '-s', nginx_home_path, '/etc/nginx/sites-enabled'])
p.wait()

loader = Loader('Обновляем конфигурацию nginx', 'Конфигурация nginx обновлена', 'В конфигурации nginx есть ошибка')
loader.start()

# p = Popen(['systemctl', 'restart', 'nginx'], stderr=PIPE, stdout=PIPE)
# p.wait()

p = Popen(['nginx', '-s', 'reload'], stderr=PIPE, stdout=PIPE)
p.wait()

if p.returncode != 0:

    loader.error()
    print(scriptutils.error(p.stderr.read().decode()))
    print(scriptutils.error(p.stdout.read().decode()))
    exit(p.returncode)
else:
    loader.success()