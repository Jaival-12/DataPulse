"""Pure, bounded on-demand analytics for original and processed DataPulse files."""
from __future__ import annotations

from collections import Counter
from typing import Any, Literal

import numpy as np
import pandas as pd

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.pipeline import ProcessedDataset
from app.services.pipeline_service import PipelineInputError, ProcessedFileError, safe_processed_path, source_path
from app.services.profiling_service import (
    InvalidProfileSource, ProfileSourceMissing, ProfileTooLarge, UnsupportedProfileFormat,
    _parse_date, _parse_number, _safe_value, build_profile, load_dataset_frame,
)
from app.utils.analytics_helpers import (
    MAX_AGGREGATE_GROUPS, MAX_CORRELATION_COLUMNS, MAX_HISTOGRAM_BINS,
    MAX_TIMESERIES_POINTS, MAX_TOP_VALUES, generated_at, is_missing, json_key, numeric_values, parsed_dates, safe_number,
)

NUMERIC_TYPES = {"integer", "float", "number", "numeric_mixed"}
DATE_TYPES = {"date", "datetime"}


class AnalyticsColumnError(ValueError):
    pass


class AnalyticsRequestError(ValueError):
    pass


class AnalyticsLineageError(ValueError):
    pass


def load_original_analytics(dataset: Dataset) -> tuple[pd.DataFrame, int]:
    if dataset.format not in {"csv", "json"}:
        raise UnsupportedProfileFormat
    try:
        path = source_path(dataset, settings.storage_dir)
    except PipelineInputError as exc:
        if "unavailable" in str(exc):
            raise ProfileSourceMissing from exc
        raise InvalidProfileSource from exc
    frame = load_dataset_frame(path, dataset.format, settings.max_profile_mb * 1024 * 1024, settings.storage_dir)
    return frame, int(path.stat().st_size)


def load_processed_analytics(dataset: ProcessedDataset) -> tuple[pd.DataFrame, int]:
    if dataset.file_type not in {"csv", "json"}:
        raise UnsupportedProfileFormat
    path = safe_processed_path(settings.storage_dir, dataset.storage_path)
    frame = load_dataset_frame(path, dataset.file_type, settings.max_profile_mb * 1024 * 1024, path.parent)
    return frame, int(path.stat().st_size)


def load_analytics_reference(db, reference) -> tuple[pd.DataFrame, int, Dataset | ProcessedDataset]:
    if reference.type == "original":
        source = db.get(Dataset, reference.id)
        if source is None:
            raise LookupError("Dataset not found.")
        frame, size = load_original_analytics(source)
        return frame, size, source
    source = db.get(ProcessedDataset, reference.id)
    if source is None:
        raise LookupError("Processed dataset not found.")
    frame, size = load_processed_analytics(source)
    return frame, size, source


def compare_references(db, left_reference, right_reference) -> dict[str, Any]:
    left, left_size, left_record = load_analytics_reference(db, left_reference)
    right, right_size, right_record = load_analytics_reference(db, right_reference)
    if left_reference.type == "original":
        if left_record.id != right_record.source_dataset_id:
            raise AnalyticsLineageError("Original and processed datasets do not share the same source lineage.")
    elif right_reference.type == "original":
        if right_record.id != left_record.source_dataset_id:
            raise AnalyticsLineageError("Original and processed datasets do not share the same source lineage.")
    elif left_record.source_dataset_id != right_record.source_dataset_id:
        raise AnalyticsLineageError("Processed datasets do not share the same source lineage.")
    result = compare_frames(left, right, left_size_bytes=left_size, right_size_bytes=right_size)
    result["left"].update({"type": left_reference.type, "id": left_reference.id})
    result["right"].update({"type": right_reference.type, "id": right_reference.id})
    return result


def _profile_column(frame: pd.DataFrame, column_name: str, profile_data: dict[str, Any] | None = None) -> tuple[dict[str, Any], pd.Series]:
    matches = [index for index, name in enumerate(frame.columns) if str(name) == column_name]
    if not matches:
        raise AnalyticsColumnError(f"Column '{column_name}' was not found.")
    profile = profile_data if profile_data is not None else build_profile(frame)
    return profile["columns"][matches[0]], frame.iloc[:, matches[0]]


def _numeric_summary(series: pd.Series) -> dict[str, Any]:
    converted, missing_count, invalid_count = numeric_values(series)
    values = np.asarray([value for value in converted if value is not None], dtype="float64")
    count = int(values.size)
    if count:
        quartiles = np.quantile(values, [0.25, 0.5, 0.75])
        edges = np.histogram_bin_edges(values, bins=min(MAX_HISTOGRAM_BINS, max(1, int(np.sqrt(count)))))
        frequencies, edges = np.histogram(values, bins=edges)
        histogram = [{"bin_start": safe_number(edges[i]), "bin_end": safe_number(edges[i + 1]), "count": int(frequencies[i])} for i in range(len(frequencies))]
        mean = safe_number(np.mean(values))
        median = safe_number(np.median(values))
        minimum = safe_number(np.min(values))
        maximum = safe_number(np.max(values))
        variance = safe_number(np.var(values, ddof=1)) if count > 1 else None
        standard_deviation = safe_number(np.std(values, ddof=1)) if count > 1 else None
        q25, q50, q75 = (safe_number(value) for value in quartiles)
    else:
        histogram = []
        mean = median = minimum = maximum = variance = standard_deviation = q25 = q50 = q75 = None
    return {
        "count": count, "missing_count": missing_count, "invalid_count": invalid_count,
        "mean": mean, "median": median, "minimum": minimum, "maximum": maximum,
        "range": safe_number(maximum - minimum) if maximum is not None and minimum is not None else None,
        "standard_deviation": standard_deviation, "variance": variance,
        "q25": q25, "q50": q50, "q75": q75,
        "distinct_count": int(len(set(values.tolist()))), "histogram": histogram,
    }


def _categorical_summary(series: pd.Series) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    values: dict[str, Any] = {}
    missing_count = 0
    for value in series.tolist():
        if is_missing(value):
            missing_count += 1
            continue
        key = json_key(value)
        counts[key] += 1
        values[key] = _safe_value(value)
    non_null_count = sum(counts.values())
    top = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:MAX_TOP_VALUES]
    return {
        "non_null_count": non_null_count,
        "distinct_count": len(counts),
        "top_values": [{"value": values[key], "count": count, "percentage": round(count * 100 / non_null_count, 4) if non_null_count else 0.0} for key, count in top],
        "missing_count": missing_count,
        "cardinality": len(counts),
    }


def analyze_column(frame: pd.DataFrame, column_name: str, profile_data: dict[str, Any] | None = None) -> dict[str, Any]:
    column, series = _profile_column(frame, column_name, profile_data)
    kind = column["detected_type"]
    result: dict[str, Any] = {
        "name": column_name, "detected_type": kind,
        "non_null_count": int(column["non_null_count"]), "missing_count": int(column["missing_count"]),
        "distinct_count": int(column["distinct_count"]), "numeric": None, "categorical": None, "date": None,
    }
    if kind in NUMERIC_TYPES or kind == "empty":
        result["numeric"] = _numeric_summary(series)
    elif kind in DATE_TYPES:
        dates, missing, invalid = parsed_dates(series)
        valid = [value for value in dates if value is not None]
        result["date"] = {
            "valid_count": len(valid), "invalid_count": invalid, "missing_count": missing,
            "earliest": min(valid).isoformat() if valid else None,
            "latest": max(valid).isoformat() if valid else None,
        }
    else:
        result["categorical"] = _categorical_summary(series)
    return result


def analyze_overview(frame: pd.DataFrame, dataset_size_bytes: int) -> dict[str, Any]:
    profile = build_profile(frame)
    columns = profile["columns"]
    return {
        "total_records": profile["total_rows"], "total_columns": profile["total_columns"],
        "numeric_columns": [item["name"] for item in columns if item["detected_type"] in NUMERIC_TYPES],
        "categorical_columns": [item["name"] for item in columns if item["detected_type"] in {"categorical", "string", "boolean", "identifier"}],
        "date_columns": [item["name"] for item in columns if item["detected_type"] in DATE_TYPES],
        "missing_cells": profile["total_missing_cells"], "duplicate_records": profile["duplicate_rows"],
        "dataset_size_bytes": int(dataset_size_bytes), "generated_at": generated_at(),
    }


def analyze_columns(frame: pd.DataFrame) -> list[dict[str, Any]]:
    profile = build_profile(frame)
    result = []
    for column in profile["columns"]:
        result.append({"name": column["name"], "detected_type": column["detected_type"],
                       "non_null_count": column["non_null_count"], "missing_count": column["missing_count"],
                       "distinct_count": column["distinct_count"],
                       "invalid_count": (column.get("numeric_statistics") or {}).get("invalid_numeric_values", 0)
                       + (column.get("date_statistics") or {}).get("invalid_date_count", 0)})
    return result


def _date_group(value: pd.Timestamp, granularity: str) -> str:
    if granularity == "daily":
        return value.strftime("%Y-%m-%d")
    if granularity == "weekly":
        iso = value.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return value.strftime("%Y-%m")


def analyze_timeseries(frame: pd.DataFrame, date_column: str, granularity: Literal["daily", "weekly", "monthly"],
                       measure_column: str | None = None, aggregation: Literal["sum", "average", "count"] = "count",
                       limit: int = MAX_TIMESERIES_POINTS) -> dict[str, Any]:
    if not 1 <= limit <= MAX_TIMESERIES_POINTS:
        raise AnalyticsRequestError(f"Time-series result limit must be between 1 and {MAX_TIMESERIES_POINTS}.")
    date_profile, date_series = _profile_column(frame, date_column)
    if date_profile["detected_type"] not in DATE_TYPES and not (frame.empty and date_profile["detected_type"] == "empty"):
        raise AnalyticsRequestError(f"Column '{date_column}' is not detected as a date or datetime column.")
    if measure_column is not None:
        measure_profile, measure_series = _profile_column(frame, measure_column)
        if aggregation != "count" and measure_profile["detected_type"] not in NUMERIC_TYPES | {"empty"}:
            raise AnalyticsRequestError(f"Measure column '{measure_column}' is not numeric.")
        measure_converted, _, measure_invalid = numeric_values(measure_series)
    else:
        measure_series = None
        measure_converted = [None] * len(frame)
        measure_invalid = 0
    if aggregation != "count" and measure_series is None:
        raise AnalyticsRequestError("A numeric measure column is required for sum and average.")
    dates, missing_count, invalid_count = parsed_dates(date_series)
    periods: dict[str, dict[str, Any]] = {}
    valid_date_count = 0
    for index, parsed in enumerate(dates):
        if parsed is None:
            continue
        valid_date_count += 1
        period = _date_group(parsed, granularity)
        item = periods.setdefault(period, {"record_count": 0, "measure_sum": 0.0, "measure_count": 0})
        item["record_count"] += 1
        number = measure_converted[index]
        if number is not None:
            item["measure_sum"] += number
            item["measure_count"] += 1
    ordered_periods = sorted(periods)
    points = []
    for period in ordered_periods[:limit]:
        item = periods[period]
        if aggregation == "count":
            aggregate = item["record_count"]
        elif item["measure_count"] == 0:
            aggregate = None
        elif aggregation == "sum":
            aggregate = safe_number(item["measure_sum"])
        else:
            aggregate = safe_number(item["measure_sum"] / item["measure_count"])
        points.append({"period": period, "record_count": item["record_count"], "aggregate_value": aggregate})
    return {"date_column": date_column, "granularity": granularity, "measure_column": measure_column,
            "aggregation": aggregation, "valid_date_count": valid_date_count,
            "invalid_date_count": invalid_count, "missing_date_count": missing_count,
            "invalid_measure_count": measure_invalid, "total_periods": len(ordered_periods),
            "truncated": len(ordered_periods) > limit, "points": points}


def analyze_correlation(frame: pd.DataFrame, profile_data: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = profile_data if profile_data is not None else build_profile(frame)
    profiles = profile["columns"]
    columns = [item["name"] for item in profiles if item["detected_type"] in NUMERIC_TYPES]
    if len(columns) > MAX_CORRELATION_COLUMNS:
        raise AnalyticsRequestError(f"Correlation is limited to {MAX_CORRELATION_COLUMNS} numeric columns per request.")
    if len(columns) < 2:
        return {"numeric_columns": columns, "correlations": {}, "pair_counts": {}}
    numeric = {}
    for name in columns:
        converted, _, _ = numeric_values(frame[name])
        numeric[name] = np.asarray([np.nan if value is None else value for value in converted], dtype="float64")
    matrix: dict[str, dict[str, float | None]] = {name: {} for name in columns}
    counts: dict[str, dict[str, int]] = {name: {} for name in columns}
    for left_index, left in enumerate(columns):
        for right in columns[left_index:]:
            valid = np.isfinite(numeric[left]) & np.isfinite(numeric[right])
            x, y = numeric[left][valid], numeric[right][valid]
            count = int(valid.sum())
            value: float | None = None
            if count >= 2:
                if np.ptp(x) > 0 and np.ptp(y) > 0:
                    value = safe_number(np.corrcoef(x, y)[0, 1])
            matrix[left][right] = value
            matrix[right][left] = value
            counts[left][right] = count
            counts[right][left] = count
    return {"numeric_columns": columns, "correlations": matrix, "pair_counts": counts}


def aggregate_frame(frame: pd.DataFrame, group_by: str, operation: Literal["count", "sum", "average", "minimum", "maximum"],
                    measure_column: str | None = None, limit: int = MAX_AGGREGATE_GROUPS,
                    date_granularity: Literal["daily", "weekly", "monthly"] | None = None) -> dict[str, Any]:
    if not 1 <= limit <= MAX_AGGREGATE_GROUPS:
        raise AnalyticsRequestError(f"Result limit must be between 1 and {MAX_AGGREGATE_GROUPS}.")
    group_profile, groups = _profile_column(frame, group_by)
    if date_granularity is None and group_profile["detected_type"] not in {"categorical", "string", "boolean", "identifier"} and not (frame.empty and group_profile["detected_type"] == "empty"):
        raise AnalyticsRequestError("group_by must be categorical or date-derived with date_granularity.")
    if date_granularity is not None and group_profile["detected_type"] not in DATE_TYPES and not (frame.empty and group_profile["detected_type"] == "empty"):
        raise AnalyticsRequestError("date_granularity can only be used with a date or datetime group_by column.")
    date_values: list[pd.Timestamp | None] | None = None
    dropped_missing = dropped_invalid = 0
    if date_granularity:
        date_values, dropped_missing, dropped_invalid = parsed_dates(groups)
    if operation != "count" and measure_column is None:
        raise AnalyticsRequestError(f"A measure column is required for {operation}.")
    measure: pd.Series | None = None
    converted: list[float | None] = []
    if measure_column:
        measure_profile, measure = _profile_column(frame, measure_column)
        if operation != "count" and measure_profile["detected_type"] not in NUMERIC_TYPES | {"empty"}:
            raise AnalyticsRequestError(f"Measure column '{measure_column}' is not numeric.")
        converted, _, _ = numeric_values(measure)
    buckets: dict[str, dict[str, Any]] = {}
    for index, raw_group in enumerate(groups.tolist()):
        if date_granularity:
            group_date = date_values[index]
            if group_date is None:
                continue
            key_value = _date_group(group_date, date_granularity)
        else:
            key_value = None if is_missing(raw_group) else _safe_value(raw_group)
        key = json_key(key_value)
        bucket = buckets.setdefault(key, {"group": key_value, "record_count": 0, "value_sum": 0.0,
                                          "valid_count": 0, "missing_count": 0, "invalid_count": 0,
                                          "minimum": None, "maximum": None})
        bucket["record_count"] += 1
        if measure is not None:
            number = converted[index]
            if is_missing(measure.iloc[index]):
                bucket["missing_count"] += 1
            elif number is None:
                bucket["invalid_count"] += 1
            else:
                bucket["value_sum"] += number
                bucket["valid_count"] += 1
                bucket["minimum"] = number if bucket["minimum"] is None else min(bucket["minimum"], number)
                bucket["maximum"] = number if bucket["maximum"] is None else max(bucket["maximum"], number)
    all_groups = []
    for bucket in buckets.values():
        if operation == "count":
            value = bucket["record_count"]
        elif not bucket["valid_count"]:
            value = None
        elif operation == "sum":
            value = safe_number(bucket["value_sum"])
        elif operation == "average":
            value = safe_number(bucket["value_sum"] / bucket["valid_count"])
        elif operation == "minimum":
            value = bucket["minimum"]
        else:
            value = bucket["maximum"]
        all_groups.append({"group": bucket["group"], "record_count": bucket["record_count"], "aggregate_value": value,
                           "valid_count": bucket["valid_count"], "missing_count": bucket["missing_count"],
                           "invalid_count": bucket["invalid_count"]})
    all_groups.sort(key=lambda item: (-item["record_count"], json_key(item["group"])))
    return {"group_by": group_by, "operation": operation, "measure_column": measure_column,
            "date_granularity": date_granularity, "total_groups": len(all_groups),
            "truncated": len(all_groups) > limit, "groups": all_groups[:limit],
            "dropped_missing_group_values": dropped_missing,
            "dropped_invalid_group_values": dropped_invalid}


def _summary_for_compare(frame: pd.DataFrame) -> dict[str, Any]:
    profile = build_profile(frame)
    return {"total_records": profile["total_rows"], "total_columns": profile["total_columns"],
            "missing_cells": profile["total_missing_cells"], "duplicate_records": profile["duplicate_rows"],
            "columns": profile["columns"]}


def compare_frames(left: pd.DataFrame, right: pd.DataFrame, *, left_size_bytes: int, right_size_bytes: int) -> dict[str, Any]:
    left_summary, right_summary = _summary_for_compare(left), _summary_for_compare(right)
    left_names = [str(name) for name in left.columns]
    right_names = [str(name) for name in right.columns]
    common = [name for name in left_names if name in set(right_names)]
    removed, added = [name for name in left_names if name not in common], [name for name in right_names if name not in common]
    possible_renames = []
    if len(left) == len(right):
        left_signatures: dict[str, list[str]] = {name: [json_key(value) for value in left.iloc[:, index].tolist()] for index, name in enumerate(left_names) if name in removed}
        right_signatures: dict[str, list[str]] = {name: [json_key(value) for value in right.iloc[:, index].tolist()] for index, name in enumerate(right_names) if name in added}
        pairs = [(old, new) for old in removed for new in added if left_signatures[old] == right_signatures[new]]
        used_left: set[str] = set()
        used_right: set[str] = set()
        for old, new in pairs:
            if old not in used_left and new not in used_right:
                possible_renames.append({"from": old, "to": new, "confidence": "exact_values"})
                used_left.add(old)
                used_right.add(new)
        removed = [name for name in removed if name not in used_left]
        added = [name for name in added if name not in used_right]
    left_profiles = {item["name"]: item for item in left_summary["columns"]}
    right_profiles = {item["name"]: item for item in right_summary["columns"]}
    numeric_changes = {}
    categorical_changes = {}
    for name in common:
        left_detail, right_detail = analyze_column(left, name), analyze_column(right, name)
        if left_detail["numeric"] is not None and right_detail["numeric"] is not None:
            a, b = left_detail["numeric"], right_detail["numeric"]
            numeric_changes[name] = {"left": a, "right": b,
                                     "mean_change": safe_number(b["mean"] - a["mean"]) if a["mean"] is not None and b["mean"] is not None else None,
                                     "minimum_change": safe_number(b["minimum"] - a["minimum"]) if a["minimum"] is not None and b["minimum"] is not None else None,
                                     "maximum_change": safe_number(b["maximum"] - a["maximum"]) if a["maximum"] is not None and b["maximum"] is not None else None}
        if left_detail["categorical"] is not None and right_detail["categorical"] is not None:
            categorical_changes[name] = {"left_top_values": left_detail["categorical"]["top_values"],
                                          "right_top_values": right_detail["categorical"]["top_values"]}
    return {
        "left": {"total_records": left_summary["total_records"], "total_columns": left_summary["total_columns"], "dataset_size_bytes": left_size_bytes},
        "right": {"total_records": right_summary["total_records"], "total_columns": right_summary["total_columns"], "dataset_size_bytes": right_size_bytes},
        "row_count_change": right_summary["total_records"] - left_summary["total_records"],
        "column_count_change": right_summary["total_columns"] - left_summary["total_columns"],
        "missing_cells_change": right_summary["missing_cells"] - left_summary["missing_cells"],
        "duplicate_records_change": right_summary["duplicate_records"] - left_summary["duplicate_records"],
        "common_columns": common, "added_columns": added, "removed_columns": removed,
        "possible_renames": possible_renames, "numeric_changes": numeric_changes,
        "categorical_changes": categorical_changes, "generated_at": generated_at(),
    }
