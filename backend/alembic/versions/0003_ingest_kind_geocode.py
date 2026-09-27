"""ingest_kind: geocode and aggregate runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27 14:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_VALUES = (
    "ppr",
    "gtfs",
    "osm",
    "census",
    "pobal",
    "schools",
    "boundaries",
    "crime",
    "planning",
    "environment",
    "benchmarks",
)


def upgrade() -> None:
    op.execute("ALTER TYPE ingest_kind ADD VALUE IF NOT EXISTS 'geocode'")
    op.execute("ALTER TYPE ingest_kind ADD VALUE IF NOT EXISTS 'aggregate'")


def downgrade() -> None:
    # Postgres cannot drop enum values: rebuild the type without them. Runs of the removed
    # kinds go first, with the geocode attempts that point at them.
    op.execute(
        "DELETE FROM geocode_attempt WHERE run_id IN "
        "(SELECT id FROM ingest_run WHERE kind::text IN ('geocode', 'aggregate'))"
    )
    op.execute("DELETE FROM ingest_run WHERE kind::text IN ('geocode', 'aggregate')")
    op.execute("ALTER TYPE ingest_kind RENAME TO ingest_kind_old")
    values = ", ".join(f"'{v}'" for v in OLD_VALUES)
    op.execute(f"CREATE TYPE ingest_kind AS ENUM ({values})")
    op.execute(
        "ALTER TABLE ingest_run ALTER COLUMN kind TYPE ingest_kind USING kind::text::ingest_kind"
    )
    op.execute("DROP TYPE ingest_kind_old")
