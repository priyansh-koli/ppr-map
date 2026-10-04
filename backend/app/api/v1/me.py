"""The signed-in user's own account, wishlist and history (docs/api.md, Me).

Every query here is filtered by the caller's own user id, so another user's item is a 404,
never a 403 (docs/permissions.md).
"""

import json
from datetime import datetime, timedelta
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import clear_session_cookie
from app.auth.deps import User, require
from app.auth.passwords import hash_password, password_problem, verify_password
from app.auth.permissions import Perm
from app.auth.ratelimit import forget, limit
from app.auth.sessions import CurrentUser, forget_cached_user, revoke_sessions
from app.db import get_session
from app.policies import PRIVACY_VERSION
from app.redis_client import get_redis
from app.schemas.auth import Me, MePatch, PasswordChangeIn, PasswordIn
from app.schemas.base import ApiModel, Money
from app.schemas.properties import PropertySummary
from app.schemas.search import Page
from app.services import email as mail
from app.services.accounts import export, keep_an_admin, load_me

router = APIRouter(prefix="/me", tags=["me"])

Db = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]
Mailer = Annotated[mail.Mailer, Depends(mail.get_mailer)]
WishlistUser = Annotated[CurrentUser, Depends(require(Perm.WISHLIST_WRITE))]
HistoryUser = Annotated[CurrentUser, Depends(require(Perm.HISTORY_WRITE))]

MAX_WISHLIST = 500
MAX_COMPARE = 4
# Viewing the same property again within this window is one visit, not several.
VIEW_DEDUPE = timedelta(minutes=30)
HISTORY_KEEP = timedelta(days=365)
NOT_FOUND = HTTPException(404, "Not found")
# Re-entering the password (change password, close account, admin role change): each try is a
# 64 MiB argon2 verify on a small shared pool, so wrong guesses are capped per account.
REAUTH_TRIES = (5, 15 * 60)


@router.get("", response_model=Me)
async def get_me(user: User, db: Db) -> Me:
    return await load_me(db, user.id)


@router.patch("", response_model=Me)
async def patch_me(body: MePatch, user: User, db: Db, cache: Cache) -> Me:
    fields = body.model_dump(exclude_unset=True)
    if "full_name" in fields:
        await db.execute(
            sa.text("UPDATE app_user SET full_name = :n, updated_at = now() WHERE id = :u"),
            {"n": body.full_name, "u": user.id},
        )
    if "history_enabled" in fields and body.history_enabled is not None:
        await db.execute(
            sa.text("UPDATE app_user SET history_enabled = :h, updated_at = now() WHERE id = :u"),
            {"h": body.history_enabled, "u": user.id},
        )
    if "marketing_opt_in" in fields and body.marketing_opt_in is not None:
        # A consent record only when the choice actually changes.
        changed = await db.execute(
            sa.text(
                "UPDATE app_user SET marketing_opt_in = :m, updated_at = now() "
                "WHERE id = :u AND marketing_opt_in IS DISTINCT FROM :m RETURNING id"
            ),
            {"m": body.marketing_opt_in, "u": user.id},
        )
        if changed.one_or_none() is not None:
            await db.execute(
                sa.text(
                    "INSERT INTO consent_record (user_id, kind, document_version, granted) "
                    "VALUES (:u, 'marketing_email', :v, :g)"
                ),
                {"u": user.id, "v": PRIVACY_VERSION, "g": body.marketing_opt_in},
            )
    if body.profile is not None:
        # Only the profile fields sent are written; the others keep their stored values.
        sent = body.profile.model_dump(exclude_unset=True)
        p = body.profile.model_dump()
        keep = {k: k not in sent for k in p}
        await db.execute(
            sa.text(
                "INSERT INTO user_profile (user_id, user_type, counties, budget_min, budget_max, "
                "property_interest) VALUES (:u, :t, CAST(:c AS county[]), :bmin, :bmax, :pi) "
                "ON CONFLICT (user_id) DO UPDATE SET "
                "user_type = CASE WHEN :keep_t THEN user_profile.user_type "
                "ELSE excluded.user_type END, "
                "counties = CASE WHEN :keep_c THEN user_profile.counties "
                "ELSE excluded.counties END, "
                "budget_min = CASE WHEN :keep_bmin THEN user_profile.budget_min "
                "ELSE excluded.budget_min END, "
                "budget_max = CASE WHEN :keep_bmax THEN user_profile.budget_max "
                "ELSE excluded.budget_max END, "
                "property_interest = CASE WHEN :keep_pi THEN user_profile.property_interest "
                "ELSE excluded.property_interest END, "
                "updated_at = now()"
            ),
            {
                "u": user.id,
                "t": p["user_type"],
                "c": p["counties"],
                "bmin": p["budget_min"],
                "bmax": p["budget_max"],
                "pi": p["property_interest"],
                "keep_t": keep["user_type"],
                "keep_c": keep["counties"],
                "keep_bmin": keep["budget_min"],
                "keep_bmax": keep["budget_max"],
                "keep_pi": keep["property_interest"],
            },
        )
    await db.commit()
    await forget_cached_user(cache, db, user.id)
    return await load_me(db, user.id)


async def confirm_password(
    db: AsyncSession, cache: Redis | None, user_id: object, password: str
) -> None:
    """403 unless `password` is the account's own; at most REAUTH_TRIES wrong ones (429)."""
    key = f"reauth:{user_id}"
    await limit(cache, key, *REAUTH_TRIES)
    hash_: str = (
        await db.execute(
            sa.text("SELECT password_hash FROM app_user WHERE id = :u"), {"u": user_id}
        )
    ).scalar_one()
    if not await verify_password(hash_, password):
        raise HTTPException(403, "The password is wrong")
    await forget(cache, key)


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordChangeIn,
    user: User,
    db: Db,
    cache: Cache,
    mailer: Mailer,
    background: BackgroundTasks,
) -> None:
    """Change the password; every other session is signed out and reset links stop working."""
    await confirm_password(db, cache, user.id, body.current_password)
    if problem := password_problem(body.new_password, user.email):
        raise HTTPException(422, problem)
    await db.execute(
        sa.text("UPDATE app_user SET password_hash = :p, updated_at = now() WHERE id = :u"),
        {"p": await hash_password(body.new_password), "u": user.id},
    )
    await db.execute(
        sa.text(
            "UPDATE password_reset_token SET used_at = now() WHERE user_id = :u AND used_at IS NULL"
        ),
        {"u": user.id},
    )
    await revoke_sessions(db, cache, user.id, keep=user.session_id)
    background.add_task(mailer.send, mail.password_changed(user.email, user.full_name))


@router.delete("", status_code=204)
async def delete_me(body: PasswordIn, user: User, response: Response, db: Db, cache: Cache) -> None:
    """Close the account now; its data is purged after 30 days (`app.cli purge-deleted`).
    The last active admin cannot (409): someone must be able to run the site."""
    await confirm_password(db, cache, user.id, body.password)
    await keep_an_admin(db, user.id)
    await db.execute(
        sa.text(
            "UPDATE app_user SET deleted_at = now(), is_active = false, updated_at = now() "
            "WHERE id = :u"
        ),
        {"u": user.id},
    )
    await revoke_sessions(db, cache, user.id)
    clear_session_cookie(response)


@router.get("/export")
async def export_me(user: User, db: Db) -> Response:
    """Everything stored about the account, as a JSON download (GDPR access request)."""
    data = await export(db, user.id)
    return Response(
        json.dumps(data, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="ppr-map-account.json"'},
    )


# --- wishlist ------------------------------------------------------------------------------


class WishlistIn(ApiModel):
    property_id: str | None = Field(None, description="The property's public id")
    area_slug: str | None = None
    note: str | None = Field(None, max_length=2000)


class WishlistNote(ApiModel):
    note: str | None = Field(None, max_length=2000)


class WishlistItemOut(ApiModel):
    id: int
    kind: str
    property_id: str | None
    area_slug: str | None
    title: str
    note: str | None
    created_at: datetime
    latest_price_eur: Money | None = None
    latest_sale_date: str | None = None


WISHLIST = """
SELECT w.id, w.target_kind::text, p.public_id, a.slug,
       coalesce(p.address_display, a.name) AS title, w.note, w.created_at,
       (SELECT s.price_eur FROM sale s WHERE s.property_id = p.id AND s.withdrawn_at IS NULL
        ORDER BY s.sale_date DESC, s.id DESC LIMIT 1) AS price,
       (SELECT s.sale_date::text FROM sale s WHERE s.property_id = p.id AND s.withdrawn_at IS NULL
        ORDER BY s.sale_date DESC, s.id DESC LIMIT 1) AS sale_date
FROM wishlist_item w
LEFT JOIN property p ON p.id = w.property_id
LEFT JOIN area a ON a.id = w.area_id
WHERE w.user_id = :u AND NOT coalesce(p.is_suppressed, false) {extra}
ORDER BY w.created_at DESC, w.id DESC
"""


def _item(r: Any) -> WishlistItemOut:
    return WishlistItemOut(
        id=r[0],
        kind=r[1],
        property_id=r[2],
        area_slug=r[3],
        title=r[4],
        note=r[5],
        created_at=r[6],
        latest_price_eur=r[7],
        latest_sale_date=r[8],
    )


async def _one_item(db: AsyncSession, user_id: object, item_id: int) -> WishlistItemOut:
    sql = WISHLIST.format(extra="AND w.id = :id")
    row = (await db.execute(sa.text(sql), {"u": user_id, "id": item_id})).one_or_none()
    if row is None:
        raise NOT_FOUND
    return _item(row)


@router.get("/wishlist", response_model=list[WishlistItemOut])
async def wishlist(user: WishlistUser, db: Db) -> list[WishlistItemOut]:
    rows = (await db.execute(sa.text(WISHLIST.format(extra="")), {"u": user.id})).all()
    return [_item(r) for r in rows]


@router.post(
    "/wishlist",
    status_code=201,
    response_model=WishlistItemOut,
    responses={200: {"model": WishlistItemOut, "description": "Already saved"}},
)
async def add_to_wishlist(
    body: WishlistIn, user: WishlistUser, db: Db, response: Response
) -> WishlistItemOut:
    """Save a property or an area (201). Saving the same one again returns the existing item
    (200), with its note replaced if a new one is given."""
    if (body.property_id is None) == (body.area_slug is None):
        raise HTTPException(422, "Give either propertyId or areaSlug")
    if body.property_id is not None:
        target = await db.execute(
            sa.text("SELECT id FROM property WHERE public_id = :p AND NOT is_suppressed"),
            {"p": body.property_id},
        )
        kind, column = "property", "property_id"
    else:
        target = await db.execute(
            sa.text("SELECT id FROM area WHERE slug = :s"), {"s": body.area_slug}
        )
        kind, column = "area", "area_id"
    target_id = target.scalar_one_or_none()
    if target_id is None:
        raise NOT_FOUND
    # One add at a time per user, so the size cap holds under concurrent requests.
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:u AS text), 1))"),
        {"u": user.id},
    )
    existing = (
        await db.execute(
            sa.text(
                f"UPDATE wishlist_item SET note = coalesce(:n, note) "  # noqa: S608
                f"WHERE user_id = :u AND {column} = :t RETURNING id"
            ),
            {"u": user.id, "t": target_id, "n": body.note},
        )
    ).scalar_one_or_none()
    if existing is not None:
        await db.commit()
        response.status_code = 200
        return await _one_item(db, user.id, existing)
    count: int = (
        await db.execute(
            sa.text("SELECT count(*) FROM wishlist_item WHERE user_id = :u"), {"u": user.id}
        )
    ).scalar_one()
    if count >= MAX_WISHLIST:
        raise HTTPException(409, f"A wishlist holds at most {MAX_WISHLIST} items")
    item_id: int = (
        await db.execute(
            sa.text(
                f"INSERT INTO wishlist_item (user_id, target_kind, {column}, note) "  # noqa: S608
                "VALUES (:u, CAST(:k AS wishlist_target_kind), :t, :n) RETURNING id"
            ),
            {"u": user.id, "k": kind, "t": target_id, "n": body.note},
        )
    ).scalar_one()
    await db.commit()
    return await _one_item(db, user.id, item_id)


@router.patch("/wishlist/{item_id}", response_model=WishlistItemOut)
async def note_wishlist_item(
    item_id: int, body: WishlistNote, user: WishlistUser, db: Db
) -> WishlistItemOut:
    done = await db.execute(
        sa.text("UPDATE wishlist_item SET note = :n WHERE id = :id AND user_id = :u RETURNING id"),
        {"n": body.note, "id": item_id, "u": user.id},
    )
    if done.one_or_none() is None:
        raise NOT_FOUND
    await db.commit()
    return await _one_item(db, user.id, item_id)


@router.delete("/wishlist/{item_id}", status_code=204)
async def remove_wishlist_item(item_id: int, user: WishlistUser, db: Db) -> None:
    done = await db.execute(
        sa.text("DELETE FROM wishlist_item WHERE id = :id AND user_id = :u RETURNING id"),
        {"id": item_id, "u": user.id},
    )
    if done.one_or_none() is None:
        raise NOT_FOUND
    await db.commit()


@router.get("/wishlist/compare", response_model=list[PropertySummary])
async def compare(
    user: WishlistUser,
    db: Db,
    ids: Annotated[
        str, Query(description="Up to 4 property ids from the wishlist, comma-separated")
    ],
) -> list[PropertySummary]:
    """Side by side: the hover summaries of up to four saved properties, in the order given."""
    wanted = [i for i in dict.fromkeys(i.strip() for i in ids.split(",")) if i]
    if any("\x00" in i for i in wanted):
        raise HTTPException(422, "ids must not contain NUL characters")
    if not 1 <= len(wanted) <= MAX_COMPARE:
        raise HTTPException(422, f"Compare 1 to {MAX_COMPARE} properties")
    rows = (
        await db.execute(
            sa.text(
                "SELECT p.public_id, ps.payload FROM wishlist_item w "
                "JOIN property p ON p.id = w.property_id "
                "JOIN property_summary ps ON ps.property_id = p.id "
                "WHERE w.user_id = :u AND p.public_id = ANY(:ids) AND NOT p.is_suppressed"
            ),
            {"u": user.id, "ids": wanted},
        )
    ).all()
    found = {r[0]: r[1] for r in rows}
    if len(found) != len(wanted):
        raise NOT_FOUND
    return [PropertySummary.model_validate(found[i]) for i in wanted]


# --- history -------------------------------------------------------------------------------


class ViewIn(ApiModel):
    property_id: str


class ViewOut(ApiModel):
    id: int
    property_id: str
    address: str
    viewed_at: datetime


@router.post("/history/views", status_code=204)
async def record_view(body: ViewIn, user: HistoryUser, db: Db) -> None:
    """Record a property page visit, unless history is switched off (then nothing is kept)."""
    if not user.history_enabled:
        return
    # Serialise visits by the same user, so two tabs opening a page count once.
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:u AS text), 2))"),
        {"u": user.id},
    )
    await db.execute(
        sa.text(
            "INSERT INTO view_history (user_id, property_id) "
            "SELECT :u, p.id FROM property p WHERE p.public_id = :p AND NOT p.is_suppressed "
            "AND NOT EXISTS (SELECT 1 FROM view_history v WHERE v.user_id = :u "
            "AND v.property_id = p.id AND v.viewed_at > now() - :window)"
        ),
        {"u": user.id, "p": body.property_id, "window": VIEW_DEDUPE},
    )
    await db.execute(
        sa.text("DELETE FROM view_history WHERE user_id = :u AND viewed_at < now() - :keep"),
        {"u": user.id, "keep": HISTORY_KEEP},
    )
    await db.commit()


@router.get("/history/views", response_model=Page[ViewOut])
async def views(
    user: HistoryUser,
    db: Db,
    page: Annotated[int, Query(ge=1, le=100)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 50,
) -> Page[ViewOut]:
    """Property pages visited in the last 12 months, newest first."""
    visible = (
        "FROM view_history v JOIN property p ON p.id = v.property_id "
        "WHERE v.user_id = :u AND NOT p.is_suppressed AND v.viewed_at > now() - :keep"
    )
    params = {"u": user.id, "keep": HISTORY_KEEP}
    total: int = (await db.execute(sa.text(f"SELECT count(*) {visible}"), params)).scalar_one()
    rows = (
        await db.execute(
            sa.text(
                f"SELECT v.id, p.public_id, p.address_display, v.viewed_at {visible} "
                "ORDER BY v.viewed_at DESC, v.id DESC LIMIT :limit OFFSET :offset"
            ),
            {**params, "limit": page_size, "offset": (page - 1) * page_size},
        )
    ).all()
    return Page[ViewOut](
        items=[ViewOut(id=r[0], property_id=r[1], address=r[2], viewed_at=r[3]) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/history/views", status_code=204)
async def clear_views(user: HistoryUser, db: Db) -> None:
    await db.execute(sa.text("DELETE FROM view_history WHERE user_id = :u"), {"u": user.id})
    await db.commit()


@router.delete("/history/views/{view_id}", status_code=204)
async def delete_view(view_id: int, user: HistoryUser, db: Db) -> None:
    done = await db.execute(
        sa.text("DELETE FROM view_history WHERE id = :id AND user_id = :u RETURNING id"),
        {"id": view_id, "u": user.id},
    )
    if done.one_or_none() is None:
        raise NOT_FOUND
    await db.commit()
