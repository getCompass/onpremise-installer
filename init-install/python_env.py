#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для создания виртуального окружения Python и установки пакетов.
"""

import subprocess
import sys
import shutil
from pathlib import Path
from typing import Tuple


def create_venv(venv_path: Path) -> bool:
    """
    Создает виртуальное окружение Python.
    
    Args:
        venv_path: Путь к директории виртуального окружения
    
    Returns:
        bool: True если успешно создано, False иначе
    """
    try:
        if venv_path.exists():
            print(f"[INFO] Виртуальное окружение уже существует: {venv_path}")
            return True

        python_bin = shutil.which("python3") or "/usr/bin/python3"
        result = subprocess.run(
            [python_bin, "-m", "venv", str(venv_path)],
            check=True,
            timeout=60,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"[INFO] Виртуальное окружение создано: {venv_path}")
        return True
    except subprocess.TimeoutExpired:
        print("[ERROR] Превышено время ожидания создания venv")
        return False
    except Exception as e:
        print(f"[ERROR] Ошибка создания venv: {e}")
        return False


def get_venv_python(venv_path: Path) -> Path:
    """
    Возвращает путь к интерпретатору Python в виртуальном окружении.
    
    Args:
        venv_path: Путь к директории виртуального окружения
    
    Returns:
        Path: Путь к python в venv
    """
    return venv_path / "bin" / "python"


def get_venv_pip(venv_path: Path) -> Path:
    """
    Возвращает путь к pip в виртуальном окружении.
    
    Args:
        venv_path: Путь к директории виртуального окружения
    
    Returns:
        Path: Путь к pip в venv
    """
    return venv_path / "bin" / "pip"


def install_python_packages(venv_path: Path, requirements_file: Path, 
                           additional_packages: list = None) -> Tuple[bool, str]:
    """
    Устанавливает Python-пакеты в виртуальное окружение.
    
    Args:
        venv_path: Путь к директории виртуального окружения
        requirements_file: Путь к файлу requirements.txt
        additional_packages: Дополнительные пакеты для установки
    
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    if not venv_path.exists():
        if not create_venv(venv_path):
            return False, "Не удалось создать виртуальное окружение"
    
    pip_bin = get_venv_pip(venv_path)
    
    # Обновляем pip
    try:
        subprocess.run(
            [str(pip_bin), "install", "--upgrade", "pip"],
            check=True,
            timeout=300,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
    except Exception as e:
        print(f"[WARN] Не удалось обновить pip: {e}")
    
    # Устанавливаем пакеты из requirements.txt
    if requirements_file.exists():
        try:
            result = subprocess.run(
                [str(pip_bin), "install", "-r", str(requirements_file)],
                check=False,
                timeout=600,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Неизвестная ошибка"
                return False, error_msg
        except subprocess.TimeoutExpired:
            return False, "Превышено время ожидания установки пакетов из requirements.txt"
        except Exception as e:
            return False, str(e)
    
    # Устанавливаем дополнительные пакеты
    if additional_packages:
        try:
            result = subprocess.run(
                [str(pip_bin), "install"] + additional_packages,
                check=False,
                timeout=300,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Неизвестная ошибка"
                return False, error_msg
        except subprocess.TimeoutExpired:
            return False, "Превышено время ожидания установки дополнительных пакетов"
        except Exception as e:
            return False, str(e)
    
    return True, ""

