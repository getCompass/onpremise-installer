#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import subprocess, argparse

from utils import scriptutils
from pathlib import Path
import docker, yaml, json
from time import sleep
from loader import Loader
from docker.errors import APIError

scriptutils.assert_root()

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_resolved_path = str(script_path.resolve())

parser = argparse.ArgumentParser(add_help=False)

parser.add_argument("--use-default-values", required=False, action="store_true")
parser.add_argument("--install-integration", required=False, action="store_true")
parser.add_argument("--docker-prune", required=False, action="store_true")
parser.add_argument("-e", "--environment", required=False, default="production", type=str, help="Окружение, в котором разворачиваем")
# ВНИМАНИЕ - в data передается json
parser.add_argument(
    "--data", required=False, type=json.loads, help="дополнительные данные для развертывания"
)
parser.add_argument("--is-restore-db", required=False, default=0, type=int, help="запуск от скрипта бекапа")
args = parser.parse_args()
use_default_values = args.use_default_values
install_integration = args.install_integration
docker_prune = args.docker_prune
override_data = args.data if args.data else {}
if not override_data:
    override_data = {}
product_type = override_data.get("product_type", "") if override_data else ""
is_restore_db = bool(args.is_restore_db == 1)

environment = args.environment

# пишем константы
values_name = "compass"
stack_name_prefix = environment + "-" + values_name
stack_name = stack_name_prefix + "-monolith"
domino_id = "d1"


# класс для сравнения версии инсталлятора
class Version(tuple):
    def __new__(cls, text):
        return super().__new__(cls, tuple(int(x) for x in text.split(".")))

# обновить конфиги пространств
def update_space_configs(monolith_container: docker.models.containers.Container):

    result = monolith_container.exec_run(
    user="www-data",
    cmd=[
        "bash",
        "-c",
        "php src/Compass/Pivot/sh/php/domino/force_update_company_db.php",
        ],
    )
    # форсированный апдейт конфигов идет каждые 180 секунд
    sleep(180)

    return result

def wait_go_database():

    # ждем поднятия go_database
    timeout = 180
    n = 0
    loader = Loader(
        "Ждем готовности go_database",
        "go_database готов",
        "go_database не может подняться",
    )
    loader.start()

    while n <= timeout:

        nginx_service = None

        # ждем, пока у сервиса не будет статуса обновления completed
        service_list = client.services.list(filters={
            "name": "%s_go-database" % (stack_name),
        })

        if len(service_list) > 0:
            go_database_service = service_list[0]

        if go_database_service is None:
            n = n + 5
            sleep(5)
            if n == timeout:
                loader.error()
                scriptutils.die("go_database не поднялся")
            continue

        if (go_database_service.attrs.get("UpdateStatus") is not None and go_database_service.attrs["UpdateStatus"].get(
                "State") == "paused"):
            n = n + 40
            if n == timeout:
                loader.error()
                scriptutils.die("go_database не поднялся")

            # обновляем nginx
            sleep(20)
            go_database_service.update()
            sleep(20)
            continue

        if (go_database_service.attrs.get("UpdateStatus") is not None and go_database_service.attrs["UpdateStatus"].get(
                "State") != "completed"):
            n = n + 5
            sleep(5)
            if n == timeout:
                loader.error()
                scriptutils.die("go_database не поднялся")
            continue

        healthy_docker_container_list = client.containers.list(
            filters={
                "name": "%s_go-database" % (stack_name),
                "health": "healthy",
            }
        )
        if len(healthy_docker_container_list) > 0:
            break

        n = n + 5
        sleep(5)
        if n == timeout:
            loader.error()
            scriptutils.die("go_database не поднялся")
    loader.success()

# получить контейнер монолита
def get_monolith_container():
    timeout = 900
    n = 0
    while n <= timeout:

        monolith_service = None

        service_list = client.services.list(filters={
            "name": "%s_php-monolith" % (stack_name),
        })

        if len(service_list) > 0:
            monolith_service = service_list[0]

        if monolith_service is None:
            continue

        # ждем, пока у сервиса не будет статуса обновления completed
        if (monolith_service.attrs.get("UpdateStatus") is not None and monolith_service.attrs["UpdateStatus"].get(
                "State") != "completed"):
            continue

        # проверяем, что контейнер жив
        healthy_docker_container_list = client.containers.list(
            filters={
                "name": "%s_php-monolith" % (stack_name),
                "health": "healthy",
            }
        )
        if len(healthy_docker_container_list) > 0:
            found_monolith_container = healthy_docker_container_list[0]
            break

        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die("не смогли найти php_monolith контейнер")
    return found_monolith_container

# получаем текущую версию инсталлятора
script_dir = str(Path(__file__).parent.resolve())
version_path = Path(script_dir + "/../.version")

if not version_path.exists():
    current_version = "0.0.0"
else:
    current_version = version_path.open("r").read()


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

if docker_prune:
    print("Очищаем неиспользуемые docker контейнеры")
    subprocess.run(
        ["docker", "system", "prune", "--force"]
    ).returncode == 0 or scriptutils.die("Ошибка при очистке неиспользуемых docker контейнеров")

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
service_label = values_dict.get("service_label") if values_dict.get("service_label") else ""
if service_label != "":
    stack_name = stack_name + "-" + service_label

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

script_dir = str(Path(__file__).parent.resolve())
service_label_path = Path(script_dir + "/../.service_label")

# если файл с service_label отсутствует, то считаем что он пустой
current_service_label = ""
need_delete_old_stack = False
need_repair_all_teams = False
if service_label_path.exists():
    current_service_label = service_label_path.open("r").read()
    need_delete_old_stack = True

if service_label == "" and current_service_label != "":
    stack_name = stack_name + f"-{current_service_label}"

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

# подключаемся к докеру
client = docker.from_env()

if need_delete_old_stack and ((current_service_label != "" and current_service_label != service_label) or (current_service_label == "" and service_label != "")):

    try:
        scriptutils.warning("Перед тем как продолжить, убедитесь, что установлен label.role для ноды на текущем сервере!")
        if input("При смене service_label приложение будет недоступно для пользователей в течение ~5 минут, продолжить? [y/N]\n").lower() != "y":
            scriptutils.die("Смена service_label была отменена")
    except UnicodeDecodeError as e:
        print("Не смогли декодировать ответ. Error: ", e)
        exit(0)

    # удаляем стаки компаний
    get_stack_command = ["docker", "stack", "ls"]
    grep_command = ["grep", stack_name_prefix]
    grep_company_command = ["grep", r"\-company"]
    delete_command = ["xargs", "docker", "stack", "rm"]

    # сначала удаляем компанейские стаки
    get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
    grep_process = subprocess.Popen(
        grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
    )
    grep_company_process = subprocess.Popen(
        grep_company_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
    )
    delete_process = subprocess.Popen(
        delete_command, stdin=grep_company_process.stdout, stdout=subprocess.PIPE
    )
    output, _ = delete_process.communicate()

    # удаляем остальные стаки
    get_stack_command = ["docker", "stack", "ls"]
    grep_command = ["grep", stack_name_prefix]
    grep_monolith_command = ["grep", "-v", r"\-company"]
    delete_command = ["xargs", "docker", "stack", "rm"]

    # сначала удаляем компанейские стаки
    get_stack_process = subprocess.Popen(get_stack_command, stdout=subprocess.PIPE)
    grep_process = subprocess.Popen(
        grep_command, stdin=get_stack_process.stdout, stdout=subprocess.PIPE
    )
    grep_monolith_process = subprocess.Popen(
        grep_monolith_command, stdin=grep_process.stdout, stdout=subprocess.PIPE
    )
    delete_process = subprocess.Popen(
        delete_command, stdin=grep_monolith_process.stdout, stdout=subprocess.PIPE
    )
    output, _ = delete_process.communicate()

    # ждем, пока все контейнеры удалятся
    timeout = 600
    n = 0
    while n <= timeout:
        docker_container_list = client.containers.list(filters={"name": stack_name_prefix}, sparse=True, ignore_removed=True)

        if len(docker_container_list) < 1:
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die("Не смогли удалить все контейнеры при смене service_label")

    # ждем удаления сетей
    timeout = 120
    n = 0
    while n <= timeout:
        docker_network_list = client.networks.list(filters={"name": stack_name_prefix})

        if len(docker_network_list) < 1:
            break
        n = n + 5
        sleep(5)
        if n == timeout:
            scriptutils.die("Не смогли удалить сети при смене service_label")

    sleep(10)

    # удаляем volumes jitsi
    jitsi_volume_list = client.volumes.list(filters={"name": "%s_jitsi-custom-" % stack_name})
    for volume in jitsi_volume_list:
        try:
            volume.remove()
        except docker.errors.NotFound:
            continue
        except docker.errors.APIError as e:
            print("Не удалось удалить один из jitsi volume при смене service_label: ", e)

    need_repair_all_teams = True

# подключаемся к докеру
client = docker.from_env()
php_migration_container_name = "%s_php-migration" % stack_name
need_update_migrations_after_deploy = True

container_list = client.containers.list(filters={'name': php_migration_container_name, 'health': 'healthy'})
if len(container_list) > 0:
    need_update_migrations_after_deploy = False

# в 6.0.0 появился php_migration и можем спокойно накатывать миграции ДО update.py
if Version(current_version) >= Version("6.0.1") and not need_update_migrations_after_deploy and not is_restore_db:

    # накатываем миграцию на компании
    sb = subprocess.run(
        [
            "python3",
            script_resolved_path + "/companies_database_migrations_up.py",
            "-e",
            environment,
            "-v",
            values_name,
            "--service-label",
            current_service_label,
        ]
    )
    if sb.returncode == 1:
        exit(1)

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

# после deploy актуализируем service_label для получения корректного имя стака
current_service_label = ""
if service_label_path.exists():
    current_service_label = service_label_path.open("r").read()

if service_label == "" and current_service_label == "":
    stack_name = stack_name_prefix + "-monolith"

print("Префикс сервисов: %s" % stack_name)

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
        "name": "%s_php-monolith" % (stack_name),
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
            "name": "%s_php-monolith" % (stack_name),
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
        "name": "%s_nginx" % (stack_name),
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
            "name": "%s_nginx" % (stack_name),
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
sleep(60)
loader.success()

# Если версия меньше 4.1.0 - обновляем конфиги пространств
if Version(current_version) < Version("4.1.0"):

    wait_go_database()
    sleep(30)

    loader = Loader("Запускаем пространства...", "Запустили пространства", "Не смогли запустить пространства").start()

    try:
        result = update_space_configs(found_monolith_container)
        if result.exit_code != 0:
            found_monolith_container = get_monolith_container()
            result = update_space_configs(found_monolith_container)
    except APIError as e:
        found_monolith_container = get_monolith_container()
        result = update_space_configs(found_monolith_container)

    if result.exit_code != 0:
        scriptutils.die("Не смогли обновить конфигурацию пространств. Убедитесь, что окружение поднялось корректно.")

    loader.success()

    loader = Loader(
        "Ждем готовности микросервисов",
        "Микросервисы готовы",
        "Микросервисы не могут подняться",
    ).start()

    # обновляем сервисы
    service_list = client.services.list(filters={
        "name": "%s_go-" % (stack_name),
    })

    for service in service_list:
        service.force_update()
    sleep(90)

    loader.success()

# если версия была ниже 6.0.1 - php_migration еще не задеплоен и необходимо накатить один раз миграции ПОСЛЕ update.py
if (Version(current_version) < Version("6.0.1") or need_update_migrations_after_deploy) and not is_restore_db:

    # накатываем миграцию на компании
    sb = subprocess.run(
        [
            "python3",
            script_resolved_path + "/companies_database_migrations_up.py",
            "-e",
            environment,
            "-v",
            values_name,
            "--service-label",
            current_service_label,
        ]
    )
    if sb.returncode == 1:
        exit(1)

print("Запускаем скрипт проверки занятых компаний")
subprocess.run([
    "python3", script_resolved_path + "/check_is_busy_companies.py",
    "-e",
    environment,
    "-v",
    values_name, ]).returncode == 0 or scriptutils.die("Ошибка при проверке занятых компаний")

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
        "--service_label",
        service_label
    ]
)
loader.success()

if need_repair_all_teams:
    subprocess.run(
        [
            "python3",
            script_resolved_path + "/replication/repair_all_teams.py",
            "-e",
            environment,
            "-v",
            values_name
        ]
    )
