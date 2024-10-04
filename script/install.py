#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import subprocess, argparse

from utils import scriptutils
from pathlib import Path
import docker, yaml
from time import sleep
from loader import Loader
from utils.scriptutils import bcolors

scriptutils.assert_root()

# функция проверки наличия предыдущей установки
def check_previous_install(global_file_path: Path):

    with global_file_path.open("r") as global_file:
        global_values = yaml.safe_load(global_file)
        global_values = {} if global_values is None else global_values

    # если у нас нет информации по root_mount_path, не проверяем и проходим на установку
    if global_values == {}:
        return
    
    root_mount_path_str = global_values.get("root_mount_path")
    if root_mount_path_str is None:
        return

    root_mount_path = Path(root_mount_path_str)

    # если папка существует, и там есть хотя бы один файлик - говорим об этом пользователю
    if root_mount_path.exists() and any(root_mount_path.iterdir()):

        confirm = input(
            scriptutils.warning("Обнаружены данные Compass в директории root_mount_path. Для предотвращения ошибок рекомендуем удалить эти данные перед продолжением установки. Продолжить установку? [Y/n]\n")
            )

        if confirm.lower() != "y":
            scriptutils.die("Установка прервана")

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

# пользователь должен подтвердить согласие с условиями публичной оферты
begin_confirm_text = "Пожалуйста, подтвердите согласие с условиями публичной оферты"
begin_confirm_text += bcolors.OKBLUE + " (getcompass.ru/docs/on-premise/offer.pdf)" + bcolors.ENDC
begin_confirm_text += " и политики конфиденциальности"
begin_confirm_text += bcolors.OKBLUE + " (getcompass.ru/docs/privacy.pdf)" + bcolors.ENDC
begin_confirm_text += ", чтобы начать установку.\n"
end_confirm_text = "Введите «"
end_confirm_text += bcolors.OKGREEN + "Y" + bcolors.ENDC
end_confirm_text += "» для подтверждения согласия или «n» для отмены установки:"
confirm_text = begin_confirm_text + end_confirm_text

confirm = "n"
while confirm != "y":

    confirm = input(confirm_text).lower().strip()

    # если пользователь дал некорректный ответ
    if confirm != "y" and confirm != "n":
        print(bcolors.FAIL + "Указано некорректное значение" + bcolors.ENDC)
        confirm_text = end_confirm_text

    # если пользователь не подтвердил согласие - выходим
    if confirm == "n":
        exit(1)

# подготовка
script_dir = str(Path(__file__).parent.resolve())

# проверяем, что папка с данными для компасса пуста
global_file_path = Path("%s/../configs/global.yaml" % (script_dir))

if global_file_path.exists():
    check_previous_install(global_file_path)

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

print("Валидируем данные главного пользователя")
subprocess.run(
    ["python3", script_resolved_path + "/create_root_user.py", "--validate-only"]
).returncode == 0 or scriptutils.die("Ошибка при валидации данных пользователя")

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

print("Запускаем скрипт инициализации проекта")
command = [script_resolved_path + "/init.py", "-e", environment, "-v", values_name, "-p", "monolith"]
if use_default_values:
    command.append("--use-default-values")

subprocess.run(command).returncode == 0 or scriptutils.die(
    "Ошибка при сверке конфигурации приложения"
)

print("Запускаем скрипт генерации конфигурации известных БД")
if subprocess.run(["python3", script_resolved_path + "/validate_db_configuration.py"]).returncode != 0:
    scriptutils.die("Ошибка при создании конфигурации известных БД")

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
    docker_container_list = client.containers.list(
        filters={
            "name": "%s-monolith_php-monolith" % (stack_name_prefix),
            "health": "healthy",
        }
    )
    if len(docker_container_list) > 0:
        found_monolith_container = docker_container_list[0]
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

timeout = 60
n = 0
loader = Loader(
    "Ждем готовности nginx",
    "nginx готов",
    "nginx не может подняться",
)
loader.start()

while n <= timeout:
    docker_container_list = client.containers.list(
        filters={
            "name": "%s-monolith_nginx-monolith" % (stack_name_prefix),
            "health": "healthy",
        }
    )
    if len(docker_container_list) > 0:
        found_nginx_container = docker_container_list[0]
        break
    n = n + 5
    sleep(5)
    if n == timeout:
        loader.error()
        scriptutils.die("nginx не поднялся")
loader.success()
sleep(10)

# инициализируем приложение
loader = Loader(
    "Инициализируем приложение",
    "Приложение инициализировано",
    "Приложение не может инициализироваться",
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

# создаем первого пользователя
print("Создаем первого пользователя")
subprocess.run(["python3", script_resolved_path + "/create_root_user.py"])

# создаем команду
print("Создаем команду")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/create_team.py",
        "-e",
        environment,
        "-v",
        values_name,
        "--init",
    ]
)
