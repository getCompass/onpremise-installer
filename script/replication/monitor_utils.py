import json
import os
from typing import Optional, Tuple


def decide_lag_alert(previous_state, lag_seconds, threshold_sec, now_ts,
                     repeat_interval_sec: int = 3600) -> Tuple[str, dict]:
    if previous_state is None:
        previous_state = {"lagged": False, "last_alert": 0}

    is_lagged = threshold_sec > 0 and lag_seconds is not None and lag_seconds > threshold_sec

    if is_lagged:
        if not previous_state.get("lagged"):
            return "alert", {"lagged": True, "last_alert": now_ts}
        if now_ts - previous_state.get("last_alert", 0) >= repeat_interval_sec:
            return "repeat", {"lagged": True, "last_alert": now_ts}
        return "none", dict(previous_state)

    if previous_state.get("lagged"):
        return "recovered", {"lagged": False, "last_alert": 0}

    return "none", {"lagged": False, "last_alert": 0}


def should_stop_keepalived(is_master_relationship: bool, last_state: Optional[str],
                           is_state_changing: bool = False) -> bool:
    if is_master_relationship:
        return False

    if last_state == "master":
        return False

    # во время перехода состояния обработчик может ещё не успеть запустить
    # репликацию - остановка keepalived убила бы его на середине работы
    if is_state_changing:
        return False

    return True


# маркер процесса обработчика смены состояния keepalived
STATE_HANDLER_PROCESS_MARKER = "keepalived_status_changed.py"


# проверяем, запущен ли прямо сейчас обработчик смены состояния
# живой процесс - единственный достоверный признак идущего перехода:
# last_state пишется в начале работы обработчика и не отличает
# "работает" от "умер на середине", а файл-метка остается лежать
# после его убийства
def is_state_handler_running(process_root: str = "/proc") -> bool:
    try:
        entries = os.listdir(process_root)
    except OSError:
        return False

    marker = STATE_HANDLER_PROCESS_MARKER.encode()

    for entry in entries:
        if not entry.isdigit():
            continue

        try:
            with open(os.path.join(process_root, entry, "cmdline"), "rb") as cmdline_file:
                cmdline = cmdline_file.read()
        except OSError:
            continue

        if marker in cmdline:
            return True

    return False


def read_keepalived_last_state(state_file_path: str = "/etc/keepalived/last_state") -> Optional[str]:
    try:
        with open(state_file_path) as state_file:
            content = state_file.read().strip().lower()
        return content if content else None
    except OSError:
        return None


def acquire_single_instance_lock(pid_file: str) -> bool:
    try:
        try:
            descriptor = os.open(pid_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held_pid = _read_lock_pid(pid_file)
            if held_pid is not None and _is_pid_alive(held_pid):
                return False

            try:
                os.unlink(pid_file)
            except OSError:
                return False

            try:
                descriptor = os.open(pid_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False

        with os.fdopen(descriptor, "w") as lock_file:
            lock_file.write(str(os.getpid()))

        return True
    except OSError:
        return False


def release_single_instance_lock(pid_file: str):
    try:
        os.unlink(pid_file)
    except OSError:
        pass


def load_lag_alert_state(state_file_path: str) -> dict:
    try:
        with open(state_file_path) as state_file:
            content = state_file.read().strip()
        loaded = json.loads(content) if content else {}
        return loaded if isinstance(loaded, dict) else {}
    except OSError:
        return {}


def save_lag_alert_state(state_file_path: str, state: dict):
    try:
        with open(state_file_path, "w") as state_file:
            state_file.write(json.dumps(state))
    except OSError:
        pass


def _read_lock_pid(pid_file: str) -> Optional[int]:
    try:
        with open(pid_file) as lock_file:
            content = lock_file.read().strip()
        return int(content) if content.isdigit() else None
    except OSError:
        return None


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
