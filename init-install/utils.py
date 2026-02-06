from subprocess import Popen, PIPE
from typing import List, Tuple
import colors
import subprocess


def run_pipe_commands(command_list: List[List[str]]) -> Tuple[str, str]:
    """Запуск команд, соединенных в единый пайп"""
    process_list = []
    current_stdin = PIPE
    for command in command_list:
        process = Popen(command, stdin=current_stdin, stdout=PIPE)
        current_stdin = process.stdout
        process_list.append(process)

    return process.communicate()


def run(
    cmd, check=False, verbose=True, timeout: int = 600
) -> subprocess.CompletedProcess:
    """Запуск команды."""
    verbose and colors.print_info(f"[RUN] {cmd}")

    shell = False
    if isinstance(cmd, str):
        shell = True
    result = subprocess.run(
        cmd, shell=shell, capture_output=True, text=True, timeout=timeout
    )
    if check and result.returncode != 0:
        colors.print_warning(f"Команда завершилась с кодом {result.returncode}")
    return result


def get_os_dist() -> str:
    """Получить название дистрибутива системы"""

    os_id = run(". /etc/os-release && echo $ID", verbose=False).stdout
    return os_id.strip()


def get_os_based_dist_list() -> List[str]:
    """Получить название дистрибутивов системы, на котором основан текущий"""

    r = run(". /etc/os-release && echo $ID_LIKE", verbose=False)

    dist_id_str: str = r.stdout
    return list(map(lambda id: id.strip(), dist_id_str.split(" ")))


def get_dist_version(os_dist: str) -> str:
    """Получить версию дистрибутива системы"""

    version: str = ""
    if os_dist == "ubuntu":
        version = run(
            '. /etc/lsb-release && echo "$DISTRIB_CODENAME"', verbose=False
        ).stdout
    # другого варианта пока не вижу - в deb подобных дистрибутивах не получить pretty name версии, а репозиторий не кушает числовые версии
    elif os_dist == "debian":
        dist_version: int = int(
            run(
                "sed 's/\/.*//' /etc/debian_version | sed 's/\..*//'", verbose=False
            ).stdout
        )

        # если это действительно дебиан - забираем настоящее имя из VERSION_CODENAME
        if get_os_dist() == "debian":
            version = run(". /etc/os-release && echo $VERSION_CODENAME", verbose=False).stdout

        # если это debian like дистрибутив - ищем по версии
        if dist_version == 13:
            version = "trixie"
        elif dist_version == 12:
            version = "bookworm"
        elif dist_version == 11:
            version = "bullseye"
        elif dist_version == 10:
            version = "buster"
        elif dist_version == 9:
            version = "stretch"
        elif dist_version == 8:
            version = "jessie"
        else:
            version = dist_version
    else:
        version = run(". /etc/os-release && echo $VERSION_ID", verbose=False).stdout

    return version.strip()
