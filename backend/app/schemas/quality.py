from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, model_validator

QualityDimension = Literal["completeness", "validity", "uniqueness", "consistency", "rule_based_correctness"]
QualitySeverity = Literal["critical", "high", "medium", "low"]
QualityRuleType = Literal["required_columns", "not_null", "unique", "non_negative", "greater_than", "range"]


class QualityRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: QualityRuleType
    column: StrictStr | None = None
    columns: list[StrictStr] | None = Field(default=None, min_length=1, max_length=100)
    value: StrictInt | StrictFloat | None = None
    min_value: StrictInt | StrictFloat | None = None
    max_value: StrictInt | StrictFloat | None = None

    @model_validator(mode="after")
    def validate_fields(self):
        if self.type == "required_columns":
            if not self.columns or any(not item.strip() for item in self.columns):
                raise ValueError("required_columns needs a non-empty columns list")
            if len(self.columns) != len(set(self.columns)):
                raise ValueError("required_columns values must be unique")
            if self.column is not None or self.value is not None or self.min_value is not None or self.max_value is not None:
                raise ValueError("required_columns does not accept column or numeric values")
            return self
        if not self.column or not self.column.strip():
            raise ValueError(f"{self.type} requires a non-empty column")
        if self.columns is not None:
            raise ValueError(f"{self.type} does not accept columns")
        if self.type == "greater_than":
            if self.value is None or self.min_value is not None or self.max_value is not None:
                raise ValueError("greater_than requires value and does not accept range bounds")
        elif self.type == "range":
            if self.min_value is None or self.max_value is None or self.value is not None:
                raise ValueError("range requires min_value and max_value")
            if self.min_value > self.max_value:
                raise ValueError("range min_value must not exceed max_value")
        elif self.value is not None or self.min_value is not None or self.max_value is not None:
            raise ValueError(f"{self.type} does not accept numeric values")
        return self


class AnalyzeQualityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[QualityRuleIn] = Field(default_factory=list, max_length=100)


class DataQualityReportOut(BaseModel):
    id: str
    dataset_id: str | None
    processed_dataset_id: str | None
    overall_score: float | None
    quality_label: str
    dimension_scores: dict[str, float | None]
    scoring_weights: dict[str, float]
    methodology: dict[str, Any]
    rules: list[dict[str, Any]]
    total_rows: int
    total_columns: int
    total_issues: int
    status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DataQualityIssueOut(BaseModel):
    id: str
    report_id: str
    dimension: QualityDimension
    issue_type: str
    severity: QualitySeverity
    column_name: str | None
    affected_rows: int
    affected_percentage: float
    description: str
    sample_values: list[Any]
    recommendation: str
    model_config = ConfigDict(from_attributes=True)


class DataQualityReportPage(BaseModel):
    items: list[DataQualityReportOut]
    total: int
    limit: int
    offset: int


class DataQualityIssuePage(BaseModel):
    items: list[DataQualityIssueOut]
    total: int
    limit: int
    offset: int
