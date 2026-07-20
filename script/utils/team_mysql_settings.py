#!/usr/bin/env python3

import json
import re
from pathlib import Path
from typing import Optional

import yaml


SECTION_KEY = "team_mysql_settings"
BUFFER_POOL_SIZE_KEY = "innodb_buffer_pool_size_mb"
THREAD_CONCURRENCY_KEY = "innodb_thread_concurrency"
TABLE_OPEN_CACHE_KEY = "table_open_cache"


def make_settings(
        buffer_pool_size: Optional[int],
        innodb_thread_concurrency: Optional[int],
        table_open_cache: Optional[int],
) -> dict:
    settings = {}

    if buffer_pool_size is not None:
        _assert_positive_int(buffer_pool_size, "buffer_pool_size")
        settings[BUFFER_POOL_SIZE_KEY] = buffer_pool_size

    if innodb_thread_concurrency is not None:
        _assert_non_negative_int(innodb_thread_concurrency, "innodb_thread_concurrency")
        settings[THREAD_CONCURRENCY_KEY] = innodb_thread_concurrency

    if table_open_cache is not None:
        _assert_positive_int(table_open_cache, "table_open_cache")
        settings[TABLE_OPEN_CACHE_KEY] = table_open_cache

    return settings


def to_json(settings: dict) -> str:
    if len(settings) < 1:
        return ""

    return json.dumps(settings, separators=(",", ":"))


def get_for_company(team_config_path: Path, company_id: int) -> dict:
    config = _load_yaml(team_config_path)
    section = config.get(SECTION_KEY, {})
    if section is None:
        return {}

    if not isinstance(section, dict):
        raise ValueError("team_mysql_settings должен быть yaml-словарем")

    value = section.get(_team_key(company_id), {})
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError("%s.%s должен быть yaml-словарем" % (SECTION_KEY, _team_key(company_id)))

    return _normalize_settings(value)


def validate_config(config: dict):
    section = config.get(SECTION_KEY, {})
    if section is None:
        return

    if not isinstance(section, dict):
        raise ValueError("team_mysql_settings должен быть yaml-словарем")

    for team_key, settings in section.items():
        if not re.match(r"^team_\d+$", str(team_key)):
            raise ValueError("ключи team_mysql_settings должны иметь формат team_<id>")

        if settings is None:
            continue

        if not isinstance(settings, dict):
            raise ValueError("%s.%s должен быть yaml-словарем" % (SECTION_KEY, team_key))

        _normalize_settings(settings)


def set_for_company(team_config_path: Path, company_id: int, settings: dict):
    normalized_settings = _normalize_settings(settings)
    config = _load_yaml(team_config_path)
    section = config.get(SECTION_KEY, {})
    if section is None:
        section = {}

    if not isinstance(section, dict):
        raise ValueError("team_mysql_settings должен быть yaml-словарем")

    section[_team_key(company_id)] = normalized_settings
    _write_section(team_config_path, section)


def delete_for_company(team_config_path: Path, company_id: int):
    config = _load_yaml(team_config_path)
    section = config.get(SECTION_KEY, {})
    if not isinstance(section, dict) or len(section) < 1:
        return

    section.pop(_team_key(company_id), None)
    _write_section(team_config_path, section)


def _load_yaml(team_config_path: Path) -> dict:
    if not team_config_path.exists():
        return {}

    with team_config_path.open("r") as config_file:
        config = yaml.safe_load(config_file)

    return {} if config is None else config


def _normalize_settings(settings: dict) -> dict:
    normalized = {}

    if BUFFER_POOL_SIZE_KEY in settings and settings[BUFFER_POOL_SIZE_KEY] not in (None, ""):
        value = _to_int(settings[BUFFER_POOL_SIZE_KEY], BUFFER_POOL_SIZE_KEY)
        _assert_positive_int(value, BUFFER_POOL_SIZE_KEY)
        normalized[BUFFER_POOL_SIZE_KEY] = value

    if THREAD_CONCURRENCY_KEY in settings and settings[THREAD_CONCURRENCY_KEY] not in (None, ""):
        value = _to_int(settings[THREAD_CONCURRENCY_KEY], THREAD_CONCURRENCY_KEY)
        _assert_non_negative_int(value, THREAD_CONCURRENCY_KEY)
        normalized[THREAD_CONCURRENCY_KEY] = value

    if TABLE_OPEN_CACHE_KEY in settings and settings[TABLE_OPEN_CACHE_KEY] not in (None, ""):
        value = _to_int(settings[TABLE_OPEN_CACHE_KEY], TABLE_OPEN_CACHE_KEY)
        _assert_positive_int(value, TABLE_OPEN_CACHE_KEY)
        normalized[TABLE_OPEN_CACHE_KEY] = value

    return normalized


def _write_section(team_config_path: Path, section: dict):
    text = team_config_path.read_text() if team_config_path.exists() else ""
    section_text = _format_section(section)
    team_config_path.write_text(_replace_section(text, section_text))


def _format_section(section: dict) -> str:
    if len(section) < 1:
        return ""

    lines = [SECTION_KEY + ":\n"]
    for team_key in sorted(section.keys(), key=_team_sort_key):
        settings = _normalize_settings(section[team_key])
        if len(settings) < 1:
            continue

        lines.append("  %s:\n" % team_key)
        for setting_key in [BUFFER_POOL_SIZE_KEY, THREAD_CONCURRENCY_KEY, TABLE_OPEN_CACHE_KEY]:
            if setting_key in settings:
                lines.append("    %s: %s\n" % (setting_key, settings[setting_key]))

    return "".join(lines)


def _replace_section(text: str, section_text: str) -> str:
    lines = text.splitlines(keepends=True)
    start = None

    for index, line in enumerate(lines):
        if re.match(r"^%s\s*:" % re.escape(SECTION_KEY), line):
            start = index
            break

    if start is None:
        if section_text == "":
            return text

        separator = "\n" if text.endswith("\n") or text == "" else "\n\n"
        return text + separator + section_text

    end = _find_section_end(lines, start)

    replacement = [] if section_text == "" else [section_text]
    new_lines = lines[:start] + replacement + lines[end:]
    return "".join(new_lines)


def _find_section_end(lines: list, start: int) -> int:
    if _section_header_has_inline_value(lines[start]):
        return start + 1

    end = start + 1
    for index in range(start + 1, len(lines)):
        line = lines[index]

        if line.strip() == "":
            continue

        if line.startswith((" ", "\t")):
            end = index + 1
            continue

        break

    return end


def _section_header_has_inline_value(line: str) -> bool:
    match = re.match(r"^%s\s*:(.*)$" % re.escape(SECTION_KEY), line)
    if not match:
        return False

    suffix = match.group(1).strip()
    return suffix != "" and not suffix.startswith("#")


def _team_key(company_id: int) -> str:
    return "team_%s" % company_id


def _team_sort_key(team_key: str):
    match = re.match(r"^team_(\d+)$", str(team_key))
    if match:
        return int(match.group(1))
    return str(team_key)


def _to_int(value, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("%s должен быть целым числом" % field_name)


def _assert_positive_int(value: int, field_name: str):
    if not isinstance(value, int) or value < 1:
        raise ValueError("%s должен быть целым числом больше 0" % field_name)


def _assert_non_negative_int(value: int, field_name: str):
    if not isinstance(value, int) or value < 0:
        raise ValueError("%s должен быть целым числом больше или равным 0" % field_name)
