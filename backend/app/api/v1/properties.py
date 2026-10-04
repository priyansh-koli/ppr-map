"""Meta, hover card, synced list and property page (docs/api.md)."""

import contextlib
import json
import math
import time
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.filters import sales_filter
from app.api.v1.search import list_item, parse_bbox
from app.db import get_session
from app.redis_client import REDIS_ERRORS, get_redis
from app.schemas.properties import (
    AreaRef,
    AreaSeries,
    Calibration,
    Comparable,
    Comparables,
    IndexSeries,
    Location,
    Meta,
    PriceEstimate,
    PropertyDetail,
    PropertyList,
    PropertySummary,
    Sale,
    SaleBrief,
    SalesFilter,
    StatsPoint,
    VatEstimate,
    Vicinity,
)
from app.services import estimate, rates, rppi, search
from app.services import properties as q

router = APIRouter(tags=["properties"])

# A bounding box larger than this is a national view: the map shows grid cells there, and
# the list asks the user to zoom in rather than sort 800,000 sales.
MAX_BBOX_DEGREES = (0.6, 0.4)
SUMMARY_TTL_S = 7 * 24 * 3600
NOT_FOUND = HTTPException(404, "No such property")
# Public ids are short and printable; anything else (a NUL byte, say) is refused up front.
PropertyId = Annotated[str, Path(max_length=64, pattern=r"^[^\x00-\x1f\x7f]+$")]


# The data version changes once a month; the hover path reads it at most once a minute.
META_TTL_S = 60.0


class _Shared:
    meta: tuple[float, Meta] | None = None


def forget_meta() -> None:
    """After an admin edit that changes the map, so this process serves the new tiles version
    at once; other processes follow within META_TTL_S."""
    _Shared.meta = None


Session = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]


async def _meta(session: AsyncSession) -> Meta:
    now = time.monotonic()
    if _Shared.meta is not None and now - _Shared.meta[0] < META_TTL_S:
        return _Shared.meta[1]
    row = await q.meta(session)
    if row is None:
        raise HTTPException(503, "Data is not loaded yet")
    edited = f".e{int(row[4].timestamp() * 1_000_000)}" if row[4] else ""
    meta_ = Meta(
        data_version=row[0],
        tiles_version=row[0] + edited,
        ppr_max_sale_date=row[1],
        provisional_from=row[2],
        last_ingest_at=row[3],
    )
    _Shared.meta = (now, meta_)
    return meta_


@router.get("/meta", response_model=Meta)
async def meta(session: Session) -> Meta:
    """Data freshness for the banner: the latest sale in the register and what is provisional."""
    return await _meta(session)


@router.get("/properties/{property_id}/summary", response_model=PropertySummary)
async def summary(property_id: PropertyId, session: Session, cache: Cache) -> PropertySummary:
    """The hover card: one precomputed row, cached in Redis per data version."""
    payload: dict[str, Any] | None = None
    key = f"summary:{property_id}:{(await _meta(session)).data_version}"
    if cache is not None:
        try:
            hit = await cache.get(key)
            payload = json.loads(hit) if hit else None
        except REDIS_ERRORS:
            cache = None
    if payload is None:
        payload = await q.summary(session, property_id)
        if payload is None:
            raise NOT_FOUND
        if cache is not None:
            with contextlib.suppress(*REDIS_ERRORS):
                await cache.set(key, json.dumps(payload, default=str), ex=SUMMARY_TTL_S)
    return PropertySummary.model_validate(payload)


@router.get(
    "/properties",
    response_model=PropertyList,
    responses={422: {"description": "The box is too large: zoom in"}},
)
async def list_properties(
    session: Session,
    filters: Annotated[SalesFilter, Depends(sales_filter)],
    bbox: Annotated[str, Query(description="west,south,east,north in degrees")],
    sort: Literal["-date", "date", "-price", "price", "-change", "change"] = "-date",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> PropertyList:
    """The list view synced with the map: the latest matching sale per property in the box.
    It is /search limited to the box, so it takes the same filters."""
    box = parse_bbox(bbox)
    assert box is not None
    w, s, e, n = box
    if e - w > MAX_BBOX_DEGREES[0] or n - s > MAX_BBOX_DEGREES[1]:
        raise HTTPException(422, "Zoom in to list sales")
    empty = PropertyList(items=[], total=0, page=page, page_size=page_size)
    found = await search.envelope(session, filters, box)
    if found is None:
        return empty
    rows = await search.search(session, filters, found, sort, page, page_size)
    if not rows or not rows[0][15]:
        return empty
    return PropertyList(
        items=[list_item(r) for r in rows if r[0] is not None],
        total=rows[0][15],
        page=page,
        page_size=page_size,
    )


def _vat_estimates(price: Decimal, sold_on: date) -> list[VatEstimate]:
    """VAT added back at the rates for the sale's date; none if the rates cannot be read."""
    try:
        return [
            VatEstimate(rate=float(rate), price_eur=amount, applies_to=applies)
            for rate, amount, applies in rates.vat_estimates(price, sold_on)
        ]
    except (OSError, ValidationError, LookupError):
        return []


def _caveats(confidence: str, sales: list[Sale], provisional_from: date) -> list[str]:
    out = []
    if confidence not in ("exact", "street"):
        out.append(
            "This location is approximate: the address could only be placed at "
            + {
                "locality": "its town, village or townland.",
                "routing_key": "the typical location of its Eircode routing key.",
                "county": "its county.",
            }.get(confidence, "a rough location.")
            + " Distances to nearby places are not shown."
            if confidence != "unmatched"
            else "This address has not been placed on the map, so it has no location and no "
            "distances to nearby places."
        )
    if any(s.vat_exclusive for s in sales):
        out.append(
            "New-build prices are filed without VAT; the price paid was higher. The VAT-inclusive "
            "figures are estimates at the rate for the sale date, not the price paid."
        )
    if any(s.not_full_market_price for s in sales):
        out.append(
            "At least one sale was filed as not at full market price, so it is left out of "
            "area medians."
        )
    if any(s.bulk_group_size for s in sales):
        out.append(
            "At least one sale was part of a bulk or portfolio sale, so its price may be a "
            "share of a total."
        )
    if any(s.date >= provisional_from for s in sales):
        out.append("Sales from the last two months are provisional: late filings still arrive.")
    return out


@router.get("/properties/{property_id}", response_model=PropertyDetail)
async def property_detail(property_id: PropertyId, session: Session) -> PropertyDetail:
    """The property page: every sale, location precision, areas, vicinity and area trend."""
    meta_ = await _meta(session)
    p = await q.detail(session, property_id)
    if p is None:
        raise NOT_FOUND
    sales = [
        Sale(
            date=r[0],
            price_eur=r[1],
            is_new=r[2],
            not_full_market_price=r[3],
            vat_exclusive=r[4],
            bulk_group_size=r[5],
            size_band=r[6],
            possible_duplicate=r[7],
            vat_estimates=_vat_estimates(r[1], r[0]) if r[4] else [],
        )
        for r in await q.sales(session, p.id)
    ]
    areas = [
        AreaRef(kind=r[0], name=r[1], slug=r[2])
        for r in await q.areas(session, p.id, p.county_area_id)
    ]
    since = date(meta_.ppr_max_sale_date.year - 5, meta_.ppr_max_sale_date.month, 1)
    candidates = [i for i in (p.settlement_id, p.county_area_id) if i is not None]
    area, rows = await q.series(session, candidates, since)
    series = (
        AreaSeries(
            area=AreaRef(kind=area.kind, name=area.name, slug=area.slug),
            points=[
                StatsPoint(
                    period_start=r[0], n=r[1], median=r[2], provisional=r[3], suppressed=r[4]
                )
                for r in rows
            ],
        )
        if area
        else None
    )
    summary_payload = await q.summary(session, property_id) or {}
    vicinity = Vicinity.model_validate(summary_payload.get("vicinity") or {"flood": _FLOOD})
    return PropertyDetail(
        id=p.public_id,
        address=p.address_display,
        county=p.county,
        routing_key=p.eircode_routing_key,
        dublin_district=p.dublin_district,
        location=Location(
            lat=p[6],
            lng=p[7],
            confidence=p.geocode_confidence,
            method=p.geocode_method,
            source=p.geocode_source,
        ),
        sales=sales,
        areas=areas,
        vicinity=vicinity,
        area_series=series,
        caveats=_caveats(p.geocode_confidence, sales, meta_.provisional_from),
        data_version=meta_.data_version,
    )


def _months_before(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, min(day.day, 28))


def _pct(log_ratio: float) -> float:
    """A log error as a percentage against the index: ln(1.1) -> 10.0."""
    return round((math.exp(log_ratio) - 1) * 100, 1)


@router.get("/properties/{property_id}/estimate", response_model=PriceEstimate)
async def price_estimate(property_id: PropertyId, session: Session) -> PriceEstimate:
    """What the CSO price index implies the home's last market sale would fetch now, with the
    range repeat sales in its region landed in (D-020, D-053). When no estimate can be given,
    `eligible` is false and `reason` says why."""
    found, reason = await estimate.estimate(session, property_id)
    if found is None and reason is None:
        raise NOT_FOUND
    if found is None:
        return PriceEstimate(eligible=False, reason=estimate.REASONS[reason or "no_index"])
    return PriceEstimate(
        eligible=True,
        low_eur=found.low,
        mid_eur=found.mid,
        high_eur=found.high,
        based_on=SaleBrief(date=found.sold_on, price_eur=found.sold_for),
        series=IndexSeries(key=found.series, label=rppi.SERIES[found.series]),
        index_month=found.index_month,
        index_change_pct=round((float(found.index_now) / float(found.index_then) - 1) * 100, 1),
        calibration=Calibration(
            years_between=found.band,
            pairs=found.pairs,
            pooled=found.pooled,
            low_pct=_pct(found.p10),
            median_pct=_pct(found.p50),
            high_pct=_pct(found.p90),
        ),
    )


@router.get("/properties/{property_id}/comparables", response_model=Comparables)
async def comparables(
    property_id: PropertyId,
    session: Session,
    radius_m: Annotated[int, Query(alias="radiusM", ge=100, le=2000)] = 500,
    months: Annotated[int, Query(ge=6, le=60)] = 24,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> Comparables:
    """Market sales of other homes on the same street or within `radiusM`, in the last
    `months` of the register: same street first, then nearest. Only for homes placed at their
    house or street, and only against others placed as precisely."""
    p = await q.detail(session, property_id)
    if p is None:
        raise NOT_FOUND
    empty = Comparables(available=False, radius_m=radius_m, months=months, total=0, items=[])
    if p.geocode_confidence not in ("exact", "street"):
        return empty.model_copy(
            update={
                "reason": "This home is placed only at its town or area, so distances to other "
                "sales would mean little."
            }
        )
    latest = (await _meta(session)).ppr_max_sale_date
    since = _months_before(latest, months)
    rows = await q.comparables(session, property_id, radius_m, since, limit)
    return Comparables(
        available=True,
        radius_m=radius_m,
        months=months,
        total=rows[0].total if rows else 0,
        median_eur=rows[0].median if rows else None,
        items=[
            Comparable(
                id=r.public_id,
                address=r.address_display,
                confidence=r.conf,
                date=r.sale_date,
                price_eur=r.price_eur,
                is_new=r.is_new,
                vat_exclusive=r.vat_exclusive,
                distance_m=r.distance_m,
                same_street=bool(r.same_street),
            )
            for r in rows
        ],
    )


_FLOOD = {"note": "Check the OPW flood maps", "link": "https://www.floodinfo.ie/map/floodmaps/"}
