from pathlib import Path

import yaml


ROOT = Path(__file__).parents[2]


def test_airflow_compose_keeps_metadata_separate_and_private():
    airflow = yaml.safe_load((ROOT / "docker-compose.airflow.yml").read_text(encoding="utf-8"))
    datapulse = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = airflow["services"]
    assert services["airflow-scheduler"]["image"] == "apache/airflow:2.11.2"
    assert services["airflow-webserver"]["image"] == "apache/airflow:2.11.2"
    assert services["airflow-scheduler"]["environment"]["AIRFLOW__CORE__EXECUTOR"] == "LocalExecutor"
    assert "airflow-db" in services["airflow-scheduler"]["environment"]["AIRFLOW__DATABASE__SQL_ALCHEMY_CONN"]
    assert services["airflow-db"].get("ports") is None
    assert services["airflow-webserver"]["ports"] == ["127.0.0.1:8080:8080"]
    assert airflow["volumes"].keys() >= {"airflow_metadata", "airflow_logs"}
    assert services["airflow-scheduler"]["volumes"] == services["airflow-webserver"]["volumes"]
    assert datapulse["services"]["api"]["environment"]["AIRFLOW_SCHEDULES_DIR"] == "/app/airflow_dags/schedules"
    assert any("./airflow/dags:/app/airflow_dags" in mount for mount in datapulse["services"]["api"]["volumes"])
    assert "airflow-db" not in datapulse["services"]["api"].get("depends_on", {})


def test_airflow_environment_example_contains_placeholders_not_credentials():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "replace-with" in example
    assert "DATAPULSE_INTERNAL_TOKEN=" in example and "AIRFLOW_FERNET_KEY=" in example
    assert "airflow:airflow" not in example
