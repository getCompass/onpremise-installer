#!/usr/bin/env python3

import sys, yaml, argparse

sys.dont_write_bytecode = True

from pathlib import Path
import shutil

current_script_path = Path(__file__).parent
utils_path = current_script_path.parent.parent / 'script'
sys.path.append(str(utils_path))

from utils import scriptutils

scriptutils.assert_root()
script_dir = str(Path(__file__).parent.resolve())

# ---АРГУМЕНТЫ СКРИПТА---#
parser = argparse.ArgumentParser()

parser.add_argument('-v', '--values', required=False, type=str, help='Название values файла окружения')
parser.add_argument('-e', '--environment', required=False, type=str, help='Окружение, в котором развернут проект')

args = parser.parse_args()
# ---КОНЕЦ АРГУМЕНТОВ СКРИПТА---#

YELLOW = '\033[93m'
BOLD = '\033[1m'
END = '\033[0m'

values_arg = args.values if args.values else ''
environment = args.environment if args.environment else ''
stack_name_prefix = environment + '-' + values_arg

values_file_path = Path('%s/../../src/values.%s.yaml' % (script_dir, values_arg))
if not values_file_path.exists():
    exit(0)

with values_file_path.open('r') as values_file:
    current_values = yaml.safe_load(values_file)
    current_values = {} if current_values is None else current_values

if not scriptutils.is_replication_enabled(current_values):
    exit(0)

if not scriptutils.is_replication_master_server(current_values):
    exit(0)

print(
    "\n".join([
        f"{YELLOW}!!!В этой версии релиза изменилась версия Manticore Search!!!",
        "Перед обновлением сервера необходимо выполнить шаги:",
        "1. На обоих серверах выполните обновление репозитория:",
        "   git pull",
        "",
        f"2. На {BOLD}неактивном{END} {YELLOW}сервере выполните остановку сервиса manticore:",
        "   sudo docker service scale production-compass-monolith-reserve_manticore-d1=0",
        "",
        f"3. На {BOLD}неактивном{END} {YELLOW}сервере удалите файлы, хранящие метаданные кластера manticore.",
        "   Получите значение поле root_mount_path, запустив из директории установщика:",
        "    root_mount_path=$(grep root_mount_path configs/global.yaml | grep -v '^#' | awk -F'\"' '{print $2}')",
        "    echo \"root_mount_path = $root_mount_path\"",
        "",
        "    Удалите файлы:",
        "    sudo rm -f \"$root_mount_path/manticore/d1_domino/manticore.json\" \"$root_mount_path/manticore/d1_domino/galera.cache\" \"$root_mount_path/manticore/d1_domino/grastate.dat\"",
        "",
        "4. Продолжите обновление сервера.",
        "",
        "---",
        "После обновления сервера:",
        f"5. На {BOLD}активном{END} {YELLOW}сервере создайте кластер manticore:",
        "   sudo python3 script/replication/start_manticore_replication.py --type master --need-update-company 1",
        "",
        f"6. На {BOLD}неактивном{END} {YELLOW}сервере выполните обновление приложения:",
        "   sudo python3 script/update.py",
        "",
        f"7. На {BOLD}неактивном{END} {YELLOW}сервере подключите ноду к кластеру в manticore:",
        "   sudo python3 script/replication/start_manticore_replication.py --type reserve --master-mysql-server-id 1",
        "",
        "Ссылка на инструкцию:",
        f"https://doc-onpremise.getcompass.ru/update.html#id28{END}",
        "",
    ])
)

try:
    if input("Предустановочные пункты 1-3 выполнены? Начать обновление? [Y/n]\n").lower() != "y":
        scriptutils.die("Обновление приложения было отменено")
except UnicodeDecodeError as e:
    print("Не смогли декодировать ответ. Error: ", e)
    exit(1)