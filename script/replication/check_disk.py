#!/usr/bin/python3

import argparse
import subprocess
import sys
import os
from datetime import datetime

# куда логируем состояние диска
LOG_FILE = "/var/log/keepalived_health.log"

SIMULATION_FAILURE_FLAG_FILE = "/tmp/simulate_keepalived_failure"

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=True)

parser.add_argument("--path", type=str, required=True, help="Путь к приложению или директории")
parser.add_argument("--threshold", type=int, default=5, help="Минимальный требуемый процент свободного места")
args = parser.parse_args()

dir_path = args.path
threshold = args.threshold

# получаем точку монтирования директории
def get_mount_point(path: str):
    try:
        real_path = os.path.realpath(path)
        result = subprocess.run(
            ["df", "--output=target", real_path],
            capture_output=True,
            text=True,
            check=True
        )
        lines = result.stdout.strip().split('\n')
        return lines[-1] if len(lines) > 1 else None
    except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
        print(f"[ERROR] Не удалось определить точку монтирования для {path}: {str(e)}", file=sys.stderr)
        log_error(f"Не удалось определить точку монтирования для {path}")
        return None

# проверяем диск
def check_disk_space(path: str, threshold: int = 10):

    mount_point = get_mount_point(path)
    if not mount_point:
        return False, 100  # при ошибке считаем диск переполненным

    try:
        result = subprocess.run(
            ["df", "--output=pcent", mount_point],
            capture_output=True,
            text=True,
            check=True
        )
        usage_line = result.stdout.strip().split('\n')[-1]
        used_percent = int(usage_line.strip().replace('%', ''))
        return (used_percent < (100 - threshold)), used_percent

    except (subprocess.CalledProcessError, ValueError, IndexError) as e:
        print(f"[ERROR] Ошибка проверки диска: {str(e)}", file=sys.stderr)
        log_error(f"Ошибка проверки диска: {str(e)}")
        return False, 100

# пишем в лог результат
def log_entry(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [DISK] {message}\n")

# пишем в лог ошибку при попытке проверить
def log_error(error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [ERROR] {error}\n")

# для симуляции падения
def simulate_failure():
    log_entry("Status: FAILED")
    sys.exit(1)

if __name__ == "__main__":

    is_ok, used = check_disk_space(dir_path, threshold)

    try:
        with open(SIMULATION_FAILURE_FLAG_FILE, "r") as f:
            failed_service = f.read().strip()
            if failed_service == "disk":
                log_entry(f"Status: CRITICAL (99.9% used)")
                sys.exit(1)
    except FileNotFoundError:
        pass

    if is_ok:
        log_entry(f"Status: OK ({used}% used)")
        sys.exit(0)
    else:
        log_entry(f"Status: CRITICAL ({used}% used)")
        sys.exit(1)