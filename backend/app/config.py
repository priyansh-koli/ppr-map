from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment (see .env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = Field(
        default="postgresql+psycopg://pprmap:pprmap@localhost:5432/pprmap",
        description="SQLAlchemy URL; the psycopg 3 driver serves both sync and async use.",
    )
    redis_url: str = "redis://localhost:6379/0"
    app_base_url: str = "http://localhost:8080"
    session_secret: str = Field(default="", repr=False)
    csrf_secret: str = Field(default="", repr=False)
    ip_hash_salt: str = Field(default="", repr=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
