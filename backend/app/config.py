from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repo root. Alembic and `python -m app.cli` run from backend/, so a
# relative ".env" would miss it. In the Docker image this file does not exist and is ignored.
REPO_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
# config/ holds rates.yaml and sources.yaml; the Docker image sets PPR_CONFIG_DIR=/srv/config.
REPO_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


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
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = Field(default="", repr=False)
    email_from: str = "PPR Map <no-reply@localhost>"
    session_secret: str = Field(default="", repr=False)
    csrf_secret: str = Field(default="", repr=False)
    ip_hash_salt: str = Field(default="", repr=False)
    ppr_config_dir: Path = REPO_CONFIG_DIR

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


def secure_cookies(settings: Settings) -> bool:
    """Secure, __Host- cookies in production; plain ones on http://localhost in development."""
    return settings.environment == "production"
