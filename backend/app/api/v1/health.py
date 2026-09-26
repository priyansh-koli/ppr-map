from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.schemas.base import ApiModel

router = APIRouter(tags=["meta"])

CheckStatus = Literal["ok", "error"]


class Health(ApiModel):
    status: CheckStatus
    database: CheckStatus
    redis: CheckStatus


async def ping_database(session: AsyncSession) -> None:
    await session.execute(sa.text("SELECT 1"))


async def _ping_redis() -> None:
    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    try:
        await client.ping()
    finally:
        await client.aclose()


def get_redis_ping() -> Callable[[], Awaitable[None]]:
    return _ping_redis


async def _check(probe: Awaitable[None]) -> CheckStatus:
    try:
        await probe
    except Exception:
        return "error"
    return "ok"


@router.get("/health", response_model=Health, responses={503: {"model": Health}})
async def health(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis_ping: Annotated[Callable[[], Awaitable[None]], Depends(get_redis_ping)],
) -> Health:
    """Liveness and dependency check: database and Redis."""
    result = Health(
        status="ok",
        database=await _check(ping_database(session)),
        redis=await _check(redis_ping()),
    )
    if "error" in (result.database, result.redis):
        result.status = "error"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
