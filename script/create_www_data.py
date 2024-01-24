#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import pwd, getpass
from subprocess import Popen, PIPE
from loader import Loader

from utils import scriptutils

exec_user_name = "www-data"
exec_user_uid = 33

# проверяем, что запустили от рута
scriptutils.assert_root()


def add_user(name: str, uid: int):
    password = getpass.getpass("Введите пароль для пользователя %s: " % (name))

    # запускаем процесс
    p = Popen(["groupadd", "-g", str(uid), name], stdout=PIPE, stderr=PIPE)
    p.wait()

    if p.returncode != 0:
        print(scriptutils.error(p.stdout.read().decode()))
        print(scriptutils.error(p.stdout.read().decode()))
        exit(1)

    p = Popen(
        ["useradd", "-M", "-u", str(uid), "-g", name, "-p", password, name],
        stdout=PIPE,
        stderr=PIPE,
    )
    p.wait()

    if p.returncode != 0:
        print(scriptutils.error(p.stdout.read().decode()))
        print(scriptutils.error(p.stdout.read().decode()))
        exit(1)

    print(scriptutils.success("Пользователь www-data создан"))


def create_user_dialog(name: str, uid: int):
    try:
        user = pwd.getpwnam(exec_user_name)

        if user.pw_uid == uid:
            print(
                scriptutils.success("Пользователь %s уже существует в системе" % (name))
            )
            return

        confirm = input(
            "Пользователь %s существует в системе, но имеет неправильный uid (%i). Пересоздать пользователя?[y/N]\n"
            % (name, user.pw_uid)
        )

        if confirm != "y":
            return
        add_user(name, uid)
    except KeyError:
        add_user(name, uid)


create_user_dialog(exec_user_name, exec_user_uid)
