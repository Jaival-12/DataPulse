from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class ProcessedDatasetOut(BaseModel):
    id: str
    execution_id: str
    source_dataset_id: str
    filename: str
    file_type: str
    file_size: int
    row_count: int
    column_count: int
    storage_path: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ProcessedDatasetPage(BaseModel):
    items: list[ProcessedDatasetOut]
    total: int
    limit: int
    offset: int


class ProcessedDatasetPreview(BaseModel):
    dataset: ProcessedDatasetOut
    rows: list[dict[str, Any]]


class ExecutionLogOut(BaseModel):
    execution_id: str
    logs: list[dict[str, Any]]
