#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import shutil
import time
import argparse
import socket
from pathlib import Path
from textwrap import dedent
import re
import yaml
from typing import Union, List, Tuple
import utils
import readline

# Импортируем новые модули
import system_check
import package_manager
import python_env
import firewall_manager
import nodejs_manager
import docker_manager
import system_limits
import colors

PYTHON_PACKAGES = [
    "pyyaml~=6.0.1",
    "pyopenssl~=24.0.0",
    "docker~=7.1.0",
    "mysql_connector_python~=8.2.0",
    "python-dotenv~=1.0.0",
    "psutil~=5.9.6",
    "pycryptodome~=3.21.0",
    "requests",
]

INSTALLER_GIT_URL = "https://github.com/getCompass/onpremise-installer.git"
# ---------- утилиты ----------


def write_file(path: Path, content: str, mode=0o644, exist_ok=True) -> None:
    """Записывает файл с указанными правами."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not exist_ok:
        raise FileExistsError(str(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(path, mode)
    print(colors.Colors.info(f"[WRITE] {path} (mode {oct(mode)})"))


def backup(path: Path) -> None:
    """Создает резервную копию файла."""
    if path.exists():
        b = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
        shutil.copy2(path, b)
        print(colors.Colors.info(f"[BACKUP] {path} -> {b}"))


def require_root():
    """Проверяет, что скрипт запущен от root."""
    if os.geteuid() != 0:
        print(colors.Colors.error("Этот скрипт нужно запускать с правами root (sudo)"))
        sys.exit(1)


def get_server_ip() -> str:
    """
    Получает реальный IP адрес сервера.

    Returns:
        str: IP адрес сервера или 'localhost'
    """
    try:
        # Пытаемся подключиться к внешнему адресу для определения IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            # Альтернативный способ через hostname
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and ip != "127.0.0.1":
                return ip
        except Exception:
            pass
    return "localhost"


def ask_user(prompt: str, default: bool = False, confirm_all: bool = False) -> bool:
    """
    Запрашивает подтверждение у пользователя.

    Args:
        prompt: Текст запроса
        default: Значение по умолчанию
        confirm_all: Если True, автоматически соглашаться

    Returns:
        bool: Ответ пользователя
    """
    if confirm_all:
        print(colors.Colors.info(f"{prompt} [автоматически: да]"))
        return True

    default_text = "Y/n" if default else "y/N"
    colored_prompt = colors.Colors.highlight(f"{prompt} [{default_text}]: ")
    response = input(colored_prompt).strip().lower()

    if not response:
        return default

    return response in ("y", "yes", "да", "д")


# ---------- вспомогательные функции для образов ----------


def _load_values_yaml(paths: list) -> dict:
    """Загружает values.yaml (первый найденный). Возвращает dict (может быть пустым)."""
    for p in paths:
        if p and p.exists():
            with open(p, "r", encoding="utf-8") as f:
                try:
                    return yaml.safe_load(f) or {}
                except Exception as e:
                    print(f"[WARN] Не удалось распарсить {p}: {e}")
                    return {}
    return {}


def _get_by_dotted_path(data: dict, dotted: str) -> Union[dict, None]:
    """Берет значение по пути вида '.projects.monolith.service.go_event.tag'. Возвращает None если чего-то не хватает."""
    if not dotted:
        return None
    path = dotted.strip()
    if path.startswith("."):
        path = path[1:]
    cur = data
    for key in path.split("."):
        if key == "":
            continue
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


_TPL_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _render_placeholders(
    s: str, values_dict: dict, local_vars: Union[dict, None] = None
) -> str:
    """Подставляет {{...}} из values.yaml."""

    def repl(m):
        expr = m.group(1).strip()
        expr = expr.split("|", 1)[0].strip()
        if expr.startswith("$"):
            path = expr[1:]
            root, *rest = path.split(".")
            base = (local_vars or {}).get(root)
            if base is None:
                return m.group(0)
            cur = base
            for key in rest:
                if not key:
                    continue
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    return m.group(0)
            return str(cur)
        val = _get_by_dotted_path(values_dict, expr)
        return str(val) if val is not None else m.group(0)

    return _TPL_RE.sub(repl, s)


def _extract_images_from_file(path: Path) -> List[str]:
    """Достает строки image: ... из *.goyaml."""
    images = []
    if not path.exists():
        return images
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\s*image\s*:\s*(.+?)\s*$", line)
            if not m:
                continue
            raw = m.group(1).strip()
            if (raw.startswith('"') and raw.endswith('"')) or (
                raw.startswith("'") and raw.endswith("'")
            ):
                raw = raw[1:-1]
            images.append(raw)
    return images


def _start_bg_pull(image: str) -> None:
    """Запускает docker image pull в фоне (без ожидания завершения)."""
    cmd = f"docker image pull {image} >/var/log/compass-image-pull.log 2>&1 &"
    print(f"[BACKGROUND-IMAGE-PULL] {image}")
    subprocess.Popen(cmd, shell=True)


def _build_local_vars(values_dict: dict) -> dict:
    """Эмулирует поведение из go_template: $file_node := index .projects.file .file_node_id; $domino := index .projects.domino .domino_id."""
    locals_map = {}
    projects_file = _get_by_dotted_path(values_dict, ".projects.file") or {}
    projects_domino = _get_by_dotted_path(values_dict, ".projects.domino") or {}
    file_node_id = _get_by_dotted_path(values_dict, ".file_node_id")
    domino_id = _get_by_dotted_path(values_dict, ".domino_id")
    if isinstance(projects_file, dict) and file_node_id in projects_file:
        locals_map["file_node"] = projects_file[file_node_id]
    if isinstance(projects_domino, dict) and domino_id in projects_domino:
        locals_map["domino"] = projects_domino[domino_id]
    return locals_map


# ---------- основные функции установки ----------


def collect_packages_confirmation(
    package_manager_type: str, confirm_all: bool = False
) -> Tuple[bool, List[str]]:
    """
    Собирает подтверждение на установку пакетов.

    Returns:
        tuple[bool, list]: (подтверждено, список отсутствующих пакетов)
    """
    missing = package_manager.get_missing_packages(package_manager_type)

    if not missing:
        colors.print_info("Все необходимые пакеты установлены.")
        return True, []

    colors.print_info(f"Отсутствуют следующие пакеты ({len(missing)}):")
    for pkg in missing:
        print(f"  - {pkg}")

    doc_url = package_manager.get_documentation_url(package_manager_type)

    if not ask_user(
        "\nУстановить отсутствующие пакеты автоматически?",
        default=True,
        confirm_all=confirm_all,
    ):
        colors.print_info(f"Для ручной установки следуйте инструкциям:")
        print(f"{doc_url}")
        return False, []

    return True, missing


def execute_packages_installation(missing: list, package_manager_type: str) -> bool:
    """
    Выполняет установку пакетов.
    """
    if not missing:
        return True

    colors.print_info("Устанавливаю пакеты...")
    success, error = package_manager.install_packages(missing, package_manager_type)

    if not success:
        colors.print_error(f"\nОшибка установки пакетов: {error}")
        doc_url = package_manager.get_documentation_url(package_manager_type)
        colors.print_info(f"Для ручной установки следуйте инструкциям:")
        print(f"{doc_url}")
        return False

    colors.print_success("Пакеты успешно установлены.")
    return True


def setup_system_packages(package_manager_type: str, confirm_all: bool = False) -> bool:
    """
    Проверяет и устанавливает системные пакеты.
    """
    colors.print_step("\n[ШАГ 1] Проверка системных пакетов...")

    confirmed, missing = collect_packages_confirmation(
        package_manager_type, confirm_all
    )
    if not confirmed:
        return False

    return execute_packages_installation(missing, package_manager_type)


def collect_python_confirmation(
    venv_path: Path, requirements_file: Path, confirm_all: bool = False
) -> bool:
    """
    Собирает подтверждение на настройку Python окружения.
    """

    if venv_path.exists():
        colors.print_info(f"Виртуальное окружение уже существует: {venv_path}")
    else:
        colors.print_info(f"Будет создано виртуальное окружение: {venv_path}")

    # Не проверяем requirements.txt на этом этапе, так как репозиторий еще не клонированvenv_path
    # Файл будет установлен после клонирования репозитория
    colors.print_info(f"Будет установлен requirements.txt: {requirements_file}")

    # Дополнительные пакеты для установщика
    colors.print_info(
        f"Будет установлено {len(PYTHON_PACKAGES)} дополнительных пакетов"
    )

    if not ask_user(
        "Создать виртуальное окружение и установить Python-пакеты?",
        default=True,
        confirm_all=confirm_all,
    ):
        colors.print_info("Пропущена настройка Python окружения.")
        return False

    return True


def execute_python_setup(venv_path: Path, requirements_file: Path) -> bool:
    """
    Выполняет настройку Python окружения.
    """
    success, error = python_env.install_python_packages(
        venv_path, requirements_file, PYTHON_PACKAGES
    )

    if not success:
        colors.print_error(f"Ошибка установки Python-пакетов: {error}")
        return False

    colors.print_success("Python окружение настроено.")
    return True


def setup_python_environment(
    venv_path: Path, requirements_file: Path, confirm_all: bool = False
) -> bool:
    """
    Создает venv и устанавливает Python-пакеты.
    """
    colors.print_step("\n[ШАГ 2] Настройка Python окружения...")

    if not collect_python_confirmation(venv_path, requirements_file, confirm_all):
        return False

    return execute_python_setup(venv_path, requirements_file)


def collect_nodejs_confirmation(confirm_all: bool = False) -> Tuple[bool, str]:
    """
    Собирает подтверждение на настройку Nodejs окружения.
    """

    if nodejs_manager.check_nodejs_installed():
        colors.print_info("Найден установленный Node.js")
        return True, ""

    nodejs_version = "v22.0.0"

    if not ask_user(
        f"\nУстановить Node.js?",
        default=True,
        confirm_all=confirm_all,
    ):
        return False, ""

    return True, nodejs_version


def execute_nodejs_setup(package_manager: str, version: str) -> bool:
    """
    Выполняет настройку Nodejs окружения.
    """

    if nodejs_manager.check_nodejs_installed():
        return True
    success, error = nodejs_manager.install_node_js(package_manager, version)

    if not success:
        colors.print_error(f"Ошибка установки Node.js {version}: {error}")
        return False

    colors.print_success("Nodejs установлен.")
    return True


def collect_docker_confirmation(confirm_all: bool = False) -> bool:
    """
    Собирает подтверждение на настройку Docker окружения.
    """

    if docker_manager.check_docker_installed():
        colors.print_info("Найден установленный Docker")
        return True

    if not ask_user(
        f"\nУстановить Docker?",
        default=True,
        confirm_all=confirm_all,
    ):
        return False

    return True


def execute_docker_setup(package_manager: str) -> bool:
    """
    Выполняет настройку Docker окружения.
    """

    if docker_manager.check_docker_installed():
        docker_manager.enable_docker()
        return True
    success, error = docker_manager.install_docker(package_manager)

    if not success:
        colors.print_error(f"Ошибка установки Docker: {error}")
        return False

    colors.print_success("Docker установлен.")
    return True


def collect_firewall_confirmation(confirm_all: bool = False) -> Tuple[bool, bool]:
    """
    Собирает подтверждение на настройку фаервола.

    Returns:
        tuple[bool, bool]: (подтверждено, продолжать_без_настройки)
    """
    firewall_type = firewall_manager.detect_firewall()

    if not firewall_type:
        colors.print_warning(
            "Не найден доступный фаервол (firewalld/nftables/iptables)"
        )
        colors.print_warning("Продолжаю без настройки фаервола...")
        return False, True

    colors.print_info(f"Обнаружен фаервол: {firewall_type}")

    # Выводим описание правил, которые будут применены
    rules_description = firewall_manager.get_firewall_rules_description(
        firewall_manager.get_listening_ssh_ports()
    )
    colors.print_info("Будут применены следующие правила фаервола:")
    print(rules_description)

    doc_url = firewall_manager.get_documentation_url()

    if not ask_user(
        f"Настроить фаервол ({firewall_type}) с указанными правилами?",
        default=True,
        confirm_all=confirm_all,
    ):
        colors.print_info(f"\nДля ручной настройки фаервола следуйте инструкциям:")
        print(f"{doc_url}")

        if not ask_user(
            "Продолжить установку без настройки фаервола?",
            default=True,
            confirm_all=confirm_all,
        ):
            colors.print_info("Установка прервана пользователем.")
            return False, False

        return False, True

    return True, True


def execute_firewall_setup() -> bool:
    """
    Выполняет настройку фаервола.
    """
    firewall_type = firewall_manager.detect_firewall()
    colors.print_info(f"Настраиваю фаервол ({firewall_type})...")

    success, error = firewall_manager.configure_firewall()

    if not success:
        colors.print_error(f"\nОшибка настройки фаервола: {error}")
        doc_url = firewall_manager.get_documentation_url()
        colors.print_info(f"Для ручной настройки следуйте инструкциям:")
        print(f"{doc_url}")
        return False

    colors.print_success("Фаервол настроен.")
    return True


def collect_limits_confirmation(confirm_all: bool = False) -> bool:
    """
    Собирает подтверждение на настройку системных лимитов.
    """
    colors.print_info("Будут настроены следующие системные лимиты и параметры ядра:")

    limits_description = """
1. Systemd лимиты (/etc/systemd/system.conf.d/50-limits.conf):
   - DefaultLimitNOFILE=512000:1048576
   - DefaultLimitNPROC=65536:131072
   - Будет выполнен: systemctl daemon-reexec

2. Kernel параметры (/etc/sysctl.d/99-threads-max.conf):
   - kernel.threads-max = 200000
   - Будет выполнен: sysctl --system

3. Docker лимиты:
   - /etc/systemd/system/docker.service.d/limits.conf:
     * LimitNOFILE=infinity
     * LimitNPROC=infinity
     * TasksMax=infinity
   - /etc/docker/daemon.json:
     * nofile: Hard=1048576, Soft=512000
     * nproc: Hard=65536, Soft=32768
   - Будет выполнен: systemctl daemon-reload && systemctl restart docker

4. Nginx лимиты:
   - /etc/systemd/system/nginx.service.d/limits.conf:
     * LimitNOFILE=1048576
     * LimitNPROC=131072
   - Будет выполнен: systemctl daemon-reload && systemctl restart nginx
"""
    print(limits_description)

    if not ask_user(
        "Применить указанные лимиты и параметры ядра?",
        default=True,
        confirm_all=confirm_all,
    ):
        colors.print_info("Настройка лимитов пропущена.")
        return False

    return True


def execute_limits_setup() -> bool:
    """
    Выполняет настройку системных лимитов.
    """
    colors.print_info("Настраиваю системные лимиты и параметры ядра...")

    success, error = system_limits.configure_all_limits()

    if not success:
        colors.print_error(f"\nОшибка настройки лимитов: {error}")
        return False

    colors.print_success("Системные лимиты настроены.")
    return True


def setup_firewall(confirm_all: bool = False) -> bool:
    """
    Настраивает фаервол.
    """

    confirmed, continue_without = collect_firewall_confirmation(confirm_all)

    if not continue_without:
        return False

    if not confirmed:
        return True  # Пропускаем настройку, но продолжаем

    return execute_firewall_setup()


def perform_installation(
    base_dir: Path,
    installer_dir: Path,
    webinstaller_dir: Path,
    venv_path: Path,
    package_manager_type: str,
    confirm_all: bool = False,
) -> None:
    """
    Выполняет основную установку приложения.
    """

    front_dist = webinstaller_dir / "frontend" / "dist"
    backend_req = webinstaller_dir / "backend" / "requirements.txt"
    python_bin = python_env.get_venv_python(venv_path)

    # Клонируем/обновляем репозиторий
    if not installer_dir.exists():
        colors.print_info(f"[GIT] Клонирую репозиторий в {installer_dir} ...")
        utils.run(f"git clone {INSTALLER_GIT_URL} '{installer_dir}'")
    else:
        colors.print_info(f"[GIT] Папка {installer_dir} уже существует, обновляю ...")
        utils.run(f"git -C '{installer_dir}' fetch --all --prune || true")
        utils.run(f"git -C '{installer_dir}' pull || true")

    # Настраиваем nginx
    nginx_conf = Path("/etc/nginx/nginx.conf")
    backup(nginx_conf)

    # В разных дистрибутивах разный пользователь - ищем его в текущем конфиге
    nginx_user = "www-data"
    with open(nginx_conf, "r") as f:

        prefix = "user "
        while True:
            line = f.readline()
            if line.startswith(prefix):
                nginx_user = line[len(prefix) :].strip("\n;")
                break

            if not line:
                break

    nginx_conf_content = (
        dedent(
            """\
        user %s;

        # ставим равным кол-ву ядер
        worker_processes auto;
        worker_shutdown_timeout 12h;
        pid /run/nginx.pid;

        # core
        worker_rlimit_nofile 512000;
        timer_resolution 100ms;
        worker_priority -5;

        events {
        	worker_connections 63152;
        	worker_aio_requests 512;
        	multi_accept on;
        	use epoll;
        }

        http {

        	log_format access_log_default_format '$request_time $upstream_response_time "$host" "$server_name" $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" "$gzip_ratio"';

        	#######################################################
        	# Common
        	#######################################################

        	# говорим браузеру что у нас только https
        	add_header Strict-Transport-Security "max-age=15768000" always;

        	# уязвимость 206 Partial Content
        	proxy_set_header Range "";
        	proxy_set_header Request-Range "";

        	aio threads;
        	server_tokens off; # отключаем показ версии nginx
        	sendfile on; # оставляем включенным в любом случае

        	# отправка заголовков одним пакетом
        	tcp_nopush on;
        	tcp_nodelay on;

        	# keepalive соединения клиент -> сервер
        	keepalive_timeout 120s;
        	keepalive_requests 300;

        	# сброс соединения с тупящими клиентами
        	reset_timedout_connection on;

        	# таймауты
        	client_header_timeout 10s; # заголовок запроса
        	client_body_timeout 10s; # тело запроса
        	send_timeout 35s; # чтение ответа

        	# разрешаем продолжение загрузки
        	max_ranges 2;

        	# буферы
        	client_body_buffer_size 1M; # максимальный размер буфера для хранения тела запроса клиента
        	client_header_buffer_size 1M; # максимальный размер буфера для хранения заголовков запроса клиента
        	large_client_header_buffers 2 1M; # количество и размер буферов для чтения большого заголовка запроса клиента

        	# максимальный размер тела запроса
        	# нужен для больших POST запросов
        	client_max_body_size 30m;

        	# максимальный размер хэш таблицы для mime типов файлов
        	types_hash_max_size 2048;

        	# кэширование директив server_name
        	server_names_hash_bucket_size 128;
        	server_names_hash_max_size 1024;

        	include /etc/nginx/mime.types;
        	default_type application/octet-stream;

        	# resolver
        	resolver 127.0.0.1 ipv6=off;

        	#######################################################
        	# SSL
        	#######################################################

        	ssl_protocols TLSv1.2 TLSv1.3;
        	ssl_ciphers kEECDH+AES128:kEECDH:kEDH:-3DES:kRSA+AES128:kEDH+3DES:DES-CBC3-SHA:!RC4:!aNULL:!eNULL:!MD5:!EXPORT:!LOW:!SEED:!CAMELLIA:!IDEA:!PSK:!SRP:!SSLv2:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305;
        	ssl_prefer_server_ciphers off;
        	ssl_session_cache shared:SSL:300m;
        	ssl_session_timeout 1h;

        	#######################################################
        	# logs
        	#######################################################

        	access_log /var/log/nginx/access.log access_log_default_format buffer=4096k; #buffer=256k;
        	error_log /var/log/nginx/error.log;

        	#######################################################
        	# gzip
        	#######################################################

        	gzip on;
        	gzip_static on;
        	gzip_http_version 1.0;
        	gzip_proxied any;
        	gzip_vary on;
        	gzip_disable "msie6";

        	gzip_min_length 1000; # минимальный размер сжимаемого файла
        	gzip_buffers 16 8k; # буферы: количество размер
        	gzip_comp_level 4; # уровень сжатия

        	gzip_types image/png image/jpeg image/jpg image/x-icon image/gif image/bmp video/quicktime video/webm video/ogg video/mpeg video/mp4 video/x-ms-wmv video/x-flv video/3gpp video/3gpp2 audio/mp4 audio/mpeg audio/midi audio/webm audio/ogg audio/basic audio/L24 audio/vorbis audio/x-ms-wma audio/x-ms-wax audio/vnd.rn-realaudio audio/vnd.wave audio/mp3 audio/aac audio/x-aac audio/x-hx-aac-adts application/pdf application/msword application/rtf application/vnd.ms-excel application/vnd.ms-powerpoint application/vnd.oasis.opendocument.text application/vnd.oasis.opendocument.spreadsheet application/javascript application/json application/xml application/cmd text/plain text/css text/csv text/javascript text/php text/xml text/markdown cache-manifest;

        	#######################################################
        	# http2
        	#######################################################

        	http2_recv_buffer_size 512k;
        	http2_chunk_size 2k;
        	http2_max_concurrent_streams 512;

        	#######################################################
        	# Fastcgi
        	#######################################################

        	# fastcgi
        	include /etc/nginx/fastcgi_params;
        	fastcgi_index index.php;
        	fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        	fastcgi_keep_conn off; # обязательно отключаем keep-alive
        	fastcgi_cache off; # никакого кэширования ответов от fastcgi
        	fastcgi_force_ranges off;
        	fastcgi_intercept_errors off; # не обрабатываем ответы в которых код > 300 с помощью error_page
        	fastcgi_connect_timeout 30s;
        	fastcgi_send_timeout 30s;
        	fastcgi_read_timeout 30s;
        	fastcgi_limit_rate 0; # убираем лимит скорость чтения ответа от fastcgi
        	fastcgi_ignore_client_abort off; # не закрываем соединение с fastcgi сервером в случае если клиент оборвался

        	# буферизация ответа от fastcgi сервера
        	fastcgi_buffering on;
        	fastcgi_buffers 64 4k;
        	fastcgi_busy_buffers_size 252k;
        	fastcgi_buffer_size 4k; # размер буфера для первого заголовка ответа от fastcgi сервера
        	fastcgi_max_temp_file_size 0; # не пишем в файл

        	#######################################################
        	# Virtual Host Configs
        	#######################################################

            include /etc/nginx/conf.d/*.conf;
            include /etc/nginx/sites-enabled/*;
            include /etc/nginx/sites-enabled-installer/*;
        }
    """
        )
        % nginx_user
    )
    write_file(nginx_conf, nginx_conf_content, mode=0o644)

    # Создаем site-конфиг
    sites_dir = Path("/etc/nginx/sites-enabled-installer")
    sites_dir.mkdir(parents=True, exist_ok=True)
    installer_nginx = sites_dir / "installer.nginx"

    installer_nginx_content = dedent(
        f"""\
        server {{
            listen 53794 default_server;
            listen [::]:53794 default_server;
            server_name _;

            root {front_dist};
            index index.html;

            location = / {{
                return 301 /install;
            }}

            location /api/ {{
                proxy_pass         http://127.0.0.1:8000/api/;
                proxy_http_version 1.1;
                proxy_set_header   Host              $host;
                proxy_set_header   X-Real-IP         $remote_addr;
                proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
                proxy_set_header   X-Forwarded-Proto $scheme;
            }}

            location /static/ {{
                alias              {front_dist}/static/;
                expires            30d;
                add_header         Cache-Control "public";
            }}

            location / {{
                try_files $uri $uri/ /index.html;
            }}
        }}
    """
    )
    write_file(installer_nginx, installer_nginx_content, mode=0o644)

    # Проверяем и перезагружаем nginx
    utils.run("nginx -t")
    utils.run("nginx -s reload")

    # -------------------------
    # Node.js + pnpm
    # -------------------------

    # Установка pnpm: предпочтительно через corepack (без зависимости от npm),
    # если corepack не сработал — fallback на npm.
    if not shutil.which("pnpm"):
        colors.print_info("[INFO] Устанавливаю pnpm...")

        corepack_path = shutil.which("corepack")
        if corepack_path:
            r1 = utils.run("corepack enable", check=False)
            r2 = utils.run("corepack prepare pnpm@latest-10 --activate", check=False)
            if r1 == 0 and r2 == 0 and shutil.which("pnpm"):
                pass
            else:
                colors.print_warning(
                    "[WARN] corepack не смог установить pnpm, пробую через npm..."
                )
                if not shutil.which("npm"):
                    # последняя попытка: поставить npm (best-effort), чтобы не падать на ровном месте
                    if package_manager_type == "deb":
                        utils.run(
                            "apt-get update && apt-get install -y npm", check=False
                        )
                    else:
                        utils.run(
                            "yum install -y npm || dnf install -y npm", check=False
                        )
                if not shutil.which("npm"):
                    raise RuntimeError("npm не найден в PATH — не могу установить pnpm")
                utils.run("npm install -g pnpm@latest-10")
        else:
            if not shutil.which("npm"):
                # попытка добрать npm
                if package_manager_type == "deb":
                    utils.run("apt-get update && apt-get install -y npm", check=False)
                else:
                    utils.run("yum install -y npm || dnf install -y npm", check=False)
            if not shutil.which("npm"):
                raise RuntimeError("npm не найден в PATH — не могу установить pnpm")
            utils.run("npm install -g pnpm@latest-10")

    # Собираем фронтенд
    colors.print_info("Собираю фронтенд...")
    utils.run(f"cd {webinstaller_dir}/frontend && CI=true pnpm install && pnpm build && cd ../")

    # Создаем systemd сервис
    service_path = Path("/etc/systemd/system/compass-installer.service")
    service_content = dedent(
        f"""\
        [Unit]
        Description=Compass On-Premise Web Installer
        After=network.target

        [Service]
        Type=simple
        WorkingDirectory={webinstaller_dir}
        ExecStart={python_bin} -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
        Restart=on-failure
        User=root
        Group=root
        Environment=PYTHONUNBUFFERED=1
        Environment="PATH={venv_path}/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

        [Install]
        WantedBy=multi-user.target
    """
    )
    write_file(service_path, service_content, mode=0o644)
    utils.run("systemctl daemon-reload")
    utils.run("systemctl enable --now compass-installer.service")

    # Предварительная загрузка docker-образов
    try:
        compose_main = installer_dir / "src/monolith/compose.goyaml"
        compose_over = installer_dir / "src/monolith/compose.override.production.goyaml"

        values_candidates = [installer_dir / "src/values.yaml"]
        values_map = _load_values_yaml(values_candidates)
        local_vars = _build_local_vars(values_map)

        raw_images = []
        raw_images += _extract_images_from_file(compose_main)
        raw_images += _extract_images_from_file(compose_over)

        resolved = set()
        for raw in raw_images:
            img = _render_placeholders(raw, values_map, local_vars=local_vars)
            resolved.add(img)

        if resolved:
            colors.print_info(
                f"[IMAGES] Найдено {len(resolved)} образ(ов) — запускаю docker pull в фоне"
            )
            try:
                Path("/var/log/compass-image-pull.log").touch(exist_ok=True)
            except Exception:
                pass
            for image in sorted(resolved):
                _start_bg_pull(image)
        else:
            colors.print_warning("[IMAGES] Образы не найдены")
    except Exception as e:
        colors.print_warning(f"[IMAGES] Ошибка предварительной загрузки образов: {e}")


# ---------- главная функция ----------


def main() -> None:
    """Главная функция скрипта."""
    parser = argparse.ArgumentParser(
        description="Скрипт подготовки сервера для установки Compass On-Premise",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s                    # Полная установка с интерактивными запросами
  %(prog)s --confirm-all      # Полная установка без запросов
  %(prog)s --packages         # Только установка системных пакетов
  %(prog)s --python           # Только настройка Python окружения
  %(prog)s --nodejs           # Только настройка Node.js окружения
  %(prog)s --docker           # Только настройка Docker окружения
  %(prog)s --firewall         # Только настройка фаервола
        """,
    )

    parser.add_argument(
        "--confirm-all",
        action="store_true",
        help="Автоматически соглашаться на все запросы",
    )
    parser.add_argument(
        "--packages",
        action="store_true",
        help="Выполнить проверку и установку системных пакетов",
    )
    parser.add_argument(
        "--python",
        action="store_true",
        help="Выполнить настройку Python окружения",
    )
    parser.add_argument(
        "--nodejs",
        action="store_true",
        help="Выполнить настройку Nodejs окружения",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Выполнить настройку Docker окружения",
    )
    parser.add_argument(
        "--firewall",
        action="store_true",
        help="Выполнить настройку фаервола",
    )

    args = parser.parse_args()

    require_root()

    BASE_DIR = Path(__file__).resolve().parent
    INSTALLER_DIR = Path(BASE_DIR / "../").resolve()
    WEBINSTALLER_DIR = INSTALLER_DIR / "web_installer"
    VENV_PATH = INSTALLER_DIR / ".venv"
    BACKEND_REQ = WEBINSTALLER_DIR / "backend" / "requirements.txt"

    colors.print_info(f"BASE_DIR = {BASE_DIR}")

    # Проверяем версию Python
    try:
        system_info = system_check.get_system_info()
        if not system_info.get("python_version_ok", False):
            py_major = system_info.get("python_major", "?")
            py_minor = system_info.get("python_minor", "?")
            colors.print_error(
                f"Требуется Python 3.8+, установлена версия {py_major}.{py_minor}"
            )
            colors.print_error("Пожалуйста, обновите Python до версии 3.8 или выше")
            sys.exit(1)
    except Exception as e:
        colors.print_error(f"Не удалось проверить версию Python: {e}")
        sys.exit(1)

    # Определяем тип системы
    try:
        package_manager_type = system_info["package_manager"]
        colors.print_info(f"Тип системы: {package_manager_type}")
    except Exception as e:
        colors.print_error(f"Не удалось определить тип системы: {e}")
        sys.exit(1)

    # Режим пакеты
    if args.packages:
        colors.print_step("\n[ШАГ 1] Проверка системных пакетов...")
        confirmed, missing = collect_packages_confirmation(
            package_manager_type, args.confirm_all
        )
        if confirmed and missing:
            colors.print_step("\n[ШАГ 1] Установка системных пакетов...")
            if not execute_packages_installation(missing, package_manager_type):
                sys.exit(1)
        colors.print_success("\nУстановка пакетов завершена.")

    # Режим Python
    if args.python:
        colors.print_step("\n[ШАГ 2] Настройка Python окружения...")
        if not collect_python_confirmation(VENV_PATH, BACKEND_REQ, args.confirm_all):
            sys.exit(1)
        if not execute_python_setup(VENV_PATH, BACKEND_REQ):
            sys.exit(1)
        colors.print_success("\nНастройка Python окружения завершена.")

    # Режим Nodejs
    if args.nodejs:
        colors.print_step("\n[ШАГ 3] Настройка Nodejs окружения...")

        success, version = collect_nodejs_confirmation(args.confirm_all)
        if not success:
            sys.exit(1)
        if not execute_nodejs_setup(package_manager_type, version):
            sys.exit(1)
        colors.print_success("\nНастройка Nodejs окружения завершена.")

    # Режим Docker
    if args.docker:
        colors.print_step("\n[ШАГ 4] Настройка Docker окружения...")

        success, version = collect_docker_confirmation(args.confirm_all)
        if not success:
            sys.exit(1)
        if not execute_docker_setup(package_manager_type):
            sys.exit(1)
        colors.print_success("\nНастройка Docker окружения завершена.")

    
    # Режим фаервол
    if args.firewall:
        colors.print_step("\n[ШАГ 5] Проверка правил фаервола...")
        confirmed, continue_without = collect_firewall_confirmation(args.confirm_all)
        if not continue_without:
            sys.exit(1)
        if confirmed:
            if not execute_firewall_setup():
                sys.exit(1)
        colors.print_success("\nНастройка фаервола завершена.")

    full_install = not (args.packages or args.python or args.nodejs or args.docker or args.firewall)
    if not full_install:
        return
    
    # Полная установка
    colors.print_highlight("\n" + "=" * 60)
    colors.print_highlight("Начало подготовки сервера для установки Compass On-Premise")
    colors.print_highlight("=" * 60)

    # ФАЗА 1: Сбор всех подтверждений
    colors.print_step("\n[ФАЗА 1] Сбор подтверждений...")

    # Подтверждение 1: Пакеты
    colors.print_step("\n[ШАГ 1] Проверка системных пакетов...")
    packages_confirmed, missing_packages = collect_packages_confirmation(
        package_manager_type, args.confirm_all
    )
    if not packages_confirmed:
        colors.print_error("\nНе удалось получить подтверждение на установку пакетов.")
        sys.exit(1)

    # Подтверждение 2: Python окружение
    colors.print_step("\n[ШАГ 2] Настройка Python окружения...")
    python_confirmed = collect_python_confirmation(
        VENV_PATH, BACKEND_REQ, args.confirm_all
    )
    if not python_confirmed:
        colors.print_error(
            "\nНе удалось получить подтверждение на настройку Python окружения."
        )
        sys.exit(1)

    # Подтверждение 3: Nodejs окружение
    colors.print_step("\n[ШАГ 3] Настройка Nodejs окружения...")
    nodejs_confirmed, nodejs_version = collect_nodejs_confirmation(args.confirm_all)
    if not nodejs_confirmed:
        colors.print_error(
            "\nНе удалось получить подтверждение на настройку Nodejs окружения."
        )
        sys.exit(1)

    # Подтверждение 4: Docker окружение
    colors.print_step("\n[ШАГ 4] Настройка Docker окружения...")
    docker_confirmed = collect_docker_confirmation(args.confirm_all)
    if not docker_confirmed:
        colors.print_error(
            "\nНе удалось получить подтверждение на настройку Docker окружения."
        )
        sys.exit(1)

    # Подтверждение 5: Фаервол
    colors.print_step("\n[ШАГ 5] Проверка правил фаервола...")
    firewall_confirmed, firewall_continue = collect_firewall_confirmation(
        args.confirm_all
    )
    if not firewall_continue:
        colors.print_error("\nУстановка прервана пользователем.")
        sys.exit(1)

    # Подтверждение 5: Системные лимиты
    colors.print_step("\n[ШАГ 6] Настройка системных лимитов и параметров ядра...")
    limits_confirmed = collect_limits_confirmation(args.confirm_all)

    # ФАЗА 2: Выполнение действий
    colors.print_step("\n[ФАЗА 2] Выполнение установки...")

    # Действие 1: Установка пакетов
    if missing_packages:
        colors.print_step("\n[ШАГ 1] Установка системных пакетов...")
        if not execute_packages_installation(missing_packages, package_manager_type):
            colors.print_error("\nНе удалось установить системные пакеты.")
            sys.exit(1)

    # Действие 2: Настройка Python окружения
    colors.print_step("\n[ШАГ 2] Настройка Python окружения...")
    if not execute_python_setup(VENV_PATH, BACKEND_REQ):
        colors.print_error("\nНе удалось настроить Python окружение.")
        sys.exit(1)

    # Действие 3: Настройка Nodejs
    if nodejs_confirmed:
        colors.print_step("\n[ШАГ 3] Настройка Node.js...")
        if not execute_nodejs_setup(package_manager_type, nodejs_version):
            colors.print_error(
                "\nНе удалось настроить Node.js..."
            )
            sys.exit(1)

    # Действие 4: Настройка Docker
    if docker_confirmed:
        colors.print_step("\n[ШАГ 4] Настройка Docker...")
        if not execute_docker_setup(package_manager_type):
            colors.print_error(
                "\nНе удалось настроить Docker..."
            )
            sys.exit(1)
    # Действие 5: Настройка фаервола
    if firewall_confirmed:
        colors.print_step("\n[ШАГ 5] Настройка фаервола...")
        if not execute_firewall_setup():
            colors.print_warning(
                "\nНе удалось настроить фаервол, но продолжаю установку..."
            )

    # Действие 6: Настройка системных лимитов
    if limits_confirmed:
        colors.print_step("\n[ШАГ 6] Настройка системных лимитов...")
        if not execute_limits_setup():
            colors.print_warning(
                "\nНе удалось настроить лимиты, но продолжаю установку..."
            )

    # Действие 5: Основная установка
    colors.print_step("\n[ШАГ 7] Выполнение установки...")
    perform_installation(
        BASE_DIR,
        INSTALLER_DIR,
        WEBINSTALLER_DIR,
        VENV_PATH,
        package_manager_type,
        args.confirm_all,
    )

    # Выводим адрес установщика
    server_ip = get_server_ip()
    installer_url = f"http://{server_ip}:53794"

    colors.print_highlight("\n" + "=" * 60)
    colors.print_success("Установщик успешно запущен!")
    colors.print_highlight("=" * 60)
    colors.print_info(f"Web-установщик запущен на адресе: {colors.Colors.highlight(installer_url)}")
    colors.print_info(
        f"Или локально: {colors.Colors.highlight('http://localhost:53794')}"
    )
    colors.print_info(
        "Далее заполните форму корректными данными и нажмите «Установить»."
    )
    colors.print_highlight("=" * 60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        colors.print_info("Установка прервана пользователем.")
        sys.exit(1)
    except Exception as e:
        colors.print_error(f"\n{e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
