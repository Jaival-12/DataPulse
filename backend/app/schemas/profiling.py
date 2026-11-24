from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict

class DatasetProfileOut(BaseModel):
    id: str
    dataset_id: str
    profile_data: dict[str, Any]
    generated_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
