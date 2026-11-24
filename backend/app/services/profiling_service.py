import json
import math
import re
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

class ProfileError(Exception):
    """Base class for safe profile-input errors."""

class ProfileSourceMissing(ProfileError):
    pass

class ProfileTooLarge(ProfileError):
    pass

class UnsupportedProfileFormat(ProfileError):
    pass

class InvalidProfileSource(ProfileError):
    pass

IDENTIFIER_NAME = re.compile(r"^(?:id|uuid|identifier|key|zip|zip_code|zipcode|postal_code|phone|phone_number|phonenumber|.*_(?:id|uuid|identifier|key|code|zip|zip_code|postal_code|phone|phone_number|account_number))$", re.I)
DATE_SHAPE = re.compile(r"(?:\d{1,4}[-/]\d{1,2}[-/]\d{1,4}|\d{4}-\d{2}-\d{2}T\d{2}:\d{2}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})")
NUMERIC_TEXT = re.compile(r"^[+-]?(?:(?:\d{1,3}(?:,\d{3})+)|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?$")
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y")

def _normalized_name(value: object) -> str:
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", str(value)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")

def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy(deep=True)
    for column in result.columns:
        series = result[column]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            def normalize_value(value):
                if isinstance(value, str):
                    normalized = value.strip()
                    if not normalized or normalized.lower() in {"nan", "nat"}:
                        return pd.NA
                    if normalized.lower() in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}:
                        return pd.NA
                if isinstance(value, (dict, list)):
                    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
                return value
            result[column] = series.map(normalize_value)
        if pd.api.types.is_numeric_dtype(result[column]):
            numeric = pd.to_numeric(result[column], errors="coerce")
            result[column] = numeric.where(np.isfinite(numeric), np.nan)
    return result

def _is_date_series(series: pd.Series) -> bool:
    values = series.dropna()
    if not len(values) or not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return False
    if not values.map(lambda value: bool(DATE_SHAPE.search(str(value)))).all():
        return False
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    return bool(parsed.notna().all())

def _column_type(name: object, series: pd.Series) -> str:
    if series.isna().all():
        return "empty"
    if IDENTIFIER_NAME.fullmatch(_normalized_name(name)):
        return "identifier"
    present = series.dropna()
    if pd.api.types.is_bool_dtype(series) or (len(present) > 0 and present.map(lambda value: isinstance(value, (bool, np.bool_))).all()):
        return "boolean"
    parsed_dates = [_parse_date(value) for value in present]
    if any(item is not None for item in parsed_dates) or any(DATE_SHAPE.search(str(value)) for value in present):
        return "datetime" if any(_is_datetime_text(value) for value in present) else "date"
    parsed = [_parse_number(value) for value in present]
    valid = [value for value in parsed if value is not None]
    if valid:
        if len(valid) != len(parsed):
            return "numeric_mixed"
        return "integer" if all(value.is_integer() for value in valid) else "float"
    if present.map(lambda value: isinstance(value, (bool, np.bool_)) or str(value).lower() in {"true", "false"}).all():
        return "boolean"
    if present.map(lambda value: isinstance(value, (str, int, float))).all():
        distinct = int(present.nunique())
        return "categorical" if distinct < len(present) and distinct <= max(10, min(50, int(2 * math.sqrt(len(present))))) else "string"
    return "mixed"

def _parse_number(value):
    if isinstance(value, (bool, np.bool_)) or value is None or value is pd.NA:
        return None
    if isinstance(value, str):
        if not NUMERIC_TEXT.fullmatch(value.strip()):
            return None
        value = value.replace(",", "").strip()
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None

def _is_datetime_text(value):
    text = str(value).strip().replace("Z", "+00:00")
    if "T" not in text and " " not in text:
        return False
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        return False

def _parse_date(value):
    if isinstance(value, (pd.Timestamp, datetime)):
        try: return pd.Timestamp(value)
        except (ValueError, TypeError): return None
    if isinstance(value, date):
        return pd.Timestamp(value)
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try: return pd.Timestamp(datetime.strptime(text, fmt))
        except ValueError: pass
    try:
        if _is_datetime_text(text): return pd.Timestamp(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except (ValueError, TypeError): pass
    return None

def _safe_value(value):
    if value is None or value is pd.NA or (isinstance(value, (float, np.floating)) and not math.isfinite(float(value))):
        return None
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)

def _percentage(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) * 100 / float(denominator), 4) if denominator else 0.0

def _numeric_statistics(series: pd.Series) -> dict | None:
    parsed = [_parse_number(value) for value in series.dropna()]
    values = pd.Series([value for value in parsed if value is not None], dtype="float64")
    valid_count = len(values)
    invalid_count = len(parsed) - valid_count
    conversion = _percentage(valid_count, len(parsed))
    if values.empty:
        return {"count": 0, "valid_numeric_values": 0, "invalid_numeric_values": invalid_count, "numeric_conversion_percentage": conversion, "histogram": [], "mean": None, "median": None, "minimum": None, "maximum": None, "standard_deviation": None, "q25": None, "q50": None, "q75": None}
    quantiles = values.quantile([0.25, 0.5, 0.75])
    def finite(value):
        result = float(value)
        return result if math.isfinite(result) else None
    std = values.std(ddof=1) if len(values) > 1 else np.nan
    edges = np.histogram_bin_edges(values.to_numpy(), bins=min(10, max(1, int(math.sqrt(len(values))))))
    counts, edges = np.histogram(values.to_numpy(), bins=edges)
    histogram = [{"bin_start": float(edges[i]), "bin_end": float(edges[i + 1]), "count": int(counts[i])} for i in range(len(counts))]
    return {"count": int(values.count()), "valid_numeric_values": valid_count, "invalid_numeric_values": invalid_count, "numeric_conversion_percentage": conversion, "histogram": histogram, "mean": finite(values.mean()), "median": finite(values.median()),
            "minimum": finite(values.min()), "maximum": finite(values.max()), "standard_deviation": finite(std),
            "q25": finite(quantiles.loc[0.25]), "q50": finite(quantiles.loc[0.5]), "q75": finite(quantiles.loc[0.75])}

def _categorical_statistics(series: pd.Series, non_null_count: int) -> dict:
    counts = series.dropna().value_counts(dropna=True).head(10)
    top_values = [{"value": _safe_value(value), "count": int(count), "percentage": _percentage(count, non_null_count)} for value, count in counts.items()]
    return {"distinct_count": int(series.nunique(dropna=True)), "top_values": top_values}

def build_profile(frame: pd.DataFrame) -> dict:
    """Profile a copy of a tabular frame and return JSON-safe summary metrics."""
    data = _normalize_frame(frame)
    rows, columns = data.shape
    missing_cells = int(data.isna().to_numpy().sum()) if rows and columns else 0
    cell_count = rows * columns
    duplicate_rows = int(data.duplicated(keep="first").sum()) if rows else 0
    column_profiles = []
    detected_types = []

    for position, name in enumerate(data.columns):
        series = data.iloc[:, position]
        kind = _column_type(name, series)
        detected_types.append(kind)
        non_null = int(series.notna().sum())
        missing = rows - non_null
        distinct = int(series.nunique(dropna=True)) if non_null else 0
        numeric_stats = _numeric_statistics(series) if kind in {"integer", "float", "number", "numeric_mixed"} else None
        categorical_stats = _categorical_statistics(series, non_null) if kind in {"categorical", "boolean"} else None
        identifier_stats = None
        if kind == "identifier":
            identifier_stats = {"duplicate_identifier_count": max(0, non_null - distinct), "sample_values": [_safe_value(value) for value in series.dropna().head(5)]}
        date_stats = None
        if kind in {"date", "datetime"}:
            dates = [_parse_date(value) for value in series.dropna()]
            valid_dates = [value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC") for value in dates if value is not None]
            invalid_dates = len(dates) - len(valid_dates)
            distinct = len({value.isoformat() for value in valid_dates})
            date_stats = {"valid_date_count": len(valid_dates), "invalid_date_count": invalid_dates, "missing_date_count": missing,
                          "earliest_date": min(valid_dates).isoformat() if valid_dates else None,
                          "latest_date": max(valid_dates).isoformat() if valid_dates else None}
        column_profiles.append({
            "name": str(name), "detected_type": kind, "total_records": rows, "non_null_count": non_null,
            "missing_count": missing, "missing_percentage": _percentage(missing, rows),
            "distinct_count": distinct, "unique_percentage": _percentage(distinct, non_null),
            "numeric_statistics": numeric_stats, "categorical_statistics": categorical_stats,
            "identifier_statistics": identifier_stats, "date_statistics": date_stats,
        })

    return {
        "total_rows": int(rows), "total_columns": int(columns), "total_missing_cells": missing_cells,
        "missing_cell_percentage": _percentage(missing_cells, cell_count), "duplicate_rows": duplicate_rows,
        "duplicate_row_percentage": _percentage(duplicate_rows, rows), "unique_rows": int(rows - duplicate_rows),
        "numeric_column_count": sum(kind in {"integer", "float", "number", "numeric_mixed"} for kind in detected_types),
        "categorical_column_count": sum(kind in {"categorical", "identifier"} for kind in detected_types),
        "date_column_count": sum(kind in {"date", "datetime"} for kind in detected_types),
        "boolean_column_count": sum(kind == "boolean" for kind in detected_types),
        "overall_completeness_percentage": _percentage(cell_count - missing_cells, cell_count),
        "columns": column_profiles,
    }

def load_dataset_frame(path: Path, file_format: str, max_bytes: int, storage_root: Path) -> pd.DataFrame:
    if file_format not in {"csv", "json"}:
        raise UnsupportedProfileFormat
    try:
        root = storage_root.resolve()
        source = path.resolve()
        if source.parent != root:
            raise ProfileSourceMissing
        if not source.is_file():
            raise ProfileSourceMissing
        if source.stat().st_size > max_bytes:
            raise ProfileTooLarge
        if file_format == "csv":
            try:
                return pd.read_csv(source, encoding="utf-8-sig", dtype=object)
            except pd.errors.EmptyDataError:
                return pd.DataFrame()
        raw = json.loads(source.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            rows = raw.get("data") if isinstance(raw.get("data"), list) else [raw]
        else:
            rows = raw
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise InvalidProfileSource
        return pd.DataFrame(rows)
    except (ProfileError,):
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, pd.errors.ParserError, ValueError, OSError) as exc:
        raise InvalidProfileSource from exc
