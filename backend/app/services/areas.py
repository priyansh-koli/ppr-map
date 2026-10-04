"""Reads for area pages (D-049): the area, its parents, precomputed statistics from
`area_stats`, and a price distribution counted from market sales. Nothing calls a third party."""

from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import rppi

# Display shapes are simplified further for the page, by kind (degrees).
SIMPLIFY = {
    "country": 0.01,
    "county": 0.002,
    "settlement": 0.0003,
    "electoral_division": 0.0005,
    "townland": 0.0002,
    "small_area": 0.0001,
}
# Kinds whose statistics exist only as quarters and years (D-037).
COARSE_KINDS = ("small_area", "townland")


def period_kinds(kind: str) -> list[str]:
    """The series an area of this kind has (possibly empty, where nothing sold)."""
    if kind in COARSE_KINDS:
        return ["quarter", "year"]
    return ["month", "quarter", "rolling_12m", "year"]


# Price bands for the distribution, in euro; the last is open-ended.
BIN_EDGES = [0, 100_000, 150_000, 200_000, 250_000, 300_000, 350_000, 400_000, 450_000,
             500_000, 600_000, 700_000, 800_000, 1_000_000, 1_500_000]  # fmt: skip

AREA = """
SELECT a.id, a.kind::text, a.name, a.name_ga, a.slug, a.code, a.source,
       ST_AsGeoJSON(ST_SimplifyPreserveTopology(a.geom, :tolerance), 5),
       ST_XMin(a.geom), ST_YMin(a.geom), ST_XMax(a.geom), ST_YMax(a.geom)
FROM area a WHERE a.slug = :slug
"""
KIND = "SELECT kind::text FROM area WHERE slug = :slug"

# Parents from the nearest up: a Small Area's ED, then its county.
PARENTS = """
WITH RECURSIVE up AS (
    SELECT p.id, p.kind, p.name, p.slug, p.parent_id, 1 AS depth
    FROM area a JOIN area p ON p.id = a.parent_id WHERE a.id = :id
    UNION ALL
    SELECT p.id, p.kind, p.name, p.slug, p.parent_id, up.depth + 1
    FROM up JOIN area p ON p.id = up.parent_id
)
SELECT kind::text, name, slug, id FROM up ORDER BY depth
"""
COUNTRY = "SELECT kind::text, name, slug, id FROM area WHERE kind = 'country' LIMIT 1"

POINT = """
SELECT period_start, n_sales, median_price, p25, p75, provisional, suppressed
FROM area_stats
WHERE area_id = :id AND period_kind = CAST(:kind AS period_kind) AND segment = 'all'
  AND period_start = :start
"""

SERIES = """
SELECT period_start, n_sales, median_price, p25, p75, provisional, suppressed
FROM area_stats
WHERE area_id = :id AND period_kind = CAST(:kind AS period_kind)
  AND segment = CAST(:segment AS segment)
ORDER BY period_start
"""


# ED attributes; a Small Area shows its ED's, labelled as such (D-011).
ATTRIBUTES = """
SELECT aa.key, aa.value, aa.value_text, aa.source, aa.as_of, aa.licence, a.kind::text, a.name
FROM area_attribute aa JOIN area a ON a.id = aa.area_id
WHERE aa.area_id = ANY(:ids)
ORDER BY array_position(:ids, aa.area_id), aa.source, aa.key
"""

CHILDREN = """
SELECT c.kind::text, c.name, c.slug, st.n_sales,
       CASE WHEN st.suppressed THEN NULL ELSE st.median_price END
FROM area c
JOIN area_stats st ON st.area_id = c.id AND st.segment = 'all'
     AND st.period_kind = CAST(:period_kind AS period_kind) AND st.period_start = :start
WHERE {where}
ORDER BY st.n_sales DESC, c.name
LIMIT :limit
"""
CHILD_FILTER = {
    "country": ("county", "c.kind = 'county'"),
    "county": ("settlement", "c.kind = 'settlement' AND c.parent_id = :id"),
    "electoral_division": ("small_area", "c.kind = 'small_area' AND c.parent_id = :id"),
}

# Which properties are in an area: counties by the county they were filed under; the rest by
# the join the geocoder made (Small Areas and EDs for exact and street points only, D-035).
MEMBERSHIP = {
    "country": "true",
    "county": "p.county::text = :code",
    "settlement": "p.settlement_id = :id",
    "electoral_division": "p.ed_id = :id",
    "small_area": "p.small_area_id = :id",
    "townland": "p.townland_id = :id",
}
DISTRIBUTION = """
SELECT width_bucket(s.price_eur, CAST(:edges AS numeric[])) AS bucket, count(*)
FROM sale s JOIN property p ON p.id = s.property_id
WHERE {member} AND NOT p.is_suppressed
  AND s.withdrawn_at IS NULL AND NOT s.not_full_market_price AND s.bulk_group_id IS NULL
  AND NOT s.is_possible_duplicate
  AND s.sale_date >= :start AND s.sale_date < :end
GROUP BY 1
"""


async def area(session: AsyncSession, slug: str) -> Any:
    kind = (await session.execute(sa.text(KIND), {"slug": slug})).scalar_one_or_none()
    if kind is None:
        return None
    params = {"slug": slug, "tolerance": SIMPLIFY.get(kind, 0.0005)}
    return (await session.execute(sa.text(AREA), params)).one()


async def parents(session: AsyncSession, area_id: int, kind: str) -> list[Any]:
    rows = list((await session.execute(sa.text(PARENTS), {"id": area_id})).all())
    if kind != "country":
        country = (await session.execute(sa.text(COUNTRY))).one_or_none()
        if country:
            rows.append(country)
    return rows


async def point(session: AsyncSession, area_id: int, kind: str, start: date) -> Any:
    params = {"id": area_id, "kind": kind, "start": start}
    return (await session.execute(sa.text(POINT), params)).one_or_none()


async def series(session: AsyncSession, area_id: int, kind: str, segment: str) -> list[Any]:
    params = {"id": area_id, "kind": kind, "segment": segment}
    return list((await session.execute(sa.text(SERIES), params)).all())


async def country_id(session: AsyncSession) -> int | None:
    found = await session.execute(sa.text("SELECT id FROM area WHERE kind = 'country' LIMIT 1"))
    return found.scalar_one_or_none()


async def attributes(session: AsyncSession, area_ids: list[int]) -> list[Any]:
    return list((await session.execute(sa.text(ATTRIBUTES), {"ids": area_ids})).all())


async def children(
    session: AsyncSession, area_id: int, kind: str, period_kind: str, start: date, limit: int
) -> tuple[str | None, list[Any]]:
    if kind not in CHILD_FILTER:
        return None, []
    child_kind, where = CHILD_FILTER[kind]
    # A child kind with coarse statistics only is ranked on the matching year.
    sql = CHILDREN.format(where=where)
    params = {"id": area_id, "period_kind": period_kind, "start": start, "limit": limit}
    return child_kind, list((await session.execute(sa.text(sql), params)).all())


async def distribution(
    session: AsyncSession, area_id: int, kind: str, code: str, start: date, end: date
) -> list[int]:
    """Market sales in [start, end) per price band, as counts (len(BIN_EDGES) bands)."""
    sql = DISTRIBUTION.format(member=MEMBERSHIP[kind])
    params = {"id": area_id, "code": code, "start": start, "end": end, "edges": BIN_EDGES}
    counts = [0] * len(BIN_EDGES)
    for bucket, n in (await session.execute(sa.text(sql), params)).all():
        counts[min(max(int(bucket), 1), len(BIN_EDGES)) - 1] += int(n)
    return counts


def suppress_bins(counts: list[int], min_n: int) -> list[int | None]:
    """Each band's count, or None where it is hidden. Bands under `min_n` sales are hidden;
    the total is published, so once one is, the hidden bands must not be recoverable by
    subtraction (P1 #14): empty bands are hidden with them (a shown 0 narrows the gap down),
    then the smallest shown bands, until the hidden ones hold at least `min_n` sales between
    at least two bands."""
    hidden = {i for i, c in enumerate(counts) if 0 < c < min_n}
    if not hidden:
        return list(counts)
    hidden |= {i for i, c in enumerate(counts) if c == 0}
    shown = sorted((c, i) for i, c in enumerate(counts) if i not in hidden)
    while shown and (sum(counts[i] for i in hidden) < min_n or len(hidden) < 2):
        hidden.add(shown.pop(0)[1])
    return [None if i in hidden else c for i, c in enumerate(counts)]


INDEX_CHANGE = """
SELECT now.period, now.value / before.value - 1
FROM benchmark_series now
JOIN benchmark_series before ON before.source = now.source
     AND before.series_key = now.series_key
     AND before.period = (now.period - interval '12 months')::date
WHERE now.source = :source AND now.series_key = :key
ORDER BY now.period DESC LIMIT 1
"""


async def index_change(session: AsyncSession, key: str) -> Any:
    params = {"source": rppi.SOURCE, "key": key}
    return (await session.execute(sa.text(INDEX_CHANGE), params)).one_or_none()


async def index_version(session: AsyncSession) -> str:
    """The latest load of the CSO index, so cached area pages follow a reload."""
    sql = "SELECT max(id) FROM ingest_run WHERE kind = 'benchmarks' AND status = 'succeeded'"
    return str((await session.execute(sa.text(sql))).scalar())
