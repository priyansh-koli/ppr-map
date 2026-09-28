"""sales tiles below z14: coarser cells, placed where their sales are (D-044)

64 cells per tile side put a cell every 8 px of a 512 px tile, so the zoomed-out map was an
even carpet of dots that hid the basemap. Cells are now 16 per side (32 px), and each is
drawn at the mean position of its sales instead of the cell's centre, so groups sit on the
towns and streets they stand for. Each sale is still counted in one cell of one tile.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-28 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The mean of points inside a square lies inside it, so a cell never drifts into its
# neighbour's space.
SALES_CELLS = r"""
CREATE OR REPLACE FUNCTION tile_sales_cells(z integer, x integer, y integer, query_params json)
RETURNS TABLE (i integer, j integer, n integer, median integer, cx float8, cy float8)
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    WITH env AS (
        SELECT ST_XMin(e) AS x0, ST_YMin(e) AS y0, (ST_XMax(e) - ST_XMin(e)) / 16 AS cell,
               ST_Transform(e, 4326) AS e4326
        FROM (SELECT ST_TileEnvelope(z, x, y) AS e) t
    ), binned AS (
        SELECT floor((ST_X(p) - env.x0) / env.cell)::int AS i,
               floor((ST_Y(p) - env.y0) / env.cell)::int AS j,
               ST_X(p) AS px, ST_Y(p) AS py, price_eur
        FROM env,
             LATERAL (SELECT ST_Transform(m.geom, 3857) AS p, m.price_eur
                      FROM tile_matching_sales(env.e4326, query_params) m) s
    )
    SELECT b.i, b.j, count(*)::int,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY b.price_eur))::int,
           avg(b.px), avg(b.py)
    FROM binned b
    WHERE b.i BETWEEN 0 AND 15 AND b.j BETWEEN 0 AND 15
    GROUP BY b.i, b.j
$$;
"""

# Migration 0004's version.
PREVIOUS_SALES_CELLS = r"""
CREATE OR REPLACE FUNCTION tile_sales_cells(z integer, x integer, y integer, query_params json)
RETURNS TABLE (i integer, j integer, n integer, median integer, cx float8, cy float8)
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    WITH env AS (
        SELECT ST_XMin(e) AS x0, ST_YMin(e) AS y0, (ST_XMax(e) - ST_XMin(e)) / 64 AS cell,
               ST_Transform(e, 4326) AS e4326
        FROM (SELECT ST_TileEnvelope(z, x, y) AS e) t
    ), binned AS (
        SELECT floor((ST_X(p) - env.x0) / env.cell)::int AS i,
               floor((ST_Y(p) - env.y0) / env.cell)::int AS j, price_eur
        FROM env,
             LATERAL (SELECT ST_Transform(m.geom, 3857) AS p, m.price_eur
                      FROM tile_matching_sales(env.e4326, query_params) m) s
    )
    SELECT b.i, b.j, count(*)::int,
           round(percentile_cont(0.5) WITHIN GROUP (ORDER BY b.price_eur))::int,
           env.x0 + (b.i + 0.5) * env.cell, env.y0 + (b.j + 0.5) * env.cell
    FROM binned b, env
    WHERE b.i BETWEEN 0 AND 63 AND b.j BETWEEN 0 AND 63
    GROUP BY b.i, b.j, env.x0, env.y0, env.cell
$$;
"""


def upgrade() -> None:
    op.execute(SALES_CELLS)


def downgrade() -> None:
    op.execute(PREVIOUS_SALES_CELLS)
