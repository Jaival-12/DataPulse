import pandas as pd

from app.services.quality_engine import DEFAULT_WEIGHTS, analyze_quality


def test_analyzes_missing_invalid_duplicate_inconsistent_values_and_rules_without_mutating_frame():
    frame = pd.DataFrame({
        "customer_id": ["A1", "A1", "B2", "C3"],
        "amount": ["10", "not-a-number", "-2", " "] ,
        "event_date": ["2026-01-01", "2026-13-40", "2026/01/03", "2026-01-01"],
        "category": ["North", "north", "South ", "South"],
        "email": ["a@example.com", "bad", "b@example.com", "c@example.com"],
    })
    before = frame.copy(deep=True)

    result = analyze_quality(frame, [
        {"type": "non_negative", "column": "amount"},
        {"type": "required_columns", "columns": ["missing_field"]},
    ])

    assert frame.equals(before)
    assert result["dimension_scores"]["completeness"] == 95.0
    assert result["dimension_scores"]["validity"] < 100
    assert result["dimension_scores"]["uniqueness"] < 100
    assert result["dimension_scores"]["consistency"] < 100
    assert result["dimension_scores"]["rule_based_correctness"] < 100
    assert result["overall_score"] == round(sum(result["dimension_scores"][key] * weight for key, weight in DEFAULT_WEIGHTS.items()) / sum(DEFAULT_WEIGHTS.values()), 2)
    issue_types = {issue["issue_type"] for issue in result["issues"]}
    assert {"missing_values", "invalid_numeric", "invalid_date", "invalid_email", "duplicate_identifiers", "leading_trailing_whitespace", "inconsistent_capitalization", "mixed_date_formats", "required_column_missing", "rule_violation"}.issubset(issue_types)
    assert all(len(issue["sample_values"]) <= 5 for issue in result["issues"])


def test_does_not_score_dimensions_without_applicable_observations_as_perfect():
    result = analyze_quality(pd.DataFrame())

    assert result["overall_score"] is None
    assert result["quality_label"] == "Not scored"
    assert result["dimension_scores"] == {
        "completeness": None,
        "validity": None,
        "uniqueness": None,
        "consistency": None,
        "rule_based_correctness": None,
    }


def test_weighted_score_renormalizes_only_dimensions_that_were_measured():
    result = analyze_quality(pd.DataFrame({"x": ["a", "b", "c"]}))

    assert result["dimension_scores"]["rule_based_correctness"] is None
    assert result["overall_score"] == round(
        sum(result["dimension_scores"][key] * DEFAULT_WEIGHTS[key] for key in ("completeness", "uniqueness", "consistency"))
        / sum(DEFAULT_WEIGHTS[key] for key in ("completeness", "uniqueness", "consistency")),
        2,
    )


def test_limits_issue_count_and_examples():
    frame = pd.DataFrame({f"required_{index}": [None, None] for index in range(520)})
    result = analyze_quality(frame)

    assert len(result["issues"]) <= 500
    assert result["methodology"]["issues_truncated"] is True
    assert all(len(issue["sample_values"]) <= 5 for issue in result["issues"])
