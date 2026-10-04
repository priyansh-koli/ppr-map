"""Saved searches, their alerts, CSV export, and one-click unsubscribe (docs/api.md; D-050).

Every query is filtered by the caller's id: another user's search is a 404, never a 403.
"""

import csv
import io
import json
import unicodedata
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, ValidationError, field_validator
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require
from app.auth.permissions import EXPORT_ROWS_PER_EXPORT, EXPORTS_PER_DAY, Perm, Role
from app.auth.ratelimit import limit
from app.auth.sessions import CurrentUser
from app.db import get_session
from app.redis_client import get_redis
from app.schemas.base import ApiModel
from app.services import alerts, search
from app.services import email as mail

router = APIRouter(tags=["me"])

Db = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]
SearchUser = Annotated[CurrentUser, Depends(require(Perm.SAVED_SEARCH_WRITE))]
ExportUser = Annotated[CurrentUser, Depends(require(Perm.EXPORT_CSV))]
Frequency = Literal["off", "on_data_update", "weekly"]
NOT_FOUND = HTTPException(404, "Not found")
MAX_SAVED = 50

# ODbL (R-06): coordinates placed with OpenStreetMap data carry its notice with them.
CSV_NOTICE = [
    "# Contains Residential Property Price Register data (c) Property Services Regulatory "
    "Authority; it may contain errors.",
    "# Locations are estimates (see location_precision). Where placed with OpenStreetMap data "
    "they are (c) OpenStreetMap contributors, available under the Open Database Licence.",
]
CSV_COLUMNS = [
    "address",
    "county",
    "eircode_routing_key",
    "sale_date",
    "price_eur",
    "new_or_second_hand",
    "vat_exclusive",
    "not_full_market_price",
    "bulk_sale",
    "location_precision",
    "latitude",
    "longitude",
    "sales_on_record",
    "url",
]


def _query(value: dict[str, str]) -> dict[str, str]:
    """A search as its URL parameters: validated filters, plus the sort."""
    params = {k: v for k, v in value.items() if k not in ("sort", "nearSource", "page")}
    try:
        f, sort = alerts.parse_query({**params, "sort": value.get("sort", "-date")})
    except ValidationError as exc:
        raise ValueError(
            "not a valid search: "
            + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        ) from None
    return {**f.to_params(), **({"sort": sort} if sort != "-date" else {})}


class SavedSearchIn(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    query: dict[str, str] = Field(description="The search's URL parameters, as on /search")
    alert_frequency: Frequency = "off"

    _clean_query = field_validator("query")(_query)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        # Control characters and line or paragraph separators (U+2028) would break the
        # alert email's subject line, every time (P2 #39).
        if not value or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in value):
            raise ValueError("name must be 1 to 100 printable characters")
        return value


class SavedSearchPatch(ApiModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    query: dict[str, str] | None = None
    alert_frequency: Frequency | None = None

    _clean_query = field_validator("query")(lambda v: None if v is None else _query(v))
    _name = field_validator("name")(lambda v: SavedSearchIn._name(v) if v is not None else v)


class SavedSearchOut(ApiModel):
    id: uuid.UUID
    name: str
    query: dict[str, str]
    alert_frequency: Frequency
    alerts_active: bool = Field(
        description="False while the email is unverified: nothing is sent until it is"
    )
    created_at: datetime
    last_alerted_at: datetime | None
    last_alert_matches: int | None


class Unsubscribe(ApiModel):
    token: str = Field(max_length=100)


class Unsubscribed(ApiModel):
    name: str


SELECT = """
SELECT ss.id, ss.name, ss.query, ss.alert_frequency::text, ss.created_at, ss.last_alerted_at,
       (SELECT d.n_matches FROM alert_delivery d WHERE d.saved_search_id = ss.id
        ORDER BY d.id DESC LIMIT 1)
FROM saved_search ss WHERE ss.user_id = :u {extra}
ORDER BY ss.created_at DESC, ss.id
"""


def _out(r: Any, user: CurrentUser) -> SavedSearchOut:
    return SavedSearchOut(
        id=r[0],
        name=r[1],
        query=r[2],
        alert_frequency=r[3],
        alerts_active=r[3] != "off" and user.email_verified,
        created_at=r[4],
        last_alerted_at=r[5],
        last_alert_matches=r[6],
    )


async def _one(db: AsyncSession, user: CurrentUser, sid: uuid.UUID) -> SavedSearchOut:
    row = (
        await db.execute(sa.text(SELECT.format(extra="AND ss.id = :id")), {"u": user.id, "id": sid})
    ).one_or_none()
    if row is None:
        raise NOT_FOUND
    return _out(row, user)


@router.get("/me/saved-searches", response_model=list[SavedSearchOut])
async def saved_searches(user: SearchUser, db: Db) -> list[SavedSearchOut]:
    rows = (await db.execute(sa.text(SELECT.format(extra="")), {"u": user.id})).all()
    return [_out(r, user) for r in rows]


@router.post("/me/saved-searches", status_code=201, response_model=SavedSearchOut)
async def save_search(body: SavedSearchIn, user: SearchUser, db: Db) -> SavedSearchOut:
    """Save a search. Its alerts cover sales filed from now on, not the register as it is."""
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:u AS text), 4))"),
        {"u": user.id},
    )
    count: int = (
        await db.execute(
            sa.text("SELECT count(*) FROM saved_search WHERE user_id = :u"), {"u": user.id}
        )
    ).scalar_one()
    if count >= MAX_SAVED:
        raise HTTPException(409, f"You can keep at most {MAX_SAVED} saved searches")
    ready = await alerts.ready_run(db)
    sid: uuid.UUID = (
        await db.execute(
            sa.text(
                "INSERT INTO saved_search (user_id, name, query, alert_frequency, "
                "alerted_through_run_id) VALUES (:u, :n, CAST(:q AS jsonb), "
                "CAST(:f AS alert_frequency), :ready) RETURNING id"
            ),
            {
                "u": user.id,
                "n": body.name,
                "q": _json(body.query),
                "f": body.alert_frequency,
                "ready": ready,
            },
        )
    ).scalar_one()
    await db.commit()
    return await _one(db, user, sid)


@router.get("/me/saved-searches/{sid}", response_model=SavedSearchOut)
async def saved_search(sid: uuid.UUID, user: SearchUser, db: Db) -> SavedSearchOut:
    return await _one(db, user, sid)


@router.patch("/me/saved-searches/{sid}", response_model=SavedSearchOut)
async def update_saved_search(
    sid: uuid.UUID, body: SavedSearchPatch, user: SearchUser, db: Db
) -> SavedSearchOut:
    """Rename, change the filters or the alert. Changing the filters, or switching an alert
    on that was off, starts its alerts from the register as it is now: an alert never sends
    the sales filed while it was off (P2 #38)."""
    sent = body.model_dump(exclude_unset=True)
    if any(v is None for v in sent.values()):
        raise HTTPException(422, "Fields cannot be set to null")
    switching_on = sent.get("alert_frequency", "off") != "off"
    ready = await alerts.ready_run(db) if "query" in sent or switching_on else None
    done = await db.execute(
        sa.text(
            "UPDATE saved_search SET name = coalesce(:n, name), "
            "query = coalesce(CAST(:q AS jsonb), query), "
            "alert_frequency = coalesce(CAST(:f AS alert_frequency), alert_frequency), "
            # The CASE sees the row as it was, so `alert_frequency = 'off'` is the old value.
            "alerted_through_run_id = CASE WHEN :requery OR (:on AND alert_frequency = 'off') "
            "THEN :ready ELSE alerted_through_run_id END, updated_at = now() "
            "WHERE id = :id AND user_id = :u RETURNING id"
        ),
        {
            "n": body.name,
            "q": _json(body.query) if body.query is not None else None,
            "f": body.alert_frequency,
            "requery": "query" in sent,
            "on": switching_on,
            "ready": ready,
            "id": sid,
            "u": user.id,
        },
    )
    if done.one_or_none() is None:
        raise NOT_FOUND
    await db.commit()
    return await _one(db, user, sid)


@router.delete("/me/saved-searches/{sid}", status_code=204)
async def delete_saved_search(sid: uuid.UUID, user: SearchUser, db: Db) -> None:
    done = await db.execute(
        sa.text("DELETE FROM saved_search WHERE id = :id AND user_id = :u RETURNING id"),
        {"id": sid, "u": user.id},
    )
    if done.one_or_none() is None:
        raise NOT_FOUND
    await db.commit()


def _role_limit(user: CurrentUser, table: dict[Role, int | None]) -> int:
    return max((table[r] or 0) for r in {*user.roles, Role.ANONYMOUS})


@router.get(
    "/me/saved-searches/{sid}/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_saved_search(sid: uuid.UUID, user: ExportUser, db: Db, cache: Cache) -> Response:
    """The search's matches as CSV, in its sort order, up to your role's row limit (500 for a
    user). Each role also has a daily number of exports (docs/permissions.md)."""
    rows_cap = _role_limit(user, EXPORT_ROWS_PER_EXPORT)
    per_day = _role_limit(user, EXPORTS_PER_DAY)
    stored = await _one(db, user, sid)
    await limit(cache, f"export:{user.id}:{date.today().isoformat()}", per_day, 24 * 3600)
    try:
        f, sort = alerts.parse_query(stored.query)
    except ValidationError:
        raise HTTPException(422, "This saved search no longer works; edit its filters") from None
    box = await search.envelope(db, f, None)
    rows = await search.search(db, f, box, sort, 1, rows_cap) if box else []
    total = rows[0][15] if rows else 0
    buf = io.StringIO()
    for line in CSV_NOTICE:
        buf.write(line + "\n")
    if total > rows_cap:
        buf.write(f"# The first {rows_cap:,} of {total:,} matches.\n")
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    detail = await _details(db, [r[0] for r in rows if r[0] is not None])
    for r in rows:
        if r[0] is None:
            continue
        county, routing_key = detail.get(r[0], ("", ""))
        writer.writerow(
            [
                _cell(r[1]),
                county,
                routing_key or "",
                r[5].isoformat(),
                f"{r[6]:.2f}",
                "new" if r[7] else "second-hand",
                _yes(r[9]),
                _yes(r[8]),
                _yes(r[10]),
                r[2],
                f"{r[3]:.6f}",
                f"{r[4]:.6f}",
                r[11],
                mail.link(f"/property/{r[0]}"),
            ]
        )
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ppr-map-search-{stamp}.csv"'},
    )


async def _details(db: AsyncSession, ids: list[str]) -> dict[str, tuple[str, str | None]]:
    rows = await db.execute(
        sa.text(
            "SELECT public_id, county::text, eircode_routing_key FROM property "
            "WHERE public_id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    return {r[0]: (r[1], r[2]) for r in rows}


def _yes(v: bool) -> str:
    return "yes" if v else "no"


def _cell(text: str) -> str:
    # A cell starting with = + - @ runs as a formula in a spreadsheet; quote it (CSV injection).
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


@router.post("/alerts/unsubscribe", response_model=Unsubscribed, tags=["alerts"])
async def unsubscribe(body: Unsubscribe, db: Db) -> Unsubscribed:
    """Switch off one saved search's alert from the link in its email, without signing in."""
    sid = alerts.check_unsubscribe_token(body.token)
    if sid is None:
        raise HTTPException(400, "This link is not valid")
    row = (
        await db.execute(
            sa.text(
                "UPDATE saved_search SET alert_frequency = 'off', updated_at = now() "
                "WHERE id = :id RETURNING name"
            ),
            {"id": sid},
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(404, "This saved search no longer exists")
    await db.commit()
    return Unsubscribed(name=row[0])
