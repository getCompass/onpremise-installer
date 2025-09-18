#!/usr/bin/env python3

import sys, os

sys.dont_write_bytecode = True

import subprocess, argparse

from utils import scriptutils
from pathlib import Path
import docker, yaml
from time import sleep
from loader import Loader
from utils.scriptutils import bcolors
import json

scriptutils.assert_root()

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())

# === ПРОГРЕСС УСТАНОВКИ ===
STEPS_FILE = Path(script_resolved_path).parent / ".install_completed_steps.json"


def ensure_steps_file():
    if not STEPS_FILE.exists():
        try:
            STEPS_FILE.write_text("[]", encoding="utf-8")
        except Exception:
            # трекинг не ломает установку
            pass


def append_step(step: str):
    try:
        ensure_steps_file()
        raw = STEPS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw.strip() or "[]")
        if not isinstance(data, list):
            data = []
        if step not in data:
            data.append(step)
            STEPS_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # трекинг не ломает установку
        pass


parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("--use-default-values", required=False, action="store_true")
parser.add_argument("--install-integration", required=False, action="store_true")
parser.add_argument("--confirm-all", required=False, action="store_true")
parser.add_argument("--validate-only", required=False, action="store_true")
parser.add_argument("--installer-output", required=False, action="store_true")
parser.add_argument("-e", "--environment", required=False, default="production", type=str,
                    help="Окружение, в котором разворачиваем")
# ВНИМАНИЕ - в data передается json
parser.add_argument(
    "--data", required=False, type=json.loads, help="дополнительные данные для развертывания"
)
args = parser.parse_args()
use_default_values = args.use_default_values
install_integration = args.install_integration
confirm_all = args.confirm_all
validate_only = args.validate_only
installer_output = args.installer_output
override_data = args.data if args.data else {}
if not override_data:
    override_data = {}
product_type = override_data.get("product_type", "") if override_data else ""

environment = args.environment

QUIET = (validate_only and installer_output)


def log(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)


invalid_keys = []


def run_validation(command, key_name):
    global invalid_keys
    if installer_output:
        command.append("--installer-output")
    # Если нужен интерактив (нет --installer-output), не глушим вывод и даём увидеть промпты
    capture = bool(installer_output)
    result = subprocess.run(command, text=True, capture_output=capture)
    if result.returncode != 0:
        try:
            # если скрипт вывел JSON с ошибками
            errors = json.loads(result.stdout.strip() or "[]")
            invalid_keys.extend(errors)
        except Exception:
            # если скрипт выводит только текст — сохраняем ключ по умолчанию
            invalid_keys.append(key_name)
    return result.returncode


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
    if root_mount_path.exists() and any(root_mount_path.iterdir()) and not validate_only and not confirm_all:

        confirm = input(
            scriptutils.warning(
                "Обнаружены данные Compass в директории root_mount_path. Для предотвращения ошибок рекомендуем удалить эти данные перед продолжением установки. Продолжить установку? [Y/n]\n")
        )

        if confirm.lower() != "y":
            scriptutils.die("Установка прервана")


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

confirm = "y" if confirm_all else "n"
while confirm != "y":

    confirm = input(confirm_text).lower().strip()

    # если пользователь дал некорректный ответ
    if confirm != "y" and confirm != "n":
        log(bcolors.FAIL + "Указано некорректное значение" + bcolors.ENDC)
        confirm_text = end_confirm_text

    # если пользователь не подтвердил согласие - выходим
    if confirm == "n":
        exit(1)

# проверяем, что папка с данными для компасса пуста
global_file_path = Path("%s/../configs/global.yaml" % (script_resolved_path))

if global_file_path.exists():
    check_previous_install(global_file_path)

log("Создаем пользователя www-data, от имени которого будет работать приложение")
command = ["python3", script_resolved_path + "/create_www_data.py"]
if validate_only:
    command.append("--validate-only")
if installer_output:
    command.append("--installer-output")
subprocess.run(command).returncode == 0 or scriptutils.die("" if QUIET else "Ошибка при создании пользователя www-data")

log("Проверяем конфигурацию БД")
command = ["python3", script_resolved_path + "/validate_db_configuration.py", "--validate-only"]
if installer_output:
    command.append("--installer-output")
if subprocess.run(command).returncode != 0:
    scriptutils.die("" if QUIET else "Ошибка при валидации конфигурации БД")

log("Валидируем конфигурацию капчи")
command = [
    "python3",
    script_resolved_path + "/generate_captcha_configuration.py",
    "--validate-only",
]
if confirm_all:
    command.append("--confirm-all")
if installer_output:
    command.append("--installer-output")
return_code = run_validation(command, "captcha")
if return_code == 1:
    exit(1)

if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации конфигурации капчи")

log("Валидируем конфигурацию sms провайдеров")
return_code = run_validation(
    [
        "python3",
        script_resolved_path + "/generate_sms_service_configuration.py",
        "--validate-only",
    ],
    "auth"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации конфигурации sms провайдеров")

log("Валидируем конфигурацию аутентификации")
return_code = run_validation(
    [
        "python3",
        script_resolved_path + "/generate_auth_data_configuration.py",
        "--validate-only",
    ],
    "auth"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации конфигурации аутентификации")

log("Валидируем конфигурацию ограничений")
return_code = run_validation(
    [
        "python3",
        script_resolved_path + "/generate_restrictions_configuration.py",
        "--validate-only",
    ],
    "restrictions"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации конфигурации ограничений")

log("Валидируем конфигурацию парсинга превью ссылок")
return_code = run_validation(
    [
        "python3",
        script_resolved_path + "/generate_preview_configuration.py",
        "--validate-only",
    ],
    "preview"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации конфигурации парсинга превью ссылок")

log("Валидируем конфигурацию приложения")
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
return_code = run_validation(command, "init")
if return_code != 0 and not QUIET:
    exit(1)

log("Валидируем конфигурацию отказоустойчивости и бд")
return_code = run_validation(["python3", script_resolved_path + "/replication/validate_db_docker.py"], "replication")
if return_code != 0 and not QUIET:
    scriptutils.die("Отказоустойчивость можно настроить только для docker драйвера баз данных")

return_code = run_validation(["python3", script_resolved_path + "/replication/validate_os.py"], "replication")
if return_code != 0 and not QUIET:
    scriptutils.die("В данной версии приложения отказоустойчивость нельзя включить в RPM-системах")

return_code = run_validation(
    [
        "python3",
        script_resolved_path + "/generate_ssl_certificates.py",
        "-e",
        environment,
        "-v",
        values_name,
        "--validate-only",
    ], "ssl"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации сертификатов")

log("Валидируем данные главного пользователя")
return_code = run_validation(
    ["python3", script_resolved_path + "/create_root_user.py", "--validate-only"],
    "root_user"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации данных пользователя")

return_code = run_validation(
    [
        "python3",
        script_resolved_path + "/create_team.py",
        "-e",
        environment,
        "-v",
        values_name,
        "--init",
        "--validate-only"
    ],
    "team"
)
if return_code != 0 and not QUIET:
    scriptutils.die("Ошибка при валидации данных команды")

if validate_only:
    print(json.dumps(invalid_keys, ensure_ascii=False).strip())
    sys.exit(0)

log("Запускаем скрипт генерации конфигурации капчи")
command = ["python3", script_resolved_path + "/generate_captcha_configuration.py"]
if confirm_all:
    command.append("--confirm-all")
subprocess.run(command).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации капчи")

log("Запускаем скрипт генерации конфигурации sms провайдеров")
subprocess.run(
    ["python3", script_resolved_path + "/generate_sms_service_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации sms провайдеров")

log("Запускаем скрипт генерации конфигурации аутентификации")
subprocess.run(
    ["python3", script_resolved_path + "/generate_auth_data_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации аутентификации")

log("Запускаем скрипт генерации конфигурации ограничений")
subprocess.run(
    ["python3", script_resolved_path + "/generate_restrictions_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации ограничений")

log("Запускаем скрипт генерации конфигурации парсинга превью ссылок")
subprocess.run(
    ["python3", script_resolved_path + "/generate_preview_configuration.py"]
).returncode == 0 or scriptutils.die("Ошибка при создании конфигурации парсинга превью ссылок")

log("Запускаем скрипт инициализации проекта")
command = [script_resolved_path + "/init.py", "-e", environment, "-v", values_name, "-p", "monolith"]
if use_default_values:
    command.append("--use-default-values")

subprocess.run(command).returncode == 0 or scriptutils.die(
    "Ошибка при сверке конфигурации приложения"
)

if Path(script_resolved_path + "/../src/values." + environment + "." + values_name + ".yaml").exists():
    specified_values_file_name = str(
        Path(script_resolved_path + "/../src/values." + environment + "." + values_name + ".yaml").resolve()
    )
elif (
        product_type
        and Path(script_resolved_path + "/../src/values." + values_name + "." + product_type + ".yaml").exists()
):
    specified_values_file_name = str(
        Path(script_resolved_path + "/../src/values." + values_name + "." + product_type + ".yaml").resolve()
    )
elif (Path(script_resolved_path + "/../src/values." + values_name + ".yaml").exists()):
    specified_values_file_name = str(Path(script_resolved_path + "/../src/values." + values_name + ".yaml").resolve())
else:
    specified_values_file_name = str(Path(script_resolved_path + "/../src/values.yaml").resolve())

with open(specified_values_file_name, "r") as values_file:
    values_dict = yaml.safe_load(values_file)

# добавляем к префиксу stack-name также пометку сервиса, если такая имеется
service_label = values_dict.get("service_label")
if service_label is not None and service_label != "":
    stack_name = stack_name + "-" + service_label

log("Запускаем скрипт генерации конфигурации известных БД")
if subprocess.run(["python3", script_resolved_path + "/validate_db_configuration.py"]).returncode != 0:
    scriptutils.die("Ошибка при создании конфигурации известных БД")

log(
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

log("Проводим генерацию ключей безопасности")
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
monolith_variable_nginx_path = Path("%s/../src/monolith/variable/nginx" % (script_resolved_path))
subprocess.run(["rm", "-rf", monolith_variable_nginx_path])

monolith_config_nginx_path = Path("%s/../src/monolith/config/nginx" % (script_resolved_path))
subprocess.run(["rm", "-rf", monolith_config_nginx_path])

monolith_config_join_web_path = Path(
    "%s/../src/monolith/config/join_web" % (script_resolved_path)
)
subprocess.run(["rm", "-rf", monolith_config_join_web_path])

log("Разворачиваем приложение")
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
    log("Разворачиваем интеграцию")
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
    log("php_monolith вернул " + str(e.return_code) + " exit code")

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

append_step("intall_monolith")

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

    append_step("init_monolith")

    # создаем первого пользователя
    log("Создаем первого пользователя")
    subprocess.run(
        ["python3", script_resolved_path + "/create_root_user.py", "-e", environment, "--service_label", service_label])
else:
    log("Запускаем репликацию mysql в monolith")
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
    log("Настраиваем репликацию мантикоры")
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
log("Создаем команду")
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

append_step("create_team")
