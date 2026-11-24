import uuid
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.session import get_db
from app.models.dataset import Dataset, DatasetColumn
from app.repositories.datasets import get_dataset
from app.schemas.dataset import DatasetOut, DatasetPage, PreviewOut
from app.services.ingestion import inspect_upload, column_type, read_preview
from app.services.pipeline_service import ProcessedFileError, safe_processed_path
from app.services.orchestration_service import remove_schedule_manifest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"])

@router.post("", response_model=DatasetOut, status_code=201)
async def upload_dataset(file: UploadFile = File(...), db: Session = Depends(get_db)):
    payload = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB upload limit.")
    fmt, frame = inspect_upload(file.filename, payload)
    key = uuid.uuid4().hex
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    target = settings.storage_dir / f"{key}.{fmt}"
    target.write_bytes(payload)
    dataset = Dataset(name=Path(file.filename or f"dataset.{fmt}").name[:255], storage_key=key, format=fmt,
                      size_bytes=len(payload), row_count=len(frame), column_count=len(frame.columns))
    dataset.columns = [DatasetColumn(name=str(name)[:255], data_type=column_type(frame.iloc[:, i]), position=i)
                       for i, name in enumerate(frame.columns)]
    try:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        raise HTTPException(500, "Dataset could not be saved.")
    return dataset

@router.get("", response_model=DatasetPage)
def list_datasets(search: str | None = None, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(Dataset)
    if search:
        query = query.filter(Dataset.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(Dataset.created_at.desc()).offset(offset).limit(limit).all()
    return DatasetPage(items=items, total=total, limit=limit, offset=offset)

@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset_detail(dataset_id: str, db: Session = Depends(get_db)):
    dataset = get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    return dataset

@router.get("/{dataset_id}/preview", response_model=PreviewOut)
def preview_dataset(dataset_id: str, limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    dataset = get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    path = settings.storage_dir / f"{dataset.storage_key}.{dataset.format}"
    return PreviewOut(dataset=dataset, rows=read_preview(path, dataset.format, limit))

@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found.")
    path = settings.storage_dir / f"{dataset.storage_key}.{dataset.format}"
    processed_paths = [item.storage_path for item in dataset.processed_datasets]
    scheduled_pipeline_ids = [item.id for item in dataset.pipelines if item.schedule is not None]
    db.delete(dataset)
    db.commit()
    for pipeline_id in scheduled_pipeline_ids:
        try:
            remove_schedule_manifest(pipeline_id, settings.airflow_schedules_dir)
        except OSError:
            logger.warning("Could not remove Airflow schedule manifest for pipeline %s after source deletion", pipeline_id)
    path.unlink(missing_ok=True)
    for relative in processed_paths:
        try:
            safe_processed_path(settings.storage_dir, relative).unlink(missing_ok=True)
        except ProcessedFileError:
            pass
