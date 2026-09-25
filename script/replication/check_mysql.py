#!/usr/bin/python3
import subprocess
import sys
from datetime import datetime

# куда логируем состояние mysql
LOG_FILE = "/var/log/keepalived_health.log"

SIMULATION_FAILURE_FLAG_FILE = "/tmp/simulate_keepalived_failure"

MYSQL_NAME_MARKER = "_mysql"


# команда для получения всех сервисов swarm
# фильтр name= в docker service ls сопоставляется по началу имени,
# а имена mysql сервисов содержат _mysql в середине - поэтому
# отбор mysql сервисов выполняется при разборе вывода
def service_ls_command():
    return ["docker", "service", "ls", "--format", "{{.Name}} {{.Replicas}}"]


# получаем список запущенных mysql контейнеров
def list_mysql_containers():
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=_mysql", "--format", "{{.Names}}"],
            capture_output=True,
            text=True
        )
    except Exception as e:
        log_error(f"Docker ps check failed: {str(e)}")
        return None

    if result.returncode != 0:
        log_error(f"Docker ps check failed: {result.stderr.strip()}")
        return None

    return [name for name in result.stdout.split() if name.strip()]


# получаем mysql сервисы swarm и их реплики: {имя сервиса: (running, desired)}
def list_mysql_services():
    try:
        result = subprocess.run(
            service_ls_command(),
            capture_output=True,
            text=True
        )
    except Exception as e:
        log_error(f"Docker service ls check failed: {str(e)}")
        return None

    if result.returncode != 0:
        log_error(f"Docker service ls check failed: {result.stderr.strip()}")
        return None

    return parse_service_replicas(result.stdout)


# разбираем вывод docker service ls в {имя сервиса: (running, desired)}
# оставляем только mysql сервисы: их имена содержат _mysql
def parse_service_replicas(output) -> dict:
    services = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) != 2 or "/" not in parts[1]:
            continue
        if MYSQL_NAME_MARKER not in parts[0]:
            continue
        running, desired = parts[1].split("/", 1)
        try:
            services[parts[0]] = (int(running), int(desired))
        except ValueError:
            continue
    return services


# контейнеры сервиса: задачи swarm называются <имя сервиса>.<slot>.<id>
def service_containers(service_name, container_list):
    prefix = service_name + "."
    return [name for name in container_list if name.startswith(prefix)]


# получаем результат docker inspect для health статуса контейнера
def inspect_container_health(container_name):
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_name],
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        log_error(f"Inspect {container_name} failed: {str(e)}")
        return 1, "", ""


# определяем состояние контейнера по результату docker inspect
def classify_health_probe(inspect_rc, inspect_stdout, inspect_stderr) -> str:
    if inspect_rc == 0:
        return "healthy" if inspect_stdout.strip() == "healthy" else "not-healthy"

    if "Health" in inspect_stderr:
        return "no-healthcheck"

    return "error"


# активная проверка живости для контейнеров без docker healthcheck
def probe_container_alive(container_name):
    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "mysqladmin", "ping", "-h", "127.0.0.1",
                "-u", "root", "--password=root",
                "--connect-timeout=3"
            ],
            capture_output=True,
            text=True
        )
    except Exception as e:
        log_error(f"Probe {container_name} failed: {str(e)}")
        return False

    return result.returncode == 0


# проверяем, что mysql контейнер жив
def container_is_healthy(container_name):
    inspect_rc, inspect_stdout, inspect_stderr = inspect_container_health(container_name)
    health_state = classify_health_probe(inspect_rc, inspect_stdout, inspect_stderr)

    if health_state == "healthy":
        return True

    if health_state == "no-healthcheck":
        is_alive = probe_container_alive(container_name)
        log_entry(f"{container_name}: no docker healthcheck, mysqladmin probe {'ok' if is_alive else 'failed'}")
        return is_alive

    log_error(f"{container_name}: health status '{inspect_stdout.strip() or inspect_stderr.strip()}'")
    return False


# проверяем состояние mysql сервисов: каждый сервис с desired > 0
# должен иметь живой контейнер; сервисы, свернутые к 0 (штатное
# выключение через docker service scale <имя>=0), игнорируются
def check_mysql():
    container_list = list_mysql_containers()

    if container_list is None:
        return False

    services = list_mysql_services()

    if not services:
        log_error("no mysql services found in docker swarm")
        return False

    healthy = True
    checked_containers = set()

    for service_name, (_, desired) in services.items():
        if desired == 0:
            log_entry(f"{service_name}: scaled to 0, skipping")
            checked_containers.update(service_containers(service_name, container_list))
            continue

        svc_containers = service_containers(service_name, container_list)

        if len(svc_containers) < 1:
            log_error(f"{service_name}: no running containers (desired replicas {desired})")
            healthy = False
            continue

        for container_name in svc_containers:
            log_entry(f"checking {container_name}")

            if not container_is_healthy(container_name):
                healthy = False

        checked_containers.update(svc_containers)

    for container_name in container_list:
        if container_name in checked_containers:
            continue

        log_entry(f"checking {container_name}")

        if not container_is_healthy(container_name):
            healthy = False

    return healthy


# пишем в лог результат проверки
def log_entry(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [MYSQL] {message}\n")


# пишем в лог ошибку проверки
def log_error(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] [ERROR] {message}\n")


# для симуляции падения
def simulate_failure():
    log_entry("Status: FAILED")
    sys.exit(1)


if __name__ == "__main__":

    try:
        with open(SIMULATION_FAILURE_FLAG_FILE, "r") as f:
            failed_service = f.read().strip()
            if failed_service == "mysql":
                log_entry("Status: FAILED")
                sys.exit(1)
    except FileNotFoundError:
        pass

    # проверяем mysql
    if check_mysql():
        log_entry("Status: OK")
        sys.exit(0)
    else:
        log_entry("Status: FAILED")
        sys.exit(1)
