"""matching sales: leave out repeat filings, as the area statistics do (P1 #18)

The register holds 1,193 sales filed twice (the same date, address and price). The ingest
flags every repeat as `is_possible_duplicate` and the area statistics leave them out, but
`tile_matching_sales` did not, so the map, the list, search and alerts counted them and
their totals did not match the area pages. The repeats are now left out of the matches and
of `n_sales`; the first filing of each still counts. The property page still lists both,
marked as a possible repeat.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-04 21:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Migration 0012's filters with the repeats left out.
FILTERS = r"""
    WHERE p.geom && env AND NOT p.is_suppressed
      AND p.geocode_confidence <= tile_param_confidence(params)
      AND s.withdrawn_at IS NULL AND NOT s.is_possible_duplicate
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
"""

PREVIOUS_FILTERS = r"""
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
"""

SIGNATURE = r"""
CREATE OR REPLACE FUNCTION tile_matching_sales(env geometry, params json)
RETURNS TABLE (
    property_id bigint, public_id text, geom geometry, confidence geocode_confidence,
    sale_date date, price_eur numeric, is_new boolean, nfmp boolean, vatx boolean,
    bulk boolean, n_sales bigint
)
LANGUAGE sql STABLE PARALLEL SAFE AS $$
"""


def _matching_sales(filters: str, n_sales_where: str) -> str:
    return (
        SIGNATURE
        + r"""
    SELECT m.property_id, m.public_id, m.geom, m.confidence, m.sale_date, m.price_eur,
           m.is_new, m.nfmp, m.vatx, m.bulk,
           (SELECT count(*) FROM sale a
            WHERE a.property_id = m.property_id AND """
        + n_sales_where
        + r""")
    FROM (
    SELECT DISTINCT ON (s.property_id)
           p.id AS property_id, p.public_id, p.geom, p.geocode_confidence AS confidence,
           s.sale_date, s.price_eur, s.is_new, s.not_full_market_price AS nfmp,
           s.vat_exclusive AS vatx, s.bulk_group_id IS NOT NULL AS bulk
    FROM property p JOIN sale s ON s.property_id = p.id
"""
        + filters
        + r"""
    ORDER BY s.property_id, s.sale_date DESC, s.id DESC
    ) m
$$;
"""
    )


def upgrade() -> None:
    op.execute(
        _matching_sales(FILTERS, "a.withdrawn_at IS NULL AND NOT a.is_possible_duplicate")
    )


def downgrade() -> None:
    op.execute(_matching_sales(PREVIOUS_FILTERS, "a.withdrawn_at IS NULL"))
