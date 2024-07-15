#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import subprocess

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils
import docker

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

client = docker.from_env()

docker_monolith_janus_nginx_service_list = client.services.list(filters={'name': 'production-compass-monolith_nginx-janus'})
if len(docker_monolith_janus_nginx_service_list) > 0:

    delete_command = ["docker", "service", "rm", "production-compass-monolith_nginx-janus"]

    try:

        delete_process = subprocess.Popen(
            delete_command, stdout=subprocess.PIPE
        )
        output, _ = delete_process.communicate()
    except Exception as e:
        print(f"{str(e)}")

docker_monolith_janus_service_list = client.services.list(filters={'name': 'production-compass-monolith_janus-janus'})
if len(docker_monolith_janus_service_list) > 0:

    delete_command = ["docker", "service", "rm", "production-compass-monolith_janus-janus"]

    try:

        delete_process = subprocess.Popen(
            delete_command, stdout=subprocess.PIPE
        )
        output, _ = delete_process.communicate()
    except Exception as e:
        print(f"{str(e)}")

docker_monolith_php_janus_service_list = client.services.list(filters={'name': 'production-compass-monolith_php-janus-janus'})
if len(docker_monolith_php_janus_service_list) > 0:

    delete_command = ["docker", "service", "rm", "production-compass-monolith_php-janus-janus"]

    try:

        delete_process = subprocess.Popen(
            delete_command, stdout=subprocess.PIPE
        )
        output, _ = delete_process.communicate()
    except Exception as e:
        print(f"{str(e)}")
