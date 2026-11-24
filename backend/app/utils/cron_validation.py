"""Five-field cron validation shared with Airflow's standard cron syntax."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from croniter import croniter
except ImportError:  # Dependency-free fallback for constrained/offline test environments.
    croniter = None

_MONTHS = {name: index for index, name in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
)}
_WEEKDAYS = {name: index for index, name in enumerate(("sun", "mon", "tue", "wed", "thu", "fri", "sat"))}


def _value(token: str, names: dict[str, int]) -> int | None:
    if token.isdigit():
        return int(token)
    return names.get(token.lower())


def _valid_field(field: str, minimum: int, maximum: int, names: dict[str, int] | None = None,
                 allow_seven: bool = False) -> bool:
    names = names or {}
    if not field:
        return False
    for part in field.split(","):
        if not part:
            return False
        base, slash, step_text = part.partition("/")
        if slash and (not step_text.isdigit() or int(step_text) < 1):
            return False
        if "/" in step_text:
            return False
        if base == "*":
            continue
        if base.count("-") > 1:
            return False
        if "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = _value(start_text, names), _value(end_text, names)
            if start is None or end is None or start > end:
                return False
        else:
            start = end = _value(base, names)
            if start is None:
                return False
        upper = 7 if allow_seven else maximum
        if start < minimum or end > upper:
            return False
    return True


def is_valid_cron(expression: str) -> bool:
    if croniter is not None:
        return bool(croniter.is_valid(expression))
    fields = expression.split()
    if len(fields) != 5 or not re.fullmatch(r"[\w*/,\-]+(?:\s+[\w*/,\-]+){4}", expression.strip()):
        return False
    return all((
        _valid_field(fields[0], 0, 59),
        _valid_field(fields[1], 0, 23),
        _valid_field(fields[2], 1, 31),
        _valid_field(fields[3], 1, 12, _MONTHS),
        _valid_field(fields[4], 0, 6, _WEEKDAYS, allow_seven=True),
    ))


def next_cron_run(expression: str, timezone_name: str, start_date: datetime | None = None) -> datetime | None:
    if croniter is None:
        return None
    zone = ZoneInfo(timezone_name)
    now = datetime.now(zone)
    if start_date is not None:
        start = start_date.replace(tzinfo=zone) if start_date.tzinfo is None else start_date.astimezone(zone)
        now = max(now, start)
    return croniter(expression, now).get_next(datetime)
