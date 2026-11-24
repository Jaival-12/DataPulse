"""Validated, deterministic DataFrame transformations for ETL pipelines."""
from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Any

import numpy as np
import pandas as pd


class TransformationError(ValueError):
    """A step configuration or value cannot be safely applied."""


TEXT_OPERATIONS = {"trim_whitespace", "lowercase", "uppercase", "title_case"}
OPERATIONS = {
    "remove_duplicates", "fill_missing", "rename_columns", "remove_columns",
    "reorder_columns", "filter_rows", "convert_type", "add_calculated_column",
    *TEXT_OPERATIONS,
}
FILTER_OPERATORS = {
    "equals", "not_equals", "greater_than", "less_than", "greater_than_or_equal",
    "less_than_or_equal", "contains", "not_contains", "is_null", "is_not_null",
}
NUMERIC_OPERATORS = {"greater_than", "less_than", "greater_than_or_equal", "less_than_or_equal"}


def _require_keys(config: dict[str, Any], required: set[str], allowed: set[str]) -> None:
    missing = required - config.keys()
    extra = config.keys() - allowed
    if missing:
        raise TransformationError(f"Missing configuration field(s): {', '.join(sorted(missing))}.")
    if extra:
        raise TransformationError(f"Unknown configuration field(s): {', '.join(sorted(extra))}.")


def _columns(frame: pd.DataFrame, columns: Any) -> list[str]:
    if not isinstance(columns, list) or not columns or any(not isinstance(c, str) or not c for c in columns):
        raise TransformationError("columns must be a non-empty list of column names.")
    if len(set(columns)) != len(columns):
        raise TransformationError("columns must not contain duplicates.")
    missing = [name for name in columns if name not in frame.columns]
    if missing:
        raise TransformationError(f"Column(s) not found: {', '.join(missing)}.")
    return columns


def _column(frame: pd.DataFrame, name: Any) -> str:
    if not isinstance(name, str) or name not in frame.columns:
        raise TransformationError(f"Column not found: {name}.")
    return name


def _coerce_numeric_series(series: pd.Series, column: str) -> pd.Series:
    try:
        values = pd.to_numeric(series, errors="coerce")
    except (ValueError, TypeError) as exc:
        raise TransformationError(f"Column '{column}' must contain numeric values.") from exc
    invalid = series.notna() & values.isna()
    nonfinite = values.notna() & ~np.isfinite(values)
    if invalid.any() or nonfinite.any():
        raise TransformationError(f"Column '{column}' must contain numeric values.")
    return values


def _is_missing(value: Any) -> bool:
    if value is None or value is pd.NA or value is pd.NaT:
        return True
    try:
        missing = pd.isna(value)
        if missing is pd.NA:
            return True
        return bool(missing) if np.isscalar(missing) else False
    except (TypeError, ValueError):
        return False


def _rename(frame: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    _require_keys(config, {"mapping"}, {"mapping"})
    mapping = config["mapping"]
    if not isinstance(mapping, dict) or not mapping:
        raise TransformationError("mapping must be a non-empty object of old and new column names.")
    _columns(frame, list(mapping))
    if any(not isinstance(new, str) or not new.strip() for new in mapping.values()):
        raise TransformationError("New column names must be non-empty strings.")
    names = [mapping.get(name, name) for name in frame.columns]
    if len(set(names)) != len(names):
        raise TransformationError("Rename would create a duplicate column name that already exists.")
    result = frame.rename(columns=mapping).copy()
    return result, {"renamed_columns": mapping}


def _fill_missing(frame: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    if config.get("strategy") == "drop_rows":
        _require_keys(config, {"strategy"}, {"strategy", "columns"})
        subset = _columns(frame, config["columns"]) if "columns" in config else None
        before = len(frame)
        result = frame.dropna(subset=subset).copy()
        return result, {"removed_rows": before - len(result), "strategy": "drop_rows"}
    _require_keys(config, {"column", "strategy"}, {"column", "strategy", "value"})
    name = _column(frame, config["column"])
    strategy = config["strategy"]
    series = frame[name]
    missing_count = int(series.isna().sum())
    if strategy == "constant":
        if "value" not in config or config["value"] is None or isinstance(config["value"], (dict, list)):
            raise TransformationError("constant strategy requires a non-null scalar value.")
        fill_value = config["value"]
    elif strategy in {"mean", "median"}:
        if pd.api.types.is_bool_dtype(series):
            raise TransformationError(f"{strategy} fill requires a numeric column.")
        numeric_values = _coerce_numeric_series(series, name)
        if numeric_values.notna().sum() == 0:
            raise TransformationError(f"{strategy} fill requires at least one non-missing value.")
        fill_value = float(numeric_values.mean() if strategy == "mean" else numeric_values.median())
    elif strategy == "mode":
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            raise TransformationError("mode fill requires a categorical or string column.")
        modes = series.dropna().mode()
        if modes.empty:
            raise TransformationError("mode fill requires at least one non-missing value.")
        fill_value = modes.iloc[0]
    else:
        raise TransformationError("strategy must be drop_rows, constant, mean, median, or mode.")
    result = frame.copy()
    result[name] = result[name].fillna(fill_value)
    return result, {"filled_values": missing_count, "strategy": strategy, "column": name}


def _filter_rows(frame: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    operator = config.get("operator")
    required = {"column", "operator"} if operator in {"is_null", "is_not_null"} else {"column", "operator", "value"}
    _require_keys(config, required, {"column", "operator", "value"})
    name = _column(frame, config["column"])
    if operator not in FILTER_OPERATORS:
        raise TransformationError(f"operator must be one of: {', '.join(sorted(FILTER_OPERATORS))}.")
    series = frame[name]
    value = config.get("value")
    if operator == "is_null":
        mask = series.isna()
    elif operator == "is_not_null":
        mask = series.notna()
    elif operator in {"contains", "not_contains"}:
        if not isinstance(value, str) or not series.dropna().map(lambda item: isinstance(item, str)).all():
            raise TransformationError(f"{operator} requires a string value and string column.")
        mask = series.astype("string").str.contains(re.escape(value), regex=True, na=False)
        if operator == "not_contains":
            mask = series.notna() & ~mask
    else:
        if isinstance(value, (dict, list)):
            raise TransformationError("Filter value must be a scalar.")
        if operator in {"equals", "not_equals"} and value is None:
            raise TransformationError("Use is_null or is_not_null for missing values.")
        if operator in NUMERIC_OPERATORS or (isinstance(value, (int, float)) and not isinstance(value, bool) and not pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or pd.api.types.is_bool_dtype(series):
                raise TransformationError(f"{operator} requires a numeric column and numeric value.")
            compared = _coerce_numeric_series(series, name)
        else:
            compared = series
        try:
            operations = {
                "equals": lambda: compared == value,
                "not_equals": lambda: compared != value,
                "greater_than": lambda: compared > value,
                "less_than": lambda: compared < value,
                "greater_than_or_equal": lambda: compared >= value,
                "less_than_or_equal": lambda: compared <= value,
            }
            mask = operations[operator]()
        except (TypeError, ValueError) as exc:
            raise TransformationError(f"Cannot apply {operator} to column '{name}'.") from exc
        mask = mask.fillna(False)
    result = frame.loc[mask].copy()
    return result, {"removed_rows": len(frame) - len(result), "operator": operator, "column": name}


def _strict_date(value: Any) -> pd.Timestamp:
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return pd.Timestamp(datetime.strptime(text, fmt).date())
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return pd.Timestamp(parsed)
    except ValueError as exc:
        raise TransformationError(f"cannot convert value '{text}' to date.") from exc


def _convert_type(frame: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    _require_keys(config, {"column", "target_type"}, {"column", "target_type"})
    name = _column(frame, config["column"])
    target = config["target_type"]
    if target not in {"string", "integer", "float", "boolean", "date"}:
        raise TransformationError("target_type must be string, integer, float, boolean, or date.")
    series = frame[name]
    try:
        if target == "string":
            converted = series.map(lambda value: value if _is_missing(value) else str(value))
        elif target in {"integer", "float"}:
            values = pd.to_numeric(series, errors="raise")
            if (series.notna() & values.isna()).any() or (values.notna() & ~np.isfinite(values)).any():
                raise ValueError("non-finite or invalid values cannot be converted")
            if target == "integer":
                if ((values.dropna() % 1) != 0).any():
                    raise ValueError("fractional values cannot be converted to integer")
                converted = values.astype("Int64")
            else:
                converted = values.astype("Float64")
        elif target == "boolean":
            mapping = {True: True, False: False, 1: True, 0: False, "true": True, "false": False, "1": True, "0": False}
            def parse_bool(value):
                if pd.isna(value): return pd.NA
                key = value.strip().lower() if isinstance(value, str) else value
                if key not in mapping: raise ValueError(f"invalid boolean value '{value}'")
                return mapping[key]
            converted = series.map(parse_bool).astype("boolean")
        else:
            converted = series.map(lambda value: pd.NaT if _is_missing(value) else _strict_date(value).date())
    except (ValueError, TypeError, OverflowError, TransformationError) as exc:
        raise TransformationError(f"Column '{name}' cannot convert to {target}: {exc}.") from exc
    result = frame.copy()
    result[name] = converted
    return result, {"column": name, "target_type": target, "converted_values": int(series.notna().sum())}


def _calculated_column(frame: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    _require_keys(config, {"name", "left", "operator", "right"}, {"name", "left", "operator", "right"})
    name = config["name"]
    if not isinstance(name, str) or not name.strip():
        raise TransformationError("Calculated output name must be a non-empty string.")
    if name in frame.columns:
        raise TransformationError(f"Calculated output column '{name}' already exists.")
    def operand(spec: Any) -> pd.Series | float:
        if isinstance(spec, dict) and set(spec) == {"column"}:
            col = _column(frame, spec["column"])
            values = frame[col]
            if pd.api.types.is_bool_dtype(values):
                raise TransformationError(f"Calculated operand '{col}' must be numeric.")
            try:
                converted = pd.to_numeric(values, errors="raise")
            except (ValueError, TypeError) as exc:
                raise TransformationError(f"Calculated operand '{col}' must be numeric.") from exc
            if (values.notna() & converted.isna()).any() or (converted.notna() & ~np.isfinite(converted)).any():
                raise TransformationError(f"Calculated operand '{col}' must contain finite numeric values.")
            return converted
        if isinstance(spec, (int, float)) and not isinstance(spec, bool) and math.isfinite(float(spec)):
            return float(spec)
        raise TransformationError("Each calculated operand must be a column reference or finite number operand.")
    op = config["operator"]
    if op not in {"add", "subtract", "multiply", "divide"}:
        raise TransformationError("operator must be add, subtract, multiply, or divide.")
    left, right = operand(config["left"]), operand(config["right"])
    try:
        if op == "add": calculated = left + right
        elif op == "subtract": calculated = left - right
        elif op == "multiply": calculated = left * right
        else:
            if isinstance(right, pd.Series):
                zero = right.eq(0) & right.notna()
                if zero.any(): raise TransformationError("Division by zero is not allowed.")
            elif right == 0:
                raise TransformationError("Division by zero is not allowed.")
            calculated = left / right
        if isinstance(calculated, pd.Series) and np.isinf(pd.to_numeric(calculated, errors="coerce")).any():
            raise TransformationError("Calculated result is not finite.")
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        if isinstance(exc, TransformationError): raise
        raise TransformationError(f"Calculated operation failed: {exc}.") from exc
    result = frame.copy()
    result[name] = calculated
    return result, {"output_column": name, "operator": op}


def apply_transformation(frame: pd.DataFrame, operation: str, config: dict[str, Any]) -> tuple[pd.DataFrame, dict]:
    """Apply one validated operation and return a new frame and step summary."""
    if operation not in OPERATIONS:
        raise TransformationError(f"Unsupported operation '{operation}'.")
    if not isinstance(config, dict):
        raise TransformationError("Step configuration must be an object.")
    original = frame.copy(deep=True)
    if operation == "remove_duplicates":
        _require_keys(config, set(), {"subset"})
        subset = _columns(original, config["subset"]) if config.get("subset") is not None else None
        result = original.drop_duplicates(subset=subset, keep="first").copy()
        return result, {"removed_rows": len(original) - len(result)}
    if operation == "fill_missing": return _fill_missing(original, config)
    if operation == "rename_columns": return _rename(original, config)
    if operation == "remove_columns":
        _require_keys(config, {"columns"}, {"columns"})
        columns = _columns(original, config["columns"])
        if len(columns) == len(original.columns): raise TransformationError("At least one column must remain.")
        result = original.drop(columns=columns).copy()
        return result, {"removed_columns": columns}
    if operation == "reorder_columns":
        _require_keys(config, {"columns"}, {"columns"})
        columns = _columns(original, config["columns"])
        if len(columns) != len(original.columns) or set(columns) != set(original.columns):
            raise TransformationError("reorder columns must list every existing column exactly once.")
        return original.loc[:, columns].copy(), {"column_order": columns}
    if operation == "filter_rows": return _filter_rows(original, config)
    if operation == "convert_type": return _convert_type(original, config)
    if operation in TEXT_OPERATIONS:
        _require_keys(config, {"columns"}, {"columns"})
        columns = _columns(original, config["columns"])
        result = original.copy()
        for name in columns:
            if not result[name].dropna().map(lambda item: isinstance(item, str)).all():
                raise TransformationError(f"Text standardization requires string values in column '{name}'.")
            op = {"trim_whitespace": str.strip, "lowercase": str.lower, "uppercase": str.upper, "title_case": str.title}[operation]
            result[name] = result[name].map(lambda value: value if pd.isna(value) else op(value))
        return result, {"columns": columns, "operation": operation}
    if operation == "add_calculated_column": return _calculated_column(original, config)
    raise TransformationError(f"Unsupported operation '{operation}'.")
