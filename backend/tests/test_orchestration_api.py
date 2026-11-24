from app.core.config import settings
from app.services.orchestration_service import manifest_path


def create_pipeline(client):
    source = client.post("/api/datasets", files={"file": ("scheduled.csv", b"id,value\n1,10\n2,20\n", "text/csv")})
    assert source.status_code == 201
    result = client.post("/api/pipelines", json={"name": "scheduled", "source_dataset_id": source.json()["id"], "steps": []})
    assert result.status_code == 201
    return result.json()


def test_schedule_create_get_update_enable_disable_and_delete(client, monkeypatch):
    from datetime import datetime, timedelta
    from app.utils import cron_validation
    class FakeCroniter:
        @staticmethod
        def is_valid(_expression): return True
        def __init__(self, _expression, base): self.base = base
        def get_next(self, _result_type): return self.base + timedelta(days=1)
    monkeypatch.setattr(cron_validation, "croniter", FakeCroniter)
    pipeline = create_pipeline(client)
    url = f"/api/pipelines/{pipeline['id']}/schedule"
    created = client.post(url, json={"schedule_type": "daily", "timezone": "UTC", "retries": 2,
                                    "retry_delay_seconds": 60, "timeout_seconds": 600})
    assert created.status_code == 201, created.text
    assert created.json()["cron_expression"] == "0 0 * * *"
    assert datetime.fromisoformat(created.json()["next_run_at"]).tzinfo is not None
    assert client.get(url).json()["enabled"] is True
    assert client.post(f"{url}/disable").json()["enabled"] is False
    updated = client.put(url, json={"schedule_type": "custom", "cron_expression": "30 8 * * 1-5",
                                    "timezone": "Asia/Kolkata", "retries": 1, "retry_delay_seconds": 15,
                                    "timeout_seconds": 1200})
    assert updated.status_code == 200, updated.text
    assert updated.json()["cron_expression"] == "30 8 * * 1-5"
    assert client.post(f"{url}/enable").json()["enabled"] is True
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


def test_schedule_rejects_invalid_values_and_duplicate_create(client):
    pipeline = create_pipeline(client)
    url = f"/api/pipelines/{pipeline['id']}/schedule"
    bad = client.post(url, json={"schedule_type": "custom", "cron_expression": "99 99 * * *", "timezone": "UTC"})
    assert bad.status_code == 422
    assert client.post(url, json={"schedule_type": "hourly"}).status_code == 201
    assert client.post(url, json={"schedule_type": "daily"}).status_code == 409


def test_schedule_creation_requires_internal_service_configuration(client, monkeypatch):
    pipeline = create_pipeline(client)
    monkeypatch.setattr(settings, "datapulse_internal_token", "")
    response = client.post(f"/api/pipelines/{pipeline['id']}/schedule", json={"schedule_type": "hourly"})
    assert response.status_code == 503
    assert client.get(f"/api/pipelines/{pipeline['id']}/schedule").status_code == 404


def test_internal_execution_requires_token_and_deduplicates_airflow_run(client, monkeypatch):
    pipeline = create_pipeline(client)
    url = f"/api/pipelines/{pipeline['id']}/schedule"
    assert client.post(url, json={"schedule_type": "hourly"}).status_code == 201
    monkeypatch.setattr(settings, "datapulse_internal_token", "test-only-internal-token")
    base = f"/api/internal/orchestration/pipelines/{pipeline['id']}"
    assert client.get(f"{base}/validate", params={"dag_run_id": "scheduled__one"}).status_code == 401
    headers = {"Authorization": "Bearer test-only-internal-token"}
    assert client.get(f"{base}/validate", params={"dag_run_id": "scheduled__one"}, headers=headers).status_code == 200
    assert client.get(f"{base}/validate", params={"dag_run_id": "scheduled__/invalid"}, headers=headers).status_code == 422
    body = {"dag_run_id": "scheduled__one", "try_number": 1}
    first = client.post(f"{base}/execute", json=body, headers=headers)
    second = client.post(f"{base}/execute", json=body, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "success"
    assert client.get("/api/processed-datasets").json()["total"] == 1
    assert client.get(f"/api/pipelines/{pipeline['id']}/executions").json()["total"] == 1


def test_internal_run_report_and_monitoring_routes_do_not_expose_secrets(client, monkeypatch):
    pipeline = create_pipeline(client)
    monkeypatch.setattr(settings, "datapulse_internal_token", "monitor-token")
    headers = {"Authorization": "Bearer monitor-token"}
    dag_id = "datapulse_pipeline_" + pipeline["id"].replace("-", "")
    report = {"pipeline_id": pipeline["id"], "airflow_dag_id": dag_id,
              "airflow_run_id": "scheduled__two", "status": "success", "task_id": "execute_pipeline",
              "try_number": 1, "execution_id": None, "error_message": None}
    assert client.post("/api/internal/orchestration/runs/report", json=report, headers=headers).status_code == 200
    assert client.get("/api/orchestration/status").status_code == 200
    assert client.get("/api/orchestration/pipelines").json()["total"] == 0
    runs = client.get(f"/api/orchestration/pipelines/{pipeline['id']}/runs")
    assert runs.status_code == 200 and runs.json()["total"] == 1
    run_id = runs.json()["items"][0]["id"]
    assert client.get(f"/api/orchestration/runs/{run_id}").json()["run"]["status"] == "success"
    assert client.get(f"/api/orchestration/runs/{run_id}/logs").status_code == 200
    assert client.post("/api/internal/orchestration/runs/report", json=report).status_code == 401
    assert "monitor-token" not in client.get("/api/orchestration/status").text


def test_internal_validation_rejects_disabled_schedule_and_manual_execution_still_works(client, monkeypatch):
    pipeline = create_pipeline(client)
    url = f"/api/pipelines/{pipeline['id']}/schedule"
    assert client.post(url, json={"schedule_type": "hourly"}).status_code == 201
    assert client.post(f"{url}/disable").status_code == 200
    monkeypatch.setattr(settings, "datapulse_internal_token", "manual-token")
    headers = {"Authorization": "Bearer manual-token"}
    validate_url = f"/api/internal/orchestration/pipelines/{pipeline['id']}/validate"
    assert client.get(validate_url, params={"dag_run_id": "scheduled__disabled"}, headers=headers).status_code == 409
    manual = client.post(f"/api/pipelines/{pipeline['id']}/execute")
    assert manual.status_code == 200 and manual.json()["status"] == "success"


def test_failed_scheduled_execution_is_not_republished_on_retry(client, monkeypatch):
    source = client.post("/api/datasets", files={"file": ("invalid.csv", b"amount\n10\nmany\n", "text/csv")}).json()
    pipeline = client.post("/api/pipelines", json={"name": "permanent error", "source_dataset_id": source["id"],
        "steps": [{"operation": "convert_type", "config": {"column": "amount", "target_type": "integer"}}]}).json()
    assert client.post(f"/api/pipelines/{pipeline['id']}/schedule", json={"schedule_type": "hourly", "retries": 4}).status_code == 201
    monkeypatch.setattr(settings, "datapulse_internal_token", "retry-token")
    headers = {"Authorization": "Bearer retry-token"}
    url = f"/api/internal/orchestration/pipelines/{pipeline['id']}/execute"
    body = {"dag_run_id": "scheduled__permanent-failure", "try_number": 1}
    first = client.post(url, json=body, headers=headers)
    body["try_number"] = 2
    retried = client.post(url, json=body, headers=headers)
    assert first.status_code == retried.status_code == 200
    assert first.json()["status"] == retried.json()["status"] == "failed"
    assert first.json()["id"] == retried.json()["id"]
    assert client.get(f"/api/pipelines/{pipeline['id']}/executions").json()["total"] == 1
    assert client.get("/api/processed-datasets").json()["total"] == 0


def test_deleting_pipeline_removes_its_dag_manifest_and_prevents_execution(client, monkeypatch):
    pipeline = create_pipeline(client)
    assert client.post(f"/api/pipelines/{pipeline['id']}/schedule", json={"schedule_type": "daily"}).status_code == 201
    path = manifest_path(pipeline["id"], settings.airflow_schedules_dir)
    assert path.is_file()
    assert client.delete(f"/api/pipelines/{pipeline['id']}").status_code == 204
    assert not path.exists()
    monkeypatch.setattr(settings, "datapulse_internal_token", "deleted-token")
    response = client.get(f"/api/internal/orchestration/pipelines/{pipeline['id']}/validate",
                          params={"dag_run_id": "scheduled__after-delete"},
                          headers={"Authorization": "Bearer deleted-token"})
    assert response.status_code == 404


def test_deleting_source_removes_schedule_manifest(client):
    pipeline = create_pipeline(client)
    assert client.post(f"/api/pipelines/{pipeline['id']}/schedule", json={"schedule_type": "weekly"}).status_code == 201
    path = manifest_path(pipeline["id"], settings.airflow_schedules_dir)
    assert path.is_file()
    assert client.delete(f"/api/datasets/{pipeline['source_dataset_id']}").status_code == 204
    assert not path.exists()
