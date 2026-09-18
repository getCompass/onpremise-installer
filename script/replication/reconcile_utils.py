from replication.mysql_fence import extract_slave_status_field


def plan_replication_action(status_output) -> str:
    if not status_output or not status_output.strip():
        return "start"

    io_running = extract_slave_status_field("Slave_IO_Running", status_output)
    sql_running = extract_slave_status_field("Slave_SQL_Running", status_output)

    if io_running == "Yes" and sql_running == "Yes":
        return "ok"

    return "restart"


def plan_configure_only_action(status_output) -> str:
    if not status_output or not status_output.strip():
        return "configure"

    io_running = extract_slave_status_field("Slave_IO_Running", status_output)
    sql_running = extract_slave_status_field("Slave_SQL_Running", status_output)

    if io_running == "Yes" or sql_running == "Yes":
        return "stop-threads"

    return "ok"
