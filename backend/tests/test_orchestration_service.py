from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.schemas.orchestration import PipelineScheduleIn
from app.services.orchestration_service import pipeline_dag_id, remove_schedule_manifest, write_schedule_manifest


def test_schedule_normalizes_named_frequency_and_validates_configuration():
    config = PipelineScheduleIn(schedule_type="weekly", timezone="Asia/Kolkata", retries=3,
                                retry_delay_seconds=90, timeout_seconds=900,
                                start_date=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert config.cron_expression == "0 0 * * 0"
    assert config.timezone == "Asia/Kolkata"
    assert config.retries == 3 and config.retry_delay_seconds == 90


@pytest.mark.parametrize("payload", [
    {"schedule_type": "custom", "cron_expression": "bad cron"},
    {"schedule_type": "custom", "cron_expression": "0 0 * * *", "timezone": "Mars/Olympus"},
    {"schedule_type": "hourly", "retries": 6},
    {"schedule_type": "daily", "timeout_seconds": 0},
    {"schedule_type": "daily", "start_date": "2026-01-01T00:00:00"},
])
def test_schedule_rejects_invalid_cron_timezone_or_bounds(payload):
    with pytest.raises(ValidationError):
        PipelineScheduleIn(**payload)


def test_custom_cron_and_pipeline_dag_mapping_are_stable():
    config = PipelineScheduleIn(schedule_type="custom", cron_expression="15 4 * * 1-5", timezone="UTC")
    assert config.cron_expression == "15 4 * * 1-5"
    pipeline_id = "cc50d35e-50b7-4938-9474-d8c3c64f920e"
    assert pipeline_dag_id(pipeline_id) == pipeline_dag_id(pipeline_id)
    assert pipeline_dag_id(pipeline_id) == "datapulse_pipeline_cc50d35e50b749389474d8c3c64f920e"


def test_schedule_manifest_is_atomically_written_and_removed(tmp_path):
    config = PipelineScheduleIn(schedule_type="hourly")
    pipeline_id = "cc50d35e-50b7-4938-9474-d8c3c64f920e"
    schedule = type("Schedule", (), {**config.model_dump(), "pipeline_id": pipeline_id,
                                      "airflow_dag_id": pipeline_dag_id(pipeline_id), "enabled": True,
                                      "start_date": None})()
    path = write_schedule_manifest(schedule, tmp_path)
    assert path.is_file()
    assert '"cron_expression": "0 * * * *"' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.tmp"))
    remove_schedule_manifest(pipeline_id, tmp_path)
    assert not path.exists()


def test_next_scheduled_run_uses_configured_timezone_when_croniter_is_available(monkeypatch):
    from datetime import timedelta
    from app.utils import cron_validation
    seen = {}
    class FakeCroniter:
        def __init__(self, expression, base): seen.update(expression=expression, base=base)
        def get_next(self, result_type):
            assert result_type is datetime
            return seen["base"] + timedelta(hours=1)
    monkeypatch.setattr(cron_validation, "croniter", FakeCroniter)
    start = datetime(2099, 1, 1, tzinfo=timezone.utc)
    result = cron_validation.next_cron_run("0 * * * *", "Asia/Kolkata", start)
    assert result is not None and result.tzinfo is not None
    assert result.hour == 6 and result.minute == 30
