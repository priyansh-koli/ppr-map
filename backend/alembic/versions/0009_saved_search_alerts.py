"""saved searches: how far each has been alerted (D-050)

`alerted_through_run_id` is the PPR ingest run whose sales the search has already been
checked against. An alert reports matching sales first seen in a later run, so each newly
filed sale is reported once, and a new saved search starts from the register as it is.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-30 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "saved_search",
        sa.Column(
            "alerted_through_run_id",
            sa.BigInteger(),
            nullable=True,
            comment="PPR ingest run already checked; later runs' sales are new",
        ),
    )
    op.add_column(
        "saved_search", sa.Column("last_alerted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_saved_search_alert_frequency", "saved_search", ["alert_frequency"], unique=False
    )
    op.create_index("ix_sale_first_seen_run_id", "sale", ["first_seen_run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_sale_first_seen_run_id", table_name="sale")
    op.drop_index("ix_saved_search_alert_frequency", table_name="saved_search")
    op.drop_column("saved_search", "last_alerted_at")
    op.drop_column("saved_search", "alerted_through_run_id")
