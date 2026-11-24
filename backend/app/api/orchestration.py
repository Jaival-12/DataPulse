"""Pipeline schedule management, private Airflow bridge, and run monitoring."""
import hmac
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.pipeline import OrchestrationRun, PipelineDefinition, PipelineExecution, PipelineSchedule
from app.schemas.pipeline import PipelineExecutionOut
from app.schemas.orchestration import (
    AirflowExecutionIn, InternalPipelineValidationOut, OrchestrationRunOut,
    OrchestrationRunPage, OrchestrationRunReportIn, OrchestrationStatusOut,
    PipelineScheduleIn, PipelineScheduleOut, ScheduledPipelineItem, ScheduledPipelinePage,
)
from app.services.orchestration_service import (
    get_or_create_run, manifest_path, pipeline_dag_id, remove_schedule_manifest,
    restore_schedule_manifest, update_run_report, write_schedule_manifest,
)
from app.services.pipeline_service import PipelineInputError, execute_pipeline, source_path

logger = logging.getLogger(__name__)
schedule_router = APIRouter(prefix="/pipelines", tags=["pipeline schedules"])
monitor_router = APIRouter(prefix="/orchestration", tags=["orchestration"])
internal_router = APIRouter(prefix="/internal/orchestration", tags=["internal orchestration"], include_in_schema=False)


def _get_pipeline(db: Session, pipeline_id: str) -> PipelineDefinition:
    pipeline = db.query(PipelineDefinition).options(joinedload(PipelineDefinition.steps), joinedload(PipelineDefinition.source_dataset)).filter_by(id=pipeline_id).one_or_none()
    if pipeline is None:
        raise HTTPException(404, "Pipeline not found.")
    return pipeline


def _schedule(db: Session, pipeline_id: str) -> PipelineSchedule:
    schedule = db.query(PipelineSchedule).filter_by(pipeline_id=pipeline_id).one_or_none()
    if schedule is None:
        raise HTTPException(404, "Pipeline schedule not found.")
    return schedule


def _authorized(authorization: str | None) -> None:
    configured = settings.datapulse_internal_token
    if not configured:
        raise HTTPException(503, "Internal orchestration authentication is not configured.")
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, configured):
        raise HTTPException(401, "Invalid internal service credentials.", headers={"WWW-Authenticate": "Bearer"})


def _require_internal_token() -> None:
    if not settings.datapulse_internal_token:
        raise HTTPException(503, "Configure the internal service token before enabling schedules.")


def _replace_manifest_and_commit(db: Session, schedule: PipelineSchedule) -> PipelineSchedule:
    path = manifest_path(schedule.pipeline_id, settings.airflow_schedules_dir)
    old_contents = path.read_bytes() if path.is_file() else None
    try:
        if schedule.enabled:
            write_schedule_manifest(schedule, settings.airflow_schedules_dir)
        else:
            remove_schedule_manifest(schedule.pipeline_id, settings.airflow_schedules_dir)
        db.commit()
        db.refresh(schedule)
        return schedule
    except Exception as exc:
        db.rollback()
        try:
            restore_schedule_manifest(path, old_contents)
        except OSError:
            logger.exception("Could not restore schedule manifest for pipeline %s", schedule.pipeline_id)
        if isinstance(exc, HTTPException):
            raise
        logger.exception("Could not save schedule for pipeline %s", schedule.pipeline_id)
        raise HTTPException(503, "Schedule could not be saved to the orchestration directory.") from exc


def _schedule_values(schedule: PipelineSchedule, body: PipelineScheduleIn) -> None:
    schedule.schedule_type = body.schedule_type
    schedule.cron_expression = body.cron_expression or ""
    schedule.timezone = body.timezone
    schedule.start_date = body.start_date
    schedule.retries = body.retries
    schedule.retry_delay_seconds = body.retry_delay_seconds
    schedule.timeout_seconds = body.timeout_seconds
    schedule.updated_at = datetime.now(timezone.utc)


@schedule_router.post("/{pipeline_id}/schedule", response_model=PipelineScheduleOut, status_code=201)
def create_schedule(pipeline_id: str, body: PipelineScheduleIn, db: Session = Depends(get_db)):
    _require_internal_token()
    pipeline = _get_pipeline(db, pipeline_id)
    if db.query(PipelineSchedule.pipeline_id).filter_by(pipeline_id=pipeline_id).first():
        raise HTTPException(409, "A schedule already exists for this pipeline.")
    schedule = PipelineSchedule(pipeline_id=pipeline.id, airflow_dag_id=pipeline_dag_id(pipeline.id), enabled=True)
    _schedule_values(schedule, body)
    try:
        db.add(schedule)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "A schedule already exists for this pipeline.") from exc
    return _replace_manifest_and_commit(db, schedule)


@schedule_router.get("/{pipeline_id}/schedule", response_model=PipelineScheduleOut)
def get_schedule(pipeline_id: str, db: Session = Depends(get_db)):
    _get_pipeline(db, pipeline_id)
    return _schedule(db, pipeline_id)


@schedule_router.put("/{pipeline_id}/schedule", response_model=PipelineScheduleOut)
def update_schedule(pipeline_id: str, body: PipelineScheduleIn, db: Session = Depends(get_db)):
    _get_pipeline(db, pipeline_id)
    schedule = _schedule(db, pipeline_id)
    if schedule.enabled:
        _require_internal_token()
    _schedule_values(schedule, body)
    return _replace_manifest_and_commit(db, schedule)


@schedule_router.delete("/{pipeline_id}/schedule", status_code=204)
def delete_schedule(pipeline_id: str, db: Session = Depends(get_db)):
    _get_pipeline(db, pipeline_id)
    schedule = _schedule(db, pipeline_id)
    path = manifest_path(pipeline_id, settings.airflow_schedules_dir)
    old_contents = path.read_bytes() if path.is_file() else None
    try:
        remove_schedule_manifest(pipeline_id, settings.airflow_schedules_dir)
        db.delete(schedule)
        db.commit()
    except Exception as exc:
        db.rollback()
        restore_schedule_manifest(path, old_contents)
        logger.exception("Could not delete schedule for pipeline %s", pipeline_id)
        raise HTTPException(503, "Schedule could not be deleted.") from exc


def _set_enabled(pipeline_id: str, enabled: bool, db: Session):
    if enabled:
        _require_internal_token()
    _get_pipeline(db, pipeline_id)
    schedule = _schedule(db, pipeline_id)
    schedule.enabled = enabled
    schedule.updated_at = datetime.now(timezone.utc)
    return _replace_manifest_and_commit(db, schedule)


@schedule_router.post("/{pipeline_id}/schedule/enable", response_model=PipelineScheduleOut)
def enable_schedule(pipeline_id: str, db: Session = Depends(get_db)):
    return _set_enabled(pipeline_id, True, db)


@schedule_router.post("/{pipeline_id}/schedule/disable", response_model=PipelineScheduleOut)
def disable_schedule(pipeline_id: str, db: Session = Depends(get_db)):
    return _set_enabled(pipeline_id, False, db)


@internal_router.get("/pipelines/{pipeline_id}/validate", response_model=InternalPipelineValidationOut)
def validate_scheduled_pipeline(pipeline_id: str, dag_run_id: str = Query(min_length=1, max_length=250, pattern=r"^[A-Za-z0-9_.:+-]+$"),
                                authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    _authorized(authorization)
    try:
        dag_id = pipeline_dag_id(pipeline_id)
    except ValueError as exc:
        raise HTTPException(422, "Invalid pipeline ID.") from exc
    pipeline = _get_pipeline(db, pipeline_id)
    schedule = _schedule(db, pipeline_id)
    if schedule.airflow_dag_id != dag_id:
        raise HTTPException(409, "Pipeline schedule identity is invalid.")
    if not schedule.enabled:
        raise HTTPException(409, "Pipeline schedule is disabled.")
    source = db.query(Dataset).filter_by(id=pipeline.source_dataset_id).one_or_none()
    if source is None:
        raise HTTPException(404, "Pipeline source dataset is unavailable.")
    try:
        source_path(source, settings.storage_dir)
    except PipelineInputError as exc:
        raise HTTPException(422, "Pipeline source file is unavailable or invalid.") from exc
    try:
        get_or_create_run(db, pipeline.id, dag_id, dag_run_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Could not record scheduled run validation")
        raise HTTPException(503, "Orchestration run could not be recorded.") from exc
    return InternalPipelineValidationOut(pipeline_id=pipeline.id, source_dataset_id=source.id, airflow_dag_id=dag_id)


@internal_router.post("/pipelines/{pipeline_id}/execute", response_model=PipelineExecutionOut)
def execute_scheduled_pipeline(pipeline_id: str, body: AirflowExecutionIn,
                               authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    _authorized(authorization)
    try:
        dag_id = pipeline_dag_id(pipeline_id)
    except ValueError as exc:
        raise HTTPException(422, "Invalid pipeline ID.") from exc
    pipeline = _get_pipeline(db, pipeline_id)
    schedule = _schedule(db, pipeline_id)
    if schedule.airflow_dag_id != dag_id or not schedule.enabled:
        raise HTTPException(409, "Pipeline schedule is disabled or invalid.")
    try:
        run = get_or_create_run(db, pipeline.id, dag_id, body.dag_run_id)
        run.airflow_task_id = "execute_pipeline"
        schedule.last_scheduled_execution_at = datetime.now(timezone.utc)
        existing = db.query(PipelineExecution).filter_by(airflow_dag_id=dag_id, airflow_run_id=body.dag_run_id).one_or_none()
        if existing is not None:
            if existing.status == "running":
                db.commit()
                raise HTTPException(503, "This Airflow run is already executing.")
            run.execution_id = existing.id
            run.try_number = max(run.try_number, body.try_number)
            db.commit()
            return existing
        execution = execute_pipeline(
            db, pipeline, settings.storage_dir, settings.max_profile_mb * 1024 * 1024,
            airflow_dag_id=dag_id, airflow_run_id=body.dag_run_id,
        )
        if execution.status == "running":
            db.commit()
            raise HTTPException(503, "This Airflow run is already executing.")
        run.execution_id = execution.id
        run.try_number = max(run.try_number, body.try_number)
        db.commit()
        return execution
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Scheduled pipeline execution failed before an ETL result was recorded")
        raise HTTPException(503, "Scheduled pipeline execution could not be recorded.") from exc


@internal_router.post("/runs/report", response_model=OrchestrationRunOut)
def report_orchestration_run(body: OrchestrationRunReportIn,
                             authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    _authorized(authorization)
    try:
        run = update_run_report(db, body)
        db.commit()
        db.refresh(run)
        return run
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Could not synchronize Airflow run state")
        raise HTTPException(503, "Orchestration status could not be synchronized.") from exc


@monitor_router.get("/status", response_model=OrchestrationStatusOut)
def orchestration_status():
    directory = settings.airflow_schedules_dir
    return OrchestrationStatusOut(
        orchestration_enabled=bool(settings.datapulse_internal_token) and directory.is_dir() and os.access(directory, os.W_OK),
        schedule_directory_writable=directory.is_dir() and os.access(directory, os.W_OK),
    )


@monitor_router.get("/pipelines", response_model=ScheduledPipelinePage)
def list_scheduled_pipelines(db: Session = Depends(get_db)):
    schedules = db.query(PipelineSchedule).options(joinedload(PipelineSchedule.pipeline)).order_by(PipelineSchedule.created_at.desc()).all()
    items = []
    for schedule in schedules:
        latest = db.query(OrchestrationRun).filter_by(pipeline_id=schedule.pipeline_id).order_by(OrchestrationRun.updated_at.desc()).first()
        items.append(ScheduledPipelineItem(pipeline_id=schedule.pipeline_id, pipeline_name=schedule.pipeline.name,
                                           schedule=schedule, latest_run=latest))
    return ScheduledPipelinePage(items=items, total=len(items))


@monitor_router.get("/pipelines/{pipeline_id}/runs", response_model=OrchestrationRunPage)
def list_orchestration_runs(pipeline_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                            db: Session = Depends(get_db)):
    query = db.query(OrchestrationRun).filter_by(pipeline_id=pipeline_id)
    return OrchestrationRunPage(items=query.order_by(OrchestrationRun.updated_at.desc()).offset(offset).limit(limit).all(),
                                total=query.count(), limit=limit, offset=offset)


def _run(db: Session, run_id: str) -> OrchestrationRun:
    run = db.query(OrchestrationRun).filter_by(id=run_id).one_or_none()
    if run is None:
        raise HTTPException(404, "Orchestration run not found.")
    return run


@monitor_router.get("/runs/{run_id}")
def get_orchestration_run(run_id: str, db: Session = Depends(get_db)):
    run = _run(db, run_id)
    execution = db.query(PipelineExecution).filter_by(id=run.execution_id).one_or_none() if run.execution_id else None
    return {"run": OrchestrationRunOut.model_validate(run), "execution": execution}


@monitor_router.get("/runs/{run_id}/logs")
def get_orchestration_run_logs(run_id: str, db: Session = Depends(get_db)):
    run = _run(db, run_id)
    execution = db.query(PipelineExecution).filter_by(id=run.execution_id).one_or_none() if run.execution_id else None
    return {"run_id": run.id, "execution_id": run.execution_id,
            "logs": (execution.execution_summary or {}).get("logs", []) if execution else [],
            "orchestration_error": run.error_message}
