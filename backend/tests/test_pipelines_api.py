import json
import pytest

from app.core.config import settings
from app.services.pipeline_service import ProcessedFileError, safe_processed_path


def upload_csv(client, filename="source.csv", payload=b"id,amount,city\n1,10,Oslo\n2,20,London\n"):
    response = client.post("/api/datasets", files={"file": (filename, payload, "text/csv")})
    assert response.status_code == 201, response.text
    return response.json()


def test_pipeline_crud_validates_and_persists_ordered_steps(client):
    source = upload_csv(client)
    body = {
        "name": "clean sales", "description": "prepared source",
        "source_dataset_id": source["id"], "output_format": "json",
        "steps": [
            {"operation": "remove_duplicates", "config": {"subset": ["id"]}},
            {"operation": "filter_rows", "config": {"column": "amount", "operator": "greater_than", "value": 5}},
        ],
    }
    created = client.post("/api/pipelines", json=body)
    assert created.status_code == 201, created.text
    pipeline = created.json()
    assert pipeline["source_dataset_id"] == source["id"]
    assert [step["execution_order"] for step in pipeline["steps"]] == [0, 1]
    assert client.get("/api/pipelines").json()["total"] == 1
    assert client.get(f"/api/pipelines/{pipeline['id']}").json()["steps"][1]["operation"] == "filter_rows"

    updated = client.put(f"/api/pipelines/{pipeline['id']}", json={**body, "name": "renamed"})
    assert updated.status_code == 200 and updated.json()["name"] == "renamed"
    assert client.put(f"/api/pipelines/{pipeline['id']}", json={**body, "steps": [{"operation": "filter_rows", "config": {"column": "missing", "operator": "equals", "value": 1}}]}).status_code == 422
    assert client.delete(f"/api/pipelines/{pipeline['id']}").status_code == 204
    assert client.get(f"/api/pipelines/{pipeline['id']}").status_code == 404


def test_pipeline_rejects_missing_source_unknown_operation_and_bad_config(client):
    source = upload_csv(client)
    body = {"name": "bad", "source_dataset_id": source["id"], "steps": [{"operation": "unknown", "config": {}}]}
    assert client.post("/api/pipelines", json=body).status_code == 422
    body["steps"] = [{"operation": "filter_rows", "config": {"column": "amount", "operator": "contains", "value": 4}}]
    assert client.post("/api/pipelines", json=body).status_code == 422
    body["steps"] = []
    body["source_dataset_id"] = "missing"
    assert client.post("/api/pipelines", json=body).status_code == 404


def test_execute_pipeline_writes_separate_processed_output_and_history(client):
    source = upload_csv(client, payload=b"id,amount,city\n1,10, Oslo \n1,12, Oslo \n2,5,London\n")
    original = next(client.app.state.test_storage.glob("*.csv")).read_bytes()
    created_response = client.post("/api/pipelines", json={
        "name": "clean", "source_dataset_id": source["id"], "output_format": "json",
        "steps": [
            {"operation": "remove_duplicates", "config": {"subset": ["id"]}},
            {"operation": "trim_whitespace", "config": {"columns": ["city"]}},
            {"operation": "filter_rows", "config": {"column": "amount", "operator": "greater_than", "value": 5}},
        ],
    })
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    result = client.post(f"/api/pipelines/{created['id']}/execute")
    assert result.status_code == 200, result.text
    execution = result.json()
    assert execution["status"] == "success"
    assert execution["total_input_rows"] == 3 and execution["total_output_rows"] == 1
    assert len(execution["execution_summary"]["logs"]) == 3
    assert execution["execution_summary"]["logs"][0]["removed_rows"] == 1
    assert next(client.app.state.test_storage.glob("*.csv")).read_bytes() == original

    processed = client.get("/api/processed-datasets").json()
    assert processed["total"] == 1
    item = processed["items"][0]
    assert item["source_dataset_id"] == source["id"] and item["file_type"] == "json"
    preview = client.get(f"/api/processed-datasets/{item['id']}/preview").json()
    assert preview["rows"] == [{"id": "1", "amount": "10", "city": "Oslo"}]
    download = client.get(f"/api/processed-datasets/{item['id']}/download")
    assert download.status_code == 200
    assert json.loads(download.content) == preview["rows"]
    assert client.get(f"/api/pipelines/{created['id']}/executions").json()["total"] == 1
    assert client.get(f"/api/executions/{execution['id']}").json()["id"] == execution["id"]
    assert client.get(f"/api/executions/{execution['id']}/logs").json()["logs"][2]["status"] == "success"


def test_json_source_can_be_transformed_and_loaded_as_csv(client):
    response = client.post("/api/datasets", files={"file": ("events.json", b'[{"count":2,"city":" Oslo "},{"count":3,"city":"Rome"}]', "application/json")})
    assert response.status_code == 201
    source = response.json()
    original = next(client.app.state.test_storage.glob("*.json")).read_bytes()
    pipeline = client.post("/api/pipelines", json={
        "name": "json to csv", "source_dataset_id": source["id"], "output_format": "csv",
        "steps": [{"operation": "trim_whitespace", "config": {"columns": ["city"]}}],
    }).json()
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    assert execution["status"] == "success"
    processed = execution["processed_dataset"]
    preview = client.get(f"/api/processed-datasets/{processed['id']}/preview").json()
    assert preview["rows"] == [{"count": 2, "city": "Oslo"}, {"count": 3, "city": "Rome"}]
    assert next(client.app.state.test_storage.glob("*.json")).read_bytes() == original


def test_failed_execution_records_step_and_does_not_publish_partial_output(client):
    source = upload_csv(client, payload=b"amount,city\n10,Oslo\nmany,Rome\n")
    pipeline_response = client.post("/api/pipelines", json={
        "name": "bad run", "source_dataset_id": source["id"],
        "steps": [
            {"operation": "uppercase", "config": {"columns": ["city"]}},
            {"operation": "convert_type", "config": {"column": "amount", "target_type": "integer"}},
        ],
    })
    assert pipeline_response.status_code == 201, pipeline_response.text
    pipeline = pipeline_response.json()
    result = client.post(f"/api/pipelines/{pipeline['id']}/execute")
    assert result.status_code == 200
    execution = result.json()
    assert execution["status"] == "failed"
    assert execution["execution_summary"]["logs"][0]["status"] == "success"
    assert execution["execution_summary"]["logs"][1]["status"] == "failed"
    assert client.get("/api/processed-datasets").json()["total"] == 0
    assert list((client.app.state.test_storage / "processed").glob("*.csv")) == []


def test_processed_metadata_cascades_when_pipeline_is_deleted(client):
    source = upload_csv(client)
    pipeline = client.post("/api/pipelines", json={"name": "copy", "source_dataset_id": source["id"], "steps": []}).json()
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    processed_id = execution["processed_dataset"]["id"]
    output_path = client.app.state.test_storage / execution["processed_dataset"]["storage_path"]
    assert output_path.is_file()
    assert client.delete(f"/api/pipelines/{pipeline['id']}").status_code == 204
    assert not output_path.exists()
    assert client.get(f"/api/processed-datasets/{processed_id}").status_code == 404


def test_source_dataset_delete_cascades_pipeline_records_and_removes_output_file(client):
    source = upload_csv(client)
    pipeline = client.post("/api/pipelines", json={"name": "copy", "source_dataset_id": source["id"], "steps": []}).json()
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    output_path = client.app.state.test_storage / execution["processed_dataset"]["storage_path"]
    assert output_path.is_file()
    assert client.delete(f"/api/datasets/{source['id']}").status_code == 204
    assert not output_path.exists()
    assert client.get(f"/api/pipelines/{pipeline['id']}").status_code == 404
    assert client.get(f"/api/processed-datasets/{execution['processed_dataset']['id']}").status_code == 404


def test_execution_size_limit_records_failure_without_output(client, monkeypatch):
    source = upload_csv(client)
    pipeline = client.post("/api/pipelines", json={"name": "bounded", "source_dataset_id": source["id"], "steps": []}).json()
    monkeypatch.setattr(settings, "max_profile_mb", 0)
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    assert execution["status"] == "failed"
    assert "size limit" in execution["error_message"].lower()
    assert client.get("/api/processed-datasets").json()["total"] == 0


def test_processed_storage_path_rejects_traversal(client):
    with pytest.raises(ProcessedFileError):
        safe_processed_path(client.app.state.test_storage, "processed/../../source.csv")


def test_malformed_source_records_extract_failure_without_output(client):
    source_response = client.post("/api/datasets", files={"file": ("events.json", b'[{"event":"open"}]', "application/json")})
    source = source_response.json()
    pipeline = client.post("/api/pipelines", json={"name": "bad source", "source_dataset_id": source["id"], "steps": []}).json()
    source_file = next(client.app.state.test_storage.glob("*.json"))
    original = source_file.read_bytes()
    source_file.write_text("{broken", encoding="utf-8")
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    assert execution["status"] == "failed"
    assert execution["execution_summary"]["logs"][0]["operation"] == "extract_or_load"
    assert client.get("/api/processed-datasets").json()["total"] == 0
    source_file.write_bytes(original)


def test_database_failure_after_output_write_removes_file_and_records_failure(client, monkeypatch):
    source = upload_csv(client)
    pipeline = client.post("/api/pipelines", json={"name": "db fail", "source_dataset_id": source["id"], "steps": []}).json()
    session_class = client.app.state.test_session.class_
    original_commit = session_class.commit
    commits = 0

    def fail_final_publication(self):
        nonlocal commits
        commits += 1
        if commits == 2:
            raise RuntimeError("simulated database publication failure")
        return original_commit(self)

    monkeypatch.setattr(session_class, "commit", fail_final_publication)
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    assert execution["status"] == "failed"
    assert execution["error_message"] == "Pipeline execution failed due to an internal processing error."
    assert client.get("/api/processed-datasets").json()["total"] == 0
    processed = client.app.state.test_storage / "processed"
    assert list(processed.iterdir()) == []


def test_missing_source_file_fails_execution_without_publishing_output(client):
    source = upload_csv(client)
    pipeline = client.post("/api/pipelines", json={"name": "missing source", "source_dataset_id": source["id"], "steps": []}).json()
    next(client.app.state.test_storage.glob("*.csv")).unlink()
    execution = client.post(f"/api/pipelines/{pipeline['id']}/execute").json()
    assert execution["status"] == "failed"
    assert execution["error_message"] == "Source dataset file is unavailable."
    assert client.get("/api/processed-datasets").json()["total"] == 0

