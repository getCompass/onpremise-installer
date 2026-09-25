import re

from replication.gtid import is_subset, parse_gtid_set


PEER_SSL_CA_PATH = "/etc/mysql/ssl/mysqlRootCA.crt"
PEER_CONNECT_TIMEOUT_SEC = 5


def build_peer_read_only_command(host: str, port: int, user: str, password: str) -> str:
    return (
        "mysql -h %s -P %s -u %s -p%s "
        "--ssl-ca=%s --connect-timeout=%d "
        "-e \"SELECT @@super_read_only, @@read_only;\""
        % (host, port, user, password, PEER_SSL_CA_PATH, PEER_CONNECT_TIMEOUT_SEC)
    )


def build_peer_gtid_executed_command(host: str, port: int, user: str, password: str) -> str:
    return (
        "mysql -h %s -P %s -u %s -p%s "
        "--ssl-ca=%s --connect-timeout=%d "
        "-e \"SELECT @@global.gtid_executed;\""
        % (host, port, user, password, PEER_SSL_CA_PATH, PEER_CONNECT_TIMEOUT_SEC)
    )


# проверяем, что локальный gtid набор содержит всё, что успел закоммитить пир
def is_caught_up_with_peer(local_gtid: str, peer_gtid: str) -> bool:
    return is_subset(parse_gtid_set(peer_gtid), parse_gtid_set(local_gtid))


def parse_gtid_executed_output(query_output) -> str:
    if not query_output:
        return ""

    text = query_output.decode("utf-8", errors="ignore") if isinstance(query_output, bytes) else query_output
    lines = text.splitlines()
    if not lines:
        return ""

    value_lines = [line for line in lines[1:] if line.strip()]
    return re.sub(r"\s+", " ", " ".join(value_lines)).strip()


def is_fenced(query_output) -> bool:
    if not query_output:
        return False

    text = query_output.decode("utf-8", errors="ignore") if isinstance(query_output, bytes) else query_output
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    values = lines[-1].split("\t")
    if len(values) < 2:
        return False

    try:
        super_read_only = int(values[0])
        read_only = int(values[1])
    except ValueError:
        return False

    return super_read_only == 1 and read_only == 1


def extract_slave_status_field(field_name: str, status_output) -> str:
    if not status_output:
        return ""

    text = status_output.decode("utf-8", errors="ignore") if isinstance(status_output, bytes) else status_output
    pattern = r"%s:\s*(.*?)(?=\n\s*[A-Za-z_]+:|$)" % re.escape(field_name)
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def is_replication_drained(status_output) -> bool:
    if not status_output or not status_output.strip():
        return True

    retrieved = extract_slave_status_field("Retrieved_Gtid_Set", status_output)
    if retrieved == "":
        return True

    executed = extract_slave_status_field("Executed_Gtid_Set", status_output)
    return is_subset(parse_gtid_set(retrieved), parse_gtid_set(executed))


def evaluate_fence_attempt(results) -> str:
    if all(value is True for value in results.values()) and results:
        return "fenced"

    if any(value is not None for value in results.values()):
        return "reachable"

    return "unreachable"


def is_replication_preconfigured(status_output, expected_host, expected_port) -> bool:
    if not status_output or not status_output.strip():
        return False

    master_host = extract_slave_status_field("Master_Host", status_output)
    if master_host.strip().lower() != str(expected_host).strip().lower():
        return False

    master_port = extract_slave_status_field("Master_Port", status_output)
    try:
        if int(master_port) != int(expected_port):
            return False
    except (TypeError, ValueError):
        return False

    auto_position = extract_slave_status_field("Auto_Position", status_output)
    try:
        if int(auto_position) != 1:
            return False
    except (TypeError, ValueError):
        return False

    return True


def is_replication_started(status_output) -> bool:
    if not status_output or not status_output.strip():
        return False

    io_running = extract_slave_status_field("Slave_IO_Running", status_output)
    sql_running = extract_slave_status_field("Slave_SQL_Running", status_output)

    return sql_running == "Yes" and io_running in ("Yes", "Connecting")
