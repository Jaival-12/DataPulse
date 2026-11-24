"""Bounded, JSON-safe helpers shared by the analytics service."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from app.services.profiling_service import _parse_date, _parse_number, _safe_value

MAX_HISTOGRAM_BINS = 20
MAX_TOP_VALUES = 10
MAX_AGGREGATE_GROUPS = 100
MAX_TIMESERIES_POINTS = 500
MAX_CORRELATION_COLUMNS = 50


def is_missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        result = pd.isna(value)
        return bool(result) if np.isscalar(result) else False
    except (TypeError, ValueError):
        return False


def numeric_values(series: pd.Series) -> tuple[list[float | None], int, int]:
    """Return converted values aligned to the series, with missing/invalid counts."""
    converted: list[float | None] = []
    missing = invalid = 0
    for value in series.tolist():
        if is_missing(value):
            converted.append(None)
            missing += 1
        else:
            number = _parse_number(value)
            converted.append(number)
            invalid += number is None
    return converted, missing, invalid


def parsed_dates(series: pd.Series) -> tuple[list[pd.Timestamp | None], int, int]:
    dates: list[pd.Timestamp | None] = []
    missing = invalid = 0
    for value in series.tolist():
        if is_missing(value):
            dates.append(None)
            missing += 1
            continue
        parsed = _parse_date(value)
        if parsed is None or pd.isna(parsed):
            dates.append(None)
            invalid += 1
            continue
        stamp = pd.Timestamp(parsed)
        if stamp.tzinfo is not None:
            stamp = stamp.tz_convert("UTC").tz_localize(None)
        dates.append(stamp)
    return dates, missing, invalid


def json_key(value: Any) -> str:
    return json.dumps(_safe_value(value), sort_keys=True, ensure_ascii=False, default=str, allow_nan=False)


def safe_number(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()
