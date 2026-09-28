"""The home page's national overview (D-043). It reads only what the monthly pipeline
precomputed, and is held in memory per data version, so it costs one query set a month."""

import time
from datetime import date
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.properties import _meta
from app.db import get_session
from app.schemas.stats import CountyStat, MonthCount, Overview

router = APIRouter(tags=["stats"])
Session = Annotated[AsyncSession, Depends(get_session)]
TTL_S = 3600.0
MONTHS = 24

# Counties partition the country, so their monthly counts add up to the national one.
MONTHLY = """
SELECT s.period_start, sum(s.n_sales)::int, bool_or(s.provisional)
FROM area_stats s JOIN area a ON a.id = s.area_id
WHERE a.kind = 'county' AND s.period_kind = 'month' AND s.segment = 'all'
  AND s.period_start >= :since
GROUP BY s.period_start ORDER BY s.period_start
"""
COUNTIES = """
SELECT a.slug, a.name, s.n_sales, CASE WHEN s.suppressed THEN NULL ELSE s.median_price END,
       ST_Y(ST_PointOnSurface(a.geom)), ST_X(ST_PointOnSurface(a.geom))
FROM area a
JOIN area_stats s ON s.area_id = a.id AND s.period_kind = 'rolling_12m'
  AND s.segment = 'all' AND s.period_start = :window_end
WHERE a.kind = 'county'
ORDER BY s.n_sales DESC, a.name
"""
TOTALS = """
SELECT count(*), min(sale_date), (SELECT count(*) FROM property WHERE NOT is_suppressed)
FROM sale WHERE withdrawn_at IS NULL
"""


def _add_months(month: date, n: int) -> date:
    index = month.year * 12 + month.month - 1 + n
    return date(index // 12, index % 12 + 1, 1)


class _Shared:
    overview: tuple[float, Overview] | None = None


@router.get("/stats/overview", response_model=Overview)
async def overview(session: Session) -> Overview:
    """Sales per month nationally, and each county's latest complete 12 months."""
    meta = await _meta(session)
    now = time.monotonic()
    cached = _Shared.overview
    if cached and cached[1].data_version == meta.data_version and now - cached[0] < TTL_S:
        return cached[1]
    latest = meta.ppr_max_sale_date.replace(day=1)
    # The newest window with no provisional month in it ends just before provisional_from.
    window_end = _add_months(meta.provisional_from, -1)
    monthly = (
        await session.execute(sa.text(MONTHLY), {"since": _add_months(latest, 1 - MONTHS)})
    ).all()
    counties = (await session.execute(sa.text(COUNTIES), {"window_end": window_end})).all()
    total, first, properties = (await session.execute(sa.text(TOTALS))).one()
    result = Overview(
        data_version=meta.data_version,
        total_sales=total,
        total_properties=properties,
        first_sale_date=first,
        monthly=[MonthCount(month=m, sales=n, provisional=p) for m, n, p in monthly],
        window_start=_add_months(window_end, -11),
        window_end=window_end,
        counties=[
            CountyStat(slug=s, name=n, sales=c, median_price_eur=med, lat=lat, lng=lng)
            for s, n, c, med, lat, lng in counties
        ],
    )
    _Shared.overview = (now, result)
    return result
