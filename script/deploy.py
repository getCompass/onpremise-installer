#!/usr/bin/env python3
import glob
import sys

sys.dont_write_bytecode = True

import os, argparse, json, shutil, signal, atexit, yaml
from pathlib import Path
from utils import scriptutils
from subprocess import Popen
import hashlib, readline

# ---АГРУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument(
    "-e",
    "--environment",
    required=True,
    type=str,
    help="среда, для которой производим развертывание",
)
parser.add_argument(
    "-p", "--project", required=True, type=str, help="проект, который развертываем"
)
parser.add_argument(
    "-v",
    "--values",
    required=True,
    type=str,
    help="название файла со значениями для развертывания",
)
parser.add_argument(
    "-n", "--stack-name-prefix", required=False, type=str, help="префикс проекта"
)
parser.add_argument(
    "--project-name-override",
    required=False,
    type=str,
    help="оверрайд для имени проекта",
)

# ВНИМАНИЕ - в data передается json
parser.add_argument(
    "--data", required=False, type=json.loads, help="дополнительные данные для развертывания"
)
parser.add_argument(
    "--dry", required=False, action="store_true", help="запустить в dry-режиме"
)

parser.add_argument("--use-default-values", required=False, action="store_true")

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

# ---ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ---#


# делаем чистку
def cleanup():
    shutil.rmtree(tmp_path, ignore_errors=True)

    p = Popen(
        [
            "python3",
            script_dir + "/trigger.py",
            "-v",
            specified_values_file_name,
            "-p",
            project,
            "-t",
            "finally",
        ]
    )
    p.wait()


# переделываем override_data в строку для отправки в виде аргумента в другие скрипты
def override_data_to_string(override_data: dict) -> str:
    output = ""
    for key, value in override_data.items():
        output += key + "=" + value + " "

    if len(output) > 0:
        output = output[:-1]

    return output


# обработать env файлы
def process_goenv_files(goenv_files: list, project: str = ""):
    # формируем id проекта и путь до файлов
    project_id = ".global" if project == "" else ".project"

    for raw_variable_file in goenv_files:
        goenv_file_name = Path(raw_variable_file).name

        # пытаемся получить дополнительный префикс для файла, если такой найдется
        goenv_file_path_elements = (
            Path(raw_variable_file).absolute().as_posix().rsplit("/", 2)
        )
        prefix = (
            (goenv_file_path_elements[1] + ".")
            if goenv_file_path_elements[1] != "variable"
            else ""
        )

        # формируем итоговое имя файла, убирая из расширения префикс «go»
        env_file_name = (
            project_id + "." + prefix + str(goenv_file_name).replace(".goenv", ".env")
        )
        final_path = tmp_path + "/" + env_file_name

        # передаем файл в шаблонизатор
        Popen(
            [
                "python3",
                script_dir + "/template.py",
                raw_variable_file,
                values_file_name
                + " "
                + specified_values_file_name
                + " "
                + mount_security_file_name,
                final_path,
                override_data_to_string(override_data),
            ]
        ).wait()

        # делаем конвертацию из env файла в файл, понятный docker-swarm
        Popen(
            [script_dir + "/deploy_prepare_env.py", "-i", final_path, "-o", final_path]
        ).wait()

        # добавляем файл в список на удаление
        temporary_file_list.append(final_path)


# обработать конфигурационные файлы
def process_conf_files(config_files: list, project: str = ""):
    # формируем id проекта и путь до файлов
    project_id = ".global" if project == "" else ".project"

    # пробегаемся по всему списку файлов
    for raw_goconf_file_name in config_files:
        # имя файла из полученного списка
        goconf_file_name = Path(raw_goconf_file_name).name

        # пытаемся получить дополнительный префикс для файла, если такой найдется
        goconf_file_path_elements = (
            Path(raw_goconf_file_name).absolute().as_posix().rsplit("/", 2)
        )
        prefix = (
            (goconf_file_path_elements[1] + ".")
            if goconf_file_path_elements[1] != "config"
            else ""
        )

        # формируем итоговое имя файла, убирая из расширения префикс «go»
        conf_file_name = (
            project_id + "." + prefix + str(goconf_file_name).replace(".go", ".")
        )
        final_path = tmp_path + "/" + conf_file_name

        # передаем файл в шаблонизатор
        Popen(
            [
                "python3",
                script_dir + "/template.py",
                raw_goconf_file_name,
                values_file_name
                + " "
                + specified_values_file_name
                + " "
                + mount_security_file_name,
                final_path,
                override_data_to_string(override_data),
            ]
        ).wait()

        # снимаем short-хэш с файла
        revision = file_md5(final_path)
        override_data["config_revisions" + conf_file_name] = revision[0:7]

        # добавляем файл в список на удаление
        temporary_file_list.append(tmp_path + "/" + conf_file_name)


# функция высчитывания md5 хеша файла
def file_md5(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)

    return hash_md5.hexdigest()


# ---КОНЕЦ ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ---#

# ---СКРИПТ---#

# проверяем, что работаем из под пользователя с правами для docker
# scriptutils.assert_belongs_group('docker')

# получаем папку, где находится скрипт
script_path = Path(__file__).parent
script_dir = str(script_path.resolve())
root_path = str(Path(script_dir + "/../").resolve())
tmp_path = str(Path(root_path + "/tmp/").resolve())

# создаем папку для временных файлов и очищаем старые файлы оттуда
tmp_path_obj = Path(tmp_path)
tmp_path_obj.mkdir(exist_ok=True)
file_list = tmp_path_obj.glob("*")

for file in file_list:
    os.remove(file)

os.chdir(root_path)

# инициализируем переменные
stack_name_prefix = args.stack_name_prefix
override_data = args.data if args.data else {}
environment = args.environment
values = args.values
project = args.project
project_name_override = args.project_name_override
is_dry = args.dry
use_default_values = args.use_default_values
temporary_file_list = []
if not override_data:
    override_data = {}
# ловим сигналы и чистим tmp файлы
catchable_sigs = set(signal.Signals) - {signal.SIGKILL, signal.SIGSTOP}
atexit.register(cleanup)

for sig in catchable_sigs:
    signal.signal(signal.SIGINT, cleanup)


if not stack_name_prefix:
    stack_name_prefix = environment + "-" + values

values_file_name = str(Path("src/values.yaml").resolve())
product_type = override_data.get("product_type", "") if override_data else ""

if Path("src/values." + environment + "." + values + ".yaml").exists():
    specified_values_file_name = str(
        Path("src/values." + environment + "." + values + ".yaml").resolve()
    )
elif (
    product_type
    and Path("src/values." + values + "." + product_type + ".yaml").exists()
):
    specified_values_file_name = str(
        Path("src/values." + values + "." + product_type + ".yaml").resolve()
    )
else:
    specified_values_file_name = str(Path("src/values." + values + ".yaml").resolve())

if environment not in ["local", "tes"] and project != "search":
    # инициализируем конфиг
    exec_cmd = [script_dir + "/init.py", "-e", environment, "-v", values, "-p", project]
    if project_name_override is not None:
        exec_cmd = exec_cmd + ["--project-name-override", project_name_override]
    if use_default_values:
        exec_cmd.append("--use-default-values")
    p = Popen(exec_cmd)
    p.wait()

    if p.returncode != 0:
        print(scriptutils.error("Ошибка при сверке конфигурации приложения"))
        exit(1)

with open(specified_values_file_name, "r") as values_file:
    values_dict = yaml.safe_load(values_file)

root_mount_path = values_dict["root_mount_path"]

if environment not in ["local", "tes"] and project != "search":

    # копируем сертификаты
    cert_path = Path(str(script_path.resolve()) + "/../certs/")
    cert_create_script_path = Path(
        str(script_path.resolve()) + "/create_nginx_certs.py"
    )
    if not cert_path.exists():
        print(
            scriptutils.error(
                "Не сгенерированы сертификаты для серверов, запустите скрипт %s"
                % scriptutils.warning(str(cert_create_script_path.resolve()))
            )
        )
        exit(1)

    ssl_path = Path(root_mount_path + "/nginx/ssl")
    ssl_path.mkdir(exist_ok=True, parents=True)
    shutil.copytree(cert_path.resolve(), ssl_path.resolve(), dirs_exist_ok=True)

if project_name_override:
    stack_name = stack_name_prefix + "-" + project_name_override
    label = project_name_override
elif values_dict["projects"].get(project, {}).get("label", {}) != {}:
    stack_name = stack_name_prefix + "-" + values_dict["projects"][project]["label"]
    label = values_dict["projects"][project]["label"]
else:
    first_key = list(values_dict["projects"][project])[0]
    stack_name = (
        stack_name_prefix + "-" + values_dict["projects"][project][first_key]["label"]
    )
    label = values_dict["projects"][project][first_key]["label"]

override_data["stack_name_prefix"] = stack_name_prefix
override_data["stack_name"] = stack_name

security_file_path = Path("src/security.yaml")
security_file_name = str(security_file_path.resolve())

mount_security_file_path = Path(root_mount_path + "/security.yaml")
mount_security_file_name = str(mount_security_file_path.resolve())

if (not mount_security_file_path.exists()) and (not security_file_path.exists()):
    print(
        scriptutils.error("Не создан файл с ключами безопасности. Запустите скрипт ")
        + scriptutils.warning(script_dir + "/generate_security_keys.py")
    )
    exit(1)

if not mount_security_file_path.exists():
    shutil.copy2(security_file_name, mount_security_file_name)

# запускаем триггеры, которые нужно запустить до проекта
p = Popen(
    [
        "python3",
        script_dir + "/trigger.py",
        "-v",
        specified_values_file_name,
        "-p",
        project,
        "-t",
        "before",
    ]
)
p.wait()

# формируем глобальные env файлы
global_goenv_files = Path(root_path + "/src/_global/variable/").glob("*.goenv")
process_goenv_files(global_goenv_files)

# формирует проектные env файлы
# project_goenv_files = Path(root_path + '/src/' + project + '/variable/').glob('**/*.goenv')
project_goenv_files = glob.glob(root_path + "/src/" + project + "/variable/**/*.go*")
project_goenv_files.extend(glob.glob(root_path + "/src/" + project + "/variable/*.go*"))
process_goenv_files(project_goenv_files, project)

# формируем глобальные файлы конфигурации
config_files = Path(root_path + "/src/_global/config/").glob("*.go*")
process_conf_files(config_files)

# формируем проектные файлы конфигурации
# config_files = Path(root_path + '/src/' + project + '/config/').glob('**/*.go*')
config_files = glob.glob(root_path + "/src/" + project + "/config/**/*.go*")
config_files.extend(glob.glob(root_path + "/src/" + project + "/config/*.go*"))
process_conf_files(config_files, project)

print(override_data)
compose_file_name = ".compose.goyaml"
compose_override_file_name = ".compose.override.yaml"
compose_sidecar_file_name = ".compose.sidecar.yaml"

# формируем compose файл
p = Popen(
    [
        "python3",
        script_dir + "/template.py",
        "src/" + project + "/compose.goyaml",
        values_file_name
        + " "
        + specified_values_file_name
        + " "
        + mount_security_file_name,
        tmp_path + "/" + compose_file_name,
        override_data_to_string(override_data),
    ]
)
p.wait()

if p.returncode != 0:
    scriptutils.die("не удалось сгенерировать шаблон файла композиции")

# формируем compose файл для перезаписи
p = Popen(
    [
        "python3",
        script_dir + "/template.py",
        "src/" + project + "/compose.override." + environment + ".goyaml",
        values_file_name
        + " "
        + specified_values_file_name
        + " "
        + mount_security_file_name,
        tmp_path + "/" + compose_override_file_name,
        override_data_to_string(override_data),
    ]
)
p.wait()

if p.returncode != 0:
    scriptutils.die("не удалось сгенерировать шаблон файла перезаписи композиции")

# формируем compose файл для сайдкара
if Path("src/" + project + "/compose.sidecar." + environment + ".goyaml").exists():
    p = Popen(
        [
            "python3",
            script_dir + "/template.py",
            "src/" + project + "/compose.sidecar." + environment + ".goyaml",
            values_file_name
            + " "
            + specified_values_file_name
            + " "
            + mount_security_file_name,
            tmp_path + "/" + compose_sidecar_file_name,
            override_data_to_string(override_data),
        ]
    )
    p.wait()

    if p.returncode != 0:
        scriptutils.die("не удалось сгенерировать шаблон файла sidecar контейнеров")
else:
    f = open(tmp_path + "/" + compose_sidecar_file_name, "w")
    f.write("version: '3.8'")
    f.close()

# для dry run показываем конфигурацию и завершаем выполнение
if is_dry:
    print(scriptutils.cyan(tmp_path + "/" + compose_file_name))
    f = open(tmp_path + "/" + compose_file_name)
    # print(f.read())
    f.close()

    print(scriptutils.cyan(tmp_path + "/" + compose_override_file_name))
    f = open(tmp_path + "/" + compose_override_file_name)
    # print(f.read())
    f.close()

    for filename in temporary_file_list:
        print(scriptutils.cyan(filename))
        f = open(filename)
        # print(f.read())
        f.close()

    input("press enter to close...")
    exit(0)

# разворачиваем стак
os.chdir(tmp_path)
print(
    "Запускаю " + scriptutils.blue(project) + " в окружении " + scriptutils.cyan(values)
)
print("Название " + scriptutils.warning(stack_name))

p = Popen(
    [
        "docker",
        "stack",
        "deploy",
        "--with-registry-auth",
        "--resolve-image=always",
        "--compose-file",
        compose_file_name,
        "--compose-file",
        compose_override_file_name,
        "--compose-file",
        compose_sidecar_file_name,
        stack_name,
        "--prune",
    ]
)
p.wait()

if p.returncode != 0:
    scriptutils.die("не удалось развернуть проект")

# запускаем триггеры, которые нужно запустить после проекта
p = Popen(
    [
        "python3",
        script_dir + "/trigger.py",
        "-v",
        specified_values_file_name,
        "-p",
        project,
        "-t",
        "after",
    ]
)
p.wait()

# обновляем nginx
if project != "monolith":
    p = Popen(
        [
            "python3",
            script_dir + "/deploy_nginx.py",
            "-v",
            values,
            "-e",
            environment,
            "--data",
            json.dumps(args.data),
        ]
    )
    p.wait()
else:
    p = Popen(
        [
            "python3",
            script_dir + "/deploy_nginx_monolith.py",
            "-v",
            values,
            "-e",
            environment,
            "--data",
            json.dumps(args.data),
        ]
    )
    p.wait()

# если это домино - поднимаем поиск
if (args.project == "domino") and (environment not in ["local", "tes"]):
    p = Popen(
        [
            "python3",
            script_dir + "/deploy.py",
            "-v",
            values,
            "-e",
            environment,
            "-p",
            "search",
            "--project-name-override",
            label,
            "--data",
            json.dumps(args.data),
        ]
    )
    p.wait()
