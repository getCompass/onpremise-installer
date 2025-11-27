#!/usr/bin/env python3

import argparse, sys, yaml, glob, re, json

sys.dont_write_bytecode = True

import os
from datetime import datetime, timedelta
from typing import Dict

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils
from pathlib import Path

LOG_FILE_PREFIX_NAME = "/var/log/mysql_replication_lag"

# конфигурация
MAX_LAG = 5          # максимально допустимый лаг (сек)
HISTORY_WINDOW = 300 # анализировать только последние 300 сек
MIN_SAMPLES = 5      # минимальное количество записей

# статусы лага репликации
REPLICA_LAG_STATUS_OK = 0               # статус ок
REPLICA_LAG_STATUS_BEHIND_MASTER_OK = 1 # статус ок, реплика догоняет мастер
REPLICA_LAG_STATUS_NOT_EXIST_LOGS = 2   # отсутствуют данные по реплике
REPLICA_LAG_STATUS_PAUSE = 3            # реплика на паузе
REPLICA_LAG_STATUS_MORE_LOGS_BEHIND = 4 # реплика отстаёт от мастера

# ---АГРУМЕНТЫ СКРИПТА---#

parser = argparse.ArgumentParser(add_help=True)

parser.add_argument("-v", "--values", required=False, default="compass", type=str, help="название файла со значениями для деплоя")
parser.add_argument("--is-log-message", required=False, default=0, type=int, help="отобразить ли лог-сообщение")
parser.add_argument("--is-get-lag-count", required=False, default=0, type=int, help="получить значение лага репликации")
args = parser.parse_args()
values_name = args.values
is_log_message = bool(args.is_log_message == 1)
is_get_lag_count = bool(args.is_get_lag_count == 1)

script_dir = str(Path(__file__).parent.resolve())

# класс конфига пространства
class DbConfig:
    def __init__(self, domino_id: str, space_id: str, host: str, port: str, root_user: str, root_password: str) -> None:
        self.domino_id = domino_id
        self.space_id = space_id
        self.host = host
        self.port = port
        self.root_user = root_user
        self.root_password = root_password

def parse_log(space_id: int):
    """Читает и парсит лог-файл"""

    log_file_path = LOG_FILE_PREFIX_NAME + f"_{space_id}.log"
    if not os.path.exists(log_file_path):
        return [], None

    now = datetime.now()
    time_threshold = now - timedelta(seconds=HISTORY_WINDOW)
    valid_entries = []
    last_valid_lag = None

    with open(log_file_path, "r") as f:
        for line in f:
            try:
                timestamp_str, lag_str = line.strip().split(',')
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

                # пропускаем старые записи
                if timestamp < time_threshold:
                    continue

                # обработка значений лага
                if lag_str in ("None", "NULL"):
                    continue

                lag = int(lag_str)
                new_entry = (timestamp, lag)
                valid_entries.append(new_entry)
                last_valid_lag = lag

            except ValueError:
                continue

    return valid_entries, last_valid_lag

def analyze_replication(entries, last_lag):
    """Анализирует состояние репликации"""
    if not entries or len(entries) == 0:
        return REPLICA_LAG_STATUS_NOT_EXIST_LOGS, "Нет свежих данных в логе"

    lags = [lag for _, lag in entries]

    # проверка начальной синхронизации
    if last_lag != 0:
        is_decreasing = all(x > y for x, y in zip(lags, lags[1:]))
        if is_decreasing:
            return REPLICA_LAG_STATUS_BEHIND_MASTER_OK, f"Идет синхронизация (лаг уменьшается: {lags[0]} → {last_lag})"
        else:
            return REPLICA_LAG_STATUS_PAUSE, f"Синхронизация застряла на {last_lag} сек"

    # проверка рабочего состояния
    p95 = sorted(lags)[int(len(lags) * 0.95)]
    if p95 > MAX_LAG:
        return REPLICA_LAG_STATUS_MORE_LOGS_BEHIND, f"P95 лага {p95} > {MAX_LAG} сек"
    else:
        return REPLICA_LAG_STATUS_OK, f"Репликация в норме (P95: {p95}, текущий: {last_lag})"

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

# сформировать список конфигураций пространств
def get_space_dict(current_values: Dict) -> Dict[int, DbConfig]:
    # получаем название домино
    keys_list = list(current_values["projects"]["domino"].keys())
    domino = current_values["projects"]["domino"][keys_list[0]]
    space_config_dir = domino["company_config_dir"]
    domino_id = domino["label"]

    # формируем список пространств
    # пространства выбираются по наличию их конфига
    space_config_obj_dict = {}
    space_id_list = []
    for space_config in glob.glob("%s/*_company.json" % space_config_dir):

        s = re.search(r'([0-9]+)_company', space_config)

        if s is None:
            continue

        space_id = s.group(1)
        f = open(space_config, "r")
        space_config_dict = json.loads(f.read())
        f.close()
        if space_config_dict["status"] not in [1, 2]:
            continue

        # формируем объект конфигурации пространства
        space_config_obj = DbConfig(
            domino_id,
            int(space_id),
            space_config_dict["mysql"]["host"],
            space_config_dict["mysql"]["port"],
            "root",
            "root",
        )

        space_config_obj_dict[space_config_obj.space_id] = space_config_obj
        space_id_list.append(space_config_obj.space_id)
    return dict(sorted(space_config_obj_dict.items())), space_id_list

if __name__ == "__main__":

    # формируем список активных пространств
    current_values = get_values()
    space_config_obj_dict, space_id_list = get_space_dict(current_values)

    # добавляем проверку pivot лог-файла
    space_id_list.append(0)

    space_id_list.sort()
    replica_status = 0
    max_last_lag = 0
    for space_id in space_id_list:
        if is_log_message:
            print(f"Работаем с пространством {space_id}")
        entries, last_lag = parse_log(space_id)

        if last_lag != None and last_lag > max_last_lag:
            max_last_lag = last_lag

        print(space_id, entries, last_lag)
        status, message = analyze_replication(entries, last_lag)

        if is_log_message:
            print(message)

        if status == REPLICA_LAG_STATUS_PAUSE:
            replica_status = 1
            break
        elif status == REPLICA_LAG_STATUS_MORE_LOGS_BEHIND:
            replica_status = 2
        elif status == REPLICA_LAG_STATUS_NOT_EXIST_LOGS:
            replica_status = 3
            break

    if is_get_lag_count:
        print(max_last_lag)
    else:
        print(replica_status)