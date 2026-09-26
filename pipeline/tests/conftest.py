import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"
BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture(scope="session")
def migrated_engine() -> Iterator[sa.Engine]:
    """TEST_DATABASE_URL at the latest migration. Tests needing it are skipped without it."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set (start PostGIS with `make up`)")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    yield engine
    engine.dispose()
    mp.undo()
    get_settings.cache_clear()


@pytest.fixture
def engine(migrated_engine: sa.Engine) -> sa.Engine:
    """A migrated database with no PPR or area data in it."""
    with migrated_engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE property, sale, ingest_run, area RESTART IDENTITY CASCADE"))
    return migrated_engine


@pytest.fixture
def sample_csv() -> bytes:
    """26 real PPR rows (cp1252), chosen for the tricky cases; see test_ppr_parse.py."""
    return (FIXTURES / "ppr_sample.csv").read_bytes()
