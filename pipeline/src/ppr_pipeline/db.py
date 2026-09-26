"""Sync database access for the pipeline (the API uses async sessions)."""

import sqlalchemy as sa
from app.config import get_settings


def get_engine(url: str | None = None) -> sa.Engine:
    return sa.create_engine(url or get_settings().database_url)
