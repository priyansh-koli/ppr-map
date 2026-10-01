"""The CSO Residential Property Price Index (table HPM09) and the estimate's calibration
(D-020, D-053).

`load_rppi` replaces the index in `benchmark_series`. `calibrate` then measures how well the
index has predicted real repeat sales: for each pair of consecutive plain market sales of the
same precisely placed property, at least six months apart, the error is
ln(second price / (first price x index then / index at the first sale)). The 10th, 50th and
90th percentiles per series and band of years give the estimate's range.
"""

import csv
import io
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import httpx
import sqlalchemy as sa
from app.models.data import IngestRun
from app.models.enums import IngestKind, IngestStatus
from app.services import rppi

USER_AGENT = "ppr-map/0.1 (+https://github.com/priyansh-koli/ppr-map)"
INDEX_STATISTIC = "HPM09C01"  # the index itself (the others are percentage changes)
MIN_GAP_MONTHS = 6
Progress = Callable[[str], None]


def download(url: str, client: httpx.Client | None = None) -> bytes:
    with client or httpx.Client(timeout=60, headers={"User-Agent": USER_AGENT}) as c:
        res = c.get(url, follow_redirects=True)
        res.raise_for_status()
        return res.content


def parse_rppi(payload: bytes) -> list[tuple[str, date, float]]:
    """(series key, month, index) for every published month of every series."""
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    required = {"STATISTIC", "TLIST(M1)", "C02803V03373", "VALUE"}
    if not required <= set(reader.fieldnames or []):
        raise ValueError(f"HPM09 layout changed: expected columns {sorted(required)}")
    out = []
    for row in reader:
        if row["STATISTIC"] != INDEX_STATISTIC or not row["VALUE"].strip():
            continue
        code = row["C02803V03373"].strip()
        month = row["TLIST(M1)"].strip()
        key = rppi.series_key("00" if code == "-" else code)
        out.append((key, date(int(month[:4]), int(month[4:6]), 1), float(row["VALUE"])))
    if not out:
        raise ValueError("HPM09 held no index values")
    return out


REPLACE = """
DELETE FROM benchmark_series WHERE source = :source;
"""

# Consecutive plain market sales of one precisely placed property, and the index's error.
CALIBRATE = f"""
WITH plain AS (
    SELECT s.property_id, s.sale_date, s.price_eur,
           date_trunc('month', s.sale_date)::date AS m,
           {rppi.SERIES_SQL.format(unit="p.unit", county="p.county::text")} AS series_key
    FROM sale s JOIN property p ON p.id = s.property_id
    WHERE s.withdrawn_at IS NULL AND NOT s.not_full_market_price AND NOT s.vat_exclusive
      AND s.bulk_group_id IS NULL AND NOT s.is_possible_duplicate AND s.price_eur >= 10000
      AND p.geocode_confidence IN ('exact', 'street') AND NOT p.is_suppressed
), pairs AS (
    SELECT series_key, lag(m) OVER w AS m1, lag(price_eur) OVER w AS p1, m AS m2, price_eur AS p2
    FROM plain WINDOW w AS (PARTITION BY property_id ORDER BY sale_date)
), err AS (
    SELECT pr.series_key,
           CASE WHEN (pr.m2 - pr.m1) < 3 * 365.25 THEN '0-3y'
                WHEN (pr.m2 - pr.m1) < 7 * 365.25 THEN '3-7y' ELSE '7y+' END AS gap_band,
           ln(pr.p2 / (pr.p1 * b2.value / b1.value)) AS e
    FROM pairs pr
    JOIN benchmark_series b1 ON b1.source = :source AND b1.series_key = pr.series_key
         AND b1.period = pr.m1
    JOIN benchmark_series b2 ON b2.source = :source AND b2.series_key = pr.series_key
         AND b2.period = pr.m2
    WHERE pr.m1 IS NOT NULL AND pr.m2 >= pr.m1 + make_interval(months => :gap)
), grouped AS (
    SELECT series_key, gap_band, e FROM err
    UNION ALL
    SELECT 'all', gap_band, e FROM err
)
INSERT INTO estimate_calibration (series_key, gap_band, n, p10, p50, p90)
SELECT series_key, gap_band, count(*),
       percentile_cont(0.1) WITHIN GROUP (ORDER BY e),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY e),
       percentile_cont(0.9) WITHIN GROUP (ORDER BY e)
FROM grouped GROUP BY series_key, gap_band
"""  # noqa: S608 - the only formatted fragment is the constant rppi.SERIES_SQL


def calibrate(conn: sa.Connection) -> int:
    conn.execute(sa.text("TRUNCATE estimate_calibration"))
    conn.execute(sa.text(CALIBRATE), {"source": rppi.SOURCE, "gap": MIN_GAP_MONTHS})
    return int(
        conn.execute(
            sa.text("SELECT sum(n) FROM estimate_calibration WHERE series_key = 'all'")
        ).scalar()
        or 0
    )


def load_rppi(
    engine: sa.Engine,
    payload: bytes,
    url: str,
    progress: Progress = lambda _: None,
) -> dict[str, Any]:
    """Replace the RPPI and recompute the calibration, recorded as a `benchmarks` run."""
    started = time.monotonic()
    with engine.begin() as conn:
        run_id: int = conn.execute(
            sa.insert(IngestRun)
            .values(kind=IngestKind.BENCHMARKS, status=IngestStatus.RUNNING, source_url=url)
            .returning(IngestRun.id)
        ).scalar_one()
    try:
        rows = parse_rppi(payload)
        with engine.begin() as conn:
            conn.execute(sa.text(REPLACE), {"source": rppi.SOURCE})
            today = date.today()
            conn.execute(
                sa.text(
                    "INSERT INTO benchmark_series (source, series_key, period, value, unit, as_of) "
                    "VALUES (:source, :key, :period, :value, 'index, 2015 = 100', :as_of)"
                ),
                [
                    {"source": rppi.SOURCE, "key": k, "period": p, "value": v, "as_of": today}
                    for k, p, v in rows
                ],
            )
            progress(f"  RPPI: {len(rows):,} values")
            pairs = calibrate(conn)
            progress(f"  calibration: {pairs:,} repeat-sale pairs")
        stats = {
            "values": len(rows),
            "series": len({k for k, _, _ in rows}),
            "first_month": min(p for _, p, _ in rows).isoformat(),
            "last_month": max(p for _, p, _ in rows).isoformat(),
            "calibration_pairs": pairs,
            "seconds": round(time.monotonic() - started, 1),
        }
        with engine.begin() as conn:
            conn.execute(
                sa.update(IngestRun)
                .where(IngestRun.id == run_id)
                .values(
                    status=IngestStatus.SUCCEEDED,
                    finished_at=datetime.now(UTC),
                    rows_read=len(rows),
                    rows_inserted=len(rows),
                    stats=stats,
                )
            )
    except BaseException as exc:
        with engine.begin() as conn:
            conn.execute(
                sa.update(IngestRun)
                .where(IngestRun.id == run_id)
                .values(
                    status=IngestStatus.FAILED,
                    finished_at=datetime.now(UTC),
                    stats={"error": repr(exc)},
                )
            )
        raise
    return {"run_id": run_id, **stats}
