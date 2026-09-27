from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root. Alembic and `python -m app.cli` run from backend/, so a
# relative ".env" would miss it. In the Docker image this file does not exist and is ignored.
REPO_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment (see .env.example)."""

    model_config = SettingsConfigDict(env_file=REPO_ENV_FILE, extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+psycopg://pprmap:pprmap@localhost:5432/pprmap",
        description="SQLAlchemy URL; the psycopg 3 driver serves both sync and async use.",
    )
    redis_url: str = "redis://localhost:6379/0"
    app_base_url: str = "http://localhost:8080"
    nominatim_url: str = "http://localhost:8088"
    session_secret: str = Field(default="", repr=False)
    csrf_secret: str = Field(default="", repr=False)
    ip_hash_salt: str = Field(default="", repr=False)

    @model_validator(mode="after")
    def _secrets_in_production(self) -> Self:
        if self.environment == "production":
            missing = [
                name
                for name in ("session_secret", "csrf_secret", "ip_hash_salt")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"production needs {', '.join(missing).upper()} set")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
