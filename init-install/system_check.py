#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для определения типа системы и её характеристик.
"""

import subprocess
import shutil
from pathlib import Path


def detect_package_manager() -> None:
    """
    Определяет тип пакетного менеджера системы (rpm или deb).
    
    Returns:
        str: 'rpm' или 'deb' в зависимости от типа системы
    """
    # Проверяем наличие rpm
    if shutil.which("rpm"):
        try:
            result = subprocess.run(
                ["rpm", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return "rpm"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    
    # Проверяем наличие dpkg
    if shutil.which("dpkg"):
        try:
            result = subprocess.run(
                ["dpkg", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return "deb"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
    
    # Проверяем наличие файлов в системе
    if Path("/etc/redhat-release").exists() or Path("/etc/centos-release").exists():
        return "rpm"
    
    if Path("/etc/debian_version").exists():
        return "deb"
    
    raise RuntimeError("Не удалось определить тип системы (rpm/deb)")


def check_python_version() -> None:
    """
    Проверяет версию Python (должна быть 3.8+).
    
    Returns:
        tuple: (успех, версия_мажор, версия_минор)
    """
    import sys
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        return False, version.major, version.minor
    return True, version.major, version.minor


def get_system_info() -> None:
    """
    Получает информацию о системе.
    
    Returns:
        dict: Словарь с информацией о системе
    """
    package_manager = detect_package_manager()
    
    # Проверяем версию Python
    python_ok, py_major, py_minor = check_python_version()
    
    info = {
        "package_manager": package_manager,
        "is_rpm": package_manager == "rpm",
        "is_deb": package_manager == "deb",
        "python_version_ok": python_ok,
        "python_major": py_major,
        "python_minor": py_minor
    }
    
    # Пытаемся определить дистрибутив
    try:
        if Path("/etc/os-release").exists():
            with open("/etc/os-release", "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("ID="):
                        info["distro_id"] = line.split("=", 1)[1].strip().strip('"')
                    elif line.startswith("VERSION_ID="):
                        info["version_id"] = line.split("=", 1)[1].strip().strip('"')
    except Exception:
        pass
    
    return info

