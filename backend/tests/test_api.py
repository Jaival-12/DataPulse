def test_upload_csv_catalog_and_preview(client):
    response = client.post("/api/datasets", files={"file": ("sales.csv", b"region,total\nwest,12\neast,8", "text/plain")})
    assert response.status_code == 201
    dataset = response.json()
    assert dataset["row_count"] == 2
    assert [column["data_type"] for column in dataset["columns"]] == ["string", "integer"]
    listing = client.get("/api/datasets").json()
    assert listing["total"] == 1
    assert listing["items"][0]["name"] == "sales.csv"
    preview = client.get(f"/api/datasets/{dataset['id']}/preview").json()
    assert preview["rows"] == [{"region": "west", "total": 12}, {"region": "east", "total": 8}]

def test_upload_json_ignores_untrusted_filename_for_storage(client):
    response = client.post("/api/datasets", files={"file": ("../../unsafe.json", b'[{"active":true},{"active":false}]', "application/octet-stream")})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "unsafe.json"
    assert data["columns"][0]["data_type"] == "boolean"
    files = list(client.app.state.test_storage.iterdir())
    assert len(files) == 1 and files[0].name.endswith(".json") and "unsafe" not in files[0].name

def test_rejects_invalid_content_and_unsupported_extension(client):
    assert client.post("/api/datasets", files={"file": ("bad.json", b"not json", "application/json")}).status_code == 400
    assert client.post("/api/datasets", files={"file": ("wrong.csv", b'{"value":1}', "text/csv")}).status_code == 400
    assert client.post("/api/datasets", files={"file": ("bad.exe", b"hello", "text/plain")}).status_code == 415

def test_enforces_upload_limit(client):
    response = client.post("/api/datasets", files={"file": ("large.csv", b"x\n" + b"a" * (1024 * 1024), "text/csv")})
    assert response.status_code == 413

def test_health_reports_database_connection(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/api/health/db").json() == {"status": "ok", "database": "connected"}

def test_overview_uses_catalog_aggregates(client):
    client.post("/api/datasets", files={"file": ("one.csv", b"value\n1\n2", "text/csv")})
    client.post("/api/datasets", files={"file": ("two.json", b'[{"value":3}]', "application/json")})
    overview = client.get("/api/overview").json()
    assert overview["dataset_count"] == 2
    assert overview["record_count"] == 3
    assert len(overview["recent_datasets"]) == 2

def test_dataset_metadata_can_be_loaded_without_previewing_rows(client):
    uploaded = client.post("/api/datasets", files={"file": ("one.csv", b"value\n1", "text/csv")}).json()
    response = client.get(f"/api/datasets/{uploaded['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == uploaded["id"]
    assert response.json()["name"] == "one.csv"
