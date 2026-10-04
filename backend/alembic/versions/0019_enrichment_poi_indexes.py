"""property_enrichment: index its three references to poi

Enrich replaces the POIs inside the same transaction that replaces the vicinity rows (P1 #21).
Deleting a POI checks every foreign key that points at it, and with no index on the three
columns each check scanned all of `property_enrichment`, including the rows that transaction
had just deleted: three scans of about 415,000 rows for each of about 65,000 POIs. A run on
the dev data was still deleting after 30 minutes. With the indexes each check is a lookup.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-04 23:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("nearest_stop_id", "nearest_primary_school_id", "nearest_post_primary_school_id")


def upgrade() -> None:
    for column in COLUMNS:
        op.create_index(f"ix_property_enrichment_{column}", "property_enrichment", [column])


def downgrade() -> None:
    for column in COLUMNS:
        op.drop_index(f"ix_property_enrichment_{column}", table_name="property_enrichment")
