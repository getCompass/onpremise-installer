#!/usr/bin/env python3

import subprocess
import argparse
from pathlib import Path
from time import sleep

import docker
import pwd
import yaml

from loader import Loader
from utils import scriptutils

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---СКРИПТ---#

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

# необходимые пользователи для окржуения
required_user_list = ['www-data']

# проверяем наличие необходимых пользователей
for user in required_user_list:

    try:
        pwd.getpwnam(user)
    except KeyError:
        scriptutils.die('Необходимо создать пользователя окружения' + user)

values_file_path = Path('%s/../src/values.yaml' % (script_dir))
if not values_file_path.exists():
    exit(0)

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

loader = Loader('Накатываю миграции On-premise окружения...', 'Скрипт миграций On-premise окружения успешно выполнен',
                'Не смог накатить миграции On-premise окружения').start()

client = docker.from_env()
db_controller_tag = current_values["projects"]["domino"]["d1"]["service"]["go_database_controller"]["tag"]
db_controller_service_name = "%s-monolith_go-database-controller-d1" % stack_name_prefix
db_controller_image = "docker.getcompass.ru/backend_compass/go_database_controller:%s" % db_controller_tag
docker_db_controller_service_list = client.services.list(
    filters={'name': db_controller_service_name}
)

update_skipped = False
if docker_db_controller_service_list:
    svc = docker_db_controller_service_list[0]
    # в Spec.Image может быть и digest — режем его
    current_image = svc.attrs['Spec']['TaskTemplate']['ContainerSpec']['Image']
    running_image = current_image.split('@', 1)[0]

    if running_image == db_controller_image:
        update_skipped = True
        healthy_now = client.containers.list(
            filters={
                'label': [f'com.docker.swarm.service.name={db_controller_service_name}'],
                'health': ['healthy']
            }
        )
        if healthy_now:
            found_container = healthy_now[0]
    else:
        cmd = [
            "docker", "service", "update",
            db_controller_service_name,
            "--force", "-d",
            "--image", db_controller_image
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            out, _ = proc.communicate()
        except Exception as e:
            print(f"Ошибка при обновлении сервиса: {e}")

# если мы не пропустили апдейт, ждём «нового» контейнера
if not update_skipped:

    # сохраняем список ID текущих (старых) healthy-контейнеров
    initial_healthy = client.containers.list(
        filters={
            'label': [f'com.docker.swarm.service.name={db_controller_service_name}'],
            'health': ['healthy']
        }
    )
    initial_ids = {c.id for c in initial_healthy}

    timeout = 300
    interval = 5
    elapsed = 0

    while elapsed <= timeout:
        all_containers = client.containers.list(
            filters={'label': [f'com.docker.swarm.service.name={db_controller_service_name}']}
        )
        # фильтруем только healthy
        healthy = [
            c for c in all_containers
            if c.attrs.get('State', {}).get('Health', {}).get('Status') == 'healthy'
        ]

        # оставляем только те, чей image tag совпадает с тем, что нам нужен
        new_healthy = [c for c in healthy if c.id not in initial_ids]
        if new_healthy and len(all_containers) == 1 and len(healthy) == 1:
            break

        sleep(interval)
        elapsed += interval

    else:
        scriptutils.die(
            'Не был найден необходимый docker контейнер для выполнения миграций. Проверьте что окружение поднялось корректно')

timeout = 60
n = 0
name = "%s-monolith_php-migration" % stack_name_prefix
while n <= timeout:

    docker_container_list = client.containers.list(filters={'name': name, 'health': 'healthy'})
    if len(docker_container_list) > 0:
        found_container = docker_container_list[0]
        break

    n = n + 5
    sleep(5)
    if n == timeout:
        scriptutils.die(
            'Не был найден необходимый docker контейнер миграций компании. Проверьте что окружение поднялось корректно')

output = found_container.exec_run(user='www-data',
                                  cmd=['bash', '-c', 'php /app/src/Compass/Migration/sh/php/migrate_up.php --y'])

if output.exit_code == 0:
    loader.success()
else:
    loader.error()
    print(output.output.decode("utf-8"))
    scriptutils.error('Что то пошло не так. Не смогли накатить миграции')
