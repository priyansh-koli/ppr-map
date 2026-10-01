"""sales tiles: always plan with the request's own filters (D-054)

`tile_matching_sales` relies on its `tile_param_*` calls folding to constants when the
query is planned (migration 0008). PL/pgSQL caches the plans of the statements inside
`sales_tiles`, and from a connection's sixth call Postgres may switch to a generic plan
that leaves the parameters unknown. With an `area` filter that plan took over 30 s a tile
instead of 12 ms, so Martin's pooled connections filled up and the map stopped drawing
sales. Forcing custom plans costs about a millisecond of planning per tile.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-01 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER FUNCTION sales_tiles(integer, integer, integer, json)"
        " SET plan_cache_mode = force_custom_plan"
    )


def downgrade() -> None:
    op.execute("ALTER FUNCTION sales_tiles(integer, integer, integer, json) RESET plan_cache_mode")
