"""Search, autocomplete and search history (docs/api.md, Search; D-047)."""

import json
from typing import Annotated, Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.filters import sales_filter
from app.api.v1.me import HISTORY_KEEP
from app.auth.deps import OptionalUser, require
from app.auth.permissions import Perm
from app.auth.ratelimit import limit_caller
from app.auth.sessions import CurrentUser
from app.db import get_session
from app.redis_client import get_redis
from app.schemas.properties import (
    AreaRef,
    LatestSale,
    PriceChange,
    PropertyListItem,
    SaleFlags,
    SalesFilter,
    SearchResults,
)
from app.schemas.search import Page, SearchHistoryIn, SearchHistoryOut, Suggestion
from app.services import search as q

router = APIRouter(tags=["search"])

Db = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]
HistoryUser = Annotated[CurrentUser, Depends(require(Perm.HISTORY_WRITE))]
Filters = Annotated[SalesFilter, Depends(sales_filter)]
Sort = Literal["-date", "date", "-price", "price", "-change", "change"]

SEARCH_LIMITS = (60, 300)
AUTOCOMPLETE_LIMITS = (120, 300)
MAX_HISTORY = 200
# The coordinates of "my location" are never stored (docs/permissions.md).
MY_LOCATION = "my-location"


def list_item(r: Any) -> PropertyListItem:
    """A row of `address, confidence, lat, lng, sale..., n_sales, prev date, prev price,
    change` (after the public id) as a list item."""
    return PropertyListItem(
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
        change=(
            PriceChange(previous_date=r[12], previous_price_eur=r[13], change_pct=float(r[14]))
            if r[14] is not None
            else None
        ),
    )


def parse_bbox(bbox: str | None) -> q.Box | None:
    if bbox is None:
        return None
    try:
        w, s, e, n = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be west,south,east,north") from None
    if not (w < e and s < n):
        raise HTTPException(422, "bbox must be west,south,east,north")
    return (w, s, e, n)


@router.get(
    "/search", response_model=SearchResults, dependencies=[Depends(require(Perm.SEARCH_READ))]
)
async def search(
    request: Request,
    session: Db,
    cache: Cache,
    user: OptionalUser,
    filters: Filters,
    bbox: Annotated[str | None, Query(description="west,south,east,north")] = None,
    sort: Sort = "-date",
    page: Annotated[int, Query(ge=1, le=1000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> SearchResults:
    """Every property whose latest matching sale passes the filters: the same matches as the
    map (`/tiles/sales` takes the same parameters). `-change` sorts by the largest rise since
    the previous plain market sale."""
    await limit_caller(cache, request, user.id if user else None, "search", SEARCH_LIMITS)
    query = {**filters.to_params(), **({"sort": sort} if sort != "-date" else {})}
    places = [
        AreaRef(kind=r[0], name=r[1], slug=r[2]) for r in await q.places(session, filters.area)
    ]
    empty = SearchResults(
        items=[], total=0, page=page, page_size=page_size, bbox=None, query=query, places=places
    )
    box = await q.envelope(session, filters, parse_bbox(bbox))
    if box is None:
        return empty
    rows = await q.search(session, filters, box, sort, page, page_size)
    if not rows:
        return empty
    total, w, s, e, n = rows[0][15:20]
    return SearchResults(
        items=[list_item(r) for r in rows if r[0] is not None],
        total=total,
        page=page,
        page_size=page_size,
        bbox=[w, s, e, n] if total else None,
        query=query,
        places=places,
    )


@router.get(
    "/geocode/autocomplete",
    response_model=list[Suggestion],
    dependencies=[Depends(require(Perm.SEARCH_READ))],
)
async def autocomplete(
    request: Request,
    session: Db,
    cache: Cache,
    user: OptionalUser,
    q_: Annotated[str, Query(alias="q", min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=10)] = 10,
) -> list[Suggestion]:
    """Places and addresses we hold data for (D-006): counties, towns, Electoral Divisions,
    townlands, Eircode routing keys (and Dublin postal districts), and property addresses.
    Nothing is sent to a third party."""
    await limit_caller(
        cache, request, user.id if user else None, "autocomplete", AUTOCOMPLETE_LIMITS
    )
    text = q.normalise(q_)
    if len(text) < 2:
        return []
    out: list[Suggestion] = []
    if key := q.routing_key_for(text):
        row = await q.routing_key(session, key)
        if row:
            district = q.routing_key_district(key)
            out.append(
                Suggestion(
                    kind="routing_key",
                    label=key,
                    detail=(f"Dublin {district[1:]} · " if district else "")
                    + f"Eircode routing key · {row[0]:,} properties",
                    routing_key=key,
                    lat=row[1],
                    lng=row[2],
                )
            )
    for r in await q.areas(session, text, limit):
        out.append(
            Suggestion(
                kind=r[0],
                label=r[1],
                detail=_area_detail(r[0], r[3]),
                slug=r[2],
                lat=r[4],
                lng=r[5],
                bbox=[r[6], r[7], r[8], r[9]],
            )
        )
    if len(text) >= 3 and len(out) < limit:
        for r in await q.properties(session, text, limit - len(out)):
            out.append(
                Suggestion(
                    kind="property",
                    label=r[1],
                    detail=f"Co. {r[2].title()} · property",
                    property_id=r[0],
                    lat=r[3],
                    lng=r[4],
                )
            )
    return out[:limit]


KIND_LABEL = {
    "county": "county",
    "settlement": "town",
    "electoral_division": "Electoral Division",
    "townland": "townland",
}


def _area_detail(kind: str, county: str | None) -> str:
    label = KIND_LABEL.get(kind, kind)
    return f"Co. {county} · {label}" if county else label


# --- search history ------------------------------------------------------------------------


def history_query(body: SearchHistoryIn) -> dict[str, str]:
    """The search as it is kept: validated filters and sort, with the coordinates of the
    user's own location replaced by a marker."""
    params = dict(body.query)
    geolocated = params.pop("nearSource", None) == "geolocation"
    sort = params.pop("sort", None)
    try:
        kept = SalesFilter.model_validate(params).to_params()
    except ValidationError as exc:
        raise HTTPException(422, "query is not a valid search") from exc
    if sort in ("date", "-price", "price", "-change", "change"):
        kept["sort"] = sort
    if geolocated and "near" in kept:
        kept["near"] = MY_LOCATION
    return kept


def _history_out(r: Any) -> SearchHistoryOut:
    stored = r[1] or {}
    return SearchHistoryOut(
        id=r[0],
        query=stored.get("params", {}),
        label=stored.get("label"),
        searched_at=r[2],
    )


@router.post("/me/history/searches", status_code=204, tags=["me"])
async def record_search(body: SearchHistoryIn, user: HistoryUser, session: Db) -> None:
    """Keep a search the user ran, unless history is off. Running the same search again
    moves it to the top instead of adding a copy."""
    if not user.history_enabled:
        return
    stored = {"params": history_query(body), "label": body.label}
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:u AS text), 3))"),
        {"u": user.id},
    )
    moved = await session.execute(
        sa.text(
            "UPDATE search_history SET searched_at = now(), query = CAST(:q AS jsonb) "
            "WHERE user_id = :u AND query -> 'params' = CAST(:p AS jsonb) RETURNING id"
        ),
        {"u": user.id, "q": _json(stored), "p": _json(stored["params"])},
    )
    if moved.first() is None:
        await session.execute(
            sa.text("INSERT INTO search_history (user_id, query) VALUES (:u, CAST(:q AS jsonb))"),
            {"u": user.id, "q": _json(stored)},
        )
    # Keep the newest MAX_HISTORY searches and nothing older than 12 months.
    await session.execute(
        sa.text(
            "DELETE FROM search_history WHERE user_id = :u AND (searched_at < now() - :keep "
            "OR id NOT IN (SELECT id FROM search_history WHERE user_id = :u "
            "ORDER BY searched_at DESC, id DESC LIMIT :n))"
        ),
        {"u": user.id, "keep": HISTORY_KEEP, "n": MAX_HISTORY},
    )
    await session.commit()


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


@router.get("/me/history/searches", response_model=Page[SearchHistoryOut], tags=["me"])
async def searches(
    user: HistoryUser,
    session: Db,
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> Page[SearchHistoryOut]:
    params = {"u": user.id, "keep": HISTORY_KEEP}
    where = "WHERE user_id = :u AND searched_at > now() - :keep"
    total: int = (
        await session.execute(sa.text(f"SELECT count(*) FROM search_history {where}"), params)  # noqa: S608
    ).scalar_one()
    rows = (
        await session.execute(
            sa.text(
                f"SELECT id, query, searched_at FROM search_history {where} "  # noqa: S608
                "ORDER BY searched_at DESC, id DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        )
    ).all()
    return Page[SearchHistoryOut](
        items=[_history_out(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.delete("/me/history/searches", status_code=204, tags=["me"])
async def clear_searches(user: HistoryUser, session: Db) -> None:
    await session.execute(sa.text("DELETE FROM search_history WHERE user_id = :u"), {"u": user.id})
    await session.commit()


@router.delete("/me/history/searches/{search_id}", status_code=204, tags=["me"])
async def delete_search(search_id: int, user: HistoryUser, session: Db) -> None:
    done = await session.execute(
        sa.text("DELETE FROM search_history WHERE id = :id AND user_id = :u RETURNING id"),
        {"id": search_id, "u": user.id},
    )
    if done.one_or_none() is None:
        raise HTTPException(404, "Not found")
    await session.commit()
