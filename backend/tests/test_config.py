from app.core.config import settings

def test_neon_urls_use_installed_psycopg_driver(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://user:secret@host/db")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://user:secret@host/db"

def test_legacy_postgres_url_is_normalized(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgres://user:secret@host/db")
    assert settings.sqlalchemy_database_url == "postgresql+psycopg://user:secret@host/db"
