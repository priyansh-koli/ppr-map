"""estimate calibration: how far repeat sales land from the index (D-053)

For each CSO RPPI series and band of years between two sales, the 10th, 50th and 90th
percentiles of ln(actual second price / price the index implied from the first). The
price estimate's range comes from these, so it says how well the index has done here.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-30 21:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The street and estate parts of a normalised address: every part but the last (the town),
# without a house or unit number. "7 the gables, ballinteer road, dublin" ->
# {the gables, ballinteer road}. Two addresses sharing a part are on the same street or
# estate (comparable sales, D-053).
STREET_PARTS = r"""
CREATE FUNCTION address_street_parts(address text) RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT coalesce(array_agg(s) FILTER (WHERE s <> '' AND s !~ '^[0-9]'), '{}')
    FROM (
        SELECT trim(regexp_replace(part,
                    '^\s*((apt|apartment|unit|flat|no)\.?\s*)?[0-9][0-9a-z/-]*\s*', '')) AS s
        FROM unnest(string_to_array(address, ',')) WITH ORDINALITY AS t(part, i)
        WHERE i < array_length(string_to_array(address, ','), 1)
    ) parts
$$;
"""


def upgrade() -> None:
    op.execute(STREET_PARTS)
    op.create_table(
        "estimate_calibration",
        sa.Column("series_key", sa.Text(), nullable=False),
        sa.Column("gap_band", sa.Text(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("p10", sa.Numeric(), nullable=False),
        sa.Column("p50", sa.Numeric(), nullable=False),
        sa.Column("p90", sa.Numeric(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("series_key", "gap_band", name=op.f("pk_estimate_calibration")),
    )


def downgrade() -> None:
    op.drop_table("estimate_calibration")
    op.execute("DROP FUNCTION address_street_parts(text)")
