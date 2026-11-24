from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from app.schemas.processed_dataset import ProcessedDatasetOut
from app.services.transformations import OPERATIONS


class StepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RemoveDuplicatesConfig(StepConfig):
    subset: list[StrictStr] | None = Field(default=None, min_length=1)

    @field_validator("subset")
    @classmethod
    def unique_subset(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("subset must not contain duplicate columns")
        return value


class FillMissingConfig(StepConfig):
    strategy: Literal["drop_rows", "constant", "mean", "median", "mode"]
    column: StrictStr | None = None
    columns: list[StrictStr] | None = Field(default=None, min_length=1)
    value: Any = None

    @model_validator(mode="after")
    def validate_strategy_fields(self):
        if self.strategy == "drop_rows":
            if "column" in self.model_fields_set or "value" in self.model_fields_set:
                raise ValueError("drop_rows accepts only an optional columns list")
            if "columns" in self.model_fields_set and self.columns is None:
                raise ValueError("columns must be a list when provided")
        else:
            if not self.column:
                raise ValueError("column is required for fill strategies")
            if self.strategy == "constant" and "value" not in self.model_fields_set:
                raise ValueError("constant strategy requires value")
            if self.strategy == "constant" and (self.value is None or isinstance(self.value, (dict, list))):
                raise ValueError("constant strategy requires a non-null scalar value")
            if self.strategy != "constant" and ("value" in self.model_fields_set or "columns" in self.model_fields_set):
                raise ValueError("value and columns are not accepted for this fill strategy")
        return self


class RenameColumnsConfig(StepConfig):
    mapping: dict[StrictStr, StrictStr] = Field(min_length=1)

    @field_validator("mapping")
    @classmethod
    def nonblank_names(cls, value):
        if any(not old.strip() or not new.strip() for old, new in value.items()):
            raise ValueError("column names must not be blank")
        return value


class ColumnsConfig(StepConfig):
    columns: list[StrictStr] = Field(min_length=1)

    @field_validator("columns")
    @classmethod
    def unique_nonblank_names(cls, value):
        if any(not name.strip() for name in value) or len(value) != len(set(value)):
            raise ValueError("columns must be nonblank and unique")
        return value


class FilterRowsConfig(StepConfig):
    column: StrictStr
    operator: Literal["equals", "not_equals", "greater_than", "less_than", "greater_than_or_equal", "less_than_or_equal", "contains", "not_contains", "is_null", "is_not_null"]
    value: Any = None

    @model_validator(mode="after")
    def validate_value(self):
        needs_value = self.operator not in {"is_null", "is_not_null"}
        if needs_value and "value" not in self.model_fields_set:
            raise ValueError(f"value is required for {self.operator}")
        if not needs_value and "value" in self.model_fields_set:
            raise ValueError(f"value is not accepted for {self.operator}")
        if needs_value and isinstance(self.value, (dict, list)):
            raise ValueError("value must be a scalar")
        if self.operator in {"contains", "not_contains"} and not isinstance(self.value, str):
            raise ValueError(f"{self.operator} requires a string value")
        if self.operator in {"greater_than", "less_than", "greater_than_or_equal", "less_than_or_equal"} and (not isinstance(self.value, (int, float)) or isinstance(self.value, bool)):
            raise ValueError(f"{self.operator} requires a numeric value")
        if self.operator in {"equals", "not_equals"} and self.value is None:
            raise ValueError("Use is_null or is_not_null for missing values")
        return self


class ConvertTypeConfig(StepConfig):
    column: StrictStr
    target_type: Literal["string", "integer", "float", "boolean", "date"]


class ColumnOperand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: StrictStr


Operand = ColumnOperand | StrictInt | StrictFloat


class CalculatedColumnConfig(StepConfig):
    name: StrictStr
    left: Operand
    operator: Literal["add", "subtract", "multiply", "divide"]
    right: Operand

    @field_validator("name")
    @classmethod
    def nonblank_output_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("calculated column name must not be blank")
        return value.strip()


STEP_CONFIGS: dict[str, type[StepConfig]] = {
    "remove_duplicates": RemoveDuplicatesConfig,
    "fill_missing": FillMissingConfig,
    "rename_columns": RenameColumnsConfig,
    "remove_columns": ColumnsConfig,
    "reorder_columns": ColumnsConfig,
    "filter_rows": FilterRowsConfig,
    "convert_type": ConvertTypeConfig,
    "trim_whitespace": ColumnsConfig,
    "lowercase": ColumnsConfig,
    "uppercase": ColumnsConfig,
    "title_case": ColumnsConfig,
    "add_calculated_column": CalculatedColumnConfig,
}


class TransformationStepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: StrictStr
    config: dict[str, Any]

    @model_validator(mode="after")
    def validate_operation_config(self):
        if self.operation not in OPERATIONS:
            raise ValueError(f"Unsupported operation '{self.operation}'.")
        STEP_CONFIGS[self.operation].model_validate(self.config)
        return self

    def normalized_config(self) -> dict[str, Any]:
        return STEP_CONFIGS[self.operation].model_validate(self.config).model_dump(mode="json", exclude_unset=True)


class PipelineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr = Field(min_length=1, max_length=255)
    description: StrictStr | None = None
    source_dataset_id: StrictStr
    output_format: Literal["csv", "json"] = "csv"
    steps: list[TransformationStepIn] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class PipelineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: StrictStr | None = Field(default=None, min_length=1, max_length=255)
    description: StrictStr | None = None
    source_dataset_id: StrictStr | None = None
    output_format: Literal["csv", "json"] | None = None
    steps: list[TransformationStepIn] | None = None

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("name must not be blank")
        return value.strip() if value else value


class TransformationStepOut(BaseModel):
    id: str
    operation: str
    configuration: dict[str, Any]
    execution_order: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PipelineOut(BaseModel):
    id: str
    name: str
    description: str | None
    source_dataset_id: str
    configuration: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    steps: list[TransformationStepOut]
    model_config = ConfigDict(from_attributes=True)


class PipelinePage(BaseModel):
    items: list[PipelineOut]
    total: int
    limit: int
    offset: int


class PipelineExecutionSummary(BaseModel):
    logs: list[dict[str, Any]] = Field(default_factory=list)
    step_count: int = 0


class PipelineExecutionOut(BaseModel):
    id: str
    pipeline_id: str
    source_dataset_id: str
    status: Literal["pending", "running", "success", "failed"]
    started_at: datetime
    completed_at: datetime | None
    duration: float | None
    total_input_rows: int | None
    total_output_rows: int | None
    error_message: str | None
    execution_summary: dict[str, Any]
    airflow_dag_id: str | None = None
    airflow_run_id: str | None = None
    processed_dataset: ProcessedDatasetOut | None = None
    model_config = ConfigDict(from_attributes=True)


class PipelineExecutionPage(BaseModel):
    items: list[PipelineExecutionOut]
    total: int
    limit: int
    offset: int
