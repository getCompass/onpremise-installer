#!/usr/bin/python3
import subprocess
import sys
from datetime import datetime

# куда логируем состояние диска
LOG_FILE = "/var/log/keepalived_health.log"

SIMULATION_FAILURE_FLAG_FILE = "/tmp/simulate_keepalived_failure"

# максимальный процент использования
THRESHOLD = 3

# проверяем диск
def check_disk():
    try:
        df_output = subprocess.run(
            ["df", "--output=pcent", "/"],
            capture_output=True,
            text=True
        ).stdout.splitlines()[-1].strip()

        # получаем процент использоваения
        used_percent = int(df_output.replace('%', ''))
        return used_percent < (100 - THRESHOLD), used_percent
    except Exception as e:
        log_error(f"Disk check failed: {str(e)}")
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

    is_ok, used = check_disk()

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