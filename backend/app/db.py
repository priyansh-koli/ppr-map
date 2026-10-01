from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    # psycopg prepares a statement on its sixth run, and Postgres may then plan it once for
    # any parameters. The map filters (`tile_matching_sales`) are only fast when planned with
    # their values: a generic plan took 6 s instead of 36 ms for an area's list (D-054).
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"options": "-c plan_cache_mode=force_custom_plan"},
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
