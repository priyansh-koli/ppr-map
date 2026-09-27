"""One Redis client (a connection pool) per process, for caches, sessions and rate limits.
Redis is an accelerator: every caller handles it being down."""

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import get_settings

# redis-py raises its own exception classes (RedisError, not the built-in ConnectionError).
REDIS_ERRORS = (RedisError, OSError)


class _Shared:
    client: Redis | None = None


async def get_redis() -> Redis | None:
    if _Shared.client is None:
        _Shared.client = Redis.from_url(
            get_settings().redis_url, socket_connect_timeout=0.2, socket_timeout=0.2
        )
    return _Shared.client
