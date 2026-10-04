"""matching sales: count every sale on record, not only the matching ones

`n_sales` was a window count over the rows that passed the filters, so with a date or price
filter a property with four sales could report one. The list then read "1 sale", the CSV
said 1, and the previous-sale lookup (gated on `n_sales > 1`) never ran, so sorting by the
biggest rise under a date filter was all nulls. The count is now every sale on the property
that has not been withdrawn, as the hover card and property page list them. It is taken
after `DISTINCT ON`, once per property, and callers that do not read it never compute it.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-04 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The filters are migration 0008's, unchanged.
FILTERS = r"""
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

MATCHING_SALES = (
    SIGNATURE
    + r"""
    SELECT m.property_id, m.public_id, m.geom, m.confidence, m.sale_date, m.price_eur,
           m.is_new, m.nfmp, m.vatx, m.bulk,
           (SELECT count(*) FROM sale a
            WHERE a.property_id = m.property_id AND a.withdrawn_at IS NULL)
    FROM (
    SELECT DISTINCT ON (s.property_id)
           p.id AS property_id, p.public_id, p.geom, p.geocode_confidence AS confidence,
           s.sale_date, s.price_eur, s.is_new, s.not_full_market_price AS nfmp,
           s.vat_exclusive AS vatx, s.bulk_group_id IS NOT NULL AS bulk
    FROM property p JOIN sale s ON s.property_id = p.id
"""
    + FILTERS
    + r"""
    ORDER BY s.property_id, s.sale_date DESC, s.id DESC
    ) m
$$;
"""
)

# Migration 0008's version.
PREVIOUS_MATCHING_SALES = (
    SIGNATURE
    + r"""
    SELECT DISTINCT ON (s.property_id)
           p.id, p.public_id, p.geom, p.geocode_confidence, s.sale_date, s.price_eur,
           s.is_new, s.not_full_market_price, s.vat_exclusive, s.bulk_group_id IS NOT NULL,
           count(*) OVER (PARTITION BY s.property_id)
    FROM property p JOIN sale s ON s.property_id = p.id
"""
    + FILTERS
    + r"""
    ORDER BY s.property_id, s.sale_date DESC, s.id DESC
$$;
"""
)


def upgrade() -> None:
    op.execute(MATCHING_SALES)


def downgrade() -> None:
    op.execute(PREVIOUS_MATCHING_SALES)
