"""Registration, email verification, sign-in and password reset (docs/api.md, D-008).

Answers never reveal whether an email has an account: registering an existing email and
asking to reset an unknown one both return the same 202, and the email says what happened.
Both branches do the same slow work (a password hash) and send mail after the response, so
timing does not tell them apart either.
"""

import uuid
from datetime import timedelta
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import OptionalUser, User, session_cookie_name
from app.auth.passwords import hash_password, needs_rehash, password_problem, verify_password
from app.auth.ratelimit import forget, limit
from app.auth.sessions import ABSOLUTE, create_session, forget_cached_user, revoke_sessions
from app.auth.tokens import ip_hash, new_token, token_hash
from app.config import get_settings, secure_cookies
from app.db import get_session
from app.policies import PRIVACY_VERSION, TERMS_VERSION
from app.redis_client import get_redis
from app.schemas.auth import (
    Accepted,
    EmailIn,
    LoginIn,
    Me,
    Policies,
    RegisterIn,
    ResetIn,
    TokenIn,
)
from app.services import email as mail
from app.services.accounts import load_me

router = APIRouter(prefix="/auth", tags=["auth"])

Db = Annotated[AsyncSession, Depends(get_session)]
Cache = Annotated[Redis | None, Depends(get_redis)]
Mailer = Annotated[mail.Mailer, Depends(mail.get_mailer)]

VERIFY_FOR = timedelta(hours=24)
RESET_FOR = timedelta(hours=1)
CHECK_EMAIL = "Check your email to continue."
PURGE_AFTER = timedelta(days=30)


def check_email(message: str = CHECK_EMAIL) -> str:
    """A reply that sends mail. In development it says where to read it: Mailpit, not the
    real inbox the user typed."""
    inbox = get_settings().mail_inbox_url
    if not inbox:
        return message
    return f"{message} In development no email leaves this computer: read it in Mailpit at {inbox}."


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        session_cookie_name(),
        token,
        max_age=int(ABSOLUTE.total_seconds()),
        httponly=True,
        secure=secure_cookies(get_settings()),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        session_cookie_name(), path="/", secure=secure_cookies(get_settings()), httponly=True
    )


@router.get("/policies", response_model=Policies)
async def policies() -> Policies:
    """The versions of the terms and privacy policy that registration accepts."""
    return Policies(terms_version=TERMS_VERSION, privacy_version=PRIVACY_VERSION)


async def _issue_verification(db: AsyncSession, user_id: object) -> str:
    token = new_token()
    await db.execute(
        sa.text(
            "INSERT INTO email_verification_token (user_id, token_hash, expires_at) "
            "VALUES (:u, :h, now() + :for)"
        ),
        {"u": user_id, "h": token_hash(token), "for": VERIFY_FOR},
    )
    return token


@router.post("/register", status_code=202, response_model=Accepted)
async def register(
    body: RegisterIn,
    request: Request,
    db: Db,
    cache: Cache,
    mailer: Mailer,
    background: BackgroundTasks,
) -> Accepted:
    """Create an account and email a verification link. Always 202."""
    await limit(cache, f"register:{ip_hash(_ip(request))}", 5, 3600)
    if body.terms_version != TERMS_VERSION or body.privacy_version != PRIVACY_VERSION:
        raise HTTPException(409, "The terms or privacy policy changed; reload and accept again")
    if problem := password_problem(body.password, body.email):
        raise HTTPException(422, problem)
    email = body.email.lower()
    # Hashed before the lookup, so an existing email answers as slowly as a new one.
    password_hash = await hash_password(body.password)
    user_id: uuid.UUID | None = (
        await db.execute(
            sa.text(
                "INSERT INTO app_user (email, password_hash, full_name, marketing_opt_in) "
                "VALUES (:e, :p, :n, :m) ON CONFLICT (email) DO NOTHING RETURNING id"
            ),
            {"e": email, "p": password_hash, "n": body.full_name, "m": body.marketing_opt_in},
        )
    ).scalar_one_or_none()
    if user_id is None:
        closed_at, verified_at = (
            await db.execute(
                sa.text("SELECT deleted_at, email_verified_at FROM app_user WHERE email = :e"),
                {"e": email},
            )
        ).one()
        await db.rollback()
        notice = (
            mail.account_closed(email, (closed_at + PURGE_AFTER).date())
            if closed_at is not None
            else mail.already_registered(email, verified=verified_at is not None)
        )
        background.add_task(mailer.send, notice)
        return Accepted(message=check_email())
    await db.execute(
        sa.text(
            "INSERT INTO user_role (user_id, role_id) SELECT :u, id FROM role WHERE name = 'user'"
        ),
        {"u": user_id},
    )
    profile = body.profile.model_dump() if body.profile else {}
    await db.execute(
        sa.text(
            "INSERT INTO user_profile (user_id, user_type, counties, budget_min, budget_max, "
            "property_interest) VALUES (:u, :t, CAST(:c AS county[]), :bmin, :bmax, :pi)"
        ),
        {
            "u": user_id,
            "t": profile.get("user_type"),
            "c": profile.get("counties"),
            "bmin": profile.get("budget_min"),
            "bmax": profile.get("budget_max"),
            "pi": profile.get("property_interest"),
        },
    )
    ua = request.headers.get("user-agent")
    consents = [
        ("terms", TERMS_VERSION, True),
        ("privacy", PRIVACY_VERSION, True),
        ("age_18_plus", TERMS_VERSION, True),
        ("marketing_email", PRIVACY_VERSION, body.marketing_opt_in),
    ]
    for kind, version, granted in consents:
        await db.execute(
            sa.text(
                "INSERT INTO consent_record (user_id, kind, document_version, granted, ip_hash, "
                "user_agent) VALUES (:u, :k, :v, :g, :ip, :ua)"
            ),
            {
                "u": user_id,
                "k": kind,
                "v": version,
                "g": granted,
                "ip": ip_hash(_ip(request)),
                "ua": ua,
            },
        )
    token = await _issue_verification(db, user_id)
    await db.commit()
    background.add_task(mailer.send, mail.verify_email(email, body.full_name, token))
    return Accepted(message=check_email())


@router.post("/verify-email", response_model=Accepted)
async def verify_email(body: TokenIn, db: Db, cache: Cache) -> Accepted:
    row = (
        await db.execute(
            sa.text(
                "UPDATE email_verification_token SET used_at = now() "
                "WHERE token_hash = :h AND used_at IS NULL AND expires_at > now() "
                "RETURNING user_id"
            ),
            {"h": token_hash(body.token)},
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(400, "This link has expired or was already used")
    await db.execute(
        sa.text(
            "UPDATE app_user SET email_verified_at = coalesce(email_verified_at, now()), "
            "updated_at = now() WHERE id = :u"
        ),
        {"u": row[0]},
    )
    await db.commit()
    await forget_cached_user(cache, db, row[0])
    return Accepted(message="Your email is confirmed.")


@router.post("/resend-verification", status_code=202, response_model=Accepted)
async def resend_verification(
    user: User, db: Db, cache: Cache, mailer: Mailer, background: BackgroundTasks
) -> Accepted:
    await limit(cache, f"resend:{user.id}", 3, 3600)
    if user.email_verified:
        return Accepted(message="Your email is already confirmed.")
    token = await _issue_verification(db, user.id)
    await db.commit()
    background.add_task(mailer.send, mail.verify_email(user.email, user.full_name, token))
    return Accepted(message=check_email())


@router.post("/login", response_model=Me)
async def login(body: LoginIn, request: Request, response: Response, db: Db, cache: Cache) -> Me:
    email = body.email.lower()
    ip = ip_hash(_ip(request))
    # Per address, and a looser one per IP so one client cannot spray many addresses.
    per_email = f"login:{ip}:{token_hash(email)}"
    await limit(cache, per_email, 10, 15 * 60)
    await limit(cache, f"login:{ip}", 100, 15 * 60)
    row = (
        await db.execute(
            sa.text(
                "SELECT id, password_hash FROM app_user "
                "WHERE email = :e AND is_active AND deleted_at IS NULL"
            ),
            {"e": email},
        )
    ).one_or_none()
    # Always verify against a hash, so an unknown email takes as long as a wrong password.
    if not await verify_password(row[1] if row else None, body.password) or row is None:
        raise HTTPException(401, "The email or password is wrong")
    user_id = row[0]
    await forget(cache, per_email)
    if needs_rehash(row[1]):
        await db.execute(
            sa.text("UPDATE app_user SET password_hash = :p WHERE id = :u"),
            {"p": await hash_password(body.password), "u": user_id},
        )
    token = await create_session(db, user_id, ip, request.headers.get("user-agent"))
    await db.execute(
        sa.text("UPDATE app_user SET last_login_at = now() WHERE id = :u"), {"u": user_id}
    )
    await db.commit()
    set_session_cookie(response, token)
    return await load_me(db, user_id)


@router.post("/logout", status_code=204)
async def logout(user: OptionalUser, response: Response, db: Db, cache: Cache) -> None:
    """Sign out. Succeeds, and clears the cookie, even if the session had already ended."""
    if user is not None:
        await revoke_sessions(db, cache, user.id, only=user.session_id)
    clear_session_cookie(response)


@router.post("/logout-all", status_code=204)
async def logout_all(user: User, response: Response, db: Db, cache: Cache) -> None:
    await revoke_sessions(db, cache, user.id)
    clear_session_cookie(response)


@router.post("/forgot-password", status_code=202, response_model=Accepted)
async def forgot_password(
    body: EmailIn,
    request: Request,
    db: Db,
    cache: Cache,
    mailer: Mailer,
    background: BackgroundTasks,
) -> Accepted:
    await limit(cache, f"forgot:{ip_hash(_ip(request))}", 5, 3600)
    email = body.email.lower()
    row = (
        await db.execute(
            sa.text(
                "SELECT id, full_name FROM app_user "
                "WHERE email = :e AND is_active AND deleted_at IS NULL"
            ),
            {"e": email},
        )
    ).one_or_none()
    if row is not None:
        token = new_token()
        await db.execute(
            sa.text(
                "INSERT INTO password_reset_token (user_id, token_hash, expires_at) "
                "VALUES (:u, :h, now() + :for)"
            ),
            {"u": row[0], "h": token_hash(token), "for": RESET_FOR},
        )
        await db.commit()
        background.add_task(mailer.send, mail.reset_password(email, row[1], token))
    return Accepted(
        message=check_email("If that email has an account, a reset link is on its way.")
    )


@router.post("/reset-password", response_model=Accepted)
async def reset_password(
    body: ResetIn, db: Db, cache: Cache, mailer: Mailer, background: BackgroundTasks
) -> Accepted:
    # FOR UPDATE: a second request with the same link waits here, then finds it used.
    row = (
        await db.execute(
            sa.text(
                "SELECT t.id, u.id, u.email, u.full_name FROM password_reset_token t "
                "JOIN app_user u ON u.id = t.user_id "
                "WHERE t.token_hash = :h AND t.used_at IS NULL AND t.expires_at > now() "
                "AND u.is_active AND u.deleted_at IS NULL FOR UPDATE OF t"
            ),
            {"h": token_hash(body.token)},
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(400, "This link has expired or was already used")
    _token_id, user_id, email, name = row
    if problem := password_problem(body.password, email):
        raise HTTPException(422, problem)
    await db.execute(
        sa.text(
            "UPDATE password_reset_token SET used_at = now() WHERE user_id = :u AND used_at IS NULL"
        ),
        {"u": user_id},
    )
    await db.execute(
        sa.text("UPDATE app_user SET password_hash = :p, updated_at = now() WHERE id = :u"),
        {"p": await hash_password(body.password), "u": user_id},
    )
    # Resetting proves control of the email, so the address counts as confirmed.
    await db.execute(
        sa.text(
            "UPDATE app_user SET email_verified_at = coalesce(email_verified_at, now()) "
            "WHERE id = :u"
        ),
        {"u": user_id},
    )
    await revoke_sessions(db, cache, user_id)
    background.add_task(mailer.send, mail.password_changed(email, name))
    return Accepted(message="Your password is changed. Sign in with the new one.")
