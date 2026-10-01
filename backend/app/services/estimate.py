"""The index-based price estimate (D-020, D-053): what the CSO's price index implies a
home's last market sale would fetch now, with the range that repeat sales in its region
actually landed in. Everything is read from our own tables; nothing calls a third party."""

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import rppi

MIN_MONTHS = 6
MIN_PAIRS = 150  # below this, a series' own calibration is too thin: the pooled one is used
ROUND_TO = 1000

PROPERTY = """
SELECT p.id, p.county::text, p.unit, p.geocode_confidence::text
FROM property p WHERE p.public_id = :id AND NOT p.is_suppressed
"""
# The latest sale that is a plain market sale (as for price changes, D-043).
LAST_PLAIN = """
SELECT s.sale_date, s.price_eur FROM sale s
WHERE s.property_id = :pid AND s.withdrawn_at IS NULL AND NOT s.not_full_market_price
  AND NOT s.vat_exclusive AND s.bulk_group_id IS NULL AND NOT s.is_possible_duplicate
ORDER BY s.sale_date DESC, s.id DESC LIMIT 1
"""
INDEX = """
SELECT period, value FROM benchmark_series
WHERE source = :source AND series_key = :key AND (period = :sold OR period = (
    SELECT max(period) FROM benchmark_series WHERE source = :source AND series_key = :key))
ORDER BY period
"""
FIRST_MONTH = """
SELECT min(period) FROM benchmark_series WHERE source = :source AND series_key = :key
"""
CALIBRATION = """
SELECT series_key, n, p10, p50, p90 FROM estimate_calibration
WHERE gap_band = :band AND series_key IN (:key, 'all')
"""

REASONS = {
    "location": "Estimates are given only for homes placed at their house or street: a town-level "
    "location could be any home there.",
    "no_market_sale": "No sale of this home can be used: estimates start from a sale at full "
    "market price, not part of a bulk sale, and with its VAT included.",
    "recent": "It sold in the last six months, so that sale is the best guide to its price.",
    "before_index": "Its last market sale is older than the regional price index.",
    "no_index": "The price index is not loaded yet.",
}


@dataclass(frozen=True)
class Estimate:
    low: Decimal
    mid: Decimal
    high: Decimal
    sold_on: date
    sold_for: Decimal
    series: str
    index_month: date
    index_then: Decimal
    index_now: Decimal
    band: str
    pairs: int
    pooled: bool
    p10: float
    p50: float
    p90: float


def _round(v: float) -> Decimal:
    return Decimal(round(v / ROUND_TO) * ROUND_TO)


def _months(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


async def estimate(session: AsyncSession, public_id: str) -> tuple[Estimate | None, str | None]:
    """(estimate, None) or (None, reason key); (None, None) if there is no such property."""
    prop = (await session.execute(sa.text(PROPERTY), {"id": public_id})).one_or_none()
    if prop is None:
        return None, None
    pid, county, unit, confidence = prop
    if confidence not in ("exact", "street"):
        return None, "location"
    sale = (await session.execute(sa.text(LAST_PLAIN), {"pid": pid})).one_or_none()
    if sale is None:
        return None, "no_market_sale"
    sold_on, sold_for = sale
    code = rppi.series_code(county, unit is not None)
    key = rppi.series_key(code)
    sold_month = sold_on.replace(day=1)
    params: dict[str, Any] = {"source": rppi.SOURCE, "key": key, "sold": sold_month}
    first = (await session.execute(sa.text(FIRST_MONTH), params)).scalar_one_or_none()
    if first is None:
        return None, "no_index"
    if sold_month < first:
        return None, "before_index"
    points = {r[0]: r[1] for r in (await session.execute(sa.text(INDEX), params)).all()}
    latest = max(points)
    if _months(sold_month, latest) < MIN_MONTHS:
        return None, "recent"
    if sold_month not in points:  # the CSO left that month blank
        return None, "no_index"
    then, now = points[sold_month], points[latest]
    band = rppi.gap_band(_months(sold_month, latest) / 12)
    calibration = {
        r[0]: r for r in (await session.execute(sa.text(CALIBRATION), {"band": band, "key": key}))
    }
    own = calibration.get(key)
    chosen = own if own is not None and own[1] >= MIN_PAIRS else calibration.get("all")
    if chosen is None:
        return None, "no_index"
    mid = float(sold_for) * float(now) / float(then)
    p10, p50, p90 = float(chosen[2]), float(chosen[3]), float(chosen[4])
    return (
        Estimate(
            low=_round(mid * math.exp(p10)),
            mid=_round(mid),
            high=_round(mid * math.exp(p90)),
            sold_on=sold_on,
            sold_for=sold_for,
            series=code,
            index_month=latest,
            index_then=then,
            index_now=now,
            band=band,
            pairs=int(chosen[1]),
            pooled=chosen[0] == "all",
            p10=p10,
            p50=p50,
            p90=p90,
        ),
        None,
    )
