"""Create one lightweight scheduled DAG per manifest written by DataPulse."""
from __future__ import annotations

import logging
import os
from datetime import timedelta
from urllib.parse import quote

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowException, AirflowFailException
from airflow.operators.python import PythonOperator
from croniter import croniter

from dag_factory import DataPulseResponseError, read_schedule_manifests, request_datapulse

logger = logging.getLogger(__name__)
SCHEDULES_DIR = os.environ.get("DATAPULSE_AIRFLOW_SCHEDULES_DIR", "/opt/airflow/dags/schedules")
API_URL = os.environ.get("DATAPULSE_API_URL", "http://api:8000/api")
SERVICE_TOKEN = os.environ.get("DATAPULSE_INTERNAL_TOKEN", "")
API_TIMEOUT = min(max(int(os.environ.get("DATAPULSE_HTTP_TIMEOUT_SECONDS", "15")), 1), 60)


def _call(method: str, path: str, payload: dict | None = None, timeout: int | None = None) -> dict:
    try:
        return request_datapulse(method, path, payload, API_URL, SERVICE_TOKEN, timeout or API_TIMEOUT)
    except DataPulseResponseError as exc:
        message = f"DataPulse returned HTTP {exc.status_code}: {exc}"
        if 400 <= exc.status_code < 500 and exc.status_code not in {408, 429}:
            raise AirflowFailException(message) from exc
        raise AirflowException(message) from exc


def _run_id(context: dict) -> str:
    dag_run = context.get("dag_run")
    run_id = getattr(dag_run, "run_id", None)
    if not run_id:
        raise AirflowFailException("Airflow did not provide a DAG run ID.")
    return run_id


def _validate_pipeline(pipeline_id: str, **context) -> dict:
    run_id = quote(_run_id(context), safe="")
    return _call("GET", f"/internal/orchestration/pipelines/{pipeline_id}/validate?dag_run_id={run_id}")


def _execute_pipeline(pipeline_id: str, timeout_seconds: int = 3600, **context) -> dict:
    task_instance = context.get("ti") or context.get("task_instance")
    request_timeout = max(1, min(int(timeout_seconds) - 5, 14400))
    result = _call("POST", f"/internal/orchestration/pipelines/{pipeline_id}/execute", {
        "dag_run_id": _run_id(context),
        "try_number": max(1, int(getattr(task_instance, "try_number", 1))),
    }, timeout=request_timeout)
    if result.get("status") != "success":
        raise AirflowFailException(result.get("error_message") or "DataPulse ETL execution failed.")
    return {"execution_id": result.get("id"), "status": result.get("status")}


def _report_run(context: dict, status: str) -> None:
    dag = context.get("dag")
    dag_run = context.get("dag_run")
    task_instance = context.get("ti") or context.get("task_instance")
    pipeline_id = (getattr(dag, "dag_id", "").removeprefix("datapulse_pipeline_") if dag else "").replace("_", "-")
    if not pipeline_id or not dag_run:
        logger.error("Could not report Airflow run: missing DAG context")
        return
    execution = None
    if task_instance is not None:
        try:
            execution = task_instance.xcom_pull(task_ids="execute_pipeline")
        except Exception:
            execution = None
    exception = context.get("exception")
    payload = {
        "pipeline_id": pipeline_id,
        "airflow_dag_id": dag.dag_id,
        "airflow_run_id": dag_run.run_id,
        "status": status,
        "task_id": getattr(task_instance, "task_id", None),
        "try_number": max(0, int(getattr(task_instance, "try_number", 0))),
        "execution_id": execution.get("execution_id") if isinstance(execution, dict) else None,
        "error_message": str(exception)[:1000] if exception and status == "failed" else None,
    }
    try:
        _call("POST", "/internal/orchestration/runs/report", payload)
    except Exception:
        logger.exception("Could not synchronize orchestration status to DataPulse")


def _on_success(context: dict) -> None:
    _report_run(context, "success")


def _on_failure(context: dict) -> None:
    _report_run(context, "failed")


def build_pipeline_dag(manifest: dict) -> DAG:
    dag_id = manifest["dag_id"]
    pipeline_id = manifest["pipeline_id"]
    cron_expression = manifest["cron_expression"]
    if not croniter.is_valid(cron_expression):
        raise ValueError(f"Invalid cron expression for DAG {dag_id}.")
    timezone = pendulum.timezone(manifest["timezone"])
    start_date = pendulum.parse(manifest["start_date"]) if manifest.get("start_date") else pendulum.datetime(2020, 1, 1, tz=timezone)
    start_date = start_date.in_timezone(timezone)
    retry_delay = timedelta(seconds=int(manifest["retry_delay_seconds"]))
    timeout = timedelta(seconds=int(manifest["timeout_seconds"]))
    default_args = {
        "owner": "datapulse",
        "depends_on_past": False,
        "retries": int(manifest["retries"]),
        "retry_delay": retry_delay,
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(hours=1),
    }
    dag = DAG(
        dag_id=dag_id,
        description=f"Scheduled DataPulse pipeline {pipeline_id}",
        schedule=cron_expression,
        start_date=start_date,
        catchup=False,
        max_active_runs=1,
        max_active_tasks=1,
        dagrun_timeout=timeout,
        default_args=default_args,
        on_success_callback=_on_success,
        on_failure_callback=_on_failure,
        tags=["datapulse", "pipeline"],
    )
    with dag:
        validate = PythonOperator(
            task_id="validate_pipeline",
            python_callable=_validate_pipeline,
            op_kwargs={"pipeline_id": pipeline_id},
        )
        execute = PythonOperator(
            task_id="execute_pipeline",
            python_callable=_execute_pipeline,
            op_kwargs={"pipeline_id": pipeline_id, "timeout_seconds": int(manifest["timeout_seconds"])},
            execution_timeout=timeout,
        )
        validate >> execute
    return dag


for _schedule in read_schedule_manifests(SCHEDULES_DIR):
    globals()[_schedule["dag_id"]] = build_pipeline_dag(_schedule)
