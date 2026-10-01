"""Reads for the map, hover card and property page. The hover path reads one precomputed row
(or Redis); nothing here calls a third party (ARCHITECTURE.md goal 1)."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

META = """
SELECT r.stats ->> 'data_version', (r.stats ->> 'max_sale_date')::date,
       (r.stats ->> 'provisional_from')::date,
       (SELECT max(finished_at) FROM ingest_run WHERE kind = 'ppr' AND status = 'succeeded')
FROM ingest_run r
WHERE r.kind = 'aggregate' AND r.status = 'succeeded'
ORDER BY r.id DESC LIMIT 1
"""

SUMMARY = """
SELECT ps.payload FROM property_summary ps JOIN property p ON p.id = ps.property_id
WHERE p.public_id = :id AND NOT p.is_suppressed
"""

DETAIL = """
SELECT p.id, p.public_id, p.address_display, p.county::text, p.eircode_routing_key,
       p.dublin_district, ST_Y(p.geom), ST_X(p.geom), p.geocode_confidence::text,
       p.geocode_method, p.geocode_source, p.settlement_id, c.id AS county_area_id
FROM property p JOIN area c ON c.kind = 'county' AND c.code = p.county::text
WHERE p.public_id = :id AND NOT p.is_suppressed
"""

SALES = """
SELECT sale_date, price_eur, is_new, not_full_market_price, vat_exclusive, bulk_group_size,
       size_band::text, is_possible_duplicate
FROM sale WHERE property_id = :pid AND withdrawn_at IS NULL
ORDER BY sale_date DESC, id DESC
"""

AREAS = """
SELECT a.kind::text, a.name, a.slug FROM property p
JOIN area a ON a.id IN (p.small_area_id, p.ed_id, p.townland_id, p.settlement_id)
WHERE p.id = :pid
UNION ALL
SELECT a.kind::text, a.name, a.slug FROM area a WHERE a.id = :county_id
"""

# The most local area with enough sales for a 12-month median, over the last five years.
SERIES = """
SELECT st.period_start, st.n_sales, st.median_price, st.provisional, st.suppressed
FROM area_stats st
WHERE st.area_id = :area_id AND st.period_kind = 'rolling_12m' AND st.segment = 'all'
  AND st.period_start >= :since
ORDER BY st.period_start
"""

SERIES_AREA = """
SELECT a.id, a.kind::text, a.name, a.slug FROM area a
JOIN area_stats st ON st.area_id = a.id AND st.period_kind = 'rolling_12m'
     AND st.segment = 'all' AND NOT st.suppressed
WHERE a.id = ANY(:ids)
GROUP BY a.id ORDER BY array_position(:ids, a.id) LIMIT 1
"""


async def meta(session: AsyncSession) -> Any:
    return (await session.execute(sa.text(META))).one_or_none()


async def summary(session: AsyncSession, public_id: str) -> dict[str, Any] | None:
    row = (await session.execute(sa.text(SUMMARY), {"id": public_id})).one_or_none()
    return dict(row[0]) if row else None


async def detail(session: AsyncSession, public_id: str) -> Any:
    return (await session.execute(sa.text(DETAIL), {"id": public_id})).one_or_none()


async def sales(session: AsyncSession, property_id: int) -> list[Any]:
    return list((await session.execute(sa.text(SALES), {"pid": property_id})).all())


async def areas(session: AsyncSession, property_id: int, county_id: int) -> list[Any]:
    params = {"pid": property_id, "county_id": county_id}
    return list((await session.execute(sa.text(AREAS), params)).all())


async def series(session: AsyncSession, area_ids: list[int], since: Any) -> tuple[Any, list[Any]]:
    area = (await session.execute(sa.text(SERIES_AREA), {"ids": area_ids})).one_or_none()
    if area is None:
        return None, []
    rows = (await session.execute(sa.text(SERIES), {"area_id": area.id, "since": since})).all()
    return area, list(rows)


# Market sales near a precisely placed property (brief: "same street and within 500 m,
# last 24 months"). Distances only between exact and street points (D-035). Addresses that
# share a street or estate part are on the same street (address_street_parts, migration 0010).
COMPARABLES = """
WITH me AS MATERIALIZED (
    SELECT id, geom, address_street_parts(address_normalised) AS streets FROM property
    WHERE public_id = :id AND NOT is_suppressed AND geocode_confidence IN ('exact', 'street')
), nearby AS MATERIALIZED (
    SELECT DISTINCT ON (p.id) p.public_id, p.address_display, p.geocode_confidence::text AS conf,
           s.sale_date, s.price_eur, s.is_new, s.vat_exclusive,
           round(ST_Distance(p.geom::geography, me.geom::geography))::int AS distance_m,
           address_street_parts(p.address_normalised) && me.streets AS same_street
    FROM me, property p JOIN sale s ON s.property_id = p.id
    WHERE p.id <> me.id AND NOT p.is_suppressed
      AND p.geocode_confidence IN ('exact', 'street')
      AND p.geom && ST_Expand(me.geom, :deg)
      AND ST_DWithin(p.geom::geography, me.geom::geography, :radius)
      AND s.sale_date > :since
      AND s.withdrawn_at IS NULL AND NOT s.not_full_market_price
      AND s.bulk_group_id IS NULL AND NOT s.is_possible_duplicate
    ORDER BY p.id, s.sale_date DESC, s.id DESC
), summary AS MATERIALIZED (
    SELECT count(*) AS total,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY price_eur)
               FILTER (WHERE NOT vat_exclusive) AS median
    FROM nearby
)
SELECT n.*, summary.total, summary.median
FROM nearby n, summary
ORDER BY n.same_street DESC, n.distance_m, n.sale_date DESC
LIMIT :limit
"""


async def comparables(
    session: AsyncSession, public_id: str, radius_m: int, since: Any, limit: int
) -> list[Any]:
    params = {
        "id": public_id,
        "radius": radius_m,
        "deg": radius_m / 111_000 * 1.8,  # a degree of longitude is ~67 km at 53° N
        "since": since,
        "limit": limit,
    }
    return list((await session.execute(sa.text(COMPARABLES), params)).all())
