from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from app.utils.cron_validation import is_valid_cron
ScheduleType = Literal["hourly", "daily", "weekly", "custom"]
RunStatus = Literal["queued", "running", "success", "failed"]
SCHEDULE_CRONS = {"hourly": "0 * * * *", "daily": "0 0 * * *", "weekly": "0 0 * * 0"}


class PipelineScheduleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_type: ScheduleType = "daily"
    cron_expression: StrictStr | None = Field(default=None, max_length=120)
    timezone: StrictStr = "UTC"
    start_date: datetime | None = None
    retries: int = Field(default=2, ge=0, le=5)
    retry_delay_seconds: int = Field(default=60, ge=1, le=3600)
    timeout_seconds: int = Field(default=3600, ge=30, le=14400)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone name") from exc
        return value

    @field_validator("start_date")
    @classmethod
    def aware_start_date(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("start_date must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_cron_and_frequency(self):
        if self.schedule_type == "custom":
            expression = (self.cron_expression or "").strip()
            if len(expression.split()) != 5 or not is_valid_cron(expression):
                raise ValueError("cron_expression must be a valid five-field cron expression")
            object.__setattr__(self, "cron_expression", expression)
        else:
            if self.cron_expression is not None:
                raise ValueError("cron_expression is only accepted for custom schedules")
            object.__setattr__(self, "cron_expression", SCHEDULE_CRONS[self.schedule_type])
        return self


class PipelineScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pipeline_id: str
    schedule_type: ScheduleType
    cron_expression: str
    timezone: str
    start_date: datetime | None
    enabled: bool
    retries: int
    retry_delay_seconds: int
    timeout_seconds: int
    airflow_dag_id: str
    next_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_scheduled_execution_at: datetime | None


class ScheduledPipelineItem(BaseModel):
    pipeline_id: str
    pipeline_name: str
    schedule: PipelineScheduleOut
    latest_run: "OrchestrationRunOut | None" = None


class ScheduledPipelinePage(BaseModel):
    items: list[ScheduledPipelineItem]
    total: int


class OrchestrationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    pipeline_id: str
    airflow_dag_id: str
    airflow_run_id: str
    airflow_task_id: str | None
    status: RunStatus
    execution_id: str | None
    try_number: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    updated_at: datetime


class OrchestrationRunPage(BaseModel):
    items: list[OrchestrationRunOut]
    total: int
    limit: int
    offset: int


class OrchestrationStatusOut(BaseModel):
    orchestration_enabled: bool
    schedule_directory_writable: bool
    scheduler_service: str = "Airflow LocalExecutor"


class AirflowExecutionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dag_run_id: StrictStr = Field(min_length=1, max_length=250, pattern=r"^[A-Za-z0-9_.:+-]+$")
    try_number: int = Field(default=1, ge=1, le=100)


class OrchestrationRunReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipeline_id: StrictStr = Field(min_length=1, max_length=36)
    airflow_dag_id: StrictStr = Field(min_length=1, max_length=250)
    airflow_run_id: StrictStr = Field(min_length=1, max_length=250, pattern=r"^[A-Za-z0-9_.:+-]+$")
    status: RunStatus
    task_id: StrictStr | None = Field(default=None, max_length=250)
    try_number: int = Field(default=0, ge=0, le=100)
    execution_id: StrictStr | None = Field(default=None, max_length=36)
    error_message: StrictStr | None = Field(default=None, max_length=1000)


class InternalPipelineValidationOut(BaseModel):
    pipeline_id: str
    source_dataset_id: str
    airflow_dag_id: str
    valid: bool = True


ScheduledPipelineItem.model_rebuild()
