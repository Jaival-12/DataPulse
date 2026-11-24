"""Airflow-independent helpers used by the DataPulse DAG generator."""
import json
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAG_PREFIX = "datapulse_pipeline_"
DAG_ID_PATTERN = re.compile(r"^datapulse_pipeline_[a-f0-9]{32}$")


class DataPulseResponseError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message[:500])
        self.status_code = status_code


def pipeline_id_to_dag_id(pipeline_id: str) -> str:
    try:
        return f"{DAG_PREFIX}{uuid.UUID(pipeline_id).hex}"
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Pipeline ID must be a UUID.") from exc


def read_schedule_manifests(schedules_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(schedules_dir)
    if not root.is_dir():
        return []
    manifests = []
    for path in sorted(root.glob("datapulse_pipeline_*.json")):
        if not DAG_ID_PATTERN.fullmatch(path.stem):
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                continue
            if manifest.get("dag_id") != path.stem or manifest.get("dag_id") != pipeline_id_to_dag_id(manifest.get("pipeline_id", "")):
                continue
            if manifest.get("schedule_type") not in {"hourly", "daily", "weekly", "custom"}:
                continue
            if not isinstance(manifest.get("cron_expression"), str) or not manifest["cron_expression"].strip():
                continue
            if not isinstance(manifest.get("timezone"), str) or not manifest["timezone"].strip():
                continue
            ZoneInfo(manifest["timezone"])
            if type(manifest.get("retries")) is not int or not 0 <= manifest["retries"] <= 5:
                continue
            if type(manifest.get("retry_delay_seconds")) is not int or not 1 <= manifest["retry_delay_seconds"] <= 3600:
                continue
            if type(manifest.get("timeout_seconds")) is not int or not 30 <= manifest["timeout_seconds"] <= 14400:
                continue
            start_date = manifest.get("start_date")
            if start_date is not None:
                if not isinstance(start_date, str):
                    continue
                parsed_start = datetime.fromisoformat(start_date)
                if parsed_start.tzinfo is None or parsed_start.utcoffset() is None:
                    continue
            manifests.append(manifest)
        except (OSError, ValueError, TypeError, ZoneInfoNotFoundError, json.JSONDecodeError):
            continue
    return manifests


def request_datapulse(method: str, path: str, payload: dict | None, api_url: str,
                      token: str, timeout: int = 15) -> dict:
    if not token:
        raise ValueError("DataPulse internal service token is not configured.")
    if timeout < 1 or timeout > 14400:
        raise ValueError("DataPulse API timeout must be between 1 and 14400 seconds.")
    url = f"{api_url.rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = "DataPulse rejected the orchestration request."
        try:
            body = json.loads(exc.read())
            if isinstance(body.get("detail"), str):
                detail = body["detail"][:500]
        except (ValueError, TypeError, AttributeError):
            pass
        raise DataPulseResponseError(exc.code, detail) from exc

