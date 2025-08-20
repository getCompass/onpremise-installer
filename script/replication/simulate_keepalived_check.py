#!/usr/bin/python3
import subprocess
import sys
from pathlib import Path

SIMULATION_FAILURE_FLAG_FILE = "/tmp/simulate_keepalived_failure"

# ---АГРУМЕНТЫ СКРИПТА---#
simulate_type = sys.argv[1]
check_name = sys.argv[2] if len(sys.argv) > 2 else ""

def simulate_failed(service):
    try:
        with open(SIMULATION_FAILURE_FLAG_FILE, "w") as f:
            f.write(service)
    except OSError as e:
        if e.errno == errno.EACCES:
            print("Ошибка: Нет прав на запись в /tmp/")
        else:
            print(f"Неизвестная ошибка: {e}")
    except Exception as e:
            print(f"Ошибка: {e}")

def simulate_clean():
    Path(SIMULATION_FAILURE_FLAG_FILE).unlink(missing_ok=True)

# если передан тип симуляции = падения
if simulate_type == "simulate-failure":
    # проверяем nginx
    if check_name == "nginx":
        simulate_failed("nginx")
    # проверяем свободное место
    elif check_name == "disk":
        simulate_failed("disk")
    else:
        print("Incorrect argument \"check_name\"")
elif simulate_type == "clean":
    simulate_clean()
else:
    print("Incorrect argument \"simulate_type\"")