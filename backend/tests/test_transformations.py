import pandas as pd
import pytest

from app.services.transformations import TransformationError, apply_transformation


def test_remove_duplicates_supports_selected_key_columns():
    frame = pd.DataFrame({"id": [1, 1, 2], "value": ["first", "second", "third"]})
    result, summary = apply_transformation(frame, "remove_duplicates", {"subset": ["id"]})
    assert result.to_dict("records") == [{"id": 1, "value": "first"}, {"id": 2, "value": "third"}]
    assert summary["removed_rows"] == 1


@pytest.mark.parametrize(("strategy", "value", "expected"), [
    ("constant", 0, [1, 0, 3]),
    ("mean", None, [1, 2, 3]),
    ("median", None, [1, 2, 3]),
])
def test_fill_missing_numeric_strategies(strategy, value, expected):
    result, _ = apply_transformation(pd.DataFrame({"amount": [1, None, 3]}), "fill_missing", {"column": "amount", "strategy": strategy, **({"value": value} if value is not None else {})})
    assert result["amount"].tolist() == expected


def test_fill_missing_mode_and_drop_rows():
    frame = pd.DataFrame({"city": ["Oslo", None, "Oslo"], "n": [1, 2, 3]})
    filled, _ = apply_transformation(frame, "fill_missing", {"column": "city", "strategy": "mode"})
    assert filled["city"].tolist() == ["Oslo", "Oslo", "Oslo"]
    dropped, info = apply_transformation(frame, "fill_missing", {"strategy": "drop_rows"})
    assert len(dropped) == 2 and info["removed_rows"] == 1


def test_column_rename_remove_and_reorder():
    frame = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    renamed, _ = apply_transformation(frame, "rename_columns", {"mapping": {"a": "x"}})
    assert list(renamed.columns) == ["x", "b", "c"]
    with pytest.raises(TransformationError, match="already exists"):
        apply_transformation(frame, "rename_columns", {"mapping": {"a": "b"}})
    removed, _ = apply_transformation(frame, "remove_columns", {"columns": ["b"]})
    assert list(removed.columns) == ["a", "c"]
    reordered, _ = apply_transformation(frame, "reorder_columns", {"columns": ["c", "a", "b"]})
    assert list(reordered.columns) == ["c", "a", "b"]


@pytest.mark.parametrize(("operator", "expected"), [
    ("equals", [2]), ("not_equals", [1, 3]), ("greater_than", [3]),
    ("less_than", [1]), ("greater_than_or_equal", [2, 3]),
    ("less_than_or_equal", [1, 2]),
])
def test_filter_rows_numeric_operators(operator, expected):
    result, _ = apply_transformation(pd.DataFrame({"n": [1, 2, 3]}), "filter_rows", {"column": "n", "operator": operator, "value": 2})
    assert result["n"].tolist() == expected


@pytest.mark.parametrize(("operator", "expected"), [
    ("contains", ["north", "northeast"]),
    ("not_contains", ["south"]),
    ("is_null", [None]),
    ("is_not_null", ["north", "south", "northeast"]),
])
def test_filter_rows_text_and_null_operators(operator, expected):
    result, _ = apply_transformation(pd.DataFrame({"region": ["north", "south", "northeast", None]}), "filter_rows", {"column": "region", "operator": operator, **({"value": "north"} if "contains" in operator else {})})
    assert result["region"].tolist() == expected


def test_type_conversion_rejects_invalid_integer_instead_of_coercing_to_null():
    with pytest.raises(TransformationError, match="cannot convert"):
        apply_transformation(pd.DataFrame({"n": ["1", "many"]}), "convert_type", {"column": "n", "target_type": "integer"})


def test_type_conversion_supports_boolean_and_strict_date():
    bools, _ = apply_transformation(pd.DataFrame({"active": ["true", "false"]}), "convert_type", {"column": "active", "target_type": "boolean"})
    dates, _ = apply_transformation(pd.DataFrame({"day": ["2026-04-02"]}), "convert_type", {"column": "day", "target_type": "date"})
    assert bools["active"].tolist() == [True, False]
    assert str(dates["day"].iloc[0]) == "2026-04-02"


def test_type_conversion_supports_string_integer_float_and_rejects_impossible_date():
    text, _ = apply_transformation(pd.DataFrame({"n": [12, None]}), "convert_type", {"column": "n", "target_type": "string"})
    integer, _ = apply_transformation(pd.DataFrame({"n": ["12", None]}), "convert_type", {"column": "n", "target_type": "integer"})
    floating, _ = apply_transformation(pd.DataFrame({"n": ["1.25", None]}), "convert_type", {"column": "n", "target_type": "float"})
    assert text["n"].tolist()[0] == "12.0" and pd.isna(text["n"].tolist()[1])
    assert integer["n"].iloc[0] == 12 and pd.isna(integer["n"].iloc[1])
    assert floating["n"].iloc[0] == 1.25 and pd.isna(floating["n"].iloc[1])
    with pytest.raises(TransformationError, match="cannot convert"):
        apply_transformation(pd.DataFrame({"day": ["2026-13-40"]}), "convert_type", {"column": "day", "target_type": "date"})


@pytest.mark.parametrize(("operation", "expected"), [
    ("trim_whitespace", ["North", "west"]),
    ("lowercase", ["  north ", "west"]),
    ("uppercase", ["  NORTH ", "WEST"]),
    ("title_case", ["  North ", "West"]),
])
def test_text_standardization_applies_selected_operation(operation, expected):
    result, _ = apply_transformation(pd.DataFrame({"city": ["  North ", "west"]}), operation, {"columns": ["city"]})
    assert result["city"].tolist() == expected


@pytest.mark.parametrize(("operator", "expected"), [("add", 16), ("subtract", 4), ("multiply", 60), ("divide", 1.6666666667)])
def test_calculated_column_uses_structured_operands(operator, expected):
    result, _ = apply_transformation(pd.DataFrame({"price": [10], "discount": [6]}), "add_calculated_column", {"name": "net", "left": {"column": "price"}, "operator": operator, "right": {"column": "discount"}})
    assert result["net"].iloc[0] == pytest.approx(expected)


def test_calculated_column_rejects_division_by_zero_and_unsafe_expression():
    with pytest.raises(TransformationError, match="zero"):
        apply_transformation(pd.DataFrame({"n": [1, 2], "d": [1, 0]}), "add_calculated_column", {"name": "r", "left": {"column": "n"}, "operator": "divide", "right": {"column": "d"}})
    with pytest.raises(TransformationError, match="operand"):
        apply_transformation(pd.DataFrame({"n": [1]}), "add_calculated_column", {"name": "r", "left": "__import__('os')", "operator": "add", "right": 1})


def test_calculated_column_accepts_finite_constant_operands_and_preserves_missing():
    result, _ = apply_transformation(pd.DataFrame({"n": [2, None]}), "add_calculated_column", {"name": "adjusted", "left": {"column": "n"}, "operator": "multiply", "right": 3})
    assert result["adjusted"].iloc[0] == 6 and pd.isna(result["adjusted"].iloc[1])


def test_invalid_columns_and_incompatible_fill_strategy_are_rejected():
    frame = pd.DataFrame({"city": ["Oslo", None]})
    with pytest.raises(TransformationError, match="not found"):
        apply_transformation(frame, "remove_columns", {"columns": ["missing"]})
    with pytest.raises(TransformationError, match="numeric"):
        apply_transformation(frame, "fill_missing", {"column": "city", "strategy": "mean"})


def test_numeric_comparison_supports_numeric_csv_strings_without_coercing_output():
    result, _ = apply_transformation(pd.DataFrame({"n": ["1", "10", "2"]}), "filter_rows", {"column": "n", "operator": "greater_than", "value": 2})
    assert result["n"].tolist() == ["10"]
