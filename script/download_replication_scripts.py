#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Скопировать скрипты внутрь php-monolith контейнера

import sys

sys.dont_write_bytecode = True

import yaml, psutil
import docker
import subprocess
from utils import scriptutils

parser = scriptutils.create_parser(
    description="Скрипт для копирования скриптов репликации внутрь php-monolith контейнера с сервера.",
    usage="python3 script/download_replication_scripts.py [-v VALUES] [-e ENVIRONMENT] [--from-path FROM_PATH]",
    epilog="Пример: python3 script/download_replication_scripts.py -v compass -e production --from-path /home/replication_scripts",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument('--from-path', required=False, default="/home/replication_scripts", type=str,
                    help='Путь на сервере, откуда копируем скрипты')
args = parser.parse_args()

values_arg = args.values if args.values else ""
environment = args.environment if args.environment else ""
scripts_from_path = args.from_path if args.from_path else ""

# искомый контейнер
partial_name = "%s-%s-monolith_php-monolith" % (environment, values_arg)

result = subprocess.run(['docker', 'ps', '--filter', f'name={partial_name}', '--format', '{{.Names}}'],
                        stdout=subprocess.PIPE)
container_name = result.stdout.decode('utf-8').strip()

try:
    subprocess.run(
        ["docker", "cp", scripts_from_path, f"{container_name}:/app/dev/php"],
        check=True
    )
    print(f"Файлы успешно скопированы в контейнер {container_name}")
except subprocess.CalledProcessError as e:
    print(f"Ошибка: {e}")
