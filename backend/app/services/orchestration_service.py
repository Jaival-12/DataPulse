"""Small helpers for schedule manifests and Airflow run mirroring."""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.pipeline import OrchestrationRun, PipelineSchedule
from app.schemas.orchestration import OrchestrationRunReportIn

DAG_PREFIX = "datapulse_pipeline_"
DAG_ID_PATTERN = re.compile(r"^datapulse_pipeline_[a-f0-9]{32}$")


def pipeline_dag_id(pipeline_id: str) -> str:
    try:
        normalized = uuid.UUID(pipeline_id).hex
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Pipeline ID must be a UUID.") from exc
    return f"{DAG_PREFIX}{normalized}"


def manifest_path(pipeline_id: str, schedules_dir: Path) -> Path:
    dag_id = pipeline_dag_id(pipeline_id)
    root = schedules_dir.resolve()
    path = (root / f"{dag_id}.json").resolve()
    if path.parent != root:
        raise ValueError("Schedule manifest path is invalid.")
    return path


def schedule_manifest(schedule: PipelineSchedule) -> dict:
    return {
        "pipeline_id": schedule.pipeline_id,
        "dag_id": schedule.airflow_dag_id,
        "schedule_type": schedule.schedule_type,
        "cron_expression": schedule.cron_expression,
        "timezone": schedule.timezone,
        "start_date": schedule.start_date.isoformat() if schedule.start_date else None,
        "retries": schedule.retries,
        "retry_delay_seconds": schedule.retry_delay_seconds,
        "timeout_seconds": schedule.timeout_seconds,
    }


def write_schedule_manifest(schedule: PipelineSchedule, schedules_dir: Path) -> Path:
    if not schedule.enabled:
        raise ValueError("Disabled schedules must not produce a DAG manifest.")
    expected_dag_id = pipeline_dag_id(schedule.pipeline_id)
    if schedule.airflow_dag_id != expected_dag_id:
        raise ValueError("Schedule DAG ID does not match its pipeline ID.")
    destination = manifest_path(schedule.pipeline_id, schedules_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                         prefix=f".{destination.stem}-", suffix=".tmp", delete=False) as handle:
            temporary_path = Path(handle.name)
            json.dump(schedule_manifest(schedule), handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, destination)
        temporary_path = None
        return destination
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def remove_schedule_manifest(pipeline_id: str, schedules_dir: Path) -> None:
    manifest_path(pipeline_id, schedules_dir).unlink(missing_ok=True)


def restore_schedule_manifest(path: Path, old_contents: bytes | None) -> None:
    if old_contents is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp", delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(old_contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def get_or_create_run(db: Session, pipeline_id: str, dag_id: str, airflow_run_id: str) -> OrchestrationRun:
    if dag_id != pipeline_dag_id(pipeline_id):
        raise ValueError("DAG ID does not match the pipeline ID.")
    run = db.query(OrchestrationRun).filter_by(airflow_dag_id=dag_id, airflow_run_id=airflow_run_id).one_or_none()
    if run is None:
        run = OrchestrationRun(pipeline_id=pipeline_id, airflow_dag_id=dag_id,
                               airflow_run_id=airflow_run_id, status="running",
                               started_at=datetime.now(timezone.utc))
        db.add(run)
        db.flush()
    elif run.pipeline_id != pipeline_id:
        raise ValueError("Airflow run identity does not match the pipeline.")
    elif run.status in {"queued", "running"} and run.started_at is None:
        run.started_at = datetime.now(timezone.utc)
    return run


def update_run_report(db: Session, report: OrchestrationRunReportIn) -> OrchestrationRun:
    expected_dag_id = pipeline_dag_id(report.pipeline_id)
    if report.airflow_dag_id != expected_dag_id:
        raise ValueError("DAG ID does not match the pipeline ID.")
    run = db.query(OrchestrationRun).filter_by(
        airflow_dag_id=report.airflow_dag_id, airflow_run_id=report.airflow_run_id,
    ).one_or_none()
    now = datetime.now(timezone.utc)
    if run is None:
        run = OrchestrationRun(
            pipeline_id=report.pipeline_id, airflow_dag_id=report.airflow_dag_id,
            airflow_run_id=report.airflow_run_id, status=report.status,
            started_at=now if report.status in {"running", "success", "failed"} else None,
            try_number=report.try_number, airflow_task_id=report.task_id,
            execution_id=report.execution_id, error_message=report.error_message,
            completed_at=now if report.status in {"success", "failed"} else None,
        )
        db.add(run)
    elif run.pipeline_id != report.pipeline_id:
        raise ValueError("Airflow run identity does not match the pipeline.")
    terminal = run.status in {"success", "failed"}
    if not terminal or report.status == run.status:
        run.status = report.status
        if report.status in {"running", "success", "failed"} and run.started_at is None:
            run.started_at = now
        if report.status in {"success", "failed"}:
            run.completed_at = now
        if report.error_message is not None:
            run.error_message = report.error_message[:1000]
    if report.task_id is not None:
        run.airflow_task_id = report.task_id
    if report.try_number:
        run.try_number = max(run.try_number, report.try_number)
    if report.execution_id is not None:
        run.execution_id = report.execution_id
    run.updated_at = now
    db.flush()
    return run
