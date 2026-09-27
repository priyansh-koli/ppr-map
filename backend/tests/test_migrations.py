"""Migrations: offline SQL rendering always runs; live-database checks need TEST_DATABASE_URL."""

import io
import re
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from typer.testing import CliRunner

from app.config import get_settings
from app.models import Base
from tests.conftest import BACKEND_DIR

OFFLINE_URL = "postgresql+psycopg://offline:offline@localhost/offline"


def _alembic_config(
    url: str, monkeypatch: pytest.MonkeyPatch, buffer: io.StringIO | None = None
) -> Config:
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"), output_buffer=buffer)
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def test_upgrade_renders_every_model_table_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.StringIO()
    command.upgrade(_alembic_config(OFFLINE_URL, monkeypatch, buffer), "head", sql=True)
    sql = buffer.getvalue()
    created = set(re.findall(r"^CREATE TABLE (\w+)", sql, re.M))
    assert {t.name for t in Base.metadata.sorted_tables} <= created
    assert "CREATE EXTENSION IF NOT EXISTS postgis" in sql
    assert "audit_log_append_only" in sql


def test_url_encoded_passwords_work(monkeypatch: pytest.MonkeyPatch) -> None:
    """`%` in DATABASE_URL must not trip configparser interpolation (p@ss -> p%40ss)."""
    url = "postgresql+psycopg://offline:p%40ss@localhost/offline"
    command.upgrade(_alembic_config(url, monkeypatch, io.StringIO()), "head", sql=True)


def test_downgrade_renders_every_drop_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = io.StringIO()
    command.downgrade(_alembic_config(OFFLINE_URL, monkeypatch, buffer), "head:base", sql=True)
    dropped = set(re.findall(r"^DROP TABLE (\w+)", buffer.getvalue(), re.M))
    assert {t.name for t in Base.metadata.sorted_tables} <= dropped


# --- live database -----------------------------------------------------------------------


@pytest.fixture
def migrated_db(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[sa.Engine]:
    cfg = _alembic_config(database_url, monkeypatch)
    engine = sa.create_engine(database_url)
    # Check each step really committed: a migration that is silently rolled back (for
    # example by a stray transaction in env.py) would otherwise pass on an old database.
    command.downgrade(cfg, "base")
    assert "sale" not in sa.inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "sale" in sa.inspect(engine).get_table_names()
    yield engine
    engine.dispose()


@pytest.mark.db
def test_models_and_migrations_agree(
    migrated_db: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    command.check(_alembic_config(str(migrated_db.url.render_as_string(False)), monkeypatch))


@pytest.mark.db
def test_audit_log_is_append_only(migrated_db: sa.Engine) -> None:
    with migrated_db.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO audit_log (action, target_kind, target_id) VALUES ('t', 'test', '1')"
            )
        )
    with pytest.raises(sa.exc.DBAPIError, match="append-only"), migrated_db.begin() as conn:
        conn.execute(sa.text("UPDATE audit_log SET action = 'x'"))


@pytest.mark.db
def test_sync_permissions_is_idempotent(migrated_db: sa.Engine) -> None:
    from app.cli import cli

    runner = CliRunner()
    for _ in range(2):
        result = runner.invoke(cli, ["sync-permissions"])
        assert result.exit_code == 0, result.output
    with migrated_db.connect() as conn:
        admin_perms = conn.execute(
            sa.text(
                "SELECT count(*) FROM role_permission rp JOIN role r ON r.id = rp.role_id "
                "WHERE r.name = 'admin'"
            )
        ).scalar_one()
    assert admin_perms == 16
