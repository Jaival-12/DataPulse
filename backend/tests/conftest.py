import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.session import Base, get_db
from app.main import app
from app.core.config import settings

@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    def override_db():
        db = TestingSession()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "uploads")
    monkeypatch.setattr(settings, "airflow_schedules_dir", tmp_path / "airflow" / "dags" / "schedules")
    monkeypatch.setattr(settings, "datapulse_internal_token", "test-only-internal-token")
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    with TestClient(app) as test_client:
        test_client.app.state.test_storage = settings.storage_dir
        test_client.app.state.test_session = TestingSession
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
