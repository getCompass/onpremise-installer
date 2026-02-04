#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для настройки системных лимитов и параметров ядра.
"""

import subprocess
import shutil
from pathlib import Path
from typing import Tuple


def get_current_systemd_limits() -> dict:
    """
    Получает текущие лимиты systemd.
    
    Returns:
        dict: Словарь с текущими лимитами
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", "--property", "DefaultLimitNOFILE,DefaultLimitNPROC"],
            capture_output=True,
            text=True,
            timeout=10
        )
        limits = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                limits[key] = value
        return limits
    except Exception:
        return {}


def get_current_threads_max() -> int:
    """
    Получает текущее значение kernel.threads-max.
    
    Returns:
        int: Текущее значение threads-max
    """
    try:
        with open("/proc/sys/kernel/threads-max", "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0


def get_current_docker_limits() -> dict:
    """
    Получает текущие лимиты Docker.
    
    Returns:
        dict: Словарь с текущими лимитами Docker
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", "docker"],
            capture_output=True,
            text=True,
            timeout=10
        )
        limits = {}
        for line in result.stdout.strip().split('\n'):
            if 'LimitNOFILE' in line or 'LimitNPROC' in line or 'TasksMax' in line:
                if '=' in line:
                    key, value = line.split('=', 1)
                    limits[key] = value
        return limits
    except Exception:
        return {}


def get_current_nginx_limits() -> dict:
    """
    Получает текущие лимиты Nginx.
    
    Returns:
        dict: Словарь с текущими лимитами Nginx
    """
    try:
        result = subprocess.run(
            ["systemctl", "show", "nginx", "--property", "MainPID"],
            capture_output=True,
            text=True,
            timeout=10
        )
        pid = None
        for line in result.stdout.strip().split('\n'):
            if 'MainPID=' in line:
                pid = line.split('=', 1)[1]
                break
        
        if not pid or pid == '0':
            return {}
        
        with open(f"/proc/{pid}/limits", "r") as f:
            limits = {}
            for line in f:
                if 'open files' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        limits['open_files'] = parts[3]
                elif 'processes' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        limits['processes'] = parts[3]
            return limits
    except Exception:
        return {}


def configure_systemd_limits() -> Tuple[bool, str]:
    """
    Настраивает лимиты systemd.
    
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    try:
        # Создаем каталог
        conf_dir = Path("/etc/systemd/system.conf.d")
        conf_dir.mkdir(parents=True, exist_ok=True)
        
        # Создаем файл конфигурации
        conf_file = conf_dir / "50-limits.conf"
        content = """[Manager]
DefaultLimitNOFILE=512000:1048576
DefaultLimitNPROC=65536:131072
"""
        with open(conf_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Перезапускаем systemd
        subprocess.run(
            ["systemctl", "daemon-reexec"],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки systemd лимитов"
    except Exception as e:
        return False, str(e)


def configure_kernel_threads_max() -> Tuple[bool, str]:
    """
    Настраивает kernel.threads-max.
    
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    try:
        # Создаем файл конфигурации
        conf_file = Path("/etc/sysctl.d/99-threads-max.conf")
        content = "kernel.threads-max = 200000\n"
        
        with open(conf_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Применяем параметры
        subprocess.run(
            ["sysctl", "--system"],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки kernel.threads-max"
    except Exception as e:
        return False, str(e)


def configure_docker_limits() -> Tuple[bool, str]:
    """
    Настраивает лимиты Docker.
    
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    try:
        # Создаем каталог для systemd override
        service_dir = Path("/etc/systemd/system/docker.service.d")
        service_dir.mkdir(parents=True, exist_ok=True)
        
        # Создаем файл с лимитами systemd
        limits_file = service_dir / "limits.conf"
        content = """[Service]
LimitNOFILE=infinity
LimitNPROC=infinity
TasksMax=infinity
"""
        with open(limits_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Обновляем конфигурацию systemd
        subprocess.run(
            ["systemctl", "daemon-reload"],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        # Настраиваем daemon.json
        docker_dir = Path("/etc/docker")
        docker_dir.mkdir(parents=True, exist_ok=True)
        
        daemon_json = docker_dir / "daemon.json"
        content_json = """{
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 1048576,
      "Soft": 512000
    },
    "nproc": {
      "Name": "nproc",
      "Hard": 65536,
      "Soft": 32768
    }
  }
}
"""
        with open(daemon_json, "w", encoding="utf-8") as f:
            f.write(content_json)
        
        # Перезапускаем Docker
        subprocess.run(
            ["systemctl", "restart", "docker"],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки Docker лимитов"
    except Exception as e:
        return False, str(e)


def configure_nginx_limits() -> Tuple[bool, str]:
    """
    Настраивает лимиты Nginx.
    
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    try:
        # Создаем каталог
        service_dir = Path("/etc/systemd/system/nginx.service.d")
        service_dir.mkdir(parents=True, exist_ok=True)
        
        # Создаем файл с лимитами
        limits_file = service_dir / "limits.conf"
        content = """[Service]
LimitNOFILE=1048576
LimitNPROC=131072
"""
        with open(limits_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Обновляем конфигурацию systemd
        subprocess.run(
            ["systemctl", "daemon-reload"],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        # Перезапускаем Nginx
        subprocess.run(
            ["systemctl", "restart", "nginx"],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE
        )
        
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "Превышено время ожидания настройки Nginx лимитов"
    except Exception as e:
        return False, str(e)


def configure_all_limits() -> Tuple[bool, str]:
    """
    Настраивает все лимиты системы.
    
    Returns:
        Tuple[bool, str]: (успех, сообщение об ошибке)
    """
    # Systemd лимиты
    success, error = configure_systemd_limits()
    if not success:
        return False, f"Ошибка настройки systemd лимитов: {error}"
    
    # Kernel threads-max
    success, error = configure_kernel_threads_max()
    if not success:
        return False, f"Ошибка настройки kernel.threads-max: {error}"
    
    # Docker лимиты (если Docker установлен)
    if shutil.which("docker"):
        success, error = configure_docker_limits()
        if not success:
            return False, f"Ошибка настройки Docker лимитов: {error}"
    
    # Nginx лимиты (если Nginx установлен)
    if shutil.which("nginx"):
        success, error = configure_nginx_limits()
        if not success:
            return False, f"Ошибка настройки Nginx лимитов: {error}"
    
    return True, ""

