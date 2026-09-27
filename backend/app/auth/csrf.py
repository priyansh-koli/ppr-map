"""CSRF: a signed double-submit token (D-008).

Every API response sets a `ppr_csrf` cookie if the caller has none. The value is
`random.signature`, readable by our own JavaScript, which echoes it in `X-CSRF-Token` on
every POST, PUT, PATCH and DELETE. Another site can make the browser send the cookie but
cannot read it, and cannot set a custom header without CORS (which the API does not allow).
The signature only rejects values the server never issued; it does not tie the token to a
session, so the header check is the protection.
"""

import hashlib
import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings, secure_cookies

COOKIE = "ppr_csrf"
HEADER = "X-CSRF-Token"
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _sign(value: str) -> str:
    key = (get_settings().csrf_secret or "development-only").encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:32]


def new_csrf_token() -> str:
    value = secrets.token_urlsafe(24)
    return f"{value}.{_sign(value)}"


def _same(a: str, b: str) -> bool:
    # compare_digest raises TypeError on non-ASCII str; bytes always compare.
    return hmac.compare_digest(a.encode(), b.encode())


def valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    value, signature = token.rsplit(".", 1)
    return _same(signature, _sign(value))


def _set_cookie(response: Response) -> None:
    response.set_cookie(
        COOKIE,
        new_csrf_token(),
        httponly=False,
        secure=secure_cookies(get_settings()),
        samesite="lax",
        path="/",
    )


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        cookie = request.cookies.get(COOKIE)
        if request.method in UNSAFE:
            header = request.headers.get(HEADER)
            if not (valid(cookie) and header and _same(header, cookie or "")):
                refused = JSONResponse(
                    {
                        "type": "about:blank",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Missing or wrong CSRF token; reload the page and try again.",
                    },
                    status_code=403,
                    media_type="application/problem+json",
                )
                # A stale or tampered cookie is replaced, so the page's retry can succeed.
                if not valid(cookie):
                    _set_cookie(refused)
                return refused
        response = await call_next(request)
        if not valid(cookie):
            _set_cookie(response)
        return response
