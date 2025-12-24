#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import os, yaml, shutil, json, string, secrets, random
import docker
from pathlib import Path
from time import sleep
import urllib.request
import requests
import argparse
import subprocess
import time


class bcolors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


__confirm_yes_key__ = "Y"

MONOLITH_MYSQL_TYPE = "monolith"
TEAM_MYSQL_TYPE = "team"


# проверить, что запустили из под рута
def assert_root():
    if os.geteuid() != 0:
        die("Скрипт необходимо запускать от рута", os.EX_OSERR)


# вывести предупреждение
def warning(text: str) -> str:
    return bcolors.WARNING + text + bcolors.ENDC


# вывести успешное сообщение
def success(text: str) -> str:
    return bcolors.OKGREEN + text + bcolors.ENDC


# вывести информационное сообщение
def blue(text: str) -> str:
    return bcolors.OKBLUE + text + bcolors.ENDC


# вывести информационное сообщение
def cyan(text: str) -> str:
    return bcolors.OKCYAN + text + bcolors.ENDC


# вывести окей и завершить выполнение
def ok(text: str):
    print(bcolors.OKGREEN + text + bcolors.ENDC)
    sys.exit(0)


# вывести текст с ошибкой
def error(text: str) -> str:
    return bcolors.FAIL + text + bcolors.ENDC


# вывести ошибку и завершить выполнение
def die(text: str, exit_code: int = 1):
    print(bcolors.FAIL + text + bcolors.ENDC)
    sys.exit(exit_code)


# ждать подтверждения
def confirm(text: str):
    input_str = input(text + " " + "[" + __confirm_yes_key__ + "/n]")

    if input_str == __confirm_yes_key__:
        return

    exit(os.EX_OK)


def get_os_type_by_package_manager():
    # сначала проверяем наличие dpkg
    if shutil.which("dpkg") is not None:
        return "deb"

    # если dpkg не найден, проверяем наличие rpm
    if shutil.which("rpm") is not None:
        return "rpm"

    # если не найдены ни dpkg, ни rpm, то отдаем по дефолту
    return "deb"


def get_os_type_by_os():
    os_release_file = "/etc/os-release"

    # проверяем наличие файла /etc/os-release
    if not os.path.exists(os_release_file):
        return get_os_type_by_package_manager()

    try:
        with open(os_release_file, "r") as file:
            id_like = None
            for line in file:
                line = line.strip()

                # ищем строку ID_LIKE
                if line.startswith("ID_LIKE="):
                    id_like = line.split("=")[1].strip('"')
                    break

            # если нашли ID_LIKE, проверяем на принадлежность к deb или rpm
            if id_like:
                if "debian" in id_like:
                    return "deb"
                elif any(rpm_like in id_like for rpm_like in ["rhel", "fedora", "suse"]):
                    return "rpm"

            # если не нашли ID_LIKE, проверим ID
            file.seek(0)  # перемещаемся в начало файла
            for line in file:
                line = line.strip()

                # ищем строку ID
                if line.startswith("ID="):
                    distro_id = line.split("=")[1].strip('"')
                    if distro_id in ["ubuntu", "debian"]:
                        return "deb"
                    elif distro_id in ["fedora", "centos", "rhel"]:
                        return "rpm"
    except Exception as e:
        return get_os_type_by_package_manager()

    return get_os_type_by_package_manager()


def is_rpm_os():
    if get_os_type_by_os() == "rpm":
        return True

    return False


# включена ли репликация
def is_replication_enabled(values_dict: dict):
    if values_dict.get("service_label") is not None and values_dict.get("service_label") != "":
        return True

    return False


# мастер сервер ли
def is_replication_master_server(values_dict: dict):
    if is_replication_enabled(values_dict) == False:
        return True

    if values_dict.get("service_label") is not None and values_dict.get("service_label") != "" and values_dict.get(
            "master_service_label") is not None and values_dict.get("master_service_label") != "":
        if values_dict.get("service_label") != values_dict.get("master_service_label"):
            return False
        else:
            return True

    return True


def merge(a: dict, b: dict, path=[]):
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge(a[key], b[key], path + [str(key)])
            elif a[key] != b[key]:
                a[key] = b[key]
        else:
            a[key] = b[key]
    return a


def find_container_mysql_container(client: docker.DockerClient, mysql_type: str, domino_id: str, port: int = 0):
    """
    Ищет контейнеры по правилам:
    1) monolith -> ищем единственный контейнер c 'mysql' и 'monolith' в имени
    2) team -> ищем все контейнеры c 'mysql' и '{domino_id}-company' в имени;
               берем последний созданный (по атрибуту Created)
    """
    timeout = 600
    n = 0
    while n <= timeout:

        all_containers = client.containers.list()
        mysql_type = mysql_type.lower()

        if mysql_type == "monolith":
            matching = [c for c in all_containers
                        if ("mysql" in c.name.lower() and
                            "monolith" in c.name.lower() and
                            c.attrs.get('State', {}).get('Health', {}).get('Status') == 'healthy')]
            if len(matching) == 0:
                error_text = "Не найден ни один контейнер (mysql + monolith)."
            if len(matching) > 1:
                error_text = "Найдено несколько контейнеров (mysql + monolith). Ожидался единственный."
            else:
                found_container = matching[0]
                break
        elif mysql_type == "team":
            matching = [c for c in all_containers
                        if (("%s-company_mysql-%s" % (domino_id, str(port))) in c.name.lower() and
                            c.attrs.get('State', {}).get('Status', {}) == 'running')]
            if len(matching) == 0:
                error_text = "Не найден ни один контейнер (mysql + %s-company)." % domino_id
            else:
                # сортируем по времени создания, берём последний (reverse=True)
                matching_sorted = sorted(matching,
                                         key=lambda x: x.attrs["Created"],
                                         reverse=True)
                found_container = matching_sorted[0]
                break
        else:
            error_text = f"Неизвестный тип: {mysql_type}. Поддерживается monolith или team."
        n = n + 5
        sleep(5)
        if n == timeout:
            die(error_text)

    return found_container


# получить данные окружение из security
def get_security(values_dict: dict) -> dict:
    security_file_path = Path("%s/security.yaml" % values_dict["root_mount_path"])

    if not security_file_path.exists():
        die("Не найден файл с ключами для деплоя. Окружение было ранее развернуто?")

    with security_file_path.open("r") as security_file:
        security = yaml.safe_load(security_file)
        security = {} if security is None else security

    if security.get("replication") is None or security["replication"].get("mysql_user") is None:
        die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return security


YC_META_URL = "http://169.254.169.254/computeMetadata/v1/instance/vendor/identity"
YC_REQ_HDRS = {"Metadata-Flavor": "Google"}


def _fetch_yc_metadata(url):
    req = urllib.request.Request(url, headers=YC_REQ_HDRS)
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read()


def get_yc_params():
    try:
        # получаем документ и подпись из metadata
        yc_identity_document = _fetch_yc_metadata(f"{YC_META_URL}/document").decode("utf-8").strip()
        yc_signature_b64 = _fetch_yc_metadata(f"{YC_META_URL}/base64").decode().strip()

        # экранируем значения для шелла
        yc_identity_document = yc_identity_document
        yc_identity_document_base64_signature = yc_signature_b64
    except Exception:
        yc_identity_document = ""
        yc_identity_document_base64_signature = ""

    return yc_identity_document, yc_identity_document_base64_signature


def is_yandex_cloud_marketplace_product() -> bool:
    allowed_product_ids = ["f2el70587r2edf5f4pt6"]
    if not allowed_product_ids:
        return False

    yc_identity_document, _ = get_yc_params()

    try:
        doc = json.loads(yc_identity_document)
        product_ids = doc.get("productIds", [])
        if not isinstance(product_ids, list):
            return False

        return any(pid in product_ids for pid in allowed_product_ids)

    except Exception:
        # если невалидный json — считаем проверку проваленной
        return False


# отправляем уведомление от лица бота
def send_userbot_notice(userbot_notice_token: str, userbot_notice_chat_id: str, userbot_notice_domain: str,
                        message_text: str):
    if userbot_notice_chat_id == "" or userbot_notice_token == "" or userbot_notice_domain == "":
        return

    userbot_version = "v3"
    url = f"https://{userbot_notice_domain}/userbot/api/{userbot_version}/group/send"

    json_data = {
        'group_id': userbot_notice_chat_id,
        'text': message_text,
        'type': 'text'
    }
    headers = {
        'Authorization': f'bearer={userbot_notice_token}'
    }

    try:
        response = requests.post(url, json=json_data, headers=headers)
    except requests.RequestException as e:
        print(warning(f"Userbot send failed: {e}"))


# Возвращает форму слова в зависимости от числа n
#
# form1 — форма для 1:            "приложение"
# form2 — форма для 2–4:          "приложения"
# form5 — форма для 5–0, 11–14:   "приложений"
#
# Примеры:
#     plural(1,  "приложение", "приложения", "приложений")    -> "приложение"
#     plural(2,  "приложение", "приложения", "приложений")    -> "приложения"
#     plural(5,  "приложение", "приложения", "приложений")    -> "приложений"
#     plural(21,  "приложение", "приложения", "приложений")   -> "приложение"
def plural(n: int, form1: str, form2: str, form5: str) -> str:
    n = abs(int(n))
    n100 = n % 100
    if 11 <= n100 <= 14:
        return form5
    n10 = n % 10
    if n10 == 1:
        return form1
    if 2 <= n10 <= 4:
        return form2
    return form5


# генерируем пароль длиной size, содержащий минимум:
# - 1 цифру
# - 1 строчную букву
# - 1 прописную букву
# - 1 спецсимвол
def generate_random_password(size: int) -> str:
    if size < 4:
        print(error("size должен быть >= 4, чтобы поместились все обязательные категории символов"))
        exit(1)

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    alnum = lower + upper + digits

    # берем спецсимволы без запрещенных
    _PROHIBITED_SYMBOLS = '"\'\\`$-={}|%@()#:'
    specials = string.punctuation.translate(str.maketrans('', '', _PROHIBITED_SYMBOLS))
    if not specials:
        print(error("после исключений не осталось допустимых спецсимволов"))
        exit(1)

    # гарантируем минимум по одному из каждой категории
    required = [
        secrets.choice(lower),
        secrets.choice(upper),
        secrets.choice(digits),
        secrets.choice(specials),
    ]

    # оставшиеся символы заполняем из общего пула
    all_chars = alnum + specials
    required += [secrets.choice(all_chars) for _ in range(size - len(required))]

    # перемешиваем (криптостойко)
    rng = random.SystemRandom()
    rng.shuffle(required)

    # гарантируем, что первый символ - буква или цифра
    if required[0] in specials:
        alnum_indices = [i for i, ch in enumerate(required) if ch in alnum]
        if not alnum_indices:  # теоретически не случится, но перестрахуемся
            print(error("не удалось подобрать первый символ из [a-zA-Z0-9]"))
            exit(1)
        j = rng.choice(alnum_indices)
        required[0], required[j] = required[j], required[0]

    return "".join(required)


# создает ArgumentParser с едиными настройками форматирования
def create_parser(description: str = None, add_help: bool = True, usage: str = None,
                  epilog: str = None) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        add_help=add_help,
        description=description,
        usage=usage,
        epilog=epilog,
        formatter_class=lambda prog: argparse.HelpFormatter(
            prog,
            max_help_position=100,
            width=600
        )
    )


def parse_destination(dst: str):
    # если строка содержит "user@host:/path" или "host:/path"
    # и не начинается с "/" (чтобы не спутать с локальным путём)
    if ":" in dst and not dst.startswith("/"):
        remote_host, remote_path = dst.split(":", 1)
        return True, remote_host, remote_path
    return False, None, dst


# проверяем права доступа у пользователя к удаленой директории
def check_remote_folder(dst: str):
    is_remote, remote_host, path = parse_destination(dst)

    if is_remote:
        # проверяем, что у пользователя есть права для записи в директорию
        # сначала проверяем, существует ли директория. Если нет, создаем ее.
        cmd = f'ssh {remote_host} "if [ ! -d {path} ]; then mkdir -p {path}; fi && test -w {path}"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

        if "ERROR" in result.stdout or result.returncode != 0:
            die(f"Ошибка: У пользователя нет доступа к удаленой директории {path}")
    else:
        # локальная директория
        if not os.path.exists(path):
            # создаем директорию, если ее нет
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                die(f"Не удалось создать локальную директорию {path}: {str(e)}")

        # проверяем право на запись
        if not os.path.exists(path):
            die(f"Локальная директория {path} не существует после попытки создания.")
        if not os.access(path, os.W_OK):
            die(f"Нет прав на запись в локальную директорию {path}")


# бэкапим базу данных
def backup_db(installer_dir: str, backups_folder: str = None, backup_name_format: str = None,
              threshold_percent: str = None, auto_cleaning_limit: str = None, userbot_notice_chat_id: str = None,
              userbot_notice_token: str = None, userbot_notice_domain: str = None, userbot_notice_text: str = None,
              need_backup_configs: int = 1, need_backup_spaces: int = 1, need_backup_monolith: int = 1,
              need_backup_space_id_list: str = None):
    # путь до скрипта
    script_path = "%s/script/backup_db.py" % (installer_dir)

    # формируем команду
    cmd = [
        "python3",
        script_path,
        "--need-backup-configs", str(need_backup_configs),
        "--need-backup-spaces", str(need_backup_spaces),
        "--need-backup-monolith", str(need_backup_monolith),
    ]

    if backups_folder:
        cmd.extend(["--backups-folder", backups_folder])
    if backup_name_format:
        cmd.extend(["--backup-name-format", backup_name_format])
    if threshold_percent:
        cmd.extend(["--free-threshold-percent", str(threshold_percent)])
    if auto_cleaning_limit:
        cmd.extend(["--auto-cleaning-limit", str(auto_cleaning_limit)])
    if userbot_notice_chat_id:
        cmd.extend(["--userbot-notice-chat-id", userbot_notice_chat_id])
    if userbot_notice_token:
        cmd.extend(["--userbot-notice-token", userbot_notice_token])
    if userbot_notice_domain:
        cmd.extend(["--userbot-notice-domain", userbot_notice_domain])
    if userbot_notice_text:
        cmd.extend(["--userbot-notice-text", userbot_notice_text])
    if need_backup_space_id_list:
        cmd.extend(["--need-backup-space-id-list", need_backup_space_id_list])

    # запускаем команду
    start_time = time.time()
    subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed_time = time.time() - start_time
    print(f"Создание резервной копии базы данных заняло: {elapsed_time:.2f} sec")


# функция для расчета размера директории
def get_directory_size(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)

            # пропускаем символические ссылки
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size


# отправляем резервную копию в указанное место
def transfer_data(values_dict: dict, dst: str, hostname: str, backups_folder: str = "", userbot_notice_text: str = None,
                  userbot_notice_token: str = None, userbot_notice_chat_id: str = None,
                  userbot_notice_domain: str = None, need_send_root_mount_path: bool = True):
    # директорию, которую копируем
    src = values_dict["root_mount_path"]
    src_dirs = []
    if need_send_root_mount_path:
        src_dirs = [values_dict["root_mount_path"]]

    # получим и выведем размер директории src для справки
    directory_size = get_directory_size(src)
    print(f"Размер директории с резервной копией {src}: {directory_size / (1024 * 1024):.2f} MB")

    if backups_folder != "":
        directory_size = get_directory_size(backups_folder)
        print(f"Размер директории с бэкапами баз данных {backups_folder}: {directory_size / (1024 * 1024):.2f} MB")
        src_dirs.append(backups_folder)

    # флаги rsync
    flags = "-avzu"

    # формируем команду
    cmd = ["rsync", flags, *src_dirs, dst]

    # запускаем команду
    try:

        start_time = time.time()
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # выводим в рилтайме лог выполнения
        while True:
            output = process.stdout.readline()
            if output == b'' and process.poll() is not None:
                break
            if output:
                print(output.strip().decode())

        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Отправка резервной копии заняла: {elapsed_time:.2f} sec")
    except subprocess.CalledProcessError as e:
        error_text = "Не удалось отправить резервную копию в указанное место!"
        print(error(error_text))
        print(e)
        print(e.stdout)
        print(e.stderr)
        message_text = f"*{hostname}*: {userbot_notice_text if userbot_notice_text.strip() else error_text}"
        send_userbot_notice(userbot_notice_token, userbot_notice_chat_id, userbot_notice_domain, message_text)
        die("Исправьте проблему и выполните скрипт снова")
