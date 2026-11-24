from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "sqlite:///./datapulse.db"
    storage_dir: Path = Path("./storage")
    max_upload_mb: int = 25
    max_profile_mb: int = 25
    cors_origins: str = "http://localhost:5173"
    datapulse_internal_token: str = ""
    airflow_schedules_dir: Path = Path("../airflow/dags/schedules")
    airflow_api_url: str = "http://api:8000/api"
    airflow_http_timeout_seconds: int = 15
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

settings = Settings()
