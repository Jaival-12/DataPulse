import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.pipeline import PipelineDefinition, PipelineExecution, ProcessedDataset, TransformationStep
from app.schemas.pipeline import PipelineCreate, PipelineExecutionOut, PipelineExecutionPage, PipelineOut, PipelinePage, PipelineUpdate
from app.schemas.processed_dataset import ExecutionLogOut, ProcessedDatasetOut, ProcessedDatasetPage, ProcessedDatasetPreview
from app.services.ingestion import read_preview
from app.services.pipeline_service import (
    ProcessedFileError, execute_pipeline,
    safe_processed_path,
)
from app.services.orchestration_service import remove_schedule_manifest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pipelines", "processed datasets"])


def _pipeline(db: Session, pipeline_id: str) -> PipelineDefinition:
    pipeline = db.query(PipelineDefinition).options(joinedload(PipelineDefinition.steps)).filter(PipelineDefinition.id == pipeline_id).one_or_none()
    if pipeline is None:
        raise HTTPException(404, "Pipeline not found.")
    return pipeline


def _source_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).one_or_none()
    if dataset is None:
        raise HTTPException(404, "Source dataset not found.")
    if dataset.format not in {"csv", "json"}:
        raise HTTPException(415, "Only CSV and JSON source datasets are supported.")
    return dataset


def _set_steps(db: Session, pipeline: PipelineDefinition, requested_steps) -> None:
    if pipeline.steps:
        pipeline.steps.clear()
        db.flush()
    pipeline.steps = [
        TransformationStep(operation=step.operation, configuration=step.normalized_config(), execution_order=index)
        for index, step in enumerate(requested_steps)
    ]


def _validate_steps_against_dataset(steps, dataset: Dataset) -> None:
    names = [column.name for column in dataset.columns]
    def require(name):
        if name not in names:
            raise HTTPException(422, f"Column '{name}' is not available at this step.")
    for step in steps:
        config = step.config if hasattr(step, "config") else step.configuration
        operation = step.operation
        if operation == "remove_duplicates":
            for column in config.get("subset", []) or []: require(column)
        elif operation == "fill_missing":
            if config.get("strategy") == "drop_rows":
                for column in config.get("columns", []) or []: require(column)
            else: require(config.get("column"))
        elif operation == "rename_columns":
            mapping = config.get("mapping", {})
            for column in mapping: require(column)
            output_names = [mapping.get(name, name) for name in names]
            if len(output_names) != len(set(output_names)):
                raise HTTPException(422, "Rename would create duplicate column names.")
            names = output_names
        elif operation == "remove_columns":
            for column in config["columns"]: require(column)
            if len(config["columns"]) >= len(names):
                raise HTTPException(422, "At least one column must remain.")
            names = [name for name in names if name not in config["columns"]]
        elif operation == "reorder_columns":
            if len(config["columns"]) != len(names) or set(config["columns"]) != set(names):
                raise HTTPException(422, "reorder columns must list every available column exactly once.")
            names = list(config["columns"])
        elif operation in {"filter_rows", "convert_type"}:
            require(config.get("column"))
        elif operation in {"trim_whitespace", "lowercase", "uppercase", "title_case"}:
            for column in config["columns"]: require(column)
        elif operation == "add_calculated_column":
            for operand in (config["left"], config["right"]):
                if isinstance(operand, dict): require(operand["column"])
            if config["name"] in names:
                raise HTTPException(422, f"Calculated output column '{config['name']}' already exists.")
            names.append(config["name"])


@router.post("/pipelines", response_model=PipelineOut, status_code=201)
def create_pipeline(body: PipelineCreate, db: Session = Depends(get_db)):
    source = _source_dataset(db, body.source_dataset_id)
    _validate_steps_against_dataset(body.steps, source)
    pipeline = PipelineDefinition(name=body.name, description=body.description, source_dataset=source, configuration={"output_format": body.output_format})
    try:
        db.add(pipeline)
        db.flush()
        _set_steps(db, pipeline, body.steps)
        db.commit()
        db.refresh(pipeline)
        return pipeline
    except Exception as exc:
        db.rollback()
        logger.exception("Could not save pipeline")
        raise HTTPException(500, "Pipeline could not be saved.") from exc


@router.get("/pipelines", response_model=PipelinePage)
def list_pipelines(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(PipelineDefinition)
    total = query.count()
    items = query.options(joinedload(PipelineDefinition.steps)).order_by(PipelineDefinition.created_at.desc()).offset(offset).limit(limit).all()
    return PipelinePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/pipelines/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    return _pipeline(db, pipeline_id)


@router.put("/pipelines/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(pipeline_id: str, body: PipelineUpdate, db: Session = Depends(get_db)):
    pipeline = _pipeline(db, pipeline_id)
    changes = body.model_dump(exclude_unset=True)
    if "source_dataset_id" in changes and changes["source_dataset_id"] is not None:
        pipeline.source_dataset = _source_dataset(db, changes["source_dataset_id"])
        _validate_steps_against_dataset(pipeline.steps, pipeline.source_dataset)
    if "name" in changes and changes["name"] is not None:
        pipeline.name = changes["name"]
    if "description" in changes:
        pipeline.description = changes["description"]
    if "output_format" in changes and changes["output_format"] is not None:
        pipeline.configuration = {**(pipeline.configuration or {}), "output_format": changes["output_format"]}
    if "steps" in changes and changes["steps"] is not None:
        _validate_steps_against_dataset(body.steps or [], pipeline.source_dataset)
        _set_steps(db, pipeline, body.steps or [])
    pipeline.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(pipeline)
        return pipeline
    except Exception as exc:
        db.rollback()
        logger.exception("Could not update pipeline %s", pipeline_id)
        raise HTTPException(500, "Pipeline could not be updated.") from exc


@router.delete("/pipelines/{pipeline_id}", status_code=204)
def delete_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = _pipeline(db, pipeline_id)
    paths = [item.storage_path for execution in pipeline.executions for item in ([execution.processed_dataset] if execution.processed_dataset else [])]
    scheduled = pipeline.schedule is not None
    db.delete(pipeline)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, "Pipeline could not be deleted.") from exc
    if scheduled:
        try:
            remove_schedule_manifest(pipeline_id, settings.airflow_schedules_dir)
        except OSError:
            logger.warning("Could not remove Airflow schedule manifest for deleted pipeline %s", pipeline_id)
    for relative in paths:
        try:
            safe_processed_path(settings.storage_dir, relative).unlink(missing_ok=True)
        except ProcessedFileError:
            logger.warning("Skipped invalid processed path while deleting pipeline %s", pipeline_id)


@router.post("/pipelines/{pipeline_id}/execute", response_model=PipelineExecutionOut)
def run_pipeline(pipeline_id: str, db: Session = Depends(get_db)):
    pipeline = _pipeline(db, pipeline_id)
    try:
        return execute_pipeline(db, pipeline, settings.storage_dir, settings.max_profile_mb * 1024 * 1024)
    except Exception as exc:
        db.rollback()
        logger.exception("Unexpected pipeline execution persistence failure %s", pipeline_id)
        raise HTTPException(500, "Pipeline execution could not be recorded.") from exc


@router.get("/pipelines/{pipeline_id}/executions", response_model=PipelineExecutionPage)
def list_pipeline_executions(pipeline_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if db.query(PipelineDefinition.id).filter(PipelineDefinition.id == pipeline_id).first() is None:
        raise HTTPException(404, "Pipeline not found.")
    query = db.query(PipelineExecution).options(joinedload(PipelineExecution.processed_dataset)).filter(PipelineExecution.pipeline_id == pipeline_id)
    total = query.count()
    items = query.order_by(PipelineExecution.started_at.desc()).offset(offset).limit(limit).all()
    return PipelineExecutionPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/executions/{execution_id}", response_model=PipelineExecutionOut)
def get_execution(execution_id: str, db: Session = Depends(get_db)):
    execution = db.query(PipelineExecution).options(joinedload(PipelineExecution.processed_dataset)).filter(PipelineExecution.id == execution_id).one_or_none()
    if execution is None:
        raise HTTPException(404, "Pipeline execution not found.")
    return execution


@router.get("/executions/{execution_id}/logs", response_model=ExecutionLogOut)
def get_execution_logs(execution_id: str, db: Session = Depends(get_db)):
    execution = db.query(PipelineExecution).filter(PipelineExecution.id == execution_id).one_or_none()
    if execution is None:
        raise HTTPException(404, "Pipeline execution not found.")
    return ExecutionLogOut(execution_id=execution.id, logs=(execution.execution_summary or {}).get("logs", []))


@router.get("/processed-datasets", response_model=ProcessedDatasetPage)
def list_processed_datasets(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    query = db.query(ProcessedDataset)
    total = query.count()
    items = query.order_by(ProcessedDataset.created_at.desc()).offset(offset).limit(limit).all()
    return ProcessedDatasetPage(items=items, total=total, limit=limit, offset=offset)


def _processed_dataset(db: Session, processed_dataset_id: str) -> ProcessedDataset:
    item = db.query(ProcessedDataset).filter(ProcessedDataset.id == processed_dataset_id).one_or_none()
    if item is None:
        raise HTTPException(404, "Processed dataset not found.")
    return item


def _read_processed(item: ProcessedDataset, limit: int) -> list[dict]:
    try:
        path = safe_processed_path(settings.storage_dir, item.storage_path)
    except ProcessedFileError as exc:
        raise HTTPException(404, "Processed dataset content is unavailable.") from exc
    return read_preview(path, item.file_type, limit)


@router.get("/processed-datasets/{processed_dataset_id}", response_model=ProcessedDatasetOut)
def get_processed_dataset(processed_dataset_id: str, db: Session = Depends(get_db)):
    return _processed_dataset(db, processed_dataset_id)


@router.get("/processed-datasets/{processed_dataset_id}/preview", response_model=ProcessedDatasetPreview)
def preview_processed_dataset(processed_dataset_id: str, limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_db)):
    item = _processed_dataset(db, processed_dataset_id)
    return ProcessedDatasetPreview(dataset=item, rows=_read_processed(item, limit))


@router.get("/processed-datasets/{processed_dataset_id}/download")
def download_processed_dataset(processed_dataset_id: str, db: Session = Depends(get_db)):
    item = _processed_dataset(db, processed_dataset_id)
    try:
        path = safe_processed_path(settings.storage_dir, item.storage_path)
    except ProcessedFileError as exc:
        raise HTTPException(404, "Processed dataset content is unavailable.") from exc
    if not path.is_file():
        raise HTTPException(404, "Processed dataset content is unavailable.")
    media_type = "text/csv" if item.file_type == "csv" else "application/json"
    return FileResponse(path, media_type=media_type, filename=item.filename)
