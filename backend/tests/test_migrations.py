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
def test_purging_an_actor_keeps_their_audit_entries(migrated_db: sa.Engine) -> None:
    """Deleting an account nulls its actor id (the one change the trigger allows)."""
    with migrated_db.begin() as conn:
        user = conn.execute(
            sa.text(
                "INSERT INTO app_user (email, password_hash, full_name) "
                "VALUES ('actor@example.ie', 'x', 'Actor') RETURNING id"
            )
        ).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO audit_log (actor_user_id, action, target_kind, target_id) "
                "VALUES (:u, 'purge-test', 'test', '1')"
            ),
            {"u": user},
        )
    with migrated_db.begin() as conn:
        conn.execute(sa.text("DELETE FROM app_user WHERE id = :u"), {"u": user})
        kept = conn.execute(
            sa.text("SELECT actor_user_id FROM audit_log WHERE action = 'purge-test'")
        ).one()
        assert kept.actor_user_id is None
    with pytest.raises(sa.exc.DBAPIError, match="append-only"), migrated_db.begin() as conn:
        conn.execute(sa.text("UPDATE audit_log SET action = 'x' WHERE action = 'purge-test'"))


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


# --- database roles (migration 0014) ------------------------------------------------------

# The tables of accounts and their activity. Every other table is the pipeline's: owned by
# ppr_data, readable by Martin. A new table must be put on one side or the other.
ACCOUNT_TABLES = {
    "alembic_version",
    "alert_delivery",
    "api_key",
    "app_user",
    "audit_log",
    "consent_record",
    "email_verification_token",
    "password_reset_token",
    "permission",
    "removal_request",
    "role",
    "role_permission",
    "saved_search",
    "search_history",
    "user_profile",
    "user_role",
    "user_session",
    "view_history",
    "wishlist_item",
}
DENIED = "42501"  # insufficient_privilege


def _as_role(engine: sa.Engine, role: str, sql: str) -> str | None:
    """Run `sql` as `role` and roll back; the SQLSTATE it failed with, or None."""
    with engine.connect() as conn, conn.begin() as tx:
        conn.execute(sa.text(f"SET LOCAL ROLE {role}"))
        try:
            conn.execute(sa.text(sql))
        except sa.exc.DBAPIError as e:
            return str(getattr(e.orig, "sqlstate", "?"))
        finally:
            tx.rollback()
    return None


@pytest.mark.db
def test_every_table_belongs_to_a_database_role(migrated_db: sa.Engine) -> None:
    with migrated_db.connect() as conn:
        tables = conn.execute(
            sa.text(
                "SELECT c.relname, pg_get_userbyid(c.relowner), "
                "has_table_privilege('ppr_app', c.oid, 'SELECT'), "
                "has_table_privilege('ppr_tiles', c.oid, 'SELECT') "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND c.relname <> 'spatial_ref_sys' AND NOT EXISTS (SELECT FROM pg_depend d "
                "WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass AND d.deptype = 'e')"
            )
        ).all()
    assert len(tables) > 30
    for name, owner, app_reads, tiles_read in tables:
        if name in ACCOUNT_TABLES:
            assert owner != "ppr_data" and not tiles_read, name
            assert app_reads or name == "alembic_version", name
        else:
            assert owner == "ppr_data" and tiles_read and app_reads, name


@pytest.mark.db
def test_service_roles_cannot_escalate(migrated_db: sa.Engine) -> None:
    """No service can run programs, wipe the audit log or change the schema (P1 #8)."""
    for role in ("ppr_app", "ppr_pipeline", "ppr_tiles"):
        assert _as_role(migrated_db, role, "COPY (SELECT 1) TO PROGRAM 'true'") == DENIED
        assert _as_role(migrated_db, role, "DELETE FROM audit_log") == DENIED
        assert _as_role(migrated_db, role, "TRUNCATE audit_log") == DENIED
        assert _as_role(migrated_db, role, "DROP TABLE app_user") == DENIED
        assert _as_role(migrated_db, role, "ALTER TABLE audit_log DISABLE TRIGGER ALL") == DENIED
    assert _as_role(migrated_db, "ppr_app", "TRUNCATE sale") == DENIED
    assert _as_role(migrated_db, "ppr_app", "DELETE FROM sale") == DENIED
    assert _as_role(migrated_db, "ppr_tiles", "SELECT * FROM app_user") == DENIED
    assert _as_role(migrated_db, "ppr_tiles", "SELECT * FROM user_session") == DENIED
    assert _as_role(migrated_db, "ppr_tiles", "UPDATE property SET is_suppressed = true") == DENIED


@pytest.mark.db
def test_service_roles_can_do_their_work(migrated_db: sa.Engine) -> None:
    audit = "INSERT INTO audit_log (action, target_kind, target_id) VALUES ('t', 'test', '1')"
    assert _as_role(migrated_db, "ppr_app", audit) is None
    assert _as_role(migrated_db, "ppr_app", "UPDATE property SET is_suppressed = false") is None
    assert _as_role(migrated_db, "ppr_app", "DELETE FROM user_session") is None
    # The worker also sends alerts and purges closed accounts.
    assert _as_role(migrated_db, "ppr_pipeline", "DELETE FROM app_user") is None
    assert _as_role(migrated_db, "ppr_pipeline", "TRUNCATE property_enrichment, sale") is None
    assert _as_role(migrated_db, "ppr_pipeline", "ANALYZE property") is None
    assert _as_role(migrated_db, "ppr_pipeline", "CREATE TABLE scratch (g int)") is None
    tile = "SELECT sales_tiles(14, 7877, 5349, '{}'::json), price_hex_tiles(8, 123, 83, '{}')"
    assert _as_role(migrated_db, "ppr_tiles", tile) is None
    assert (
        _as_role(
            migrated_db,
            "ppr_tiles",
            "SELECT * FROM tile_matching_sales(ST_MakeEnvelope(-7, 52, -6, 53, 4326), '{}')",
        )
        is None
    )


@pytest.mark.db
def test_db_roles_lets_the_services_sign_in(
    migrated_db: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Roles are shared by the whole cluster, so ppr_tiles' password is put back afterwards."""
    from app.cli import cli

    with migrated_db.connect() as conn:
        saved = conn.execute(
            sa.text("SELECT rolcanlogin, rolpassword FROM pg_authid WHERE rolname = 'ppr_tiles'")
        ).one()
    monkeypatch.setenv("APP_DB_PASSWORD", "")
    monkeypatch.setenv("PIPELINE_DB_PASSWORD", "")
    monkeypatch.setenv("TILES_DB_PASSWORD", "it's 100% a test")
    get_settings.cache_clear()
    try:
        result = CliRunner().invoke(cli, ["db-roles"])
        assert result.exit_code == 0, result.output
        assert "APP_DB_PASSWORD is empty: ppr_app cannot sign in." in result.output
        assert "ppr_tiles can sign in." in result.output
        url = migrated_db.url.set(username="ppr_tiles", password="it's 100% a test")
        tiles = sa.create_engine(url)
        with tiles.connect() as conn:
            assert conn.execute(sa.text("SELECT current_user")).scalar_one() == "ppr_tiles"
        tiles.dispose()
    finally:
        get_settings.cache_clear()
        with migrated_db.begin() as conn:
            restore = conn.execute(
                sa.text(
                    "SELECT format('ALTER ROLE ppr_tiles %s PASSWORD %L', "
                    "CAST(:login AS text), CAST(:p AS text))"
                ),
                {"login": "LOGIN" if saved.rolcanlogin else "NOLOGIN", "p": saved.rolpassword},
            ).scalar_one()
            conn.connection.cursor().execute(restore)
