#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import os


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
