#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import os, yaml, shutil, json
import docker
from pathlib import Path
from time import sleep
import urllib.request

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

    if values_dict.get("service_label") is not None and values_dict.get("service_label") != "" and values_dict.get("master_service_label") is not None and values_dict.get("master_service_label") != "":
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

def find_container_mysql_container(client: docker.DockerClient, mysql_type: str, domino_id: str, port :int = 0):
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
                            "monolith" in c.name.lower())]
            if len(matching) == 0:
                error_text = "Не найден ни один контейнер (mysql + monolith)."
            if len(matching) > 1:
                error_text = "Найдено несколько контейнеров (mysql + monolith). Ожидался единственный."
            else:
                found_pivot_container = matching[0]
                break
        elif mysql_type == "team":
            matching = [c for c in all_containers
                        if (("%s-company_mysql-%s" % (domino_id, str(port))) in c.name.lower())]
            if len(matching) == 0:
                error_text = "Не найден ни один контейнер (mysql + %s-company)." % domino_id
            else:
                # сортируем по времени создания, берём последний (reverse=True)
                matching_sorted = sorted(matching,
                                         key=lambda x: x.attrs["Created"],
                                         reverse=True)
                found_pivot_container = matching_sorted[0]
                break
        else:
            error_text = f"Неизвестный тип: {mysql_type}. Поддерживается monolith или team."
        n = n + 5
        sleep(5)
        if n == timeout:
            die(error_text)
    sleep(15) # подождём немного чтобы контейнер полностью поднялся

    return found_pivot_container

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

    allowed_product_ids = []
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
