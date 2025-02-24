#!/usr/bin/env python3
# pip3 install pyyaml pyopenssl docker mysql_connector_python python-dotenv psutil

# Скрипт выполняет задачу:
# Повесить анонс принудительного обновления

import sys
sys.dont_write_bytecode = True

import argparse, yaml, psutil
import docker
from utils import scriptutils
from time import sleep
import subprocess
import os

# Конфигурация версий и фич для каждой платформы
PLATFORM_FEATURES = {
    'Минимально поддерживаемая версия приложения': {
        'electron': '1000001',
        'ios': '1000001',
        'android': '1000001'
    },
    'Версия с функционалом "Поддержка авторизации файлов"': {
        'ios': '1103915',
        'android': '100051500'
    },
    'Версия с включением функционала "Статус онлайн и контроль сессий"': {
        'ios': '1110540',
        'android': '100051701'
    },
}

def print_menu(options):
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}")
    print("4. Завершить выполнение")

def select_feature():
    print("\nПожалуйста, выберите версию из списка ниже:")
    features = list(PLATFORM_FEATURES.keys())
    print_menu(features)
    
    try:
        feature_choice = int(input("\nВведите номер версии: "))
        if feature_choice == 0:
            sys.exit(0)
        if feature_choice < 0 or feature_choice > len(features):
            raise ValueError
    except ValueError:
        print(scriptutils.error("Ошибка: Некорректный выбор. Пожалуйста, выберите существующий номер."))
        sys.exit(1)
    
    feature_name = features[feature_choice - 1]
    return feature_name

def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('-v', '--values', required=False, default="compass", type=str, help='Название values файла окружения')
    parser.add_argument('-e', '--environment', required=False, default="production", type=str, help='Окружение, в котором развернут проект')
    args = parser.parse_args()

    scriptutils.assert_root()

    feature_name = select_feature()
    print(f"\nВы выбрали фичу: {feature_name}")

    confirm = input("\nВы хотите запустить enable_force_update_announcement.py для всех платформ? (y/n): ").strip().lower()
    
    if confirm == 'y':
        # Получаем текущий путь к директории скрипта
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        for platform, version in PLATFORM_FEATURES[feature_name].items():
            print(f"\nЗапуск для платформы {platform} с версией {version}...")
            # Используем правильный путь к скрипту
            script_path = os.path.join(script_dir, 'enable_force_update_announcement.py')
            result = subprocess.run(
                ['python3', script_path,  # Используем полный путь к скрипту
                 '-v', args.values, 
                 '-e', args.environment, 
                 '-p', platform, 
                 '-c', version],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(scriptutils.success(f"\nАнонс успешно создан для платформы {platform}!"))
            else:
                print(scriptutils.error(f"\nОшибка при создании анонса для платформы {platform}:"))
                print(result.stderr)
        
        print("\nПолезные команды для дальнейших действий:")
        print("- Просмотр активных анонсов:")
        print(f"  python3 script/show_announcement.py -v {args.values} -e {args.environment}")
        print("  Эта команда позволяет вам увидеть все активные анонсы в текущем окружении.")
        print("- Отключение анонса:")
        print(f"  python3 script/disable_announcement.py -v {args.values} -e {args.environment} --announcement-id <ID>")
        print("  Эта команда используется для отключения конкретного анонса, указав его ID.")
    else:
        print("\nОперация была отменена пользователем.")

if __name__ == "__main__":
    main()