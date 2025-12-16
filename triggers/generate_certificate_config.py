#!/usr/bin/env python3

import os, argparse, yaml, json
import OpenSSL.crypto, OpenSSL.SSL
from datetime import datetime

#---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values-path', required=True, type=str, help='Путь до values файла')
parser.add_argument('-p', '--project', required=True, type=str, help='Имя проекта')
parser.add_argument('-d', '--default-values-path', required=True, type=str, help='Путь до дефолтного values файла')
args = parser.parse_args()
#---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

#---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#
# функциия для обработки проектов
def process_projects(projects_values: dict):
    
    for project, project_val in projects_values.items():

        project_host = project_val.get('host')

        if project_host is None:
            try:
                project_host = project_val['code_host']
            except KeyError:
                process_projects(project_val)
                continue
        try:
            nginx_port = project_val['service']['nginx']['external_https_port']
        except (KeyError, TypeError):
            continue
        
        nginx_certificate_path = root_path + "/src/nginx/ssl/" + project_host + ".crt"
        
        if not os.path.exists(nginx_certificate_path):
            print('у nginx ' + project + ' отсутствует сертификат')
            continue
        
        try:
            cert_file = open(nginx_certificate_path, 'r')
            cert = cert_file.read()
            cert_obj = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
        except OpenSSL.crypto.Error:
            print('Сертификат ' + project + ' невалидный!')
            exit(1)

        not_after_date = cert_obj.get_notAfter().decode('utf-8')
        expire_at = datetime.strptime(not_after_date, '%Y%m%d%H%M%S%z').timestamp()

        final_projects_object[project] = {
            'ip_address': project_host,
            'port': nginx_port,
            'certificate_available_till': int(expire_at)
        }
        

#---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

#---СКРИПТ---#
values_file_path = args.values_path
project = args.project
script_dir = os.path.dirname(os.path.realpath(__file__))
root_path = os.path.abspath(script_dir + "/../")
config_path = root_path + "/src/system/config/init_project_certificates.gojson"

with open(values_file_path, 'r') as values_file:
    values = yaml.safe_load(values_file)

project_values = values['projects']

final_projects_object = {}
process_projects(project_values)

json_string = json.dumps(final_projects_object)
f = open(config_path, "w", 644)
f.write(json_string)
exit(0)
