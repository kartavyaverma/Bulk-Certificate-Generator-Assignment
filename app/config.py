from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Bulk Certificate Generator"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5433/certificates"
    storage_dir: Path = Path("storage")
    max_recipients_per_job: int = 10000


@lru_cache
def get_settings() -> Settings:
    return Settings()
