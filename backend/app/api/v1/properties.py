"""Meta, hover card, synced list and property page (docs/api.md)."""

import contextlib
import json
import time
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.enums import GeocodeConfidence
from app.redis_client import REDIS_ERRORS, get_redis
from app.schemas.properties import (
    AreaRef,
    AreaSeries,
    LatestSale,
    Location,
    Meta,
    PropertyDetail,
    PropertyList,
    PropertyListItem,
    PropertySummary,
    Sale,
    SaleFlags,
    SalesFilter,
    StatsPoint,
    Vicinity,
)
from app.services import properties as q

router = APIRouter(tags=["properties"])

# A bounding box larger than this is a national view: the map shows grid cells there, and
# the list asks the user to zoom in rather than sort 800,000 sales.
MAX_BBOX_DEGREES = (0.6, 0.4)
SUMMARY_TTL_S = 7 * 24 * 3600
NOT_FOUND = HTTPException(404, "No such property")


# The data version changes once a month; the hover path reads it at most once a minute.
META_TTL_S = 60.0


class _Shared:
    meta: tuple[float, Meta] | None = None


def sales_filter(
    price_min: Annotated[Decimal | None, Query(alias="priceMin", ge=0)] = None,
    price_max: Annotated[Decimal | None, Query(alias="priceMax", ge=0)] = None,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    type_: Annotated[Literal["new", "second_hand", "any"], Query(alias="type")] = "any",
    exclude_non_market: Annotated[bool, Query(alias="excludeNonMarket")] = True,
    exclude_bulk: Annotated[bool, Query(alias="excludeBulk")] = True,
    min_confidence: Annotated[
        GeocodeConfidence, Query(alias="minConfidence")
    ] = GeocodeConfidence.LOCALITY,
) -> SalesFilter:
    """The map's filters, with the tiles' defaults."""
    return SalesFilter(
        price_min=price_min,
        price_max=price_max,
        date_from=date_from,
        date_to=date_to,
        type=type_,
        exclude_non_market=exclude_non_market,
        exclude_bulk=exclude_bulk,
        min_confidence=min_confidence,
    )


Session = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]


async def _meta(session: AsyncSession) -> Meta:
    now = time.monotonic()
    if _Shared.meta is not None and now - _Shared.meta[0] < META_TTL_S:
        return _Shared.meta[1]
    row = await q.meta(session)
    if row is None:
        raise HTTPException(503, "Data is not loaded yet")
    meta_ = Meta(
        data_version=row[0],
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
async def summary(property_id: str, session: Session, cache: Cache) -> PropertySummary:
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
    sort: Literal["-date", "date", "-price", "price"] = "-date",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> PropertyList:
    """The list view synced with the map: the latest matching sale per property in the box."""
    try:
        w, s, e, n = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be west,south,east,north") from None
    if not (w < e and s < n):
        raise HTTPException(422, "bbox must be west,south,east,north")
    if e - w > MAX_BBOX_DEGREES[0] or n - s > MAX_BBOX_DEGREES[1]:
        raise HTTPException(422, "Zoom in to list sales")
    rows, total = await q.list_properties(session, (w, s, e, n), filters, sort, page, page_size)
    items = [
        PropertyListItem(
            id=r[0],
            address=r[1],
            confidence=r[2],
            lat=r[3],
            lng=r[4],
            latest_sale=LatestSale(
                date=r[5],
                price_eur=r[6],
                is_new=r[7],
                flags=SaleFlags(not_full_market_price=r[8], vat_exclusive=r[9], bulk=r[10]),
            ),
            n_sales=r[11],
        )
        for r in rows
    ]
    return PropertyList(items=items, total=total, page=page, page_size=page_size)


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
        )
    if any(s.vat_exclusive for s in sales):
        out.append("New-build prices are filed without VAT; the price paid was higher.")
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
async def property_detail(property_id: str, session: Session) -> PropertyDetail:
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


_FLOOD = {"note": "Check the OPW flood maps", "link": "https://www.floodinfo.ie/map/floodmaps/"}
