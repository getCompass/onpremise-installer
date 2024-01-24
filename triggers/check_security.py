#!/usr/bin/env python3

import os, argparse, yaml
import OpenSSL.crypto, OpenSSL.SSL
from datetime import datetime

#---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values-path', required=True, type=str, help='Путь до values файла')
parser.add_argument('-p', '--project', required=True, type=str, help='Имя проекта')
parser.add_argument('-d', '--default-values-path', required=True, type=str, help='Путь до дефолтного values файла')
args = parser.parse_args()
#---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

#---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#
# функция для валидации сертификата
def validate_certificate(host:str, cert_path:str, key_path:str):

    # загружаем приватный ключ
    try:
        key_file = open(key_path, 'r')
        key = key_file.read()
        key_obj = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM, key)
    except OpenSSL.crypto.Error:
        print('Приватный ключ невалидный!')
        exit(1)

    # загружаем сертификат
    try:
        cert_file = open(cert_path, 'r')
        cert = cert_file.read()
        cert_obj = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
    except OpenSSL.crypto.Error:
        print('Сертификат невалидный!')
        exit(1)

    if cert_obj.get_subject().CN != host:
        print("Сертификат не относится к хосту проекта")
        exit(1)

    # проверяем, соотносятся ли между собой сертификат и ключ
    cert_pub = OpenSSL.crypto.dump_publickey(OpenSSL.crypto.FILETYPE_PEM, cert_obj.get_pubkey())
    key_pub = OpenSSL.crypto.dump_publickey(OpenSSL.crypto.FILETYPE_PEM, key_obj)

    if cert_pub != key_pub:
        print('Ключ и сертификат не соотносятся между собой')
        exit(1)

    # проверяем, что сертификат не истекает через 7 дней
    not_after_date = cert_obj.get_notAfter().decode('utf-8')
    expire_at = datetime.strptime(not_after_date, '%Y%m%d%H%M%S%z').timestamp()

    if (expire_at - datetime.now().timestamp()) < 604800:
        print("Сертификат истечет меньше, чем через 7 дней")
        exit(1)

# функциия для проверки проекта
def process_project(project_values):

    if type(project_values) is not dict:
        return

    service = project_values.get('service')

    if service is None:
        for project, project_node in project_values.items():

            process_project(project_node)
            return

    try:
        nginx_external_https_port = service['nginx']['external_https_port']
    except KeyError:
        print('У проекта или подпроекта отсутствует nginx')
        exit(0)
    
    if  1 > nginx_external_https_port > 65535:
        print('Неверное значение для порта nginx' + nginx_external_https_port)
        exit(1)
    
    project_host = project_values.get('host')

    if project_host is None:

        try:
            project_host = project_values['code_host']
        except KeyError:
            print('У проекта отсутствует хост')
            exit(1)
    
    nginx_certificate_path = root_mount_path + '/nginx/ssl/' + project_host + '.crt'
    nginx_key_path = root_mount_path + '/nginx/ssl/' + project_host + '.key'
    if not (os.path.isfile(nginx_certificate_path) and os.path.isfile(nginx_key_path)):
        print('У проекта отстуствует сертификат или ключ nginx')
        exit(1)
    
    validate_certificate(project_host, nginx_certificate_path, nginx_key_path)
#---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

#---СКРИПТ---#
values_file_path = args.values_path
project = args.project

with open(values_file_path, 'r') as values_file:
    values = yaml.safe_load(values_file)

root_mount_path = values['root_mount_path']

try:
    project_values = values['projects'][project]
except KeyError:
    print('Проект с именем ' + project + ' не найден')
    exit(1)
process_project(project_values)
exit(0)
