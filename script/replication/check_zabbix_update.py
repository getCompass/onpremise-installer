#!/usr/bin/env python3

import os, sys, re
from pathlib import Path

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils

script_dir = str(Path(__file__).parent.resolve())

parser = scriptutils.create_parser(
    description="Скрипт проверки обновлений zabbix-скриптов.",
    usage="python3 script/replication/check_zabbix_update.py [--init-version]",
    epilog="Пример: python3 script/replication/check_zabbix_update.py --init-version",
)
parser.add_argument("--init-version", required=False, action="store_true")
args = parser.parse_args()

init_version = args.init_version

CHANGELOG_PATH = f"{script_dir}/zabbix/CHANGELOG.md"
VERSION_PATH = f"{script_dir}/zabbix/.version"

EXIST_UPDATES_MESSAGE = (
    "Найдены изменения zabbix-скриптов для мониторинга отказоустойчивости.\n"
    "Если у вас настроен мониторинг - выполните действия ниже."
)

def get_next_version():
    """Проверяет обновления и выводит информацию"""

    is_exist_version = Path(VERSION_PATH).exists()

    # читаем текущую версию
    if is_exist_version:
        with open(VERSION_PATH, 'r') as f:
            current_version = f.read().strip()
    else:
        current_version = None

    # читаем changelog
    if not Path(CHANGELOG_PATH).exists():
        print("Ошибка проверки обновления zabbix-скриптов: Файл CHANGELOG.md не найден")
        return

    with open(CHANGELOG_PATH, 'r') as f:
        content = f.read()

    # находим все версии (формат: ## [v1] - 2023-04-16)
    versions = re.findall(r'^## \[([^\]]+)\] - (\d{4}-\d{2}-\d{2})', content, re.MULTILINE)

    if not versions:
        print("Ошибка проверки обновления zabbix-скриптов: В changelog не найдено версий")
        return

    # если файл .version отсутствует
    if not is_exist_version:
        # если не требуется инициализация - просто записываем версию
        if not init_version:
            latest_version = versions[0][0]
            with open(VERSION_PATH, 'w') as f:
                f.write(latest_version + '\n')
            return

        # показываем все версии от последней до v1
        versions_to_show = versions[::-1]  # разворачиваем от v1 до последней
        print("-" * 60)
        print(scriptutils.cyan(EXIST_UPDATES_MESSAGE))
        print()
    else:
        # есть файл .version - ищем индекс текущей версии
        current_index = None
        for i, (ver, date) in enumerate(versions):
            if ver == current_version:
                current_index = i
                break

        if current_index is None:
            # текущая версия не найдена в changelog - выводим все версии
            versions_to_show = versions[::-1]
            print("-" * 60)
            print(scriptutils.cyan(EXIST_UPDATES_MESSAGE))
            print()
        elif current_index == 0:
            # текущая версия - последняя, обновлений нет
            return
        else:
            # показываем только новые версии (которые идут после текущей)
            versions_to_show = versions[:current_index][::-1]  # от v1 до версии перед текущей
            print("-" * 60)
            print(scriptutils.cyan(EXIST_UPDATES_MESSAGE))
            print()

    # выводим версии
    for ver, date in versions_to_show:
        print(f"Версия: {ver}")
        print(f"Дата: {date}")
        print()

        # извлекаем содержимое версии
        pattern = rf'## \[{re.escape(ver)}\] - {date}\n(.*?)(?=## \[|$)'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            body = match.group(1).strip()
            body = re.sub(r'^### ', '', body, flags=re.MULTILINE)
            print(body)
            print()

        print("-" * 60)
        print()

    # обновляем .version на последнюю версию
    if not is_exist_version or (is_exist_version and current_version != versions[0][0]):
        latest_version = versions[0][0]
        with open(VERSION_PATH, 'w') as f:
            f.write(latest_version + '\n')


if __name__ == "__main__":
    get_next_version()