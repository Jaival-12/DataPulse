import pytest


def upload_csv(client, content="order_id,amount,category,event_date\n1,1,North,2026-01-01\n2,2,South,2026-01-08\n3,3,North,2026-02-02\n"):
    response = client.post("/api/datasets", files={"file": ("orders.csv", content.encode(), "text/csv")})
    assert response.status_code == 201
    return response.json()


def make_processed(client, dataset_id, output_format="csv"):
    pipeline = client.post("/api/pipelines", json={"name": "copy", "source_dataset_id": dataset_id, "output_format": output_format, "steps": []})
    assert pipeline.status_code == 201
    output = client.post(f"/api/pipelines/{pipeline.json()['id']}/execute")
    assert output.status_code == 200
    return output.json()["processed_dataset"]


def stored_file(client, dataset):
    from app.models.dataset import Dataset as DatasetModel
    db = client.app.state.test_session()
    try:
        record = db.get(DatasetModel, dataset["id"])
        return client.app.state.test_storage / f"{record.storage_key}.{record.format}"
    finally:
        db.close()


def test_original_analytics_endpoints_return_real_metrics_and_validate_requests(client):
    dataset = upload_csv(client)
    base = f"/api/analytics/datasets/{dataset['id']}"
    overview = client.get(f"{base}/overview")
    assert overview.status_code == 200
    assert overview.json()["total_records"] == 3
    assert overview.json()["dataset_size_bytes"] == dataset["size_bytes"]
    assert overview.json()["numeric_columns"] == ["amount"]
    assert "order_id" in overview.json()["categorical_columns"]
    assert client.get(f"{base}/columns").json()["columns"]
    detail = client.get(f"{base}/columns/amount")
    assert detail.status_code == 200
    assert detail.json()["numeric"]["mean"] == 2
    assert detail.json()["numeric"]["variance"] == 1
    assert client.get(f"{base}/columns/not_there").status_code == 422
    correlation_dataset = upload_csv(client, "x,y\n1,2\n2,4\n3,6\n")
    correlation = client.get(f"/api/analytics/datasets/{correlation_dataset['id']}/correlation")
    assert correlation.status_code == 200
    assert correlation.json()["correlations"]["x"]["y"] == pytest.approx(1)
    timeseries = client.post(f"{base}/timeseries", json={"date_column": "event_date", "granularity": "monthly", "measure_column": "amount", "aggregation": "sum"})
    assert timeseries.status_code == 200
    assert [point["period"] for point in timeseries.json()["points"]] == ["2026-01", "2026-02"]
    aggregate = client.post(f"{base}/aggregate", json={"group_by": "category", "operation": "average", "measure_column": "amount", "limit": 1})
    assert aggregate.status_code == 200
    assert aggregate.json()["groups"][0]["aggregate_value"] == 2
    assert aggregate.json()["truncated"] is True
    assert client.post(f"{base}/aggregate", json={"group_by": "missing", "operation": "count"}).status_code == 422
    assert client.post(f"{base}/aggregate", json={"group_by": "amount", "operation": "count"}).status_code == 422
    assert client.post(f"{base}/timeseries", json={"date_column": "amount", "granularity": "yearly"}).status_code == 422
    assert client.post(f"{base}/timeseries", json={"date_column": "event_date", "granularity": "daily", "limit": 501}).status_code == 422
    assert client.get(f"{base}/insights").json()["insights"] == []
    assert client.get("/api/analytics/datasets/unknown/overview").status_code == 404


@pytest.mark.parametrize("granularity,expected", [("daily", ["2026-01-01", "2026-01-08", "2026-02-02"]), ("weekly", ["2026-W01", "2026-W02", "2026-W06"]), ("monthly", ["2026-01", "2026-02"])])
def test_timeseries_supported_granularities_and_invalid_dates(client, granularity, expected):
    dataset = upload_csv(client, "event_date,amount\n2026-02-02,4\n2026-01-01,2\n2026-13-40,8\n,5\n2026-01-08,bad\n")
    result = client.post(f"/api/analytics/datasets/{dataset['id']}/timeseries", json={"date_column": "event_date", "granularity": granularity, "measure_column": "amount", "aggregation": "sum"})
    assert result.status_code == 200
    body = result.json()
    assert [point["period"] for point in body["points"]] == expected
    assert body["invalid_date_count"] == 1
    assert body["missing_date_count"] == 1
    assert body["invalid_measure_count"] == 1


def test_processed_analytics_and_comparison_enforce_lineage(client):
    source = upload_csv(client)
    processed = make_processed(client, source["id"])
    base = f"/api/analytics/processed-datasets/{processed['id']}"
    assert client.get(f"{base}/overview").json()["total_records"] == 3
    assert client.get(f"{base}/columns/amount").json()["numeric"]["mean"] == 2
    assert client.get(f"{base}/correlation").status_code == 200
    assert client.post(f"{base}/timeseries", json={"date_column": "event_date", "granularity": "weekly"}).status_code == 200
    assert client.post(f"{base}/aggregate", json={"group_by": "category", "operation": "count"}).status_code == 200
    assert client.get(f"{base}/insights").status_code == 200
    compared = client.post("/api/analytics/compare", json={
        "left": {"type": "original", "id": source["id"]},
        "right": {"type": "processed", "id": processed["id"]},
    })
    assert compared.status_code == 200
    assert compared.json()["row_count_change"] == 0
    assert compared.json()["common_columns"] == ["order_id", "amount", "category", "event_date"]
    processed_again = make_processed(client, source["id"])
    same_lineage = client.post("/api/analytics/compare", json={
        "left": {"type": "processed", "id": processed["id"]},
        "right": {"type": "processed", "id": processed_again["id"]},
    })
    assert same_lineage.status_code == 200
    assert client.post("/api/analytics/compare", json={
        "left": {"type": "processed", "id": processed["id"]},
        "right": {"type": "processed", "id": "unrelated"},
    }).status_code == 404
    other = upload_csv(client, "x\n1\n")
    other_output = make_processed(client, other["id"])
    rejected = client.post("/api/analytics/compare", json={
        "left": {"type": "processed", "id": processed["id"]},
        "right": {"type": "processed", "id": other_output["id"]},
    })
    assert rejected.status_code == 422


def test_source_errors_are_safe_and_size_limit_is_respected(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "max_profile_mb", 1)
    dataset = upload_csv(client)
    source = stored_file(client, dataset)
    original = source.read_bytes()
    source.write_text("not,csv\n\"broken", encoding="utf-8")
    malformed = client.get(f"/api/analytics/datasets/{dataset['id']}/overview")
    assert malformed.status_code == 400
    assert str(source) not in malformed.text
    source.write_bytes(original + b" " * (1024 * 1024 + 1))
    oversized = client.get(f"/api/analytics/datasets/{dataset['id']}/overview")
    assert oversized.status_code == 413
    json_upload = client.post("/api/datasets", files={"file": ("events.json", b'[{"value":1}]', "application/json")})
    json_source = stored_file(client, json_upload.json())
    json_source.write_text("{invalid", encoding="utf-8")
    malformed_json = client.get(f"/api/analytics/datasets/{json_upload.json()['id']}/overview")
    assert malformed_json.status_code == 400
    assert str(json_source) not in malformed_json.text


def test_analytics_never_modify_source_files(client):
    dataset = upload_csv(client)
    source = stored_file(client, dataset)
    before = source.read_bytes()
    client.get(f"/api/analytics/datasets/{dataset['id']}/overview")
    client.get(f"/api/analytics/datasets/{dataset['id']}/columns/amount")
    assert source.read_bytes() == before


def test_json_analytics_supports_nested_category_values_and_empty_data(client):
    uploaded = client.post("/api/datasets", files={"file": ("events.json", b'[{"value": "1,499", "kind": {"x": 1}}, {"value": "bad", "kind": {"x": 1}}, {"value": null, "kind": ["other"]}]', "application/json")})
    assert uploaded.status_code == 201
    dataset = uploaded.json()
    base = f"/api/analytics/datasets/{dataset['id']}"
    column = client.get(f"{base}/columns/value")
    assert column.status_code == 200
    assert column.json()["numeric"]["mean"] == 1499
    assert column.json()["numeric"]["invalid_count"] == 1
    nested = client.get(f"{base}/columns/kind")
    assert nested.status_code == 200
    assert nested.json()["categorical"]["distinct_count"] == 2
    assert len(nested.json()["categorical"]["top_values"]) == 2
    processed = make_processed(client, dataset["id"], "json")
    processed_base = f"/api/analytics/processed-datasets/{processed['id']}"
    assert client.get(f"{processed_base}/overview").json()["total_records"] == 3
    assert client.get(f"{processed_base}/columns/value").json()["numeric"]["mean"] == 1499

    empty_upload = client.post("/api/datasets", files={"file": ("empty.csv", b"value,other\n", "text/csv")})
    empty_base = f"/api/analytics/datasets/{empty_upload.json()['id']}"
    assert empty_upload.status_code == 201
    empty_overview = client.get(f"{empty_base}/overview")
    assert empty_overview.status_code == 200
    assert empty_overview.json()["total_records"] == 0


def test_processed_analytics_rejects_unsafe_storage_metadata(client):
    source = upload_csv(client)
    processed = make_processed(client, source["id"])
    db = client.app.state.test_session()
    try:
        from app.models.pipeline import ProcessedDataset
        record = db.get(ProcessedDataset, processed["id"])
        record.storage_path = "processed/../../outside.csv"
        db.commit()
    finally:
        db.close()
    response = client.get(f"/api/analytics/processed-datasets/{processed['id']}/overview")
    assert response.status_code == 400
    assert "outside" not in response.text
