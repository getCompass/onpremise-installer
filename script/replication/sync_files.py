#!/usr/bin/env python3

# Скрипт выполняет синк файлов и директорий
# Для этого используется конфигурационный файл sync_files.yaml
# Может выполняться в любой момент, не влияет на работу приложения
# Для автономной работы необходимо добавить в качестве задачи крону

import subprocess
import logging
import sys
import os
import time
from datetime import datetime
from pathlib import Path
import argparse, yaml, uuid
import tempfile
import atexit

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, parent_dir)

from utils import scriptutils

# ---АРГУМЕНТЫ СКРИПТА---#
parser = scriptutils.create_parser(
    description="Скрипт для синхронизации файлов с активного сервера на резервный.",
    usage="python3 script/replication/sync_files.py [--vip VIP] [--debug] [--validate-only] [--skip-checks]",
    epilog="Пример: python3 script/replication/sync_files.py --vip 192.168.1.1 --debug --validate-only --skip-checks",
)

parser.add_argument("--vip", required=False, default="", type=str, help="Виртуальный ip (vip) сервера")
parser.add_argument("--debug", required=False, action="store_true", help="Запустить скрипт с выводом debug-меток в файл-лог синхронизации файлов")
parser.add_argument("--validate-only", required=False, action="store_true", help='Запуск скрипта в режиме read-only, без применения изменений')
parser.add_argument("--skip-checks", required=False, action="store_true", help="Нужно ли пропустить проверки для запуска синхронизации файлов")
args = parser.parse_args()

vip = args.vip
is_debug = args.debug
is_dry = args.validate_only
is_skip_checks = args.skip_checks

SYNC_FILES_PARAMS = "/etc/rsync-replication/sync_files.yaml"
SYNC_LOG_FILE = "/var/log/rsync-replication/rsync_files.log"
APP_FILES_CHANGE_LOG = "/etc/rsync-replication/app_files_rsync_changes.log" # также устанавливается в sync_files.yaml
FIND_APP_FILES_CWD = "/etc/rsync-replication"
SYNC_LOCK_DIR = "/etc/rsync-replication"
RSYNC_TEMP_DIR = "/var/lib/rsync/.rsync_temp"

# настройки логирования
logging.basicConfig(
    level=logging.DEBUG if is_debug else logging.INFO,
    format=f"%(asctime)s - %(levelname)s - [id {str(uuid.uuid4())[:4]}] - %(message)s",
    handlers=[
        logging.FileHandler(SYNC_LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


# класс для синхронизации файлов
class SyncFiles:
    def __init__(self, config_path=None):
        self.variables = {}
        self.sync_items = []
        self.default_excludes = []
        self.ssh_key = ""
        self.bw_limit = 30000
        self.app_files_change_log = Path(APP_FILES_CHANGE_LOG)
        self.app_files_tmp = Path(tempfile.gettempdir() + f"/app_files_{datetime.now().strftime('%Y%m%d_%H%M')}.txt")
        self.unallowable_source = ["/", "/home" , "/etc", "/var", "/usr", "/bin", "/sbin", "/root", "/boot", "/dev", "/proc", "/sys"]

        if config_path and os.path.exists(config_path):
            self.load_config(config_path)

    # получаем настройки из конфигурационного файла
    def load_config(self, config_path):
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            self.variables = config.get("variables", {})
            self.ssh_key = self.variables.get("ssh_key", self.ssh_key)
            self.bw_limit = self.variables.get("bw_limit", self.bw_limit)
            self.default_excludes = config.get("default_excludes", [])

            raw_sync_items = config.get("sync_items", [])
            self.sync_items = self.process_variables(raw_sync_items)
        except Exception as e:
            logger.error(f"Ошибка загрузки конфигурации: {e}")
            raise

    # обрабатываем переменные из конфига
    def process_variables(self, sync_items):
        processed_pairs = []
        # для каждой пары
        for pair in sync_items:
            processed_pair = {}
            for key, value in pair.items():
                if isinstance(value, str):
                    processed_value = value.format(**self.variables)
                    processed_pair[key] = processed_value
                elif isinstance(value, list):
                    # обрабатываем переменные если это список
                    processed_list = []
                    for item in value:
                        if isinstance(item, str):
                            processed_list.append(item.format(**self.variables))
                        else:
                            processed_list.append(item)
                    processed_pair[key] = processed_list
                else:
                    processed_pair[key] = value

            processed_pair["full_target"] = processed_pair.get("target", "")
            processed_pairs.append(processed_pair)
        return processed_pairs

    # выстраиваем команду для rsync с учётом параметров синхронизации
    def build_rsync_command(self, sync_config):
        source = sync_config["source"]
        target = sync_config["full_target"]
        sync_mode = sync_config.get("sync_mode", "default")

        base_cmd = [
            "rsync",
            "--archive",
            "--verbose",
            "--partial",
            "--mkpath",
            f"--temp-dir={RSYNC_TEMP_DIR}",
            "--rsync-path=sudo rsync",
            "--no-whole-file",
            "--delay-updates",
            f"--bwlimit={self.bw_limit}",
            "-e", f"ssh -l rider -i {self.ssh_key} -o StrictHostKeyChecking=no -o ConnectTimeout=10"
        ]

        # для файлов приложения ищем изменённые файлы
        if sync_config.get("name", "unknown") == "app_files":
            changed_files = self.find_changed_app_files(source)
            if len(changed_files) > 0:
                base_cmd.append(f"--files-from={str(self.app_files_tmp)}")
            else:
                return ""

        if sync_mode == "include_only":
            # режим "только указанные файлы"
            includes = sync_config.get("includes", [])
            for include in includes:
                base_cmd.append(f"--include={include}")
            base_cmd.append("--exclude=*")  # исключаем всё остальное

        elif sync_mode == "mixed":
            # mixed режим - сначала включаем нужное, потом отключаем всё
            includes = sync_config.get("includes", [])
            excludes = sync_config.get("excludes", [])
            for include in includes:
                base_cmd.append(f"--include={include}")
            for exclude in excludes:
                base_cmd.append(f"--exclude={exclude}")
            for exclude in self.default_excludes:
                base_cmd.append(f"--exclude={exclude}")

        else:
            # обычный режим - только исключения
            excludes = sync_config.get("excludes", [])
            for exclude in excludes:
                base_cmd.append(f"--exclude={exclude}")
            for exclude in self.default_excludes:
                base_cmd.append(f"--exclude={exclude}")
        base_cmd.extend([source, target])
        return base_cmd

    # выполняем синхронизацию для директории
    def sync_directory(self, sync_config):
        name = sync_config.get("name", "unknown")
        source = sync_config["source"]
        target = sync_config["full_target"]

        for unallowable in self.unallowable_source:
            if source == unallowable:
                logger.warning(f"Исходный путь {source} принадлежит к запрещенной для синка: {unallowable}")
                return False

        # для директорий добавляем "/" если тот не указан
        if sync_config.get("sync_type", "dir") != "file":
            source += "/" if not source.endswith("/") else ""
            sync_config["source"] = source
            target += "/" if not target.endswith("/") else ""
            sync_config["full_target"] = target

        logger.info(f"Начало синхронизации {name}: {source} -> {target}")

        # провярем существует ли исходная директория
        if not os.path.exists(source):
            logger.warning(f"Исходная директория не существует: {source}")
            return False

        # получаем команду для выполнения
        cmd = self.build_rsync_command(sync_config)
        if name == "app_files" and len(cmd) == 0:
            logger.info(f"Нет новых файлов для синка. Пропускаем.")
            self.cleanup_app_tmp_files()
            return True

        try:
            logger.debug(f"Команда для синка: {' '.join(cmd)}")
            if is_dry:
                logger.warning(f"DRY-RUN: Пропускаем действительный синк для {name}")
                return True

            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)

            start_time = time.time()
            last_log_time = start_time
            output_lines = []
            for line in process.stdout:
                output_lines.append(line.strip())
                current_time = time.time()
                if current_time - last_log_time >= 30:
                    elapsed = current_time - start_time
                    logger.info(f"RSYNC: всё ещё выполняется... ({elapsed:.0f} сек)")
                    last_log_time = current_time

            process.wait()
            output = "\n".join(output_lines)

            if process.returncode == 0:
                logger.info(f"Успешная синхронизация {name}")
                if name == "app_files":
                    self.update_change_log()
                    self.cleanup_app_tmp_files()
                return True
            else:
                logger.error(f"Ошибка синхронизации {name}. Код {process.returncode}")
                logger.error(f"Output: {output_lines}")
                if name == "app_files":
                    self.cleanup_app_tmp_files()
                if process:
                    process.kill()
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Таймаут синхронизации {name}")
            if name == "app_files":
                self.cleanup_app_tmp_files()
            return False
        except Exception as e:
            logger.error(f"Ошибка при синхронизации {name}: {e}")
            if name == "app_files":
                self.cleanup_app_tmp_files()
            return False

    # запуск синхронизации файлов и директории
    def run_sync(self):
        if not self.check_ssh():
            return

        total_count = len(self.sync_items)

        logger.info("=" * 40)
        logger.info(f"Начинаем синхронизацию")

        for i, sync_config in enumerate(self.sync_items, 1):
            if not is_master_server():
                logger.warning(f"Завершаем синхронизацию: сервер перестал быть мастером для vip {vip}")
                logger.info("=" * 40)
                return

            # проверки нужно ли игнорировать sync_lock
            sync_name = sync_config.get("name", "unknown")
            if not sync_config.get("ignore_lock", False):
                if sync_lock(sync_name, f"{SYNC_LOCK_DIR}/{sync_name}_sync_lock.pid"):
                    continue

            self.sync_directory(sync_config)

            if i < total_count:
                time.sleep(2)

        logger.info(f"Синхронизация завершена.")
        logger.info("=" * 40)

    # проверка ssh ключа
    def check_ssh(self):
        if not os.path.exists(self.ssh_key):
            logger.error(f"SSH ключ для rider не найден: {self.ssh_key}")
            return False
        return True

    # ищем изменённые файлы с последнего синка
    def find_changed_app_files(self, source):
        changed_files = []
        try:
            if self.app_files_change_log.exists():
                # поиск файлов новее change_log
                cmd = ["find", str(source), "-type", "f", "-newer", str(self.app_files_change_log)]
                mtime_str = datetime.fromtimestamp(self.app_files_change_log.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                logger.debug(f"Поиск app_files новее чем {mtime_str}, используем файл {str(self.app_files_change_log)}")
            else:
                # для первого запуска ищем все файлы
                cmd = ["find", str(source), "-type", "f"]
                logger.debug("Первый запуск для app_files - ищем все файлы")

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, cwd=FIND_APP_FILES_CWD)

            file_count = 0
            with open(self.app_files_tmp, "w") as output_file:
                for line in process.stdout:
                    file_path = line.strip()
                    if file_path:
                        try:
                            file_path = str(Path(file_path).relative_to(source))
                            changed_files.append(file_path)
                        except ValueError:
                            changed_files.append(file_path)
                        output_file.write(f"{file_path}\n")
                        file_count += 1
                        if file_count % 10000 == 0:
                            logger.debug(f"Обработано в find для app_files: {file_count} файлов...")
            process.wait(timeout=300)

            if process.returncode == 0:
                if file_count > 0:
                    logger.info(f"Нашли {file_count} изменённых файлов для синхронизации")
            else:
                logger.error(f"Ошибка find для app_files: код {process.returncode}, stderr: {process.stderr[:500]}")

            # если обновлённых файлов нет
            if not changed_files:
                self.cleanup_app_tmp_files()
                return []

            return changed_files

        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка поиска файлов для app_files: {e}")
            self.cleanup_app_tmp_files()
            return []
        except subprocess.TimeoutExpired:
            logger.error("Таймаут при завершении процесса find")
            self.cleanup_app_tmp_files()
            return []
        except Exception as e:
            logger.error(f"Неизвестная ошибка поиска файлов для app_files: {e}")
            self.cleanup_app_tmp_files()
            return []

    # получаем относительный пути для файлов
    def get_relative_paths(self, files, source):
        prepare_files = []
        for file_path in files:
            try:
                relative_path = Path(file_path).relative_to(source)
                prepare_files.append(str(relative_path))
            except ValueError as e:
                prepare_files.append(file_path)

        return prepare_files

    # сохраняем список найденных файлов
    def save_changed_files_list(self, app_files):
        try:
            with open(self.app_files_tmp, "w") as f:
                for file_path in app_files:
                    f.write(f"{file_path}\n")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении изменённых файлов для app_files: {e}")
            return False

    # обновляем временную метку последнего синка
    def update_change_log(self):
        try:
            self.app_files_change_log.parent.mkdir(parents=True, exist_ok=True)
            self.app_files_change_log.touch()
            logger.debug(f"Обновили change log для app_files: {self.app_files_change_log}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления change log для app_files: {e}")
            return False

    # очищаем временный файл для app_files
    def cleanup_app_tmp_files(self):
        try:
            if self.app_files_tmp.exists():
                self.app_files_tmp.unlink()
        except Exception as e:
            logger.warning(f"Ошибка при очистке временных файлов для app_files: {e}")

# проверяем блокировку синхронизации файлов
# на тот случай если предыдущий синк ещё не закончился
def sync_lock(sync_name, pidfile):
    lock_dir = os.path.dirname(pidfile)
    if not os.path.exists(lock_dir):
        os.makedirs(lock_dir, exist_ok=True)

    # проверяем существует ли pid процесса
    if os.path.exists(pidfile):
        try:
            with open(pidfile, "r") as f:
                old_pid = int(f.read().strip())

            # проверяем жив ли процесс
            try:
                os.kill(old_pid, 0)
                logger.debug(f"Синхронизация файлов {sync_name} уже запущена...")
                return True
            except OSError:
                os.remove(pidfile)
        except (ValueError, IOError):
            os.remove(pidfile)

    # создаём новый pid файл
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))

    # очищаем при выходе
    def cleanup():
        if os.path.exists(pidfile):
            os.remove(pidfile)

    atexit.register(cleanup)
    return False


# является ли сервер мастером
def is_master_server():
    if is_skip_checks:
        return True

    if len(vip) < 1:
        print("Отсутствует аргумент vip для скрипта! Синхронизация остановлена")
        return False

    # проверяем наличие vip на сервере
    ip_list = []
    try:
        result = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            print(f"Ошибка выполнения hostname -I: {result.stderr}", file=sys.stderr)
            return False

        ip_list = result.stdout.strip().split()
    except Exception as e:
        print(f"Ошибка получения список ip сервера: {e}", file=sys.stderr)
        return False

    if not vip in ip_list:
        print(f"Указанный vip {vip} отсутствует среди списка ip сервера")
        return False

    return True


# проверяем, что можем выполнить синк файлов
if is_master_server():
    try:
        SyncFiles(SYNC_FILES_PARAMS).run_sync()
    except Exception as e:
        logger.error(f"Ошибка: {e}")