from pydantic import BaseModel, ConfigDict
from datetime import datetime

class ColumnOut(BaseModel):
    name: str
    data_type: str
    position: int
    model_config = ConfigDict(from_attributes=True)

class DatasetOut(BaseModel):
    id: str
    name: str
    format: str
    size_bytes: int
    row_count: int
    column_count: int
    created_at: datetime
    columns: list[ColumnOut] = []
    model_config = ConfigDict(from_attributes=True)

class DatasetPage(BaseModel):
    items: list[DatasetOut]
    total: int
    limit: int
    offset: int

class PreviewOut(BaseModel):
    dataset: DatasetOut
    rows: list[dict[str, object]]
