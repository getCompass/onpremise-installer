#!/usr/bin/env python3

import subprocess
import sys
import os

SIMULATION_FAILURE_FLAG_FILE = "/tmp/simulate_keepalived_failure"

def check_vip(vip):
    try:
        # Проверяем наличие VIP на интерфейсах
        result = subprocess.run(['ip', 'a'], stdout=subprocess.PIPE, text=True)
        return 1 if vip in result.stdout else 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: check_keepalived.py <VIP>")
        sys.exit(1)

if os.getenv(SIMULATION_FAILURE_FLAG_FILE) != None:
    print(0)
    sys.exit(0)

vip = sys.argv[1]
print(check_vip(vip))