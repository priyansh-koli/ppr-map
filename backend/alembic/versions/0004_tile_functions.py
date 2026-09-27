"""tile functions for Martin: sales and price hexes (D-004, D-009)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Martin passes the tile's query string as a JSON object of strings. Anything that does not
# parse falls back to the default, so a bad URL gives the default map, not an error.
HELPERS = r"""
CREATE FUNCTION tile_param_number(params json, key text) RETURNS numeric
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN params ->> key ~ '^\d{1,12}(\.\d{1,2})?$'
                THEN (params ->> key)::numeric END
$$;

CREATE FUNCTION tile_param_date(params json, key text) RETURNS date
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN params ->> key ~ '^\d{4}-\d{2}-\d{2}$'
                THEN to_date(params ->> key, 'YYYY-MM-DD') END
$$;

CREATE FUNCTION tile_param_bool(params json, key text, fallback boolean) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE lower(params ->> key) WHEN 'true' THEN true WHEN 'false' THEN false
                ELSE fallback END
$$;

CREATE FUNCTION tile_param_confidence(params json) RETURNS geocode_confidence
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN params ->> 'minConfidence' IN
                     ('exact', 'street', 'locality', 'routing_key', 'county')
                THEN (params ->> 'minConfidence')::geocode_confidence
                ELSE 'locality' END
$$;
"""

# The latest sale per property that passes the filters. Default: market sales only
# (not "not full market price", not in a bulk group), every year, any type, and places
# known at least to their locality.
MATCHING_SALES = r"""
CREATE FUNCTION tile_matching_sales(env geometry, params json)
RETURNS TABLE (
    property_id bigint, public_id text, geom geometry, confidence geocode_confidence,
    sale_date date, price_eur numeric, is_new boolean, nfmp boolean, vatx boolean,
    bulk boolean, n_sales bigint
)
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT DISTINCT ON (s.property_id)
           p.id, p.public_id, p.geom, p.geocode_confidence, s.sale_date, s.price_eur,
           s.is_new, s.not_full_market_price, s.vat_exclusive, s.bulk_group_id IS NOT NULL,
           count(*) OVER (PARTITION BY s.property_id)
    FROM property p JOIN sale s ON s.property_id = p.id
    WHERE p.geom && env AND NOT p.is_suppressed
      AND p.geocode_confidence <= tile_param_confidence(params)
      AND s.withdrawn_at IS NULL
      AND NOT (tile_param_bool(params, 'excludeNonMarket', true) AND s.not_full_market_price)
      AND NOT (tile_param_bool(params, 'excludeBulk', true) AND s.bulk_group_id IS NOT NULL)
      AND s.price_eur >= coalesce(tile_param_number(params, 'priceMin'), 0)
      AND s.price_eur <= coalesce(tile_param_number(params, 'priceMax'), 1e12)
      AND s.sale_date >= coalesce(tile_param_date(params, 'dateFrom'), '2010-01-01')
      AND s.sale_date <= coalesce(tile_param_date(params, 'dateTo'), '2100-01-01')
      AND (params ->> 'type' IS DISTINCT FROM 'new' OR s.is_new)
      AND (params ->> 'type' IS DISTINCT FROM 'second_hand' OR NOT s.is_new)
    ORDER BY s.property_id, s.sale_date DESC, s.id DESC
$$;
"""

# Below z14: grid cells (64 per tile side, about 75 m at z13) with the count and median of the latest matching
# sale per property. From z14: precise points (exact, street) one per property, and every
# coarser location (a town centre, a routing key, a county) as one stack with its count, so
# hundreds of sales placed at a town centre are not drawn as one misleading dot. (D-004
# said z12; a z12 tile of central Dublin points is 1.2 MB, a z14 one 68 KB.)
SALES_TILES = r"""
CREATE FUNCTION sales_tiles(z integer, x integer, y integer, query_params json)
RETURNS bytea LANGUAGE plpgsql STABLE PARALLEL SAFE AS $$
DECLARE
    env3857 geometry := ST_TileEnvelope(z, x, y);
    env4326 geometry := ST_Transform(ST_TileEnvelope(z, x, y, margin => 0.02), 4326);
    cell float8 := (ST_XMax(env3857) - ST_XMin(env3857)) / 64;
    result bytea;
    stacks bytea;
BEGIN
    IF z < 14 THEN
        SELECT ST_AsMVT(t, 'cells') INTO result FROM (
            SELECT ST_AsMVTGeom(c, env3857) AS geom, n::int AS n, round(median)::int AS median
            FROM (
                SELECT ST_SnapToGrid(ST_Transform(m.geom, 3857), cell) AS c, count(*) AS n,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY m.price_eur) AS median
                FROM tile_matching_sales(env4326, query_params) m
                GROUP BY 1
            ) g
        ) t WHERE t.geom IS NOT NULL;
        RETURN coalesce(result, ''::bytea);
    END IF;

    SELECT ST_AsMVT(t, 'sales') INTO result FROM (
        SELECT ST_AsMVTGeom(ST_Transform(m.geom, 3857), env3857) AS geom,
               m.public_id AS id, round(m.price_eur)::int AS price,
               to_char(m.sale_date, 'YYYYMMDD')::int AS date, m.is_new AS "isNew",
               m.nfmp, m.vatx, m.bulk, m.confidence::text AS confidence,
               m.n_sales::int AS "nSales"
        FROM tile_matching_sales(env4326, query_params) m
        WHERE m.confidence IN ('exact', 'street')
    ) t WHERE t.geom IS NOT NULL;

    SELECT ST_AsMVT(t, 'stacks') INTO stacks FROM (
        SELECT ST_AsMVTGeom(ST_Transform(g.geom, 3857), env3857) AS geom, g.n::int AS n,
               round(g.median)::int AS median, g.confidence::text AS confidence
        FROM (
            SELECT m.geom, min(m.confidence) AS confidence, count(*) AS n,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY m.price_eur) AS median
            FROM tile_matching_sales(env4326, query_params) m
            WHERE m.confidence NOT IN ('exact', 'street')
            GROUP BY m.geom
        ) g
    ) t WHERE t.geom IS NOT NULL;

    RETURN coalesce(result, ''::bytea) || coalesce(stacks, ''::bytea);
END
$$;
"""

# H3 resolution by zoom: r6 up to z7, r7 for z8-9, r8 from z10. Suppressed cells (n < 5)
# keep their count and have no median.
PRICE_HEX_TILES = r"""
CREATE FUNCTION price_hex_tiles(z integer, x integer, y integer, query_params json)
RETURNS bytea LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT coalesce(ST_AsMVT(t, 'hexes'), ''::bytea) FROM (
        SELECT ST_AsMVTGeom(ST_Transform(h.geom, 3857), ST_TileEnvelope(z, x, y)) AS geom,
               h.n, CASE WHEN NOT h.suppressed THEN round(h.median_price)::int END AS median,
               h.suppressed
        FROM price_hex h
        WHERE h.geom && ST_Transform(ST_TileEnvelope(z, x, y), 4326)
          AND h.resolution = CASE WHEN z < 8 THEN 6 WHEN z < 10 THEN 7 ELSE 8 END
          AND h."window" = CASE WHEN query_params ->> 'window' = 'rolling_36m'
                                THEN 'rolling_36m'::hex_window ELSE 'rolling_12m' END
          AND h.segment = CASE WHEN query_params ->> 'segment' IN ('new', 'second_hand')
                               THEN (query_params ->> 'segment')::segment ELSE 'all' END
    ) t WHERE t.geom IS NOT NULL
$$;
"""


def upgrade() -> None:
    for sql in (HELPERS, MATCHING_SALES, SALES_TILES, PRICE_HEX_TILES):
        op.execute(sql)


def downgrade() -> None:
    op.execute("DROP FUNCTION price_hex_tiles(integer, integer, integer, json)")
    op.execute("DROP FUNCTION sales_tiles(integer, integer, integer, json)")
    op.execute("DROP FUNCTION tile_matching_sales(geometry, json)")
    op.execute("DROP FUNCTION tile_param_confidence(json)")
    op.execute("DROP FUNCTION tile_param_bool(json, text, boolean)")
    op.execute("DROP FUNCTION tile_param_date(json, text)")
    op.execute("DROP FUNCTION tile_param_number(json, text)")
