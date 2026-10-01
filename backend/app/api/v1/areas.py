"""Area pages: the area, its price statistics against Ireland's, and a price distribution
(docs/api.md, Areas; D-049). Everything is read from the monthly aggregates or counted from
market sales, and held in memory per data version."""

import json
from collections import OrderedDict
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.properties import _meta
from app.api.v1.stats import _add_months
from app.auth.deps import require
from app.auth.permissions import Perm
from app.db import get_session
from app.schemas.areas import (
    AreaAttributeOut,
    AreaDetail,
    AreaStatsOut,
    Bin,
    Distribution,
    Headline,
    PeriodKindName,
    PriceIndex,
    SegmentName,
    SeriesPoint,
    SubArea,
)
from app.schemas.properties import AreaRef
from app.services import areas as q
from app.services import rppi

router = APIRouter(prefix="/areas", tags=["areas"], dependencies=[Depends(require(Perm.AREA_READ))])
Session = Annotated[AsyncSession, Depends(get_session)]
Slug = Annotated[str, Path(max_length=80, pattern=r"^[a-z0-9_-]+$")]
NOT_FOUND = HTTPException(404, "No such area")
MIN_N = 5
CACHE_SIZE = 512
CHILDREN_SHOWN = 30

POBAL_CATEGORY = {
    "Very Affluent": "Very affluent",
    "Affluent": "Affluent",
    "Marginally Above Average": "Marginally above average",
    "Marginally Below Average": "Marginally below average",
    "Disadvantaged": "Disadvantaged",
    "Very Disadvantaged": "Very disadvantaged",
}


class _Cache:
    """Answers per data version; the data changes once a month."""

    def __init__(self) -> None:
        self.items: OrderedDict[tuple[str, ...], Any] = OrderedDict()

    def get(self, key: tuple[str, ...]) -> Any:
        if key in self.items:
            self.items.move_to_end(key)
            return self.items[key]
        return None

    def put(self, key: tuple[str, ...], value: Any) -> Any:
        self.items[key] = value
        self.items.move_to_end(key)
        while len(self.items) > CACHE_SIZE:
            self.items.popitem(last=False)
        return value


_cache = _Cache()


def _month_end(first: date) -> date:
    return _add_months(first, 1) - timedelta(days=1)


def headline_window(kind: str, provisional_from: date) -> tuple[PeriodKindName, date, date, date]:
    """(period kind, period_start of the latest complete window, its first day, its last day).
    Rolling 12 months where the area has them; otherwise the latest complete calendar year."""
    if kind in q.COARSE_KINDS:
        year = provisional_from.year - 1
        return "year", date(year, 1, 1), date(year, 1, 1), date(year, 12, 31)
    last = _add_months(provisional_from, -1)  # a rolling window is labelled by its last month
    return "rolling_12m", last, _add_months(last, -11), _month_end(last)


async def _headline(
    session: AsyncSession, area_id: int, period_kind: str, start: date, first: date, last: date
) -> Headline | None:
    now = await q.point(session, area_id, period_kind, start)
    if now is None:
        return None
    before = await q.point(session, area_id, period_kind, _add_months(start, -12))
    change = None
    if now[2] is not None and before is not None and before[2]:
        change = round(float(now[2] / before[2] - 1) * 100, 1)
    return Headline(
        window_start=first,
        window_end=last,
        n=now[1],
        median=now[2],
        p25=now[3],
        p75=now[4],
        change_pct=change,
    )


def _attribute(row: Any, own_kind: str) -> AreaAttributeOut | None:
    key, value, text, source, as_of, licence, kind, name = row
    where = "" if kind == own_kind else f" of its Electoral Division, {name}"
    if source == "pobal_hp_2022" and key == "category":
        label = f"Deprivation{where}"
        shown = POBAL_CATEGORY.get(text or "", text or "")
    elif source == "pobal_hp_2022" and key == "relative_index":
        label = f"Deprivation score{where} (relative; 0 is average)"
        shown = f"{float(value):+.1f}"
    else:
        return None
    return AreaAttributeOut(
        label=label,
        value=shown,
        source="Pobal HP Deprivation Index 2022 (Electoral Division)",
        as_of=as_of,
        licence=licence,
    )


@router.get("/{slug}", response_model=AreaDetail)
async def area_detail(slug: Slug, session: Session) -> AreaDetail:
    """An area with its parents, shape, latest complete 12 months against Ireland's, what is
    known about it, and its busiest sub-areas."""
    meta = await _meta(session)
    # The CSO index can be reloaded on its own (an admin's "benchmarks" run), between aggregates.
    key = ("area", slug, meta.data_version, await q.index_version(session))
    if (hit := _cache.get(key)) is not None:
        return hit  # type: ignore[no-any-return]
    row = await q.area(session, slug)
    if row is None:
        raise NOT_FOUND
    area_id, kind = row[0], row[1]
    period_kind, start, first, last = headline_window(kind, meta.provisional_from)
    country = await q.country_id(session)
    parents = await q.parents(session, area_id, kind)
    attribute_ids = [area_id]
    if kind == "small_area" and parents and parents[0][0] == "electoral_division":
        attribute_ids.append(parents[0][3])  # a Small Area shows its ED's deprivation
    attributes = [
        a for r in await q.attributes(session, attribute_ids) if (a := _attribute(r, kind))
    ]
    child_kind = q.CHILD_FILTER.get(kind, (None, ""))[0]
    child_period, child_start = (
        ("year", date(meta.provisional_from.year - 1, 1, 1))
        if child_kind in q.COARSE_KINDS
        else ("rolling_12m", _add_months(meta.provisional_from, -1))
    )
    child_kind, child_rows = await q.children(
        session, area_id, kind, child_period, child_start, CHILDREN_SHOWN
    )
    county = row[5] if kind == "county" else next((p[2] for p in parents if p[0] == "county"), None)
    code = "00" if kind == "country" else rppi.REGION_HOUSES.get(county or "")
    price_index = None
    if code is not None and (found := await q.index_change(session, rppi.series_key(code))):
        label = "National - all residential properties" if code == "00" else rppi.SERIES[code]
        price_index = PriceIndex(
            label=label, month=found[0], change12m_pct=round(float(found[1]) * 100, 1)
        )
    result = AreaDetail(
        kind=kind,
        name=row[2],
        name_ga=row[3],
        slug=row[4],
        code=row[5],
        parents=[AreaRef(kind=p[0], name=p[1], slug=p[2]) for p in parents],
        bbox=[row[8], row[9], row[10], row[11]],
        geometry=json.loads(row[7]),
        headline=await _headline(session, area_id, period_kind, start, first, last),
        national=(
            await _headline(session, country, period_kind, start, first, last)
            if country is not None and country != area_id
            else None
        ),
        attributes=attributes,
        children=[
            SubArea(kind=c[0], name=c[1], slug=c[2], n=c[3], median=c[4]) for c in child_rows
        ],
        children_kind=child_kind if child_rows else None,
        period_kinds=q.period_kinds(kind),
        price_index=price_index,
        point_based=kind in ("small_area", "electoral_division"),
        source=row[6],
        data_version=meta.data_version,
    )
    return _cache.put(key, result)  # type: ignore[no-any-return]


# The register starts in January 2010, so a 12-month window ending before December 2010 holds
# fewer than 12 months of sales and is left out.
FIRST_FULL_WINDOW = date(2010, 12, 1)


def _points(rows: list[Any], period_kind: str = "") -> list[SeriesPoint]:
    return [
        SeriesPoint(
            period_start=r[0],
            n=r[1],
            median=r[2],
            p25=r[3],
            p75=r[4],
            provisional=r[5],
            suppressed=r[6],
        )
        for r in rows
        if period_kind != "rolling_12m" or r[0] >= FIRST_FULL_WINDOW
    ]


@router.get("/{slug}/stats", response_model=AreaStatsOut)
async def area_stats(
    slug: Slug,
    session: Session,
    period_kind: Annotated[PeriodKindName | None, Query(alias="periodKind")] = None,
    segment: SegmentName = "all",
) -> AreaStatsOut:
    """The area's series from `area_stats`, with Ireland's for the same periods. Periods with
    fewer than 5 sales keep their count and have no prices; the latest two months are
    provisional. Small Areas and townlands have quarters and years only."""
    meta = await _meta(session)
    row = await q.area(session, slug)
    if row is None:
        raise NOT_FOUND
    area_id, kind = row[0], row[1]
    chosen: PeriodKindName = period_kind or ("year" if kind in q.COARSE_KINDS else "rolling_12m")
    key = ("stats", slug, chosen, segment, meta.data_version)
    if (hit := _cache.get(key)) is not None:
        return hit  # type: ignore[no-any-return]
    if chosen not in q.period_kinds(kind):
        raise HTTPException(422, f"This area has no {chosen.replace('_', ' ')} series")
    country = await q.country_id(session)
    result = AreaStatsOut(
        area=AreaRef(kind=kind, name=row[2], slug=row[4]),
        period_kind=chosen,
        segment=segment,
        points=_points(await q.series(session, area_id, chosen, segment), chosen),
        national=(
            _points(await q.series(session, country, chosen, segment), chosen) if country else []
        ),
    )
    return _cache.put(key, result)  # type: ignore[no-any-return]


@router.get("/{slug}/distribution", response_model=Distribution)
async def distribution(slug: Slug, session: Session) -> Distribution:
    """How many market sales fell in each price band over the latest complete 12 months, with
    Ireland's shares for comparison. Bands with fewer than 5 sales are not given."""
    meta = await _meta(session)
    key = ("distribution", slug, meta.data_version)
    if (hit := _cache.get(key)) is not None:
        return hit  # type: ignore[no-any-return]
    row = await q.area(session, slug)
    if row is None:
        raise NOT_FOUND
    last = _add_months(meta.provisional_from, -1)
    first, end = _add_months(last, -11), meta.provisional_from
    counts = await q.distribution(session, row[0], row[1], row[5], first, end)
    national_key = ("national-distribution", meta.data_version)
    national = _cache.get(national_key)
    if national is None:
        country = await q.country_id(session)
        national = _cache.put(
            national_key,
            await q.distribution(session, country or 0, "country", "IE", first, end),
        )
    total_national = sum(national) or 1
    edges = q.BIN_EDGES
    result = Distribution(
        area=AreaRef(kind=row[1], name=row[2], slug=row[4]),
        window_start=first,
        window_end=end - timedelta(days=1),
        n=sum(counts),
        bins=[
            Bin(
                from_eur=edges[i],
                to_eur=edges[i + 1] if i + 1 < len(edges) else None,
                n=c if c >= MIN_N or c == 0 else None,
            )
            for i, c in enumerate(counts)
        ],
        national_share=[round(n / total_national, 4) for n in national],
    )
    return _cache.put(key, result)  # type: ignore[no-any-return]
