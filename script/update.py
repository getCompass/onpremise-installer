#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import subprocess, argparse

from utils import scriptutils
from pathlib import Path
import docker
from time import sleep
from loader import Loader

scriptutils.assert_root()

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("--use-default-values", required=False, action="store_true")
parser.add_argument("--install-integration", required=False, action="store_true")
args = parser.parse_args()
use_default_values = args.use_default_values
install_integration = args.install_integration

# пишем константы
values_name = "compass"
environment = "production"
stack_name_prefix = environment + "-" + values_name
domino_id = "d1"


# класс для сравнения версии инсталлятора
class Version(tuple):
    def __new__(cls, text):
        return super().__new__(cls, tuple(int(x) for x in text.split(".")))


# сначала актуализируем инсталлятор
sb = subprocess.run(
    [
        "python3",
        script_resolved_path + "/installer_migrations_up.py",
        "-e",
        environment,
        "-v",
        values_name,
    ]
)
if sb.returncode == 1:
    exit(1)

sb.returncode == 0 or scriptutils.die("Ошибка при выполнении миграции инсталлятора")

# подготовка
print("Создаем пользователя www-data, от имени которого будет работать приложение")
subprocess.run(
    ["python3", script_resolved_path + "/create_www_data.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании пользователя www-data")

print("Проверяем конфигурацию БД")
command = ["python3", script_resolved_path + "/validate_db_configuration.py", "--validate-only"]
if subprocess.run(command).returncode != 0:
    scriptutils.die("Ошибка при валидации конфигурации БД")

print("Валидируем конфигурацию капчи")
sb = subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_captcha_configuration.py",
        "--validate-only",
    ]
)
if sb.returncode == 1:
    exit(1)

sb.returncode == 0 or scriptutils.die("Ошибка при валидации конфигурации капчи")

print("Валидируем конфигурацию sms провайдеров")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_sms_service_configuration.py",
        "--validate-only",
    ]
).returncode == 0 or scriptutils.die(
    "Ошибка при валидации конфигурации sms провайдеров"
)

print("Валидируем конфигурацию аутентификации")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_auth_data_configuration.py",
        "--validate-only",
    ]
).returncode == 0 or scriptutils.die("Ошибка при валидации конфигурации аутентификации")

print("Валидируем конфигурацию ограничений")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_restrictions_configuration.py",
        "--validate-only",
    ]
).returncode == 0 or scriptutils.die("Ошибка при валидации конфигурации ограничений")

print("Валидируем конфигурацию парсинга превью ссылок")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_preview_configuration.py",
        "--validate-only",
    ]
).returncode == 0 or scriptutils.die("Ошибка при валидации конфигурации парсинга превью ссылок")

print("Валидируем конфигурацию приложения")
command = [
    script_resolved_path + "/init.py",
    "-e",
    environment,
    "-v",
    values_name,
    "-p",
    "monolith",
    "--validate-only",
]
subprocess.run(command).returncode == 0 or scriptutils.die(
    "Ошибка при валидации конфигурации приложения"
)

subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_ssl_certificates.py",
        "-e",
        environment,
        "-v",
        values_name,
        "--validate-only",
    ]
).returncode == 0 or scriptutils.die("Ошибка при валидации сертификатов")

subprocess.run(
    [
        "python3",
        script_resolved_path + "/create_team.py",
        "-e",
        environment,
        "-v",
        values_name,
        "--init",
        "--validate-only"
    ]
).returncode == 0 or scriptutils.die("Ошибка при валидации данных команды")

print("Запускаем скрипт генерации конфигурации известных БД")
if subprocess.run(["python3", script_resolved_path + "/validate_db_configuration.py"]).returncode != 0:
    scriptutils.die("Ошибка при создании конфигурации известных БД")

print("Запускаем скрипт генерации конфигурации капчи")
subprocess.run(
    ["python3", script_resolved_path + "/generate_captcha_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации капчи")

print("Запускаем скрипт генерации конфигурации sms провайдеров")
subprocess.run(
    ["python3", script_resolved_path + "/generate_sms_service_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации sms провайдеров")

print("Запускаем скрипт генерации конфигурации аутентификации")
subprocess.run(
    ["python3", script_resolved_path + "/generate_auth_data_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации аутентификации")

print("Запускаем скрипт генерации конфигурации ограничений")
subprocess.run(
    ["python3", script_resolved_path + "/generate_restrictions_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации ограничений")

print("Запускаем скрипт генерации конфигурации парсинга превью ссылок")
subprocess.run(
    ["python3", script_resolved_path + "/generate_preview_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации парсинга превью ссылок")

print("Запускаем скрипт инициализации проекта")
command = [script_resolved_path + "/init.py", "-e", environment, "-v", values_name, "-p", "monolith"]
if use_default_values:
    command.append("--use-default-values")
if install_integration:
    command.append("--install-integration")

subprocess.run(command).returncode == 0 or scriptutils.die(
    "Ошибка при сверке конфигурации приложения"
)

print(
    "Запускаем скрипт генерации ssl сертификатов для безопасного общения между проектами"
)
subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_ssl_certificates.py",
        "-e",
        environment,
        "-v",
        values_name,
    ]
).returncode == 0 or scriptutils.die("Ошибка при генерации сертификатов")

print("Проводим генерацию ключей безопасности")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_security_keys.py",
        "-e",
        environment,
        "-v",
        values_name,
    ]
).returncode == 0 or scriptutils.die("Ошибка при создании ключей безопасности")

script_dir = str(Path(__file__).parent.resolve())
version_path = Path(script_dir + "/../.version")

if not version_path.exists():
    current_version = 0
else:
    current_version = version_path.open("r").read()

# в 6.0.0 появился php_migration и можем спокойно накатывать миграции ДО update.py
if Version(current_version) >= Version("6.0.1"):

    # накатываем миграцию на компании
    sb = subprocess.run(
        [
            "python3",
            script_resolved_path + "/companies_database_migrations_up.py",
            "-e",
            environment,
            "-v",
            values_name,
        ]
    )
    if sb.returncode == 1:
        exit(1)

# деплой

# удаляем старые симлинки, только с помощью subproccess, ибо симлинки ведут на удаленные дериктории и unlink/rmtree просто не срабатывает

monolith_variable_nginx_path = Path("%s/../src/monolith/variable/nginx" % (script_dir))
subprocess.run(["rm", "-rf", monolith_variable_nginx_path])

monolith_config_nginx_path = Path("%s/../src/monolith/config/nginx" % (script_dir))
subprocess.run(["rm", "-rf", monolith_config_nginx_path])

monolith_config_join_web_path = Path(
    "%s/../src/monolith/config/join_web" % (script_dir)
)
subprocess.run(["rm", "-rf", monolith_config_join_web_path])

print("Разворачиваем приложение")
command = [
    "python3",
    script_resolved_path + "/deploy.py",
    "-e",
    environment,
    "-v",
    values_name,
    "-p",
    "monolith",
]
if use_default_values:
    command.append("--use-default-values")
if install_integration:
    command.append("--install-integration")
subprocess.run(command).returncode == 0 or scriptutils.die(
    "Ошибка при разворачивании приложения"
)

if install_integration:
    print("Разворачиваем интеграцию")
    command = [
        "python3",
        script_resolved_path + "/deploy.py",
        "-e",
        environment,
        "-v",
        values_name,
        "-p",
        "integration",
        "--project-name-override",
        "integration",
    ]
    if use_default_values:
        command.append("--use-default-values")
    command.append("--install-integration")
    subprocess.run(command).returncode == 0 or scriptutils.die(
        "Ошибка при разворачивании интеграции"
    )

# подключаемся к докеру
client = docker.from_env()
# ждем появления monolith
timeout = 900
n = 0
loader = Loader(
    "Ждем готовности php_monolith",
    "php_monolith готов",
    "php_monolith не может подняться",
)
loader.start()
while n <= timeout:

    monolith_service = None

    # ждем, пока у сервиса не будет статуса обновления completed
    service_list = client.services.list(filters={
        "name": "%s-monolith_php-monolith" % (stack_name_prefix),
    })

    if len(service_list) > 0:
        monolith_service = service_list[0]

    if monolith_service is None:
        continue

    if (monolith_service.attrs.get("UpdateStatus") is not None and monolith_service.attrs["UpdateStatus"].get(
            "State") != "completed"):
        continue

    # проверяем, что контейнер жив
    healthy_docker_container_list = client.containers.list(
        filters={
            "name": "%s-monolith_php-monolith" % (stack_name_prefix),
            "health": "healthy",
        }
    )
    if len(healthy_docker_container_list) > 0:
        found_monolith_container = healthy_docker_container_list[0]
        break

    n = n + 5
    sleep(5)
    if n == timeout:
        loader.error()
        scriptutils.die("php_monolith не поднялся")

# проверяем готовность monolith

output = found_monolith_container.exec_run(["sh", "wait-ready.sh"])

if output.exit_code == 0:
    loader.success()
else:
    loader.error()
    print("php_monolith вернул " + str(e.return_code) + " exit code")

# ждем поднятия nginx
timeout = 160
n = 0
loader = Loader(
    "Ждем готовности nginx",
    "nginx готов",
    "nginx не может подняться",
)
loader.start()

while n <= timeout:

    nginx_service = None

    # ждем, пока у сервиса не будет статуса обновления completed
    service_list = client.services.list(filters={
        "name": "%s-monolith_nginx-monolith" % (stack_name_prefix),
    })

    if len(service_list) > 0:
        nginx_service = service_list[0]

    if nginx_service is None:
        n = n + 5
        sleep(5)
        if n == timeout:
            loader.error()
            scriptutils.die("nginx не поднялся")
        continue

    if (nginx_service.attrs.get("UpdateStatus") is not None and nginx_service.attrs["UpdateStatus"].get(
            "State") == "paused"):
        n = n + 40
        if n == timeout:
            loader.error()
            scriptutils.die("nginx не поднялся")

        # обновляем nginx
        sleep(20)
        nginx_service.update()
        sleep(20)
        continue

    if (nginx_service.attrs.get("UpdateStatus") is not None and nginx_service.attrs["UpdateStatus"].get(
            "State") != "completed"):
        n = n + 5
        sleep(5)
        if n == timeout:
            loader.error()
            scriptutils.die("nginx не поднялся")
        continue

    healthy_docker_container_list = client.containers.list(
        filters={
            "name": "%s-monolith_nginx-monolith" % (stack_name_prefix),
            "health": "healthy",
        }
    )
    if len(healthy_docker_container_list) > 0:
        found_nginx_container = healthy_docker_container_list[0]
        break

    n = n + 5
    sleep(5)
    if n == timeout:
        loader.error()
        scriptutils.die("nginx не поднялся")
loader.success()
sleep(10)

# если версия была ниже 6.0.1 - php_migration еще не задеплоен и необходимо накатить один раз миграции ПОСЛЕ update.py
if Version(current_version) < Version("6.0.1"):

    # накатываем миграцию на компании
    sb = subprocess.run(
        [
            "python3",
            script_resolved_path + "/companies_database_migrations_up.py",
            "-e",
            environment,
            "-v",
            values_name,
        ]
    )
    if sb.returncode == 1:
        exit(1)

# инициализируем приложение
loader = Loader(
    "Обновляем приложение",
    "Приложение обновлено",
    "Приложение не может обновиться",
).start()
subprocess.run(
    [
        "python3",
        script_resolved_path + "/init_pivot.py",
        "-e",
        environment,
        "-v",
        values_name,
    ]
)
loader.success()
