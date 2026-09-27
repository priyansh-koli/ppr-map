"""Opaque server-side sessions (D-008).

The cookie holds a random token; the database holds only its keyed hash. A session ends
after 14 days without use or 90 days in all, and at once on logout, password change or
account deletion. Lookups are cached in Redis for a minute; revoking deletes the cache key
and leaves a short-lived marker, so a lookup that raced the revocation cannot re-cache it.
"""

import contextlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Perm, Role, permissions_for
from app.auth.tokens import new_token, token_hash
from app.redis_client import REDIS_ERRORS

IDLE = timedelta(days=14)
ABSOLUTE = timedelta(days=90)
TOUCH_EVERY = timedelta(minutes=5)
CACHE_TTL_S = 60


@dataclass(frozen=True, slots=True)
class CurrentUser:
    id: uuid.UUID
    email: str
    full_name: str
    email_verified: bool
    history_enabled: bool
    roles: frozenset[Role]
    session_id: int

    @property
    def permissions(self) -> frozenset[Perm]:
        return permissions_for(set(self.roles))


LOOKUP = """
SELECT s.id, s.last_seen_at, u.id, u.email, u.full_name, u.email_verified_at IS NOT NULL,
       u.history_enabled,
       coalesce(array_agg(r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles
FROM user_session s
JOIN app_user u ON u.id = s.user_id
LEFT JOIN user_role ur ON ur.user_id = u.id
LEFT JOIN role r ON r.id = ur.role_id
WHERE s.token_hash = :hash AND s.expires_at > now() AND s.last_seen_at > now() - :idle
  AND u.is_active AND u.deleted_at IS NULL
GROUP BY s.id, u.id
"""


def _cache_key(hash_: str) -> str:
    return f"session:{hash_}"


def _revoked_key(hash_: str) -> str:
    return f"session-revoked:{hash_}"


async def create_session(
    db: AsyncSession, user_id: uuid.UUID, ip_hash: str | None, user_agent: str | None
) -> str:
    token = new_token()
    await db.execute(
        sa.text(
            "INSERT INTO user_session (token_hash, user_id, last_seen_at, expires_at, ip_hash, "
            "user_agent) VALUES (:h, :u, now(), now() + :absolute, :ip, :ua)"
        ),
        {
            "h": token_hash(token),
            "u": user_id,
            "absolute": ABSOLUTE,
            "ip": ip_hash,
            "ua": user_agent,
        },
    )
    return token


async def load_session(db: AsyncSession, cache: Redis | None, token: str) -> CurrentUser | None:
    hash_ = token_hash(token)
    if cache is not None:
        try:
            hit, revoked = await cache.mget(_cache_key(hash_), _revoked_key(hash_))
            if revoked:
                return None
            if hit:
                d = json.loads(hit)
                return CurrentUser(
                    id=uuid.UUID(d["id"]),
                    email=d["email"],
                    full_name=d["full_name"],
                    email_verified=d["email_verified"],
                    history_enabled=d["history_enabled"],
                    roles=frozenset(Role(r) for r in d["roles"]),
                    session_id=d["session_id"],
                )
        except REDIS_ERRORS:
            cache = None
    row = (await db.execute(sa.text(LOOKUP), {"hash": hash_, "idle": IDLE})).one_or_none()
    if row is None:
        return None
    session_id, last_seen = row[0], row[1]
    if datetime.now(UTC) - last_seen > TOUCH_EVERY:
        await db.execute(
            sa.text("UPDATE user_session SET last_seen_at = now() WHERE id = :id"),
            {"id": session_id},
        )
        await db.commit()
    user = CurrentUser(
        id=row[2],
        email=row[3],
        full_name=row[4],
        email_verified=row[5],
        history_enabled=row[6],
        roles=frozenset(Role(r) for r in row[7] if r in Role.__members__.values()),
        session_id=session_id,
    )
    if cache is not None:
        payload = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "email_verified": user.email_verified,
            "history_enabled": user.history_enabled,
            "roles": sorted(user.roles),
            "session_id": user.session_id,
        }
        with contextlib.suppress(*REDIS_ERRORS):
            await cache.set(_cache_key(hash_), json.dumps(payload), ex=CACHE_TTL_S)
    return user


async def revoke_sessions(
    db: AsyncSession,
    cache: Redis | None,
    user_id: uuid.UUID,
    *,
    only: int | None = None,
    keep: int | None = None,
) -> None:
    """End one session (`only`), or all of a user's sessions except `keep`. Commits the
    caller's transaction first, so the cache is cleared only once the rows are gone."""
    rows = await db.execute(
        sa.text(
            "DELETE FROM user_session WHERE user_id = :u "
            "AND (CAST(:only AS bigint) IS NULL OR id = :only) "
            "AND (CAST(:keep AS bigint) IS NULL OR id <> :keep) RETURNING token_hash"
        ),
        {"u": user_id, "only": only, "keep": keep},
    )
    hashes = [r[0] for r in rows]
    await db.commit()
    if cache is not None and hashes:
        with contextlib.suppress(*REDIS_ERRORS):
            async with cache.pipeline(transaction=False) as pipe:
                for h in hashes:
                    pipe.set(_revoked_key(h), "1", ex=2 * CACHE_TTL_S)
                pipe.delete(*(_cache_key(h) for h in hashes))
                await pipe.execute()


async def forget_cached_user(cache: Redis | None, db: AsyncSession, user_id: uuid.UUID) -> None:
    """After a profile change, drop the cached copies of the user's sessions."""
    if cache is None:
        return
    rows = await db.execute(
        sa.text("SELECT token_hash FROM user_session WHERE user_id = :u"), {"u": user_id}
    )
    keys = [_cache_key(r[0]) for r in rows]
    if keys:
        with contextlib.suppress(*REDIS_ERRORS):
            await cache.delete(*keys)
