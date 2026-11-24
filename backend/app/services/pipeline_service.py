"""Bounded extract, sequential transform, and atomic load services."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.pipeline import PipelineDefinition, PipelineExecution, ProcessedDataset
from app.services.profiling_service import (
    InvalidProfileSource, ProfileSourceMissing, ProfileTooLarge,
    UnsupportedProfileFormat, load_dataset_frame,
)
from app.services.transformations import TransformationError, apply_transformation

logger = logging.getLogger(__name__)


class PipelineInputError(ValueError):
    pass


class PipelineTooLarge(ValueError):
    pass


class ProcessedFileError(ValueError):
    pass


STORAGE_KEY = re.compile(r"^[a-f0-9]{32}$")
PROCESSED_PATH = re.compile(r"^processed/[a-f0-9]{32}\.(?:csv|json)$")


def source_path(dataset: Dataset, storage_root: Path) -> Path:
    if dataset.format not in {"csv", "json"} or not STORAGE_KEY.fullmatch(dataset.storage_key):
        raise PipelineInputError("Source dataset metadata is invalid.")
    root = storage_root.resolve()
    path = (root / f"{dataset.storage_key}.{dataset.format}").resolve()
    if path.parent != root:
        raise PipelineInputError("Source dataset metadata is invalid.")
    if not path.is_file():
        raise PipelineInputError("Source dataset file is unavailable.")
    return path


def load_source_frame(dataset: Dataset, storage_root: Path, max_bytes: int) -> pd.DataFrame:
    path = source_path(dataset, storage_root)
    try:
        return load_dataset_frame(path, dataset.format, max_bytes, storage_root)
    except ProfileTooLarge as exc:
        raise PipelineTooLarge from exc
    except UnsupportedProfileFormat as exc:
        raise PipelineInputError("Only CSV and JSON source datasets are supported.") from exc
    except ProfileSourceMissing as exc:
        raise PipelineInputError("Source dataset file is unavailable.") from exc
    except InvalidProfileSource as exc:
        raise PipelineInputError("Source dataset could not be parsed.") from exc


def safe_processed_path(storage_root: Path, storage_path: str) -> Path:
    if not isinstance(storage_path, str) or not PROCESSED_PATH.fullmatch(storage_path):
        raise ProcessedFileError("Processed dataset path is invalid.")
    root = (storage_root / "processed").resolve()
    path = (storage_root / storage_path).resolve()
    if path.parent != root:
        raise ProcessedFileError("Processed dataset path is invalid.")
    return path


def write_processed_frame(frame: pd.DataFrame, output_format: str, storage_root: Path, key: str, max_bytes: int) -> tuple[Path, int, str]:
    if output_format not in {"csv", "json"} or not STORAGE_KEY.fullmatch(key):
        raise ProcessedFileError("Processed output format or key is invalid.")
    processed_root = (storage_root / "processed").resolve()
    processed_root.mkdir(parents=True, exist_ok=True)
    target = safe_processed_path(storage_root, f"processed/{key}.{output_format}")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=processed_root, prefix=".pending-", suffix=".tmp", delete=False) as temp:
            temporary_path = Path(temp.name)
            if output_format == "csv":
                frame.to_csv(temp, index=False)
            else:
                temp.write(frame.to_json(orient="records", date_format="iso", force_ascii=False))
        file_size = temporary_path.stat().st_size
        if file_size > max_bytes:
            raise PipelineTooLarge("Transformed output exceeds the configured ETL size limit.")
        os.replace(temporary_path, target)
        temporary_path = None
        return target, file_size, f"processed/{key}.{output_format}"
    except (PipelineTooLarge, ProcessedFileError):
        raise
    except Exception as exc:
        raise ProcessedFileError("Processed output could not be written.") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _safe_filename(source_name: str, key: str, output_format: str) -> str:
    stem = Path(source_name).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:180] or "dataset"
    return f"{stem}_processed_{key[:8]}.{output_format}"


def execute_pipeline(db: Session, pipeline: PipelineDefinition, storage_root: Path, max_bytes: int,
                     airflow_dag_id: str | None = None, airflow_run_id: str | None = None) -> PipelineExecution:
    if (airflow_dag_id is None) != (airflow_run_id is None):
        raise ValueError("Both Airflow DAG and run IDs are required for an orchestrated execution.")
    if airflow_dag_id is not None:
        existing = db.query(PipelineExecution).filter_by(airflow_dag_id=airflow_dag_id, airflow_run_id=airflow_run_id).one_or_none()
        if existing is not None:
            return existing
    started_clock = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    execution = PipelineExecution(
        pipeline_id=pipeline.id, source_dataset_id=pipeline.source_dataset_id,
        status="running", started_at=started_at, execution_summary={"logs": [], "step_count": len(pipeline.steps)},
        airflow_dag_id=airflow_dag_id, airflow_run_id=airflow_run_id,
    )
    db.add(execution)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if airflow_dag_id is None:
            raise
        existing = db.query(PipelineExecution).filter_by(airflow_dag_id=airflow_dag_id, airflow_run_id=airflow_run_id).one_or_none()
        if existing is not None:
            return existing
        raise
    db.refresh(execution)
    logs: list[dict] = []
    output_path: Path | None = None
    frame: pd.DataFrame | None = None
    input_rows = 0
    try:
        frame = load_source_frame(pipeline.source_dataset, storage_root, max_bytes)
        input_rows = len(frame)
        for index, step in enumerate(pipeline.steps):
            step_started = time.perf_counter()
            before = len(frame)
            try:
                transformed, summary = apply_transformation(frame, step.operation, step.configuration)
                if transformed.columns.duplicated().any():
                    raise TransformationError("Transformation produced duplicate output column names.")
                frame = transformed
                logs.append({
                    "step_id": step.id, "step_index": index, "operation": step.operation,
                    "status": "success", "duration": round(time.perf_counter() - step_started, 6),
                    "input_rows": before, "output_rows": len(frame), **summary,
                })
                logger.info("Pipeline step completed", extra={"pipeline_id": pipeline.id, "execution_id": execution.id, "step_id": step.id, "operation": step.operation, "status": "success", "input_rows": before, "output_rows": len(frame)})
            except Exception as exc:
                safe_step_error = str(exc)[:500] if isinstance(exc, TransformationError) else "Transformation step failed due to an internal error."
                logs.append({
                    "step_id": step.id, "step_index": index, "operation": step.operation,
                    "status": "failed", "duration": round(time.perf_counter() - step_started, 6),
                    "input_rows": before, "output_rows": before, "error": safe_step_error,
                })
                logger.warning("Pipeline step failed", extra={"pipeline_id": pipeline.id, "execution_id": execution.id, "step_id": step.id, "operation": step.operation, "status": "failed"})
                raise
        if frame is None:
            raise PipelineInputError("Source dataset could not be loaded.")
        output_format = pipeline.configuration.get("output_format", "csv")
        output_key = uuid.uuid4().hex
        output_path, file_size, relative_path = write_processed_frame(frame, output_format, storage_root, output_key, max_bytes)
        processed = ProcessedDataset(
            execution_id=execution.id, source_dataset_id=pipeline.source_dataset_id,
            filename=_safe_filename(pipeline.source_dataset.name, output_key, output_format),
            file_type=output_format, file_size=file_size, row_count=len(frame),
            column_count=len(frame.columns), storage_path=relative_path,
        )
        execution.processed_dataset = processed
        execution.status = "success"
        execution.total_input_rows = input_rows
        execution.total_output_rows = len(frame)
        execution.completed_at = datetime.now(timezone.utc)
        execution.duration = round(time.perf_counter() - started_clock, 6)
        execution.execution_summary = {"step_count": len(pipeline.steps), "logs": logs}
        db.commit()
        db.refresh(execution)
        return execution
    except Exception as exc:
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        # Transform/source/size errors are recorded without exposing file paths or stack traces.
        db.rollback()
        failed = db.query(PipelineExecution).filter(PipelineExecution.id == execution.id).one()
        message = "Pipeline execution failed due to an internal processing error."
        if isinstance(exc, PipelineTooLarge):
            message = "Source or transformed output exceeds the configured ETL size limit."
        elif isinstance(exc, PipelineInputError):
            message = str(exc)
        elif isinstance(exc, ProcessedFileError):
            message = str(exc)
        elif isinstance(exc, TransformationError):
            message = str(exc)[:500]
        elif logs and logs[-1].get("status") == "failed":
            message = logs[-1].get("error", "Transformation step failed.")
        failed.status = "failed"
        failed.completed_at = datetime.now(timezone.utc)
        failed.duration = round(time.perf_counter() - started_clock, 6)
        failed.total_input_rows = input_rows if frame is not None else None
        failed.total_output_rows = len(frame) if frame is not None else None
        failed.error_message = message
        if not logs:
            logs.append({"step_index": None, "operation": "extract_or_load", "status": "failed", "duration": round(time.perf_counter() - started_clock, 6), "error": message})
        failed.execution_summary = {"step_count": len(pipeline.steps), "logs": logs}
        db.commit()
        db.refresh(failed)
        return failed
