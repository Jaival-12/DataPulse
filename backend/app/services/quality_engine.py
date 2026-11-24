"""Deterministic, read-only quality analysis for tabular data frames."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np
import pandas as pd

from app.services.profiling_service import _parse_date, _parse_number, _safe_value, build_profile

DIMENSIONS = ("completeness", "validity", "uniqueness", "consistency", "rule_based_correctness")
DEFAULT_WEIGHTS = {
    "completeness": 0.25,
    "validity": 0.25,
    "uniqueness": 0.20,
    "consistency": 0.15,
    "rule_based_correctness": 0.15,
}
METHOD_VERSION = "datapulse-quality-v1"
MAX_ISSUES = 500
MAX_SAMPLES = 5
EMAIL_COLUMN = re.compile(r"(?:^|_)(?:email|e_mail)(?:_|$)", re.I)
EMAIL_VALUE = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+$", re.I)


def _missing(value: Any) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, str):
        return not value.strip()
    try:
        result = pd.isna(value)
        return bool(result) if np.isscalar(result) else False
    except (TypeError, ValueError):
        return False


def _safe_key(value: Any) -> str:
    safe = _safe_value(value)
    try:
        return json.dumps(safe, sort_keys=True, ensure_ascii=False, default=str, allow_nan=False)
    except (TypeError, ValueError):
        return repr(safe)


def _sample(values) -> list[Any]:
    result = []
    seen = set()
    for value in values:
        safe = _safe_value(value)
        key = _safe_key(safe)
        if key not in seen:
            result.append(safe)
            seen.add(key)
        if len(result) >= MAX_SAMPLES:
            break
    return result


def _pct(value: int | float, total: int | float) -> float:
    return round(value * 100 / total, 4) if total else 0.0


def _severity(issue_type: str, affected_percentage: float) -> str:
    if issue_type == "required_column_missing" or affected_percentage >= 50:
        return "critical"
    if affected_percentage >= 20:
        return "high"
    if affected_percentage >= 5:
        return "medium"
    return "low"


def _quality_label(score: float | None) -> str:
    if score is None:
        return "Not scored"
    if score >= 90:
        return "Excellent"
    if score >= 75:
        return "Good"
    if score >= 50:
        return "Needs Improvement"
    return "Poor"


def _date_format(value: str) -> str | None:
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[T ].*)?", text):
        return "ISO hyphen"
    if re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text):
        return "year slash"
    if re.fullmatch(r"\d{1,2}-\d{1,2}-\d{4}", text):
        return "day hyphen"
    return None


def analyze_quality(frame: pd.DataFrame, rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Analyze a frame without changing it and return score metadata and bounded issues."""
    rules = rules or []
    profile = build_profile(frame)
    rows, columns = frame.shape
    total_cells = rows * columns
    dimension_scores: dict[str, float | None] = {dimension: None for dimension in DIMENSIONS}
    issues: list[dict[str, Any]] = []
    issue_indexes: dict[tuple[str, str, str | None], int] = {}
    truncated = False

    def add_issue(dimension: str, issue_type: str, column_name: str | None, affected_rows: int,
                  description: str, values, recommendation: str, *, critical: bool = False) -> None:
        nonlocal truncated
        if affected_rows <= 0 and issue_type != "required_column_missing":
            return
        percentage = _pct(affected_rows, rows)
        key = (dimension, issue_type, column_name)
        samples = _sample(values)
        if key in issue_indexes:
            current = issues[issue_indexes[key]]
            current["affected_rows"] = max(current["affected_rows"], affected_rows)
            current["affected_percentage"] = _pct(current["affected_rows"], rows)
            current["sample_values"] = _sample(current["sample_values"] + samples)
            return
        if len(issues) >= MAX_ISSUES:
            truncated = True
            return
        if critical:
            severity = "critical"
        else:
            severity = _severity(issue_type, percentage)
        issue_indexes[key] = len(issues)
        issues.append({
            "dimension": dimension,
            "issue_type": issue_type,
            "severity": severity,
            "column_name": column_name,
            "affected_rows": int(affected_rows),
            "affected_percentage": percentage,
            "description": description,
            "sample_values": samples[:MAX_SAMPLES],
            "recommendation": recommendation,
        })

    # Completeness includes nulls and strings containing only whitespace.
    missing_cells = 0
    if rows and columns:
        completeness_observed = 0
        for position, name in enumerate(frame.columns):
            series = frame.iloc[:, position]
            mask = series.map(_missing)
            missing_count = int(mask.sum())
            missing_cells += missing_count
            completeness_observed += rows
            if missing_count:
                values = series[mask].tolist()
                add_issue("completeness", "missing_values", str(name), missing_count,
                          f"{missing_count} of {rows} records are missing a value in {name}.", values,
                          "Fill or remove missing values according to the field's requirements.")
        if completeness_observed:
            dimension_scores["completeness"] = round(100 * (1 - missing_cells / completeness_observed), 2)

    profile_columns = profile["columns"]
    validity_total = 0
    validity_failed = 0
    uniqueness_rates: list[float] = []
    consistency_checks = 0
    consistency_affected = 0
    checked_consistency_columns = 0
    rule_total = 0
    rule_failed = 0

    # A canonical tuple handles nested JSON values while keeping raw values untouched.
    if rows and columns:
        canonical_rows = [tuple(_safe_key(frame.iloc[row, column]) for column in range(columns)) for row in range(rows)]
        counts = Counter(canonical_rows)
        duplicate_rows = sum(count - 1 for count in counts.values() if count > 1)
        duplicate_examples = [list(frame.iloc[index].tolist()) for index, key in enumerate(canonical_rows) if counts[key] > 1]
        add_issue("uniqueness", "duplicate_rows", None, duplicate_rows,
                  f"{duplicate_rows} records repeat a complete row.", duplicate_examples,
                  "Review repeated records and remove only confirmed duplicates.")
        uniqueness_rates.append(duplicate_rows / rows)
    else:
        duplicate_rows = 0

    for position, column_profile in enumerate(profile_columns):
        name = str(column_profile["name"])
        series = frame.iloc[:, position]
        present = [(index, value) for index, value in enumerate(series.tolist()) if not _missing(value)]
        detected_type = column_profile["detected_type"]

        numeric_stats = column_profile.get("numeric_statistics")
        if numeric_stats is not None:
            valid = int(numeric_stats.get("valid_numeric_values", numeric_stats.get("count", 0)))
            invalid = int(numeric_stats.get("invalid_numeric_values", 0))
            validity_total += valid + invalid
            validity_failed += invalid
            invalid_values = [value for _, value in present if _parse_number(value) is None]
            add_issue("validity", "invalid_numeric", name, invalid,
                      f"{invalid} values in {name} cannot be converted to finite numbers.", invalid_values,
                      "Review the invalid values or select the appropriate target type before using this field.")

        date_stats = column_profile.get("date_statistics")
        if date_stats is not None:
            valid = int(date_stats.get("valid_date_count", 0))
            invalid = int(date_stats.get("invalid_date_count", 0))
            validity_total += valid + invalid
            validity_failed += invalid
            invalid_values = [value for _, value in present if _parse_date(value) is None]
            add_issue("validity", "invalid_date", name, invalid,
                      f"{invalid} non-missing values in {name} are not valid dates.", invalid_values,
                      "Correct malformed or impossible dates and use a consistent date representation.")

        normalized_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if EMAIL_COLUMN.search(normalized_name):
            invalid_values = [value for _, value in present if not EMAIL_VALUE.fullmatch(str(value).strip())]
            invalid = len(invalid_values)
            validity_total += len(present)
            validity_failed += invalid
            add_issue("validity", "invalid_email", name, invalid,
                      f"{invalid} non-missing values in {name} are not valid email addresses.", invalid_values,
                      "Check the email values for a local part and a valid domain.")

        if detected_type == "identifier" and rows:
            identifiers = [(index, value) for index, value in present]
            seen_identifiers = set()
            duplicate_ids = []
            for index, value in identifiers:
                key = _safe_key(value)
                if key in seen_identifiers:
                    duplicate_ids.append((index, value))
                seen_identifiers.add(key)
            duplicate_count = len(duplicate_ids)
            uniqueness_rates.append(duplicate_count / max(1, len(identifiers)))
            add_issue("uniqueness", "duplicate_identifiers", name, duplicate_count,
                      f"{duplicate_count} identifier occurrences in {name} repeat an earlier value.",
                      [value for _, value in duplicate_ids], "Review duplicate identifiers and confirm they refer to distinct records.")

        # Consistency checks flag observations but never normalize or rewrite values.
        string_values = [(index, value) for index, value in present if isinstance(value, str)]
        if string_values:
            checked_consistency_columns += 1
            whitespace = [(index, value) for index, value in string_values if value != value.strip()]
            if whitespace:
                add_issue("consistency", "leading_trailing_whitespace", name, len(whitespace),
                          f"{len(whitespace)} values in {name} contain leading or trailing whitespace.",
                          [value for _, value in whitespace], "Consider trimming surrounding whitespace after review.")

            variants: dict[str, list[tuple[int, str]]] = defaultdict(list)
            for index, value in string_values:
                variants[value.strip().casefold()].append((index, value))
            case_groups = [group for group in variants.values() if len({value.strip() for _, value in group}) > 1]
            if case_groups:
                affected = {index for group in case_groups for index, _ in group}
                values = [value for group in case_groups for _, value in group]
                add_issue("consistency", "inconsistent_capitalization", name, len(affected),
                          f"{len(affected)} values in {name} use different capitalization for otherwise matching categories.",
                          values, "Review category variants and standardize only when the differences are not meaningful.")

            date_formats: dict[str, list[str]] = defaultdict(list)
            for _, value in string_values:
                fmt = _date_format(value)
                if fmt and _parse_date(value) is not None:
                    date_formats[fmt].append(value)
            if len(date_formats) > 1:
                values = [value for group in date_formats.values() for value in group]
                affected = len({(value, idx) for idx, value in string_values if _date_format(value) in date_formats})
                add_issue("consistency", "mixed_date_formats", name, affected,
                          f"{name} contains valid dates in multiple representations.", values,
                          "Choose a consistent date representation after confirming locale and meaning.")

            # One consistency observation per row in this column, even if it has multiple findings.
            bad_indexes = {index for index, value in whitespace}
            for group in case_groups:
                bad_indexes.update(index for index, _ in group)
            if len(date_formats) > 1:
                bad_indexes.update(index for index, value in string_values if _date_format(value) in date_formats)
            consistency_checks += len(string_values)
            consistency_affected += len(bad_indexes)

    if rows:
        if uniqueness_rates:
            dimension_scores["uniqueness"] = round(100 * (1 - sum(uniqueness_rates) / len(uniqueness_rates)), 2)
        if checked_consistency_columns and consistency_checks:
            dimension_scores["consistency"] = round(100 * (1 - consistency_affected / consistency_checks), 2)

    # Validate and evaluate only structured rules supplied by the API.
    for rule in rules:
        rule_type = rule["type"]
        if rule_type == "required_columns":
            for name in rule.get("columns", []):
                rule_total += 1
                if name not in frame.columns:
                    rule_failed += 1
                    add_issue("rule_based_correctness", "required_column_missing", str(name), rows,
                              f"Required column {name} is not present in the dataset.", [],
                              "Add the required field to the input or update the validation rule.", critical=True)
            continue

        name = rule.get("column")
        if name not in frame.columns:
            # The API normally validates this; keep the engine safe for direct callers too.
            rule_total += 1
            rule_failed += 1
            add_issue("rule_based_correctness", "required_column_missing", str(name), rows,
                      f"Rule references missing column {name}.", [], "Add the column or remove the rule.", critical=True)
            continue
        series = frame[name]
        values = series.tolist()
        present_values = [(index, value) for index, value in enumerate(values) if not _missing(value)]
        failed: list[tuple[int, Any]] = []

        if rule_type == "not_null":
            rule_total += rows
            failed = [(index, value) for index, value in enumerate(values) if _missing(value)]
        elif rule_type == "unique":
            rule_total += len(present_values)
            seen = set()
            for index, value in present_values:
                key = _safe_key(value)
                if key in seen:
                    failed.append((index, value))
                seen.add(key)
            duplicate_count = len(failed)
            uniqueness_rates.append(duplicate_count / max(1, len(present_values)))
            add_issue("uniqueness", "duplicate_identifiers", str(name), duplicate_count,
                      f"{duplicate_count} values in {name} violate the configured uniqueness rule.",
                      [value for _, value in failed], "Review duplicate values or revise the uniqueness requirement.")
        else:
            rule_total += len(present_values)
            for index, value in present_values:
                number = _parse_number(value)
                if number is None:
                    failed.append((index, value))
                elif rule_type == "non_negative" and number < 0:
                    failed.append((index, value))
                elif rule_type == "greater_than" and number <= float(rule["value"]):
                    failed.append((index, value))
                elif rule_type == "range" and not (float(rule["min_value"]) <= number <= float(rule["max_value"])):
                    failed.append((index, value))

        rule_failed += len(failed)
        if failed and rule_type != "unique":
            descriptions = {"not_null": "must not be empty", "non_negative": "must be greater than or equal to zero"}
            if rule_type == "greater_than":
                descriptions["greater_than"] = f"must be greater than {rule['value']}"
            elif rule_type == "range":
                descriptions["range"] = f"must be between {rule['min_value']} and {rule['max_value']}"
            add_issue("rule_based_correctness", "rule_violation", str(name), len(failed),
                      f"{len(failed)} values in {name} {descriptions.get(rule_type, 'violate the configured rule')}.",
                      [value for _, value in failed], "Review the failing values or revise the rule if the constraint is not appropriate.")

    if rule_total:
        dimension_scores["rule_based_correctness"] = round(100 * (1 - rule_failed / rule_total), 2)
    if validity_total:
        dimension_scores["validity"] = round(100 * (1 - validity_failed / validity_total), 2)
    if uniqueness_rates:
        dimension_scores["uniqueness"] = round(max(0, 100 * (1 - sum(uniqueness_rates) / len(uniqueness_rates))), 2)

    measured = [(dimension_scores[name], DEFAULT_WEIGHTS[name]) for name in DIMENSIONS if dimension_scores[name] is not None]
    weight_total = sum(weight for _, weight in measured)
    overall_score = round(sum(float(score) * weight for score, weight in measured) / weight_total, 2) if weight_total else None
    method = {
        "version": METHOD_VERSION,
        "policy": "Unmeasured dimensions are null and excluded; measured dimensions are weighted by renormalizing their configured weights.",
        "measured_dimensions": [name for name in DIMENSIONS if dimension_scores[name] is not None],
        "configured_weight_total": round(sum(DEFAULT_WEIGHTS.values()), 4),
        "normalizing_weight_total": round(weight_total, 4),
        "issues_truncated": truncated,
        "max_issue_records": MAX_ISSUES,
        "max_sample_values_per_issue": MAX_SAMPLES,
    }
    return {
        "overall_score": overall_score,
        "quality_label": _quality_label(overall_score),
        "dimension_scores": dimension_scores,
        "scoring_weights": dict(DEFAULT_WEIGHTS),
        "methodology": method,
        "rules": rules,
        "total_rows": int(rows),
        "total_columns": int(columns),
        "total_issues": len(issues),
        "status": "complete" if overall_score is not None else "not_scored",
        "issues": issues,
    }
