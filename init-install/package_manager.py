#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для проверки и установки системных пакетов.
"""

import subprocess
import utils
import shutil

from typing import List, Tuple

# Список необходимых пакетов для DEB систем
DEB_PACKAGES = [
    "nginx",
    "git",
    "ca-certificates",
    "curl",
    # docker-* ставим отдельным шагом по официальной инструкции
    "python3-pip",
    "cron",
    # "nodejs" ставим отдельным шагом
]

# Список необходимых пакетов для RPM систем
RPM_PACKAGES = [
    "nginx",
    "git",
    "ca-certificates",
    "curl",
    # docker-* ставим отдельным шагом по официальной инструкции
    "python3-pip",
    "cronie",
    # "nodejs" ставим отдельным шагом
]

VIRTUALENV_PACKAGE_NAME = "python3-venv"


def _run(
    cmd: List[str], timeout: int = 300, check: bool = False
) -> subprocess.CompletedProcess:
    """
    Безопасный runner команд.
    """
    return subprocess.run(
        cmd,
        check=check,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def check_package_installed(package: str, package_manager: str) -> bool:
    """
    Проверяет, установлен ли пакет в системе.

    Args:
        package: Название пакета
        package_manager: Тип пакетного менеджера ('rpm' или 'deb')

    Returns:
        bool: True если пакет установлен, False иначе
    """
    try:
        if package_manager == "deb":
            # Используем dpkg-query для более точной проверки
            # Он возвращает код 0 только если пакет установлен
            result = subprocess.run(
                ["dpkg-query", "-W", "-f", "${Status}", package],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Пакет установлен, если команда успешна и статус содержит "install ok installed"
            if result.returncode == 0:
                status = result.stdout.strip()
                return "install ok installed" in status
            return False
        else:  # rpm
            result = subprocess.run(
                ["rpm", "-q", package], capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_missing_packages(package_manager: str) -> List[str]:
    """
    Получает список отсутствующих пакетов.
    """
    packages = DEB_PACKAGES if package_manager == "deb" else RPM_PACKAGES

    missing = []
    for package in packages:
        if not check_package_installed(package, package_manager):
            missing.append(package)

    # В centos 9 пакет идет вместо с python3, а при попытке поставить отдельно - выдает ошибку об отсутствующей зависимости
    if not _check_venv_installed():
        missing.append(VIRTUALENV_PACKAGE_NAME)

    return missing


def _check_venv_installed() -> bool:
    """
    Проверяем, что venv установлен
    """
    result = subprocess.run(
        ["python3", "-m", "venv", "/tmp/venv"], capture_output=True, text=True
    )
    if result.returncode == 0:
        shutil.rmtree("/tmp/venv")
        return True
    
    return False


def install_packages(packages: List[str], package_manager: str) -> Tuple[bool, str]:
    """
    Устанавливает пакеты в системе.

    ВАЖНО:
    - docker-* пакеты ставим не из дефолтных репозиториев, а по официальной инструкции Docker.
    """
    if not packages:
        return True, ""

    try:
        regular_packages = packages

        if package_manager == "deb":
            # Исправляем прерванную установку dpkg, если есть
            # Это нужно делать перед любыми операциями с пакетами
            dpkg_check = subprocess.run(
                ["dpkg", "--configure", "-a"],
                check=False,
                timeout=300,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Обновляем список пакетов
            update_result = subprocess.run(
                ["apt-get", "update"],
                check=False,
                timeout=300,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if update_result.returncode != 0:
                # Если обновление не удалось из-за проблем с dpkg, пробуем еще раз исправить
                if (
                    "dpkg was interrupted" in update_result.stderr
                    or "dpkg was interrupted" in update_result.stdout
                ):
                    subprocess.run(
                        ["dpkg", "--configure", "-a"],
                        check=False,
                        timeout=300,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    # Пробуем обновить еще раз
                    update_result = subprocess.run(
                        ["apt-get", "update"],
                        check=False,
                        timeout=300,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                if update_result.returncode != 0:
                    return (
                        False,
                        f"Не удалось обновить список пакетов: {update_result.stderr or update_result.stdout}",
                    )

            # 1) Ставим обычные пакеты
            if regular_packages:
                cmd = ["apt-get", "install", "-y"] + regular_packages
                result = subprocess.run(
                    cmd,
                    check=False,
                    timeout=1800,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    return False, result.stderr or result.stdout or "Неизвестная ошибка"

            return True, ""

        else:  # rpm
            # Выбираем yum/dnf
            has_yum = (
                subprocess.run(
                    ["bash", "-lc", "command -v yum >/dev/null 2>&1"]
                ).returncode
                == 0
            )
            pm = "yum" if has_yum else "dnf"

            # 1) Обычные пакеты
            if regular_packages:
                cmd = [pm, "install", "-y"] + regular_packages
                result = subprocess.run(
                    cmd,
                    check=False,
                    timeout=1800,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if result.returncode != 0:
                    return False, result.stderr or result.stdout or "Неизвестная ошибка"

            return True, ""

    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания установки пакетов"
    except Exception as e:
        return False, str(e)


def get_documentation_url(package_manager: str) -> str:
    """
    Возвращает URL документации для ручной установки пакетов.
    """
    if package_manager == "deb":
        return "https://doc-onpremise.getcompass.ru/preparation.html"
    else:
        return "https://doc-onpremise.getcompass.ru/preparation-rpm.html"
