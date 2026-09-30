"""Aggregates rebuilt after each ingest or geocode run (docs/ARCHITECTURE.md, Data flow step 9).

- `area_stats`: price statistics per area and period, from market sales only (not "not full
  market price", not in a bulk group, not a possible duplicate filing, not withdrawn).
- `price_hex`: median price per H3 cell (r8, and its r7 and r6 parents) over the last 12
  and 36 months, from exact and street points only.
- `property_summary`: the hover-card payload, one JSON row per property.

Groups with fewer than 5 sales keep their count but no prices (suppressed). Periods that
overlap the latest two months of the register are marked provisional.
"""

import time
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Any

import h3
import sqlalchemy as sa
from app.models.data import IngestRun
from app.models.enums import IngestKind, IngestStatus

MIN_N = 5
HEX_RESOLUTIONS = (6, 7, 8)
Progress = Callable[[str], None]

# Ireland as one area, so national figures are real medians rather than sums of counties.
# Its shape is the counties' display shapes merged; it holds no point-in-polygon parts.
ENSURE_COUNTRY = """
INSERT INTO area (kind, code, name, name_ga, geom, source, source_version, slug)
SELECT 'country', 'IE', 'Ireland', 'Éire', ST_Multi(ST_Union(geom)),
       'Tailte Éireann counties, merged', max(source_version), 'ireland'
FROM area WHERE kind = 'county'
HAVING count(*) > 0
ON CONFLICT (kind, code) DO NOTHING
"""

# Market sales, with the areas each one may count towards. Small Areas and EDs only for
# points precise enough to be in them (the geocoder leaves those ids empty otherwise).
CREATE_MARKET = """
CREATE TEMP TABLE market ON COMMIT DROP AS
SELECT s.id, s.property_id, s.sale_date, s.price_eur, s.is_new,
       date_trunc('month', s.sale_date)::date AS month,
       c.id AS county_id, p.settlement_id, p.ed_id, p.small_area_id, p.townland_id, p.h3_r8,
       ie.id AS country_id
FROM sale s
JOIN property p ON p.id = s.property_id
JOIN area c ON c.kind = 'county' AND c.code = p.county::text
JOIN area ie ON ie.kind = 'country' AND ie.code = 'IE'
WHERE s.withdrawn_at IS NULL AND NOT s.not_full_market_price AND s.bulk_group_id IS NULL
  AND NOT s.is_possible_duplicate AND NOT p.is_suppressed
"""

# One row per (sale, area, segment): every sale counts in "all" and in new or second-hand.
CREATE_SALE_AREA = """
CREATE TEMP TABLE sale_area ON COMMIT DROP AS
SELECT m.sale_date, m.month, m.price_eur, a.area_id, a.detail, seg.segment
FROM market m
CROSS JOIN LATERAL (VALUES
    (m.country_id, true), (m.county_id, true), (m.settlement_id, true), (m.ed_id, true),
    (m.small_area_id, false), (m.townland_id, false)
) AS a(area_id, detail)
CROSS JOIN LATERAL (VALUES
    ('all'::segment), (CASE WHEN m.is_new THEN 'new'::segment ELSE 'second_hand'::segment END)
) AS seg(segment)
WHERE a.area_id IS NOT NULL
"""

STATS_COLUMNS = """
    count(*) AS n,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY price_eur) AS median,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY price_eur) AS p25,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY price_eur) AS p75,
    avg(price_eur) AS mean
"""

# Periods that end on or after :provisional_from are provisional.
INSERT_STATS = """
INSERT INTO area_stats (area_id, period_kind, period_start, segment, n_sales, median_price,
                        p25, p75, mean_price, provisional, suppressed)
SELECT area_id, CAST(:kind AS period_kind), period_start, segment, n,
       CASE WHEN n >= :min_n THEN round(median::numeric, 2) END,
       CASE WHEN n >= :min_n THEN round(p25::numeric, 2) END,
       CASE WHEN n >= :min_n THEN round(p75::numeric, 2) END,
       CASE WHEN n >= :min_n THEN round(mean::numeric, 2) END,
       (period_start + CAST(:span AS interval) - interval '1 day')::date >= :provisional_from,
       n < :min_n
FROM (
    SELECT area_id, {start} AS period_start, segment, {stats}
    FROM {source}
    GROUP BY area_id, {start}, segment
) g
"""

# Every sale counts in the 12 monthly windows that end in its month and the 11 after.
CREATE_ROLLING = """
CREATE TEMP TABLE sale_rolling ON COMMIT DROP AS
SELECT (sa.month + make_interval(months => k))::date AS month, sa.price_eur, sa.area_id,
       sa.segment
FROM sale_area sa CROSS JOIN generate_series(0, 11) AS k
WHERE sa.detail AND (sa.month + make_interval(months => k))::date <= :last_month
"""

PERIODS: dict[str, tuple[str, str, str]] = {
    # kind: (period_start, length, source table). A rolling window is labelled by its
    # last month, so it ends where that month ends.
    "month": ("month", "1 month", "sale_area WHERE detail"),
    "quarter": ("date_trunc('quarter', month)::date", "3 months", "sale_area"),
    "year": ("date_trunc('year', month)::date", "1 year", "sale_area"),
    "rolling_12m": ("month", "1 month", "sale_rolling"),
}


def register_dates(conn: sa.Connection, aggregate_run: int) -> tuple[date, date, str]:
    """(latest sale date, first provisional day, data version).

    The version names the register (latest sale, PPR ingest run) and this aggregate run, so
    re-geocoding or re-aggregating the same register also gets new tile URLs and hover-card
    cache keys: "2026-09-18.r1.a18"."""
    max_date: date | None = conn.execute(
        sa.text("SELECT max(sale_date) FROM sale WHERE withdrawn_at IS NULL")
    ).scalar_one()
    if max_date is None:
        raise RuntimeError("no sales loaded: run `ppr ingest ppr` first")
    run_id = conn.execute(
        sa.select(sa.func.max(IngestRun.id)).where(
            IngestRun.kind == IngestKind.PPR, IngestRun.status == IngestStatus.SUCCEEDED
        )
    ).scalar_one()
    # The latest two months are provisional: late filings still arrive for them.
    month = max_date.replace(day=1)
    provisional_from = (
        date(month.year - 1, 12, 1) if month.month == 1 else date(month.year, month.month - 1, 1)
    )
    return max_date, provisional_from, f"{max_date.isoformat()}.r{run_id}.a{aggregate_run}"


def area_stats(conn: sa.Connection, provisional_from: date, last_month: date) -> int:
    conn.execute(sa.text(ENSURE_COUNTRY))
    conn.execute(sa.text(CREATE_MARKET))
    conn.execute(sa.text(CREATE_SALE_AREA))
    conn.execute(sa.text(CREATE_ROLLING), {"last_month": last_month})
    conn.execute(sa.text("TRUNCATE area_stats"))
    for kind, (start, span, source) in PERIODS.items():
        # Only constant SQL fragments from PERIODS are formatted in; values are bound.
        sql = INSERT_STATS.format(start=start, source=source, stats=STATS_COLUMNS)
        conn.execute(
            sa.text(sql),
            {"kind": kind, "span": span, "min_n": MIN_N, "provisional_from": provisional_from},
        )
    return int(conn.execute(sa.text("SELECT count(*) FROM area_stats")).scalar_one())


# --- price hexes ---------------------------------------------------------------------------

HEX_SALES = """
SELECT h3_r8, price_eur, is_new, sale_date FROM market
WHERE h3_r8 IS NOT NULL AND sale_date > :since
"""

INSERT_HEX = """
INSERT INTO price_hex (h3, "window", segment, resolution, n, median_price, suppressed, geom)
SELECT h.h3, CAST(:window AS hex_window), h.segment, h.resolution, h.n,
       CASE WHEN h.n >= :min_n THEN round(h.median::numeric, 2) END, h.n < :min_n,
       ST_Multi(ST_GeomFromText(g.wkt, 4326))
FROM (
    SELECT h3, resolution, segment, count(*) AS n,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY price_eur) AS median
    FROM hex_sale WHERE sale_date > :since
    GROUP BY 1, 2, 3
) h JOIN hex_geom g ON g.h3 = h.h3
"""


def _hex_wkt(cell: int) -> str:
    ring = [(lng, lat) for lat, lng in h3.cell_to_boundary(format(cell, "x"))]
    ring.append(ring[0])
    return "POLYGON((" + ", ".join(f"{x:.7f} {y:.7f}" for x, y in ring) + "))"


def _copy(conn: sa.Connection, table: str, columns: str, rows: Iterator[tuple[Any, ...]]) -> None:
    raw = conn.connection.driver_connection
    assert raw is not None
    with raw.cursor() as cur, cur.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def price_hexes(conn: sa.Connection, max_date: date) -> int:
    since_36 = date(max_date.year - 3, max_date.month, 1)
    since_12 = date(max_date.year - 1, max_date.month, 1)
    sales = conn.execute(sa.text(HEX_SALES), {"since": since_36}).all()
    conn.execute(
        sa.text(
            "CREATE TEMP TABLE hex_sale (h3 bigint, resolution smallint, segment segment, "
            "price_eur numeric, sale_date date) ON COMMIT DROP"
        )
    )
    cells: set[int] = set()

    def rows() -> Iterator[tuple[Any, ...]]:
        for r8, price, is_new, sale_date in sales:
            cell = format(r8, "x")
            for res in HEX_RESOLUTIONS:
                c = int(h3.cell_to_parent(cell, res), 16) if res < 8 else r8
                cells.add(c)
                yield c, res, "all", price, sale_date
                yield c, res, "new" if is_new else "second_hand", price, sale_date

    _copy(conn, "hex_sale", "h3, resolution, segment, price_eur, sale_date", rows())
    conn.execute(sa.text("CREATE TEMP TABLE hex_geom (h3 bigint, wkt text) ON COMMIT DROP"))
    _copy(conn, "hex_geom", "h3, wkt", ((c, _hex_wkt(c)) for c in cells))
    conn.execute(sa.text("TRUNCATE price_hex"))
    for window, since in (("rolling_12m", since_12), ("rolling_36m", since_36)):
        conn.execute(sa.text(INSERT_HEX), {"window": window, "since": since, "min_n": MIN_N})
    return int(conn.execute(sa.text("SELECT count(*) FROM price_hex")).scalar_one())


# --- hover summaries -----------------------------------------------------------------------

# The area line uses the most local area with unsuppressed 12-month stats: the settlement
# (exact, street and locality points), else the county. Vicinity values exist only for exact
# and street points (enrich/vicinity.py).
SUMMARIES = """
INSERT INTO property_summary (property_id, payload, data_version, computed_at)
SELECT p.id, jsonb_strip_nulls(jsonb_build_object(
    'id', p.public_id,
    'address', p.address_display,
    'confidence', p.geocode_confidence,
    'latestSale', (
        SELECT jsonb_build_object(
            'date', s.sale_date, 'priceEur', s.price_eur, 'isNew', s.is_new,
            'flags', jsonb_build_object(
                'notFullMarketPrice', s.not_full_market_price,
                'vatExclusive', s.vat_exclusive,
                'bulk', s.bulk_group_id IS NOT NULL))
        FROM sale s WHERE s.property_id = p.id AND s.withdrawn_at IS NULL
        ORDER BY s.sale_date DESC, s.id DESC LIMIT 1),
    'previousSales', (
        SELECT coalesce(jsonb_agg(jsonb_build_object('date', x.sale_date, 'priceEur', x.price_eur)
                                  ORDER BY x.sale_date DESC), '[]'::jsonb)
        FROM (SELECT s.sale_date, s.price_eur FROM sale s
              WHERE s.property_id = p.id AND s.withdrawn_at IS NULL
              ORDER BY s.sale_date DESC, s.id DESC OFFSET 1) x),
    'area', (
        SELECT jsonb_build_object(
            'name', a.name, 'kind', a.kind, 'median12m', st.median_price, 'n', st.n_sales,
            'change12mPct', CASE WHEN prev.median_price > 0 THEN
                round((st.median_price / prev.median_price - 1) * 100, 1) END,
            'provisional', st.provisional)
        FROM (VALUES (1, p.settlement_id), (2, c.id)) AS o(rank, area_id)
        JOIN area_stats st ON st.area_id = o.area_id AND st.period_kind = 'rolling_12m'
             AND st.segment = 'all' AND st.period_start = :last_month AND NOT st.suppressed
        JOIN area a ON a.id = o.area_id
        LEFT JOIN area_stats prev ON prev.area_id = st.area_id
             AND prev.period_kind = 'rolling_12m' AND prev.segment = 'all'
             AND prev.period_start = :year_before AND NOT prev.suppressed
        ORDER BY o.rank LIMIT 1),
    'vicinity', jsonb_build_object(
        'nearestStop', CASE WHEN stop.id IS NOT NULL THEN jsonb_build_object(
            'value', jsonb_build_object('name', stop.name, 'type', stop.type,
                                        'distanceM', e.nearest_stop_m),
            'source', e.provenance #>> '{transport,source}',
            'asOf', e.provenance #>> '{transport,asOf}') END,
        'nearestPrimarySchool', CASE WHEN ps.id IS NOT NULL THEN jsonb_build_object(
            'value', jsonb_build_object('name', ps.name, 'distanceM', e.nearest_primary_school_m),
            'source', e.provenance #>> '{schools,source}',
            'asOf', e.provenance #>> '{schools,asOf}') END,
        'nearestPostPrimarySchool', CASE WHEN pp.id IS NOT NULL THEN jsonb_build_object(
            'value', jsonb_build_object('name', pp.name,
                                        'distanceM', e.nearest_post_primary_school_m),
            'source', e.provenance #>> '{schools,source}',
            'asOf', e.provenance #>> '{schools,asOf}') END,
        'shopsWithin1km', CASE WHEN e.property_id IS NOT NULL THEN jsonb_build_object(
            'value', coalesce((e.amenities_1km ->> 'shop')::int, 0)
                     + coalesce((e.amenities_1km ->> 'supermarket')::int, 0),
            'source', e.provenance #>> '{amenities,source}',
            'asOf', e.provenance #>> '{amenities,asOf}') END,
        'deprivation', CASE WHEN e.deprivation_band IS NOT NULL THEN jsonb_build_object(
            'value', e.deprivation_band,
            'source', e.provenance #>> '{deprivation,source}',
            'asOf', e.provenance #>> '{deprivation,asOf}') END,
        'distances', CASE WHEN e.property_id IS NOT NULL THEN 'straight line' END,
        -- D-010: no flood value until the OPW licence allows one; always the official link.
        'flood', jsonb_build_object('note', 'Check the OPW flood maps',
                                    'link', 'https://www.floodinfo.ie/map/floodmaps/')),
    'dataVersion', CAST(:data_version AS text)
)), :data_version, now()
FROM property p
JOIN area c ON c.kind = 'county' AND c.code = p.county::text
LEFT JOIN property_enrichment e ON e.property_id = p.id
LEFT JOIN poi stop ON stop.id = e.nearest_stop_id
LEFT JOIN poi ps ON ps.id = e.nearest_primary_school_id
LEFT JOIN poi pp ON pp.id = e.nearest_post_primary_school_id
WHERE NOT p.is_suppressed AND p.id >= :lo AND p.id < :hi
"""

SUMMARY_BATCH = 50_000


def summaries(engine: sa.Engine, last_month: date, data_version: str, progress: Progress) -> int:
    year_before = date(last_month.year - 1, last_month.month, 1)
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE property_summary"))
        lo, hi = conn.execute(sa.text("SELECT min(id), max(id) FROM property")).one()
    if lo is None:
        return 0
    done = 0
    params = {"last_month": last_month, "year_before": year_before, "data_version": data_version}
    for start in range(lo, hi + 1, SUMMARY_BATCH):
        with engine.begin() as conn:
            done += conn.execute(
                sa.text(SUMMARIES), {**params, "lo": start, "hi": start + SUMMARY_BATCH}
            ).rowcount
        progress(f"  summaries: {done:,}")
    return done


def aggregate(engine: sa.Engine, progress: Progress = lambda _: None) -> dict[str, Any]:
    """Rebuild all three tables and record an `ingest_run` of kind `aggregate`."""
    with engine.begin() as conn:
        run_id: int = conn.execute(
            sa.insert(IngestRun)
            .values(kind=IngestKind.AGGREGATE, status=IngestStatus.RUNNING)
            .returning(IngestRun.id)
        ).scalar_one()
    started = time.monotonic()
    try:
        with engine.begin() as conn:
            max_date, provisional_from, data_version = register_dates(conn, run_id)
            last_month = max_date.replace(day=1)
            progress("  area stats")
            n_stats = area_stats(conn, provisional_from, last_month)
            progress("  price hexes")
            n_hex = price_hexes(conn, max_date)
        n_summaries = summaries(engine, last_month, data_version, progress)
        stats: dict[str, Any] = {
            "data_version": data_version,
            "max_sale_date": max_date.isoformat(),
            "provisional_from": provisional_from.isoformat(),
            "area_stats": n_stats,
            "price_hex": n_hex,
            "summaries": n_summaries,
            "seconds": round(time.monotonic() - started, 1),
        }
        with engine.begin() as conn:
            _finish(conn, run_id, status=IngestStatus.SUCCEEDED, rows_read=n_summaries, stats=stats)
    except BaseException as exc:
        with engine.begin() as conn:
            _finish(conn, run_id, status=IngestStatus.FAILED, stats={"error": repr(exc)})
        raise
    return {"run_id": run_id, **stats}


def _finish(conn: sa.Connection, run_id: int, **values: Any) -> None:
    conn.execute(
        sa.update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(finished_at=datetime.now(UTC), **values)
    )
