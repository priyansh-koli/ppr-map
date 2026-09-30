"""search filters for the tiles, the list and /search (D-047)

`tile_matching_sales` gains the brief's other filters: county, area, Eircode routing key,
distance from a point, VAT, and distance to a stop or school. The map, the synced list,
/search, saved searches and alerts all read this one function, so they cannot disagree on
what matches.

The function stays one plain SELECT with the parameters read inline: Postgres inlines it
into the caller, where the immutable `tile_param_*` calls on a known parameter object fold to
constants at planning time. A version that parsed them once in a CTE planned 10x slower.
County codes are compared in lower case and routing keys in upper case.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-30 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# A comma-separated list of short printable tokens, or NULL. Anything else is ignored, as
# with the other parameters: a bad URL gives the default map.
HELPERS = r"""
-- `fold` is 'lower' or 'upper' to compare case-insensitively (counties, routing keys).
CREATE FUNCTION tile_param_list(params json, key text, fold text DEFAULT '') RETURNS text[]
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN v ~ '^[A-Za-z0-9_-]{1,80}(,[A-Za-z0-9_-]{1,80}){0,49}$'
                THEN string_to_array(v, ',') END
    FROM (SELECT CASE fold WHEN 'lower' THEN lower(params ->> key)
                           WHEN 'upper' THEN upper(params ->> key)
                           ELSE params ->> key END AS v) t
$$;

-- "lat,lng" inside Ireland's neighbourhood, or NULL.
CREATE FUNCTION tile_param_point(params json, key text) RETURNS geography
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN params ->> key ~ '^\d{2}(\.\d{1,7})?,-\d{1,2}(\.\d{1,7})?$'
                     AND split_part(params ->> key, ',', 1)::float8 BETWEEN 51 AND 56
                     AND split_part(params ->> key, ',', 2)::float8 BETWEEN -11 AND -5
                THEN ST_SetSRID(ST_MakePoint(split_part(params ->> key, ',', 2)::float8,
                                             split_part(params ->> key, ',', 1)::float8),
                                4326)::geography END
$$;

-- Routing key D08 is Dublin 8: PPR addresses without an Eircode carry the postal district.
CREATE FUNCTION routing_key_district(key text) RETURNS text
LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN key = 'D6W' THEN 'D6W'
                WHEN key ~ '^D\d{2}$' THEN 'D' || ltrim(substr(key, 2), '0') END
$$;
"""

MATCHING_SALES = r"""
CREATE OR REPLACE FUNCTION tile_matching_sales(env geometry, params json)
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
      AND (params ->> 'vat' IS DISTINCT FROM 'exclusive' OR s.vat_exclusive)
      AND (params ->> 'vat' IS DISTINCT FROM 'inclusive' OR NOT s.vat_exclusive)
      AND (tile_param_list(params, 'county', 'lower') IS NULL
           OR p.county::text = ANY(tile_param_list(params, 'county', 'lower')))
      AND (tile_param_list(params, 'area') IS NULL
           OR p.county::text = ANY(ARRAY(
                  SELECT a.code FROM area a
                  WHERE a.kind = 'county' AND a.slug = ANY(tile_param_list(params, 'area'))))
           OR ARRAY[p.small_area_id, p.ed_id, p.townland_id, p.settlement_id] && ARRAY(
                  SELECT a.id FROM area a
                  WHERE a.kind <> 'county' AND a.slug = ANY(tile_param_list(params, 'area'))))
      AND (tile_param_list(params, 'routingKey', 'upper') IS NULL
           OR p.eircode_routing_key = ANY(tile_param_list(params, 'routingKey', 'upper'))
           OR (p.eircode_routing_key IS NULL AND p.dublin_district = ANY(ARRAY(
                  SELECT routing_key_district(k)
                  FROM unnest(tile_param_list(params, 'routingKey', 'upper')) k))))
      AND (tile_param_point(params, 'near') IS NULL
           OR ST_DWithin(p.geom::geography, tile_param_point(params, 'near'),
                         least(coalesce(tile_param_number(params, 'radiusM'), 1000), 20000)))
      AND (tile_param_number(params, 'maxStopM') IS NULL OR EXISTS (
               SELECT 1 FROM property_enrichment e
               WHERE e.property_id = p.id
                 AND e.nearest_stop_m <= tile_param_number(params, 'maxStopM')))
      AND (tile_param_number(params, 'maxSchoolM') IS NULL OR EXISTS (
               SELECT 1 FROM property_enrichment e
               WHERE e.property_id = p.id
                 AND least(e.nearest_primary_school_m, e.nearest_post_primary_school_m)
                     <= tile_param_number(params, 'maxSchoolM')))
    ORDER BY s.property_id, s.sale_date DESC, s.id DESC
$$;
"""

# Migration 0004's version.
PREVIOUS_MATCHING_SALES = r"""
CREATE OR REPLACE FUNCTION tile_matching_sales(env geometry, params json)
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


def upgrade() -> None:
    # Merged Small Areas were slugged "sa-268003013/268003018": a slash cannot sit in one URL
    # path segment (/area/{slug}) or in a list parameter. The pipeline now writes a hyphen.
    op.execute(
        "UPDATE area SET slug = replace(slug, '/', '-') WHERE kind = 'small_area' AND slug ~ '/'"
    )
    op.execute(HELPERS)
    op.execute(MATCHING_SALES)


def downgrade() -> None:
    # The hyphenated Small Area slugs are kept: they are valid under every revision.
    op.execute(PREVIOUS_MATCHING_SALES)
    op.execute("DROP FUNCTION routing_key_district(text)")
    op.execute("DROP FUNCTION tile_param_point(json, text)")
    op.execute("DROP FUNCTION tile_param_list(json, text, text)")
