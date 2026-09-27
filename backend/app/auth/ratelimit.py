"""Fixed-window rate limits in Redis (docs/permissions.md). If Redis is down, requests are
allowed: the limits protect against abuse, they are not a correctness guarantee."""

import contextlib

from fastapi import HTTPException
from redis.asyncio import Redis

from app.redis_client import REDIS_ERRORS


async def limit(cache: Redis | None, key: str, max_calls: int, window_s: int) -> None:
    if cache is None:
        return
    try:
        full = f"ratelimit:{key}"
        count = await cache.incr(full)
        # NX on every call, not only the first: if that first EXPIRE was lost, a key without a
        # TTL would otherwise refuse the caller for ever.
        await cache.expire(full, window_s, nx=True)
        if count > max_calls:
            ttl = await cache.ttl(full)
            raise HTTPException(
                429, "Too many attempts; try again later", headers={"Retry-After": str(max(ttl, 1))}
            )
    except REDIS_ERRORS:
        return


async def forget(cache: Redis | None, key: str) -> None:
    """Reset a limit, e.g. after a successful sign-in."""
    if cache is None:
        return
    with contextlib.suppress(*REDIS_ERRORS):
        await cache.delete(f"ratelimit:{key}")
