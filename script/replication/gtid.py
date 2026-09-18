import re
from typing import Dict, List, Tuple


Interval = Tuple[int, int]
GtidSet = Dict[str, List[Interval]]

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_INTERVAL = r"\d+(?:-\d+)?"
_BLOCK_RE = re.compile("(%s)((?::%s)+)" % (_UUID, _INTERVAL))


def parse_gtid_set(value) -> GtidSet:
    if not value or not value.strip():
        return {}

    intervals: Dict[str, List[Interval]] = {}
    for match in _BLOCK_RE.finditer(value):
        uuid = match.group(1)
        ranges: List[Interval] = []
        for item in match.group(2).split(":"):
            if not item:
                continue
            if "-" in item:
                start_str, end_str = item.split("-", 1)
                ranges.append((int(start_str), int(end_str)))
            else:
                number = int(item)
                ranges.append((number, number))
        intervals.setdefault(uuid, []).extend(ranges)

    return {uuid: _merge_intervals(ranges) for uuid, ranges in intervals.items()}


def format_gtid_set(parsed: GtidSet) -> str:
    blocks = []
    for uuid, ranges in parsed.items():
        intervals = _merge_intervals(ranges or [])
        if not intervals:
            continue
        parts = [
            "%d-%d" % interval if interval[0] != interval[1] else "%d" % interval[0]
            for interval in intervals
        ]
        blocks.append("%s:%s" % (uuid, ":".join(parts)))
    return ",".join(blocks)


def is_empty(parsed: GtidSet) -> bool:
    return all(not ranges for ranges in parsed.values())


def is_subset(a: GtidSet, b: GtidSet) -> bool:
    return is_empty(subtract(a, b))


def subtract(a: GtidSet, b: GtidSet) -> GtidSet:
    result: GtidSet = {}
    for uuid, ranges in a.items():
        removed = _merge_intervals(b.get(uuid) or [])
        remaining: List[Interval] = []
        for start, end in _merge_intervals(ranges or []):
            cursor = start
            for remove_start, remove_end in removed:
                if remove_end < cursor:
                    continue
                if remove_start > end:
                    break
                if remove_start > cursor:
                    remaining.append((cursor, remove_start - 1))
                cursor = max(cursor, remove_end + 1)
                if cursor > end:
                    break
            if cursor <= end:
                remaining.append((cursor, end))
        if remaining:
            result[uuid] = remaining
    return result


def _merge_intervals(ranges: List[Interval]) -> List[Interval]:
    if not ranges:
        return []

    ordered = sorted(set(ranges))
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
