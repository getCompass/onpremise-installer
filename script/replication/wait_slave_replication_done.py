#!/usr/bin/env python3

import sys

sys.dont_write_bytecode = True

import yaml, sys, os, time, re
import docker
from typing import Dict, List

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path

scriptutils.assert_root()

# ---АРГУМЕНТЫ СКРИПТА---#

parser = scriptutils.create_parser(
    description="Скрипт для ожидания, пока завершится репликация mysql-изменений с master сервера.",
    usage="python3 script/replication/wait_slave_replication_done.py [-v VALUES] [-e ENVIRONMENT] [--type monolith|team] [--container-id CONTAINER_ID]",
    epilog="Пример: python3 script/replication/wait_slave_replication_done.py -v compass -e production --type monolith --container-id 83Jsh3isjPqj",
)
parser.add_argument('-v', '--values', required=False, default="compass", type=str,
                    help='Название values файла окружения (например: compass)')
parser.add_argument('-e', '--environment', required=False, default="production", type=str,
                    help='Окружение, в котором развернут проект (например: production)')
parser.add_argument(
    "-t", "--type", required=False, default="monolith", type=str,
    help="На каком типе mysql запускаем (monolith или team)",
    choices=["monolith", "team"]
)
parser.add_argument("-cid", "--container-id", required=False, default=False, type=str,
                    help="ID проверяемого mysql контейнера")

args = parser.parse_args()
values_name = args.values
mysql_type = args.type.lower()
container_id = args.container_id

script_dir = str(Path(__file__).parent.resolve())


# получить данные окружение из values
def get_values() -> Dict:
    default_values_file_path = Path("%s/../../src/values.yaml" % (script_dir))
    values_file_path = Path("%s/../../src/values.%s.yaml" % (script_dir, values_name))

    if not values_file_path.exists():
        scriptutils.die("Не найден файл со значениями для деплоя. Окружение было ранее развернуто?")

    with values_file_path.open("r") as values_file:
        current_values = yaml.safe_load(values_file)
        current_values = {} if current_values is None else current_values

    with default_values_file_path.open("r") as values_file:
        default_values = yaml.safe_load(values_file)
        default_values = {} if default_values is None else default_values

    current_values = scriptutils.merge(default_values, current_values)

    if current_values.get("projects") is None or current_values["projects"].get("domino") is None:
        scriptutils.die("Файл со значениями невалиден. Окружение было ранее развернуто?")

    return current_values


def parse_last_numbers(gtid_str: str) -> List[int]:
    if not gtid_str:
        return []

    numbers = []
    # Разбиваем по запятой: 'UUID:1-10, UUID:5-20' -> ['UUID:1-10', 'UUID:5-20']
    parts = [p.strip() for p in gtid_str.split(',') if p.strip()]

    for part in parts:
        # Ищем число после последнего двоеточия или дефиса
        # r'[: -](\d+)$' — ищет цифры в самом конце фрагмента
        match = re.search(r'[: -](\d+)$', part)
        if match:
            numbers.append(int(match.group(1)))

    return numbers


def compare_gtid_sets(retrieved: str, executed: str) -> bool:
    """
    проверяем по условию:
      - Нужно, чтобы самое большое "последнее число" из Executed
        совпало с хотя бы одним из "последних чисел" в Retrieved.
      - Если max(e_nums) присутствует в r_nums => True.
    """
    if not retrieved or not executed:
        return False

    r_nums = parse_last_numbers(retrieved)  # Список чисел из Retrieved
    e_nums = parse_last_numbers(executed)  # Список чисел из Executed

    # Если мы ничего не ждем (Retrieved пуст), а SQL/IO запущены — значит мы догнали мастер
    if not r_nums:
        return True

    if not r_nums or not e_nums:
        return False

    return max(e_nums) >= max(r_nums)


# Универсальный паттерн для захвата многострочных полей GTID
def extract_gtid_field(field_name, text):
    # Ищем название поля, затем захватываем всё до тех пор,
    # пока не встретим "\n пробелы Другое_Поле:" или конец текста
    pattern = rf"{field_name}:\s*(.*?)(?=\n\s*[A-Za-z_]+:|$)"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        # Важно: убираем переносы строк и лишние пробелы ВНУТРИ найденного блока
        return re.sub(r'\s+', ' ', match.group(1)).strip()
    return ""


def wait_for_replication(mysql_container, mysql_user, mysql_pass):
    timeout = 60 * 30  # 30 минут
    interval = 5
    max_tries = timeout // interval
    cmd = f"mysql -h localhost -u {mysql_user} -p{mysql_pass} -e \"SHOW SLAVE STATUS\\G\""

    for attempt in range(max_tries):

        try:
            result = mysql_container.exec_run(cmd)
        except docker.errors.NotFound:
            return
        except Exception as e:
            print(f"[{attempt + 1}/{max_tries}] не смогли получить статус репликации для компании, ждём...")
            time.sleep(interval)
            continue

        if result.exit_code != 0:
            print(
                f"[{attempt + 1}/{max_tries}] ошибка при получении статуса репликации, код {result.exit_code}, ждём...")
            time.sleep(interval)
            continue

        output = result.output.decode("utf-8", errors="ignore")

        # Многострочный парсинг Retrieved_Gtid_Set
        retrieved_gtid = extract_gtid_field("Retrieved_Gtid_Set", output)

        # Многострочный парсинг Executed_Gtid_Set
        executed_gtid = extract_gtid_field("Executed_Gtid_Set", output)

        # Узнаём статусы IO/SQL
        match_io = re.search(r"Slave_IO_Running:\s+(\S+)", output)
        match_sql = re.search(r"Slave_SQL_Running:\s+(\S+)", output)

        if not match_io or not match_sql:
            print(f"[{attempt + 1}/{max_tries}] Не нашли Slave_IO_Running/Slave_SQL_Running, ждём...")
            time.sleep(interval)
            continue

        slave_io = match_io.group(1)
        slave_sql = match_sql.group(1)

        if slave_io == "Yes" and slave_sql == "Yes" and compare_gtid_sets(retrieved_gtid, executed_gtid):
            return
        else:
            print(f"[{attempt + 1}/{max_tries}] Репликация не завершена (IO={slave_io}, SQL={slave_sql})")
            print(f"Состояние репликации: Retrieved_Gtid_Set={retrieved_gtid}, Executed_Gtid_Set={executed_gtid}")
            time.sleep(interval)

    # если цикл истёк, значит таймаут
    scriptutils.die("Не дождались завершения репликации за 30 минут.")


def start():
    # получаем значения для выбранного окружения
    current_values = get_values()

    client = docker.from_env()
    mysql_container = client.containers.get(container_id)

    if mysql_type == "team":
        mysql_user = "root"
        mysql_pass = "root"
    else:
        mysql_user = current_values["projects"]["monolith"]["service"]["mysql"]["user"]
        mysql_pass = current_values["projects"]["monolith"]["service"]["mysql"]["password"]

    # запускаем функцию ожидания
    wait_for_replication(mysql_container, mysql_user, mysql_pass)


# точка входа в скрипт
start()
