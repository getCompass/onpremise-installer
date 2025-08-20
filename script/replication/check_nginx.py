#!/usr/bin/python3
import subprocess
import sys
from datetime import datetime

# куда логируем состояние nginx
LOG_FILE = "/var/log/keepalived_health.log"

SIMULATION_FAILURE_FLAG_FILE = "/tmp/simulate_keepalived_failure"

# проверяем состояние nginx
def check_nginx():
    try:
        # проверяем через systemd
        systemd_check = subprocess.run(
            ["systemctl", "is-active", "nginx"],
            capture_output=True,
            text=True
        ).stdout.strip() == "active"
        log_entry(f"is active nginx check: {systemd_check}")

        # через поиск процесса
        pgrep_check = subprocess.run(
            ["pgrep", "-x", "nginx"],
            stdout=subprocess.PIPE
        ).returncode == 0
        log_entry(f"pgrep nginx check: {pgrep_check}")

        return systemd_check and pgrep_check
    except Exception as e:
        log_error(f"Nginx check failed: {str(e)}")
        return False

# пишем в лог результат
def log_entry(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [NGINX] {message}\n")

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

    try:
        with open(SIMULATION_FAILURE_FLAG_FILE, "r") as f:
            failed_service = f.read().strip()
            if failed_service == "nginx":
                log_entry("Status: FAILED")
                sys.exit(1)
    except FileNotFoundError:
        pass

    # проверяем nginx
    if check_nginx():
        log_entry("Status: OK")
        sys.exit(0)
    else:
        log_entry("Status: FAILED")
        sys.exit(1)
