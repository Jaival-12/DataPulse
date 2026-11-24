import pandas as pd
import pytest

from app.services.analytics_service import (
    aggregate_frame,
    analyze_column,
    analyze_correlation,
    analyze_overview,
    analyze_timeseries,
    compare_frames,
)
from app.services.analytics_insights import generate_insights


def test_numeric_analysis_parses_grouped_values_and_tracks_invalid_and_missing():
    result = analyze_column(pd.DataFrame({"amount": ["1,499", "2.5", "bad", None]}), "amount")

    assert result["detected_type"] == "numeric_mixed"
    assert result["numeric"]["count"] == 2
    assert result["numeric"]["missing_count"] == 1
    assert result["numeric"]["invalid_count"] == 1
    assert result["numeric"]["mean"] == 750.75
    assert result["numeric"]["range"] == 1496.5
    assert len(result["numeric"]["histogram"]) <= 20


def test_categorical_analysis_returns_bounded_frequency_and_missing_counts():
    result = analyze_column(pd.DataFrame({"kind": ["a"] * 12 + ["b", None]}), "kind")

    assert result["categorical"]["non_null_count"] == 13
    assert result["categorical"]["distinct_count"] == 2
    assert result["categorical"]["top_values"][0] == {"value": "a", "count": 12, "percentage": pytest.approx(92.3077)}
    assert result["categorical"]["missing_count"] == 1
    assert result["categorical"]["cardinality"] == 2


def test_categorical_top_values_are_limited_to_ten():
    result = analyze_column(pd.DataFrame({"category": [f"value-{index}" for index in range(25)]}), "category")
    assert result["categorical"]["distinct_count"] == 25
    assert len(result["categorical"]["top_values"]) == 10


def test_timeseries_sorts_periods_and_counts_missing_and_impossible_dates():
    frame = pd.DataFrame({"day": ["2026-02-01", "2026-01-03", "2026-13-40", None], "amount": [4, 2, 8, 1]})
    result = analyze_timeseries(frame, "day", "weekly", "amount", "sum")

    assert result["invalid_date_count"] == 1
    assert result["missing_date_count"] == 1
    assert [point["period"] for point in result["points"]] == sorted(point["period"] for point in result["points"])
    assert sum(point["record_count"] for point in result["points"]) == 2
    assert all(point["aggregate_value"] in {2.0, 4.0} for point in result["points"])


def test_timeseries_bounds_periods_and_rejects_non_date_fields():
    frame = pd.DataFrame({"day": pd.date_range("2020-01-01", periods=5).astype(str), "value": range(5)})
    result = analyze_timeseries(frame, "day", "daily", limit=2)
    assert result["total_periods"] == 5
    assert result["truncated"] is True
    assert len(result["points"]) == 2
    with pytest.raises(ValueError, match="date"):
        analyze_timeseries(pd.DataFrame({"label": ["one", "two"]}), "label", "daily")


def test_timeseries_returns_empty_points_for_empty_date_column():
    result = analyze_timeseries(pd.DataFrame({"day": pd.Series(dtype="object")}), "day", "monthly")
    assert result["points"] == []
    assert result["valid_date_count"] == result["missing_date_count"] == result["invalid_date_count"] == 0


def test_correlation_uses_pairwise_counts_and_omits_constant_correlations():
    result = analyze_correlation(pd.DataFrame({"x": [1, 2, None, 4], "y": [2, 4, 8, 8], "flat": [3, 3, 3, 3]}))

    assert result["correlations"]["x"]["y"] == pytest.approx(1.0)
    assert result["pair_counts"]["x"]["y"] == 3
    assert result["correlations"]["x"]["flat"] is None


def test_correlation_requires_at_least_two_numeric_columns():
    result = analyze_correlation(pd.DataFrame({"only": [1, 2, 3], "label": ["a", "b", "c"]}))
    assert result["numeric_columns"] == ["only"]
    assert result["correlations"] == {}
    assert result["pair_counts"] == {}


def test_group_aggregation_skips_invalid_numeric_values_and_respects_limit():
    frame = pd.DataFrame({"region": ["N", "N", "S", "S"], "amount": ["2", "bad", "4", None]})
    result = aggregate_frame(frame, "region", "sum", "amount", limit=1)

    assert len(result["groups"]) == 1
    assert result["groups"][0]["group"] == "N"
    assert result["groups"][0]["aggregate_value"] == 2
    assert result["groups"][0]["invalid_count"] == 1
    assert result["truncated"] is True


@pytest.mark.parametrize("operation,expected", [("count", 3), ("sum", 6), ("average", 2), ("minimum", 1), ("maximum", 3)])
def test_group_aggregation_supports_each_operation(operation, expected):
    frame = pd.DataFrame({"region": ["N", "N", "N"], "amount": [1, 2, 3]})
    result = aggregate_frame(frame, "region", operation, None if operation == "count" else "amount")
    assert result["groups"][0]["aggregate_value"] == expected


def test_group_aggregation_restricts_grouping_to_categories_or_date_periods():
    frame = pd.DataFrame({"number": [1, 2, 3], "label": ["a", "b", "c"]})
    with pytest.raises(ValueError, match="categorical or date"):
        aggregate_frame(frame, "number", "count")


def test_date_aggregation_excludes_invalid_periods_and_counts_them():
    frame = pd.DataFrame({"day": ["2026-01-01", "2026-13-40", None], "amount": [1, 2, 3]})
    result = aggregate_frame(frame, "day", "sum", "amount", date_granularity="monthly")
    assert [item["group"] for item in result["groups"]] == ["2026-01"]
    assert result["dropped_invalid_group_values"] == 1
    assert result["dropped_missing_group_values"] == 1


def test_empty_aggregation_returns_no_groups_without_inventing_a_type():
    result = aggregate_frame(pd.DataFrame({"category": pd.Series(dtype="object")}), "category", "count")
    assert result["groups"] == []
    assert result["total_groups"] == 0


def test_overview_and_insights_are_based_on_measured_values():
    frame = pd.DataFrame({"amount": [-5, 5, 15, 25], "kind": ["common", "common", "common", "rare"], "day": ["2026-01-01"] * 4})
    overview = analyze_overview(frame, 123)
    insights = generate_insights(frame)

    assert overview["total_records"] == 4
    assert overview["total_columns"] == 3
    assert overview["dataset_size_bytes"] == 123
    assert {"amount", "kind", "day"}.issubset(set(overview["numeric_columns"] + overview["categorical_columns"] + overview["date_columns"]))
    assert any(item["insight_type"] == "negative_values" and item["evidence"]["count"] == 1 for item in insights)
    assert any(item["insight_type"] == "dominant_category" for item in insights)


def test_insights_remain_available_when_correlation_limit_is_exceeded():
    frame = pd.DataFrame({f"metric_{index}": [index, index + 1, index + 2] for index in range(51)})
    assert isinstance(generate_insights(frame), list)


def test_insights_include_missingness_dispersion_correlation_and_lineage_row_change():
    frame = pd.DataFrame({
        "measure": [0, 1000, 0, 0],
        "scaled": [0, 2000, 0, 0],
        "sparse": [None, 1, None, 2],
        "category": ["a", "a", "a", "b"],
    })
    insights = generate_insights(frame, original_row_count=6)
    types = {item["insight_type"] for item in insights}
    assert {"high_missingness", "high_dispersion", "strong_correlation", "row_count_change"}.issubset(types)
    assert next(item for item in insights if item["insight_type"] == "row_count_change")["evidence"]["change"] == -2


def test_comparison_reports_column_changes_numeric_deltas_and_exact_rename_candidates():
    left = pd.DataFrame({"old_name": ["x", "y"], "amount": [1, 2], "gone": [3, 4]})
    right = pd.DataFrame({"new_name": ["x", "y"], "amount": [2, 4], "added": [5, 6]})
    result = compare_frames(left, right, left_size_bytes=10, right_size_bytes=20)

    assert result["row_count_change"] == 0
    assert result["added_columns"] == ["added"]
    assert result["removed_columns"] == ["gone"]
    assert result["possible_renames"] == [{"from": "old_name", "to": "new_name", "confidence": "exact_values"}]
    assert result["numeric_changes"]["amount"]["mean_change"] == 1.5


def test_empty_and_all_missing_numeric_columns_have_no_fake_numeric_values():
    result = analyze_column(pd.DataFrame({"value": [None, "", pd.NA]}), "value")
    assert result["numeric"]["mean"] is None
    assert result["numeric"]["count"] == 0
    assert result["numeric"]["missing_count"] == 3
