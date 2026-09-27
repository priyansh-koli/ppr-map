"""argon2id password hashing (argon2-cffi defaults follow RFC 9106's recommendations).

Each hash takes tens of milliseconds and 64 MiB, so it runs in a worker thread (never on the
event loop) and only a few run at once."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 10
MAX_LENGTH = 128

_hasher = PasswordHasher()
# Checked against when the email is unknown, so a login takes as long either way.
_DUMMY_HASH = _hasher.hash("an unused password for timing")
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="argon2")


async def hash_password(password: str) -> str:
    return await asyncio.get_running_loop().run_in_executor(_POOL, _hasher.hash, password)


def _verify(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


async def verify_password(password_hash: str | None, password: str) -> bool:
    return await asyncio.get_running_loop().run_in_executor(_POOL, _verify, password_hash, password)


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problem(password: str, email: str) -> str | None:
    """Why a new password is refused, or None. Length over rules (NIST SP 800-63B)."""
    if len(password) < MIN_LENGTH:
        return f"Use at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Use at most {MAX_LENGTH} characters."
    if password.strip().lower() == email.strip().lower():
        return "Do not use your email address as your password."
    return None
