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
