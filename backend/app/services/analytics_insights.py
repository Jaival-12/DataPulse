"""Deterministic rule-based observations derived only from calculated analytics."""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.analytics_service import AnalyticsRequestError, analyze_column, analyze_correlation
from app.services.profiling_service import build_profile
from app.utils.analytics_helpers import numeric_values

MAX_INSIGHTS = 25


def generate_insights(frame: pd.DataFrame, original_row_count: int | None = None) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    profile = build_profile(frame)

    def add(insight_type: str, title: str, description: str, severity: str, columns: list[str], evidence: dict[str, Any]):
        if len(insights) < MAX_INSIGHTS:
            insights.append({"insight_type": insight_type, "title": title, "description": description,
                             "severity": severity, "columns": columns, "evidence": evidence})

    for column in profile["columns"]:
        if column["missing_count"] and len(frame):
            missing_percentage = round(column["missing_count"] * 100 / len(frame), 4)
            if missing_percentage >= 20:
                add("high_missingness", f"High missingness in {column['name']}",
                    f"{missing_percentage}% of records have no value for {column['name']}.",
                    "high" if missing_percentage >= 50 else "warning", [column["name"]],
                    {"missing_count": column["missing_count"], "total_records": len(frame), "missing_percentage": missing_percentage})
        detail = analyze_column(frame, column["name"], profile)
        if detail["numeric"] is not None:
            numbers = [value for value in _numeric_column(frame[column["name"]]) if value is not None]
            negative_count = sum(value < 0 for value in numbers)
            if negative_count:
                add("negative_values", f"Negative values in {column['name']}",
                    f"{negative_count} valid numeric values in {column['name']} are below zero.", "informational",
                    [column["name"]], {"count": negative_count, "minimum": min(numbers)})
            stats = detail["numeric"]
            mean, std = stats["mean"], stats["standard_deviation"]
            if mean is not None and std is not None and abs(mean) > 0 and std / abs(mean) >= 2:
                add("high_dispersion", f"High dispersion in {column['name']}",
                    f"The sample standard deviation is at least twice the absolute mean for {column['name']}.",
                    "informational", [column["name"]], {"mean": mean, "standard_deviation": std, "ratio": round(std / abs(mean), 4)})
        if detail["categorical"] is not None and detail["categorical"]["top_values"]:
            top = detail["categorical"]["top_values"][0]
            if top["percentage"] >= 75 and detail["categorical"]["distinct_count"] > 1:
                add("dominant_category", f"One value dominates {column['name']}",
                    f"The most common value accounts for {top['percentage']}% of non-missing {column['name']} values.",
                    "informational", [column["name"]], {"value": top["value"], "count": top["count"], "percentage": top["percentage"]})

    try:
        correlation = analyze_correlation(frame, profile)
    except AnalyticsRequestError:
        correlation = {"numeric_columns": [], "correlations": {}, "pair_counts": {}}
    names = correlation["numeric_columns"]
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            value = correlation["correlations"][left][right]
            if value is not None and abs(value) >= 0.8:
                direction = "positive" if value > 0 else "negative"
                add("strong_correlation", f"Strong {direction} correlation: {left} and {right}",
                    f"Pearson correlation is {value:.3f} across {correlation['pair_counts'][left][right]} pairwise observations. This is an association, not evidence of causation.",
                    "informational", [left, right], {"pearson": value, "pair_count": correlation["pair_counts"][left][right]})
    if original_row_count is not None and original_row_count != len(frame):
        delta = len(frame) - original_row_count
        add("row_count_change", "Record count changed after processing",
            f"The processed dataset has {abs(delta)} {'more' if delta > 0 else 'fewer'} records than its source.",
            "informational", [], {"source_records": original_row_count, "processed_records": len(frame), "change": delta})
    return insights
def _numeric_column(series: pd.Series) -> list[float | None]:
    return numeric_values(series)[0]
