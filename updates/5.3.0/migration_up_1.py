#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

from pathlib import Path
import os
import subprocess
import argparse

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

# конфигурация версий для фичи - Статус онлайн и контроль сессий
PLATFORM_FEATURES = {
    'Версия с включением функционала "Статус онлайн и контроль сессий"': {
        'ios': '1110540',
        'android': '100051701'
    },
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                        help='Название values файла окружения')
    parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                        help='Окружение, в котором развернут проект')
    args = parser.parse_args()

    scriptutils.assert_root()

    # зафиксированная фича
    feature_name = 'Версия с включением функционала "Статус онлайн и контроль сессий"'

    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script_path = os.path.join(base_dir, 'script', 'enable_force_update_announcement.py')

    for platform, version in PLATFORM_FEATURES[feature_name].items():
        print(f"Запуск анонса для платформы {platform} с версией {version}...")
        result = subprocess.run(
            ['python3', script_path,
             '-v', args.values,
             '-e', args.environment,
             '-p', platform,
             '-c', version],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(scriptutils.success(f"Анонс успешно создан для платформы {platform}!"))
        else:
            print(scriptutils.error(f"Ошибка при создании анонса для платформы {platform}:"))
            print(result.stderr)

if __name__ == "__main__":
    main()
