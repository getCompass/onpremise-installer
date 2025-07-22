#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import os, shutil


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
