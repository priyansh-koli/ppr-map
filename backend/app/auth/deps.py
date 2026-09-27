"""Who is calling, and what they may do. The frontend only hides UI; these enforce."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import Perm, Role, permissions_for
from app.auth.sessions import CurrentUser, load_session
from app.config import get_settings, secure_cookies
from app.db import get_session
from app.redis_client import get_redis


def session_cookie_name() -> str:
    # __Host- needs Secure, which http://localhost in development does not have.
    return "__Host-ppr_session" if secure_cookies(get_settings()) else "ppr_session"


async def optional_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_session)],
    cache: Annotated[Redis | None, Depends(get_redis)],
) -> CurrentUser | None:
    token = request.cookies.get(session_cookie_name())
    return await load_session(db, cache, token) if token else None


async def current_user(
    user: Annotated[CurrentUser | None, Depends(optional_user)],
) -> CurrentUser:
    if user is None:
        raise HTTPException(401, "Sign in first")
    return user


def require(perm: Perm) -> Callable[..., Awaitable[CurrentUser | None]]:
    """A dependency that allows the call only with `perm`. Anonymous permissions need no
    sign-in; any other one returns 401 when signed out and 403 when not granted."""

    async def check(
        user: Annotated[CurrentUser | None, Depends(optional_user)],
    ) -> CurrentUser | None:
        if perm in permissions_for({Role.ANONYMOUS}):
            return user
        if user is None:
            raise HTTPException(401, "Sign in first")
        if perm not in user.permissions:
            raise HTTPException(403, "Not allowed")
        return user

    return check


OptionalUser = Annotated[CurrentUser | None, Depends(optional_user)]
User = Annotated[CurrentUser, Depends(current_user)]
