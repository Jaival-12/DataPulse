from sqlalchemy import text
from app.core.config import settings
from app.models.dataset import Dataset
from app.services.profiling_service import build_profile
import pandas as pd

def upload_csv(client, content=b"amount,segment\n10,retail\n,online\n10,retail"):
    response = client.post("/api/datasets", files={"file": ("orders.csv", content, "text/csv")})
    assert response.status_code == 201
    return response.json()["id"]

def generate_profile(client, dataset_id):
    response = client.post(f"/api/datasets/{dataset_id}/profile")
    assert response.status_code == 200, response.text
    return response.json()

def test_csv_profile_is_generated_and_persisted(client):
    dataset_id = upload_csv(client)
    raw_source = next(client.app.state.test_storage.iterdir())
    original_bytes = raw_source.read_bytes()

    generated = client.post(f"/api/datasets/{dataset_id}/profile")
    assert generated.status_code == 200
    report = generated.json()
    assert report["dataset_id"] == dataset_id
    assert report["profile_data"]["total_rows"] == 3
    assert report["profile_data"]["duplicate_rows"] == 1
    assert report["profile_data"]["columns"][0]["numeric_statistics"]["mean"] == 10

    retrieved = client.get(f"/api/datasets/{dataset_id}/profile")
    assert retrieved.status_code == 200
    assert retrieved.json()["profile_data"] == report["profile_data"]
    assert raw_source.read_bytes() == original_bytes

def test_profile_counts_missing_and_computes_numeric_statistics(client):
    dataset_id = upload_csv(client, b"amount,label\n1,a\n2, \ninf,a\n")
    data = generate_profile(client, dataset_id)["profile_data"]
    assert data["total_rows"] == 3
    assert data["total_missing_cells"] == 2
    assert data["columns"][0]["missing_count"] == 1
    assert data["columns"][0]["numeric_statistics"]["mean"] == 1.5
    assert data["columns"][0]["numeric_statistics"]["median"] == 1.5
    assert data["columns"][0]["numeric_statistics"]["minimum"] == 1
    assert data["columns"][0]["numeric_statistics"]["maximum"] == 2
    assert data["columns"][0]["numeric_statistics"]["q25"] == 1.25

def test_mixed_numeric_csv_reports_valid_invalid_and_numeric_distribution(client):
    dataset_id = upload_csv(client, b"quantity\n2\n5\n3\nthree\n")
    column = generate_profile(client, dataset_id)["profile_data"]["columns"][0]
    stats = column["numeric_statistics"]
    assert column["detected_type"] == "numeric_mixed"
    assert stats["valid_numeric_values"] == 3
    assert stats["invalid_numeric_values"] == 1
    assert stats["numeric_conversion_percentage"] == 75.0
    assert stats["minimum"] == 2
    assert stats["maximum"] == 5
    assert sum(item["count"] for item in stats["histogram"]) == 3
    assert column["categorical_statistics"] is None

def test_formatted_numeric_csv_converts_grouped_commas_without_changing_source(client):
    dataset_id = upload_csv(client, b'amount\n"1,499"\n"2,000"\n')
    source = next(client.app.state.test_storage.iterdir())
    original = source.read_bytes()
    column = generate_profile(client, dataset_id)["profile_data"]["columns"][0]
    assert column["detected_type"] == "integer"
    assert column["numeric_statistics"]["minimum"] == 1499
    assert column["numeric_statistics"]["maximum"] == 2000
    assert column["numeric_statistics"]["numeric_conversion_percentage"] == 100.0
    assert source.read_bytes() == original

def test_dates_report_supported_formats_impossible_dates_and_missing_values(client):
    dataset_id = upload_csv(client, b"event_date,marker\n2026-05-14,a\n2026/05/15,b\n16-05-2026,c\n2026-05-17T10:15:00Z,d\n2026-13-40,e\nnot-a-date,f\n,g\n")
    column = generate_profile(client, dataset_id)["profile_data"]["columns"][0]
    assert column["detected_type"] == "datetime"
    assert column["date_statistics"] == {
        "valid_date_count": 4,
        "invalid_date_count": 2,
        "missing_date_count": 1,
        "earliest_date": "2026-05-14T00:00:00+00:00",
        "latest_date": "2026-05-17T10:15:00+00:00",
    }

def test_identifier_profile_preserves_samples_and_suppresses_frequency_data(client):
    dataset_id = upload_csv(client, b"customer_id\n001\n001\n002\n\n003\n")
    column = generate_profile(client, dataset_id)["profile_data"]["columns"][0]
    assert column["detected_type"] == "identifier"
    assert column["unique_percentage"] == 75.0
    assert column.get("identifier_statistics") is not None
    assert column["identifier_statistics"] == {
        "duplicate_identifier_count": 1,
        "sample_values": ["001", "001", "002", "003"],
    }
    assert column["categorical_statistics"] is None

def test_json_numeric_mixed_values_are_not_downgraded_to_categorical(client):
    response = client.post("/api/datasets", files={"file": ("quantities.json", b'[{"quantity":2},{"quantity":5},{"quantity":3},{"quantity":"three"}]', "application/json")})
    column = generate_profile(client, response.json()["id"])["profile_data"]["columns"][0]
    assert column["detected_type"] == "numeric_mixed"
    assert column["numeric_statistics"]["valid_numeric_values"] == 3
    assert column["numeric_statistics"]["invalid_numeric_values"] == 1

def test_nat_and_nan_text_values_are_treated_as_missing(client):
    dataset_id = upload_csv(client, b"amount,created_at\n1,2026-01-01\nNaN,NaT\n")
    profile = generate_profile(client, dataset_id)["profile_data"]
    assert profile["total_missing_cells"] == 2
    assert profile["columns"][1]["detected_type"] == "date"
    assert profile["columns"][1]["missing_count"] == 1

def test_json_profile_has_categorical_frequencies_and_duplicates(client):
    response = client.post("/api/datasets", files={"file": ("visits.json", b'[{"city":"Pune"},{"city":"Delhi"},{"city":"Pune"}]', "application/json")})
    dataset_id = response.json()["id"]
    result = generate_profile(client, dataset_id)["profile_data"]
    assert result["duplicate_rows"] == 1
    column = result["columns"][0]
    assert column["detected_type"] == "categorical"
    assert column["distinct_count"] == 2
    assert column["categorical_statistics"]["top_values"][0] == {"value": "Pune", "count": 2, "percentage": 66.6667}

def test_json_boolean_columns_are_counted_separately(client):
    response = client.post("/api/datasets", files={"file": ("flags.json", b'[{"active":true},{"active":false},{"active":true}]', "application/json")})
    result = generate_profile(client, response.json()["id"])["profile_data"]
    assert result["boolean_column_count"] == 1
    assert result["columns"][0]["detected_type"] == "boolean"
    assert result["columns"][0]["categorical_statistics"]["top_values"][0] == {"value": True, "count": 2, "percentage": 66.6667}

def test_profile_recognizes_identifiers_dates_and_empty_columns(client):
    dataset_id = upload_csv(client, b"account_id,created_at,empty\n101,2026-01-01,\n102,2026-01-02,\n")
    profile = generate_profile(client, dataset_id)["profile_data"]
    assert [c["detected_type"] for c in profile["columns"]] == ["identifier", "date", "empty"]
    assert profile["columns"][0]["numeric_statistics"] is None
    assert profile["columns"][2]["missing_count"] == 2
    assert profile["numeric_column_count"] == 0
    assert profile["date_column_count"] == 1

def test_header_only_csv_profiles_as_empty_without_division_errors(client):
    dataset_id = upload_csv(client, b"name,amount\n")
    result = generate_profile(client, dataset_id)["profile_data"]
    assert result["total_rows"] == 0
    assert result["total_columns"] == 2
    assert result["missing_cell_percentage"] == 0
    assert result["overall_completeness_percentage"] == 0

def test_empty_frame_profile_is_json_safe_and_zero_based():
    result = build_profile(pd.DataFrame())
    assert result["total_rows"] == 0
    assert result["total_columns"] == 0
    assert result["unique_rows"] == 0
    assert result["overall_completeness_percentage"] == 0

def test_profile_refresh_updates_same_report_from_current_raw_file(client):
    dataset_id = upload_csv(client, b"value\n1\n2\n")
    first = generate_profile(client, dataset_id)
    source = next(client.app.state.test_storage.iterdir())
    source.write_text("value\n1\n1\n1\n", encoding="utf-8")
    refreshed = client.post(f"/api/datasets/{dataset_id}/profile/refresh").json()
    assert refreshed["id"] == first["id"]
    assert refreshed["profile_data"]["total_rows"] == 3
    assert refreshed["profile_data"]["duplicate_rows"] == 2

def test_profile_reports_controlled_errors_for_unknown_or_missing_sources(client):
    missing = client.post("/api/datasets/not-a-dataset/profile")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Dataset not found."
    assert client.get("/api/datasets/not-a-dataset/profile").json()["detail"] == "Dataset not found."
    dataset_id = upload_csv(client)
    unsaved = client.get(f"/api/datasets/{dataset_id}/profile")
    assert unsaved.status_code == 404
    assert unsaved.json()["detail"] == "Profile has not been generated yet."
    next(client.app.state.test_storage.iterdir()).unlink()
    response = client.post(f"/api/datasets/{dataset_id}/profile")
    assert response.status_code == 404
    assert response.json()["detail"] == "Dataset source file is unavailable."
    assert "path" not in response.text.lower()

def test_profile_rejects_unsupported_stored_format(client):
    dataset_id = upload_csv(client)
    with client.app.state.test_session() as db:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).one()
        dataset.format = "parquet"
        db.commit()
    response = client.post(f"/api/datasets/{dataset_id}/profile")
    assert response.status_code == 415
    assert response.json()["detail"] == "Only CSV and JSON datasets can be profiled."

def test_profile_handles_malformed_json_source(client):
    response = client.post("/api/datasets", files={"file": ("events.json", b'[{"event":"open"}]', "application/json")})
    dataset_id = response.json()["id"]
    next(client.app.state.test_storage.iterdir()).write_text("{invalid", encoding="utf-8")
    response = client.post(f"/api/datasets/{dataset_id}/profile")
    assert response.status_code == 400
    assert response.json()["detail"] == "Dataset source could not be parsed."

def test_profile_rejects_oversized_and_malformed_source(client, monkeypatch):
    dataset_id = upload_csv(client)
    monkeypatch.setitem(settings.__dict__, "max_profile_mb", 0)
    assert client.post(f"/api/datasets/{dataset_id}/profile").status_code == 413
    monkeypatch.setitem(settings.__dict__, "max_profile_mb", 1)
    next(client.app.state.test_storage.iterdir()).write_text('value\n"unclosed\n', encoding="utf-8")
    response = client.post(f"/api/datasets/{dataset_id}/profile")
    assert response.status_code == 400
    assert "parser" not in response.text.lower()

def test_deleting_dataset_cascades_to_its_profile(client):
    dataset_id = upload_csv(client)
    generated = generate_profile(client, dataset_id)
    deleted = client.delete(f"/api/datasets/{dataset_id}")
    assert deleted.status_code == 204
    with client.app.state.test_session() as db:
        count = db.execute(text("SELECT count(*) FROM dataset_profiles WHERE dataset_id = :dataset_id"), {"dataset_id": dataset_id}).scalar_one()
    assert count == 0
