from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config

from app.core.config import settings


def test_orchestration_migration_preserves_execution_rows_and_downgrades(tmp_path, monkeypatch):
    database_path = tmp_path / "migration.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{database_path.as_posix()}")
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))
    command.upgrade(config, "0004_data_quality")
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO pipeline_definitions (id,name,description,source_dataset_id,configuration,created_at,updated_at) VALUES ('pipe','Existing',NULL,'source','{}','2026-01-01','2026-01-01')")
        connection.execute("INSERT INTO pipeline_executions (id,pipeline_id,source_dataset_id,status,started_at,completed_at,duration,total_input_rows,total_output_rows,error_message,execution_summary) VALUES ('exec','pipe','source','success','2026-01-01','2026-01-01',1,2,2,NULL,'{}')")
    command.upgrade(config, "head")
    command.check(config)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT id FROM pipeline_executions").fetchone() == ("exec",)
        assert {row[1] for row in connection.execute("PRAGMA table_info(pipeline_executions)")} >= {"airflow_dag_id", "airflow_run_id"}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"pipeline_schedules", "orchestration_runs"} <= tables
    command.downgrade(config, "0004_data_quality")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT id FROM pipeline_executions").fetchone() == ("exec",)
        assert {row[1] for row in connection.execute("PRAGMA table_info(pipeline_executions)")} >= {"id", "pipeline_id", "status"}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "pipeline_schedules" not in tables and "orchestration_runs" not in tables
