import pytest


def upload_csv(client, content="customer_id,amount,event_date,email,category\nA1,10,2026-01-01,a@example.com,North\nA1,-2,2026-13-40,bad,north\nB2,not-number,2026/01/03,c@example.com,South \n"):
    response = client.post("/api/datasets", files={"file": ("orders.csv", content.encode(), "text/csv")})
    assert response.status_code == 201
    return response.json()


def test_original_analysis_persists_paginated_reports_and_filtered_issues(client):
    dataset = upload_csv(client)
    analysis = client.post(f"/api/quality/datasets/{dataset['id']}/analyze", json={
        "rules": [{"type": "non_negative", "column": "amount"}],
    })

    assert analysis.status_code == 201
    report = analysis.json()
    assert report["dataset_id"] == dataset["id"]
    assert report["processed_dataset_id"] is None
    assert report["scoring_weights"]["completeness"] == 0.25
    assert report["methodology"]["version"] == "datapulse-quality-v1"
    assert report["dimension_scores"]["rule_based_correctness"] < 100

    history = client.get(f"/api/quality/datasets/{dataset['id']}/reports?limit=1&offset=0")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["id"] == report["id"]
    detail = client.get(f"/api/quality/reports/{report['id']}")
    assert detail.status_code == 200
    all_issues = client.get(f"/api/quality/reports/{report['id']}/issues?limit=100")
    assert all_issues.status_code == 200
    assert all_issues.json()["total"] == report["total_issues"]
    invalid = client.get(f"/api/quality/reports/{report['id']}/issues?severity=critical&dimension=validity")
    assert invalid.status_code == 200
    assert all(item["severity"] == "critical" and item["dimension"] == "validity" for item in invalid.json()["items"])
    assert client.get("/api/quality/reports?limit=1").json()["total"] == 1


def test_processed_analysis_uses_safe_path_and_has_source_lineage(client):
    dataset = upload_csv(client, "amount\n1\n2\n")
    pipeline = client.post("/api/pipelines", json={"name": "copy", "source_dataset_id": dataset["id"], "steps": []})
    assert pipeline.status_code == 201
    execution = client.post(f"/api/pipelines/{pipeline.json()['id']}/execute")
    assert execution.status_code == 200
    processed = execution.json()["processed_dataset"]

    result = client.post(f"/api/quality/processed-datasets/{processed['id']}/analyze", json={"rules": []})
    assert result.status_code == 201
    report = result.json()
    assert report["dataset_id"] is None
    assert report["processed_dataset_id"] == processed["id"]
    original_reports = client.get(f"/api/quality/datasets/{dataset['id']}/reports").json()
    assert original_reports["total"] == 0

    db = client.app.state.test_session()
    try:
        from app.models.pipeline import ProcessedDataset
        record = db.query(ProcessedDataset).filter_by(id=processed["id"]).one()
        record.storage_path = "processed/../../outside.csv"
        db.commit()
    finally:
        db.close()
    rejected = client.post(f"/api/quality/processed-datasets/{processed['id']}/analyze", json={})
    assert rejected.status_code == 400


def test_analysis_rejects_bad_ids_rules_and_nonexistent_rule_columns(client):
    assert client.post("/api/quality/datasets/missing/analyze", json={}).status_code == 404
    dataset = upload_csv(client)
    assert client.post(f"/api/quality/datasets/{dataset['id']}/analyze", json={
        "rules": [{"type": "python", "expression": "__import__('os').system('whoami')"}],
    }).status_code == 422
    assert client.post(f"/api/quality/datasets/{dataset['id']}/analyze", json={
        "rules": [{"type": "non_negative", "column": "missing"}],
    }).status_code == 422
    assert client.get("/api/quality/reports/not-a-report").status_code == 404


def test_empty_dataset_dimensions_are_not_reported_as_perfect(client):
    dataset = upload_csv(client, "id,amount\n")
    response = client.post(f"/api/quality/datasets/{dataset['id']}/analyze", json={})

    assert response.status_code == 201
    report = response.json()
    assert report["overall_score"] is None
    assert report["quality_label"] == "Not scored"
    assert report["status"] == "not_scored"
