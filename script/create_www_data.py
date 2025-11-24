#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import pwd, getpass, argparse
from subprocess import Popen, PIPE

from utils import scriptutils

parser = argparse.ArgumentParser(add_help=True)

parser.add_argument("--validate-only", required=False, action="store_true")
parser.add_argument("--installer-output", required=False, action="store_true")
args = parser.parse_args()
validate_only = args.validate_only
installer_output = args.installer_output

QUIET = (validate_only and installer_output)

def log(*args, **kwargs):
    if not QUIET:
        print(*args, **kwargs)

exec_user_name = "www-data"
exec_user_uid = 33

# проверяем, что запустили от рута
scriptutils.assert_root()

def add_user(name: str, uid: int):

    # запускаем процесс
    if scriptutils.is_rpm_os():
        p = Popen(["groupadd", name], stdout=PIPE, stderr=PIPE)
    else:
        p = Popen(["groupadd", "-g", str(uid), name], stdout=PIPE, stderr=PIPE)
    p.wait()

    if p.returncode != 0:
        log(scriptutils.error(p.stdout.read().decode()))
        log(scriptutils.error(p.stdout.read().decode()))
        exit(1)

    if scriptutils.is_rpm_os():
        p = Popen(
            ["useradd", "-u", str(uid), "-r", "-s", "/usr/sbin/nologin", "-d", "/var/www", "-g", name, name],
            stdout=PIPE,
            stderr=PIPE,
        )
    else:
        password = getpass.getpass("Введите пароль для пользователя %s: " % name)
        p = Popen(
            ["useradd", "-M", "-u", str(uid), "-g", name, "-p", password, name],
            stdout=PIPE,
            stderr=PIPE,
        )
    p.wait()

    if p.returncode != 0:
        log(scriptutils.error(p.stdout.read().decode()))
        log(scriptutils.error(p.stdout.read().decode()))
        exit(1)

    log(scriptutils.success("Пользователь www-data создан"))


def create_user_dialog(name: str, uid: int):
    try:
        user = pwd.getpwnam(exec_user_name)

        if user.pw_uid == uid:
            log(
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
