"""least-privilege database roles: the services no longer connect as the superuser (P1 #8)

The API, worker, scheduler and Martin all used POSTGRES_USER, a superuser: any SQL injection
could run `COPY ... TO PROGRAM` or wipe the audit log. Each now has its own role, and the
superuser only runs migrations (docs/permissions.md, "Database roles"):

- `ppr_app` (API, scheduler): reads every table; writes the account tables, only the few
  data columns admins edit, and may only add to `audit_log`. No TRUNCATE, no DDL.
- `ppr_pipeline` (worker): `ppr_app`, plus `ppr_data`, the owner of the data tables, so the
  pipeline can TRUNCATE, VACUUM and ANALYZE what it rebuilds. It owns none of the account
  tables or the audit log.
- `ppr_tiles` (Martin): reads the data tables only; nothing about accounts.

The roles are created without a password (NOLOGIN); `python -m app.cli db-roles`, run by
`make migrate`, gives them their passwords from .env. Roles belong to the whole cluster, not
to this database (the test database shares them), so a downgrade takes back what they were
given here and leaves the roles themselves: dropping one would sign out a service still
using it on another database. `DROP ROLE` them by hand once no database uses them.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-04 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = ("ppr_data", "ppr_app", "ppr_pipeline", "ppr_tiles")
# Built and rebuilt by the pipeline; owned by ppr_data.
DATA_TABLES = (
    "area",
    "area_attribute",
    "area_part",
    "area_stats",
    "benchmark_series",
    "environment_layer",
    "estimate_calibration",
    "gazetteer_feature",
    "geocode_attempt",
    "ingest_row_error",
    "ingest_run",
    "planning_application",
    "poi",
    "price_hex",
    "property",
    "property_enrichment",
    "property_planning",
    "property_summary",
    "sale",
)
# Accounts and their activity; the API writes them. audit_log is separate: insert only.
APP_TABLES = (
    "alert_delivery",
    "api_key",
    "app_user",
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
)
# What admins change in the data: hiding or moving a property (and its hover card), and the
# attempt a manual move records.
APP_DATA_WRITES = (
    "GRANT UPDATE ON property, property_summary TO ppr_app",
    "GRANT INSERT ON geocode_attempt TO ppr_app",
)


def _create_role(name: str) -> str:
    return (
        f"DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{name}') "
        f"THEN CREATE ROLE {name} NOLOGIN; END IF; END $$"
    )


def upgrade() -> None:
    for name in ROLES:
        op.execute(_create_role(name))
    op.execute("GRANT ppr_app, ppr_data TO ppr_pipeline")
    op.execute("GRANT USAGE ON SCHEMA public TO ppr_app, ppr_tiles")
    # vicinity.py builds scratch tables next to the data.
    op.execute("GRANT CREATE ON SCHEMA public TO ppr_data")
    data, app = ", ".join(DATA_TABLES), ", ".join(APP_TABLES)
    for table in DATA_TABLES:
        op.execute(f"ALTER TABLE {table} OWNER TO ppr_data")
    op.execute(f"GRANT SELECT ON {data}, {app}, audit_log TO ppr_app")
    op.execute(f"GRANT INSERT, UPDATE, DELETE ON {app} TO ppr_app")
    op.execute("GRANT INSERT ON audit_log TO ppr_app")
    for sql in APP_DATA_WRITES:
        op.execute(sql)
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ppr_app")
    op.execute(f"GRANT SELECT ON {data} TO ppr_tiles")


def downgrade() -> None:
    data, app = ", ".join(DATA_TABLES), ", ".join(APP_TABLES)
    for table in DATA_TABLES:
        op.execute(f"ALTER TABLE {table} OWNER TO CURRENT_USER")
    op.execute(f"REVOKE ALL ON {data}, {app}, audit_log FROM ppr_app, ppr_tiles")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM ppr_app")
    op.execute("REVOKE ALL ON SCHEMA public FROM ppr_app, ppr_tiles, ppr_data")
