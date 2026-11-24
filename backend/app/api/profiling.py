import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.dataset_profile import DatasetProfile
from app.repositories.datasets import get_dataset
from app.schemas.profiling import DatasetProfileOut
from app.services.profiling_service import (
    InvalidProfileSource, ProfileSourceMissing, ProfileTooLarge,
    UnsupportedProfileFormat, build_profile, load_dataset_frame,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/datasets", tags=["profiling"])

def _profile_path(dataset: Dataset) -> Path:
    return settings.storage_dir / f"{dataset.storage_key}.{dataset.format}"

def _load_and_profile(dataset: Dataset) -> dict:
    frame = load_dataset_frame(_profile_path(dataset), dataset.format, settings.max_profile_mb * 1024 * 1024, settings.storage_dir)
    return build_profile(frame)

def _save_profile(db: Session, dataset_id: str, profile_data: dict) -> DatasetProfile:
    now = datetime.now(timezone.utc)
    model = DatasetProfile
    values = {"id": str(uuid.uuid4()), "dataset_id": dataset_id, "profile_data": profile_data, "generated_at": now, "updated_at": now}
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(model).values(**values).on_conflict_do_update(index_elements=[model.dataset_id], set_={"profile_data": profile_data, "generated_at": now, "updated_at": now})
        db.execute(statement)
    elif dialect == "sqlite":
        statement = sqlite_insert(model).values(**values).on_conflict_do_update(index_elements=[model.dataset_id], set_={"profile_data": profile_data, "generated_at": now, "updated_at": now})
        db.execute(statement)
    else:
        saved = db.query(model).filter(model.dataset_id == dataset_id).one_or_none()
        if saved is None:
            db.add(model(**values))
        else:
            saved.profile_data = profile_data
            saved.generated_at = now
            saved.updated_at = now
    db.commit()
    return db.query(model).filter(model.dataset_id == dataset_id).one()

def _generate(dataset_id: str, db: Session) -> DatasetProfileOut:
    dataset = get_dataset(db, dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found.")
    try:
        report = _load_and_profile(dataset)
    except ProfileSourceMissing:
        raise HTTPException(404, "Dataset source file is unavailable.")
    except ProfileTooLarge:
        raise HTTPException(413, f"Dataset exceeds the {settings.max_profile_mb} MB profiling limit.")
    except UnsupportedProfileFormat:
        raise HTTPException(415, "Only CSV and JSON datasets can be profiled.")
    except InvalidProfileSource:
        raise HTTPException(400, "Dataset source could not be parsed.")
    try:
        return _save_profile(db, dataset_id, report)
    except Exception as exc:
        db.rollback()
        logger.exception("Could not persist profile for dataset %s", dataset_id)
        raise HTTPException(500, "Dataset profile could not be saved.") from exc

@router.post("/{dataset_id}/profile", response_model=DatasetProfileOut)
def generate_profile(dataset_id: str, db: Session = Depends(get_db)):
    return _generate(dataset_id, db)

@router.post("/{dataset_id}/profile/refresh", response_model=DatasetProfileOut)
def refresh_profile(dataset_id: str, db: Session = Depends(get_db)):
    return _generate(dataset_id, db)

@router.get("/{dataset_id}/profile", response_model=DatasetProfileOut)
def get_profile(dataset_id: str, db: Session = Depends(get_db)):
    if get_dataset(db, dataset_id) is None:
        raise HTTPException(404, "Dataset not found.")
    profile = db.query(DatasetProfile).filter(DatasetProfile.dataset_id == dataset_id).one_or_none()
    if profile is None:
        raise HTTPException(404, "Profile has not been generated yet.")
    return profile
