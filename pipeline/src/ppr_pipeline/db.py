"""Sync database access for the pipeline (the API uses async sessions)."""

from collections.abc import Iterator
from contextlib import contextmanager

import sqlalchemy as sa
from app.config import get_settings

# Any fixed number, the same for every pipeline process ("pprp").
PIPELINE_LOCK = 0x70707270


class PipelineBusy(RuntimeError):
    """Another pipeline step holds the lock."""


def get_engine(url: str | None = None) -> sa.Engine:
    return sa.create_engine(url or get_settings().database_url)


@contextmanager
def pipeline_lock(engine: sa.Engine) -> Iterator[None]:
    """One pipeline step at a time, wherever it runs (the worker, `make`, a shell): two at
    once rebuild the same tables and corrupt each other (P1 #22). A session advisory lock on
    a connection of its own, held for the whole run; Postgres frees it if the process dies."""
    with engine.connect() as conn:
        got = conn.execute(sa.text("SELECT pg_try_advisory_lock(:k)"), {"k": PIPELINE_LOCK})
        conn.commit()
        if not got.scalar_one():
            raise PipelineBusy("another pipeline step is running: try again when it has finished")
        try:
            yield
        finally:
            conn.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": PIPELINE_LOCK})
            conn.commit()
