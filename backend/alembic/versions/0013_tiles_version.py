"""tiles version: index the properties an administrator has hidden or moved

Martin caches tiles by URL and the map adds the data version as `v`, which changed only with
the monthly run. Hiding a property (an approved removal request) or moving it by hand left
the old point in cached tiles until then. /meta now also reports a tiles version, the data
version plus the latest such edit, read through this small partial index.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-04 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_property_admin_edited",
        "property",
        ["updated_at"],
        unique=False,
        postgresql_where=sa.text("is_suppressed OR geocode_locked"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_property_admin_edited",
        table_name="property",
        postgresql_where=sa.text("is_suppressed OR geocode_locked"),
    )
