"""Random tokens and how they are stored: only a keyed hash ever reaches the database, so a
leaked table cannot be replayed as sessions or reset links."""

import hashlib
import hmac
import secrets

from app.config import get_settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    key = (get_settings().session_secret or "development-only").encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def ip_hash(ip: str | None) -> str | None:
    """IP addresses are kept only as a salted hash (rate limits, session list)."""
    if not ip:
        return None
    salt = (get_settings().ip_hash_salt or "development-only").encode()
    return hmac.new(salt, ip.encode(), hashlib.sha256).hexdigest()
