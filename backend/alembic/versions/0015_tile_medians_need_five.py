"""sales tiles: no median for fewer than 5 sales (P1 #13)

Aggregates with n < 5 are suppressed (CONVENTIONS.md), but the zoomed-out cells and the
stacks of sales placed at a town or routing key carried a median for any count: a cell of
two sales gave away their middle price. Both now keep their count and drop the median below
5; the map draws them grey, as it does suppressed price hexes. Single sales at their address
or street (z14 and over) still carry their own price, as the register publishes it.

`sales_tiles` is redefined whole, so it keeps migration 0011's `plan_cache_mode` setting.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-04 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
           CASE WHEN count(*) >= 5
                THEN round(percentile_cont(0.5) WITHIN GROUP (ORDER BY b.price_eur))::int END,
           avg(b.px), avg(b.py)
    FROM binned b
    WHERE b.i BETWEEN 0 AND 15 AND b.j BETWEEN 0 AND 15
    GROUP BY b.i, b.j
$$;
"""

SALES_TILES = r"""
CREATE OR REPLACE FUNCTION sales_tiles(z integer, x integer, y integer, query_params json)
RETURNS bytea LANGUAGE plpgsql STABLE PARALLEL SAFE
SET plan_cache_mode = force_custom_plan AS $$
DECLARE
    env3857 geometry := ST_TileEnvelope(z, x, y);
    result bytea;
BEGIN
    IF z < 14 THEN
        SELECT ST_AsMVT(t, 'cells') INTO result FROM (
            SELECT ST_AsMVTGeom(ST_SetSRID(ST_MakePoint(c.cx, c.cy), 3857), env3857) AS geom,
                   c.n, c.median
            FROM tile_sales_cells(z, x, y, query_params) c
        ) t WHERE t.geom IS NOT NULL;
        RETURN coalesce(result, ''::bytea);
    END IF;

    WITH m AS MATERIALIZED (
        SELECT * FROM tile_matching_sales(
            ST_Transform(ST_TileEnvelope(z, x, y, margin => 0.02), 4326), query_params)
    )
    SELECT coalesce((
        SELECT ST_AsMVT(t, 'sales') FROM (
            SELECT ST_AsMVTGeom(ST_Transform(m.geom, 3857), env3857) AS geom,
                   m.public_id AS id, round(m.price_eur)::int AS price,
                   to_char(m.sale_date, 'YYYYMMDD')::int AS date, m.is_new AS "isNew",
                   m.nfmp, m.vatx, m.bulk, m.confidence::text AS confidence,
                   m.n_sales::int AS "nSales"
            FROM m WHERE m.confidence IN ('exact', 'street')
        ) t WHERE t.geom IS NOT NULL), ''::bytea)
    || coalesce((
        SELECT ST_AsMVT(t, 'stacks') FROM (
            SELECT ST_AsMVTGeom(ST_Transform(g.geom, 3857), env3857) AS geom, g.n::int AS n,
                   CASE WHEN g.n >= 5 THEN round(g.median)::int END AS median,
                   g.confidence::text AS confidence
            FROM (
                SELECT m.geom, min(m.confidence) AS confidence, count(*) AS n,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY m.price_eur) AS median
                FROM m WHERE m.confidence NOT IN ('exact', 'street')
                GROUP BY m.geom
            ) g
        ) t WHERE t.geom IS NOT NULL), ''::bytea)
    INTO result;
    RETURN result;
END
$$;
"""

# Migration 0006's version.
PREVIOUS_SALES_CELLS = r"""
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

# Migration 0004's version, with 0011's setting.
PREVIOUS_SALES_TILES = r"""
CREATE OR REPLACE FUNCTION sales_tiles(z integer, x integer, y integer, query_params json)
RETURNS bytea LANGUAGE plpgsql STABLE PARALLEL SAFE
SET plan_cache_mode = force_custom_plan AS $$
DECLARE
    env3857 geometry := ST_TileEnvelope(z, x, y);
    result bytea;
BEGIN
    IF z < 14 THEN
        SELECT ST_AsMVT(t, 'cells') INTO result FROM (
            SELECT ST_AsMVTGeom(ST_SetSRID(ST_MakePoint(c.cx, c.cy), 3857), env3857) AS geom,
                   c.n, c.median
            FROM tile_sales_cells(z, x, y, query_params) c
        ) t WHERE t.geom IS NOT NULL;
        RETURN coalesce(result, ''::bytea);
    END IF;

    WITH m AS MATERIALIZED (
        SELECT * FROM tile_matching_sales(
            ST_Transform(ST_TileEnvelope(z, x, y, margin => 0.02), 4326), query_params)
    )
    SELECT coalesce((
        SELECT ST_AsMVT(t, 'sales') FROM (
            SELECT ST_AsMVTGeom(ST_Transform(m.geom, 3857), env3857) AS geom,
                   m.public_id AS id, round(m.price_eur)::int AS price,
                   to_char(m.sale_date, 'YYYYMMDD')::int AS date, m.is_new AS "isNew",
                   m.nfmp, m.vatx, m.bulk, m.confidence::text AS confidence,
                   m.n_sales::int AS "nSales"
            FROM m WHERE m.confidence IN ('exact', 'street')
        ) t WHERE t.geom IS NOT NULL), ''::bytea)
    || coalesce((
        SELECT ST_AsMVT(t, 'stacks') FROM (
            SELECT ST_AsMVTGeom(ST_Transform(g.geom, 3857), env3857) AS geom, g.n::int AS n,
                   round(g.median)::int AS median, g.confidence::text AS confidence
            FROM (
                SELECT m.geom, min(m.confidence) AS confidence, count(*) AS n,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY m.price_eur) AS median
                FROM m WHERE m.confidence NOT IN ('exact', 'street')
                GROUP BY m.geom
            ) g
        ) t WHERE t.geom IS NOT NULL), ''::bytea)
    INTO result;
    RETURN result;
END
$$;
"""


def upgrade() -> None:
    op.execute(SALES_CELLS)
    op.execute(SALES_TILES)


def downgrade() -> None:
    op.execute(PREVIOUS_SALES_CELLS)
    op.execute(PREVIOUS_SALES_TILES)
