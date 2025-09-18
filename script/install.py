#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import subprocess, argparse

from utils import scriptutils
from pathlib import Path
import docker, yaml, json
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
            scriptutils.warning(
                "Обнаружены данные Compass в директории root_mount_path. Для предотвращения ошибок рекомендуем удалить эти данные перед продолжением установки. Продолжить установку? [Y/n]\n")
        )

        if confirm.lower() != "y":
            scriptutils.die("Установка прервана")


# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("--use-default-values", required=False, action="store_true")
parser.add_argument("--install-integration", required=False, action="store_true")
parser.add_argument("-e", "--environment", required=False, default="production", type=str,
                    help="Окружение, в котором разворачиваем")
# ВНИМАНИЕ - в data передается json
parser.add_argument(
    "--data", required=False, type=json.loads, help="дополнительные данные для развертывания"
)
args = parser.parse_args()
use_default_values = args.use_default_values
install_integration = args.install_integration
override_data = args.data if args.data else {}
if not override_data:
    override_data = {}
product_type = override_data.get("product_type", "") if override_data else ""

environment = args.environment

# пишем константы
values_name = "compass"
stack_name_prefix = environment + "-" + values_name
stack_name = stack_name_prefix + "-monolith"
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
subprocess.run(command).returncode == 0 or exit(1)

print("Валидируем конфигурацию отказоустойчивости и бд")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/replication/validate_db_docker.py",
    ]
).returncode == 0 or scriptutils.die("Отказоустойчивость можно настроить только для docker драйвера баз данных")
subprocess.run(
    [
        "python3",
        script_resolved_path + "/replication/validate_os.py",
    ]
).returncode == 0 or scriptutils.die("В данной версии приложения отказоустойчивость нельзя включить в RPM-системах")

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

print("Запускаем скрипт генерации конфигурации парсинга превью ссылок")
subprocess.run(
    ["python3", script_resolved_path + "/generate_preview_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации парсинга превью ссылок")

print("Запускаем скрипт инициализации проекта")
command = [script_resolved_path + "/init.py", "-e", environment, "-v", values_name, "-p", "monolith"]
if use_default_values:
    command.append("--use-default-values")

subprocess.run(command).returncode == 0 or scriptutils.die(
    "Ошибка при сверке конфигурации приложения"
)

if Path(script_dir + "/../src/values." + environment + "." + values_name + ".yaml").exists():
    specified_values_file_name = str(
        Path(script_dir + "/../src/values." + environment + "." + values_name + ".yaml").resolve()
    )
elif (
        product_type
        and Path(script_dir + "/../src/values." + values_name + "." + product_type + ".yaml").exists()
):
    specified_values_file_name = str(
        Path(script_dir + "/../src/values." + values_name + "." + product_type + ".yaml").resolve()
    )
elif (Path(script_dir + "/../src/values." + values_name + ".yaml").exists()):
    specified_values_file_name = str(Path(script_dir + "/../src/values." + values_name + ".yaml").resolve())
else:
    specified_values_file_name = str(Path(script_dir + "/../src/values.yaml").resolve())

with open(specified_values_file_name, "r") as values_file:
    values_dict = yaml.safe_load(values_file)

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = values_dict.get("service_label")
if service_label is not None and service_label != "":
    stack_name = stack_name + "-" + service_label

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

subprocess.run(
    [
        "python3",
        script_resolved_path + "/generate_mysql_ssl_certificates.py",
        "-e",
        environment,
        "-v",
        values_name,
    ]
).returncode == 0 or scriptutils.die("Ошибка при генерации сертификатов для mysql")

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

if scriptutils.is_rpm_os():
    subprocess.run(["cp", '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
                    '/etc/pki/ca-trust/extracted/pem/ca-certificates.crt'])

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
            "name": "%s_php-monolith" % (stack_name),
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
            "name": "%s_nginx" % (stack_name),
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

# настраиваем репликацию на основном mysql
if scriptutils.is_replication_enabled(values_dict) == True:
    subprocess.run(
        [
            "python3",
            script_resolved_path + "/replication/create_mysql_user.py",
            "-e",
            environment,
            "-v",
            values_name,
            "--type",
            "monolith",
            "--is_logs",
            str(0)
        ]
    )

if scriptutils.is_replication_master_server(values_dict):
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
            "--service_label",
            service_label
        ]
    )
    loader.success()

    # создаем первого пользователя
    print("Создаем первого пользователя")
    subprocess.run(
        ["python3", script_resolved_path + "/create_root_user.py", "-e", environment, "--service_label", service_label])
else:
    print("Запускаем репликацию mysql в monolith")
    subprocess.run(
        [
            "python3", script_resolved_path + "/replication/start_slave_replication.py",
            "-e", environment,
            "-v", values_name,
            "--type", "monolith",
            "--is-choice-space", "0"
        ]
    )

if scriptutils.is_replication_enabled(values_dict) == True:
    print("Настраиваем репликацию мантикоры")
    if scriptutils.is_replication_master_server(values_dict):
        subprocess.run(
            [
                "python3",
                script_resolved_path + "/replication/start_manticore_replication.py",
                "-e",
                environment,
                "-v",
                values_name,
                "--type",
                "master"
            ]
        )
    else:
        subprocess.run(
            [
                "python3",
                script_resolved_path + "/replication/start_manticore_replication.py",
                "-e",
                environment,
                "-v",
                values_name,
                "--type",
                "reserve"
            ]
        )

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
        "--init"
    ]
)
