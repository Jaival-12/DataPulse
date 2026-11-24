from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

AnalyticsSourceType = Literal["original", "processed"]
Granularity = Literal["daily", "weekly", "monthly"]
TimeAggregation = Literal["sum", "average", "count"]
GroupOperation = Literal["count", "sum", "average", "minimum", "maximum"]


class AnalyticsSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: AnalyticsSourceType
    id: StrictStr = Field(min_length=1, max_length=64)

    @field_validator("id")
    @classmethod
    def nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source id must not be blank")
        return value.strip()


class TimeSeriesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_column: StrictStr = Field(min_length=1, max_length=255)
    granularity: Granularity
    measure_column: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    aggregation: TimeAggregation = "count"
    limit: int = Field(default=500, ge=1, le=500)

    @model_validator(mode="after")
    def require_measure_for_numeric_aggregation(self):
        if self.aggregation != "count" and not self.measure_column:
            raise ValueError("sum and average require a numeric measure_column")
        return self


class AggregateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_by: StrictStr = Field(min_length=1, max_length=255)
    operation: GroupOperation
    measure_column: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    limit: int = Field(default=100, ge=1, le=100)
    date_granularity: Granularity | None = None

    @model_validator(mode="after")
    def validate_measure(self):
        if self.operation != "count" and not self.measure_column:
            raise ValueError(f"{self.operation} requires measure_column")
        return self


class CompareIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: AnalyticsSourceRef
    right: AnalyticsSourceRef

    @model_validator(mode="after")
    def validate_comparable_types(self):
        if self.left.type == self.right.type == "original":
            raise ValueError("Comparison requires an original and processed dataset, or two processed datasets.")
        if self.left.type == self.right.type and self.left.id == self.right.id:
            raise ValueError("A dataset cannot be compared with itself.")
        return self


class AnalyticsOverviewOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    total_records: int
    total_columns: int
    numeric_columns: list[str]
    categorical_columns: list[str]
    date_columns: list[str]
    missing_cells: int
    duplicate_records: int
    dataset_size_bytes: int
    generated_at: datetime


class AnalyticsColumnSummary(BaseModel):
    name: str
    detected_type: str
    non_null_count: int
    missing_count: int
    distinct_count: int
    invalid_count: int


class AnalyticsColumnsOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    columns: list[AnalyticsColumnSummary]
    generated_at: datetime


class AnalyticsColumnOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    name: str
    detected_type: str
    non_null_count: int
    missing_count: int
    distinct_count: int
    numeric: dict[str, Any] | None
    categorical: dict[str, Any] | None
    date: dict[str, Any] | None
    generated_at: datetime


class CorrelationOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    numeric_columns: list[str]
    correlations: dict[str, dict[str, float | None]]
    pair_counts: dict[str, dict[str, int]]
    generated_at: datetime


class TimePoint(BaseModel):
    period: str
    record_count: int
    aggregate_value: float | None


class TimeSeriesOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    date_column: str
    granularity: Granularity
    measure_column: str | None
    aggregation: TimeAggregation
    valid_date_count: int
    invalid_date_count: int
    missing_date_count: int
    invalid_measure_count: int
    total_periods: int
    truncated: bool
    points: list[TimePoint]
    generated_at: datetime


class AggregateGroup(BaseModel):
    group: Any
    record_count: int
    aggregate_value: float | int | None
    valid_count: int
    missing_count: int
    invalid_count: int


class AggregateOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    group_by: str
    operation: GroupOperation
    measure_column: str | None
    date_granularity: Granularity | None
    total_groups: int
    truncated: bool
    dropped_missing_group_values: int
    dropped_invalid_group_values: int
    groups: list[AggregateGroup]
    generated_at: datetime


class InsightOut(BaseModel):
    insight_type: str
    title: str
    description: str
    severity: Literal["informational", "warning", "high"]
    columns: list[str]
    evidence: dict[str, Any]


class InsightsOut(BaseModel):
    source_id: str
    source_type: AnalyticsSourceType
    insights: list[InsightOut]
    generated_at: datetime


class CompareOut(BaseModel):
    left: dict[str, Any]
    right: dict[str, Any]
    row_count_change: int
    column_count_change: int
    missing_cells_change: int
    duplicate_records_change: int
    common_columns: list[str]
    added_columns: list[str]
    removed_columns: list[str]
    possible_renames: list[dict[str, str]]
    numeric_changes: dict[str, Any]
    categorical_changes: dict[str, Any]
    generated_at: datetime
