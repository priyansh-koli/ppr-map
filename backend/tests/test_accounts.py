"""Accounts end to end: registration, email links, sessions, CSRF, rate limits, and each
user's own wishlist and history (docs/api.md, docs/permissions.md, D-008).

Needs TEST_DATABASE_URL and the pipeline package (for real properties to save).
"""

import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.policies import PRIVACY_VERSION, TERMS_VERSION
from app.redis_client import get_redis
from app.services.email import Email, get_mailer
from tests.conftest import make_api, property_id

pytestmark = pytest.mark.db

PASSWORD = "correct horse battery"


class Outbox:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)

    def token_for(self, to: str) -> str:
        body = next(e.body for e in reversed(self.sent) if e.to == to and "token=" in e.body)
        match = re.search(r"token=([\w-]+)", body)
        assert match, body
        return match.group(1)


class FakeRedis:
    """Enough of redis.asyncio.Redis for the caches and rate limits."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    async def get(self, key: str) -> Any:
        return self.data.get(key)

    async def mget(self, *keys: str) -> list[Any]:
        return [self.data.get(k) for k in keys]

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.data[key] = value

    async def delete(self, *keys: str) -> None:
        for k in keys:
            self.data.pop(k, None)

    async def incr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key, 0)) + 1
        return int(self.data[key])

    async def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        return None

    async def ttl(self, key: str) -> int:
        return 60

    def pipeline(self, transaction: bool = True) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    """Queues calls and runs them on `execute`, like redis.asyncio's pipeline."""

    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.calls: list[Any] = []

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.calls.append(self.redis.set(key, value, ex))

    def delete(self, *keys: str) -> None:
        self.calls.append(self.redis.delete(*keys))

    async def execute(self) -> list[Any]:
        return [await c for c in self.calls]


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def db(carlow_db: sa.Engine) -> Iterator[sa.Engine]:
    yield carlow_db
    with carlow_db.begin() as conn:
        conn.execute(sa.text("DELETE FROM app_user"))


def browser(outbox: Outbox, redis: FakeRedis) -> TestClient:
    """A client that behaves like our frontend: it echoes the CSRF cookie in a header."""

    async def cache() -> AsyncIterator[FakeRedis]:
        yield redis

    client = make_api({get_mailer: lambda: outbox, get_redis: cache})
    client.get("/api/v1/auth/policies")
    client.headers["X-CSRF-Token"] = client.cookies["ppr_csrf"]
    return client


def register(client: TestClient, email: str, **extra: Any) -> Any:
    body = {
        "fullName": "Aoife Byrne",
        "email": email,
        "password": PASSWORD,
        "age18Plus": True,
        "acceptTerms": True,
        "termsVersion": TERMS_VERSION,
        "privacyVersion": PRIVACY_VERSION,
        **extra,
    }
    return client.post("/api/v1/auth/register", json=body)


def signed_in(outbox: Outbox, redis: FakeRedis, email: str) -> TestClient:
    client = browser(outbox, redis)
    assert register(client, email).status_code == 202
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return client


def test_register_verify_and_sign_in(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = browser(outbox, redis)
    res = register(client, "Aoife@Example.ie", marketingOptIn=True)
    assert res.status_code == 202
    assert outbox.sent[-1].subject == "Confirm your email for PPR Map"

    # The same email again: the same answer, and an email saying so, not a second account.
    assert register(client, "aoife@example.ie").json() == res.json()
    assert outbox.sent[-1].subject == "You already have a PPR Map account"
    with db.connect() as conn:
        users = conn.execute(sa.text("SELECT count(*) FROM app_user")).scalar_one()
        consents = conn.execute(sa.text("SELECT count(*) FROM consent_record")).scalar_one()
    assert (users, consents) == (1, 4)

    token = outbox.token_for("aoife@example.ie")
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400

    wrong = client.post(
        "/api/v1/auth/login", json={"email": "aoife@example.ie", "password": "nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.ie", "password": "x"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]

    ok = client.post("/api/v1/auth/login", json={"email": "AOIFE@example.ie", "password": PASSWORD})
    assert ok.status_code == 200
    me = client.get("/api/v1/me").json()
    assert me["email"] == "aoife@example.ie" and me["emailVerified"] is True
    assert me["roles"] == ["user"] and "wishlist:write" in me["permissions"]
    assert "admin:users" not in me["permissions"]
    assert me["marketingOptIn"] is True

    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/me").status_code == 401


def test_registration_rules(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = browser(outbox, redis)
    assert register(client, "a@example.ie", password="short").status_code == 422
    assert register(client, "a@example.ie", age18Plus=False).status_code == 422
    assert register(client, "a@example.ie", termsVersion="2020-01-01").status_code == 409
    assert outbox.sent == []


def test_state_changes_need_the_csrf_header(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    client = browser(outbox, redis)
    del client.headers["X-CSRF-Token"]
    res = register(client, "b@example.ie")
    assert res.status_code == 403 and "CSRF" in res.json()["detail"]
    client.headers["X-CSRF-Token"] = "forged.value"
    client.cookies.set("ppr_csrf", "forged.value")
    assert register(client, "b@example.ie").status_code == 403


def test_password_reset_signs_out_everywhere(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    phone = signed_in(outbox, redis, "c@example.ie")
    laptop = browser(outbox, redis)
    assert (
        laptop.post("/api/v1/auth/forgot-password", json={"email": "nobody@x.ie"}).status_code
        == 202
    )
    sent_before = len(outbox.sent)
    assert (
        laptop.post("/api/v1/auth/forgot-password", json={"email": "c@example.ie"}).status_code
        == 202
    )
    assert len(outbox.sent) == sent_before + 1
    token = outbox.token_for("c@example.ie")
    new = "a much better passphrase"
    assert (
        laptop.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": new}
        ).status_code
        == 200
    )
    assert (
        laptop.post(
            "/api/v1/auth/reset-password", json={"token": token, "password": new}
        ).status_code
        == 400
    )
    assert phone.get("/api/v1/me").status_code == 401
    assert outbox.sent[-1].subject == "Your PPR Map password was changed"
    login = laptop.post("/api/v1/auth/login", json={"email": "c@example.ie", "password": new})
    assert login.status_code == 200


def test_changing_password_keeps_this_session_only(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    here = signed_in(outbox, redis, "d@example.ie")
    there = browser(outbox, redis)
    there.post("/api/v1/auth/login", json={"email": "d@example.ie", "password": PASSWORD})
    body = {"currentPassword": PASSWORD, "newPassword": "another long passphrase"}
    assert (
        here.post("/api/v1/me/password", json={**body, "currentPassword": "wrong"}).status_code
        == 403
    )
    assert here.post("/api/v1/me/password", json=body).status_code == 204
    assert here.get("/api/v1/me").status_code == 200
    assert there.get("/api/v1/me").status_code == 401


def test_login_is_rate_limited(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = browser(outbox, redis)
    codes = [
        client.post(
            "/api/v1/auth/login", json={"email": "e@example.ie", "password": "x"}
        ).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_wishlist_is_private_to_its_owner(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    alice = signed_in(outbox, redis, "alice@example.ie")
    bob = signed_in(outbox, redis, "bob@example.ie")
    pid = property_id(db, "178 Pollerton Road, Carlow")
    added = alice.post("/api/v1/me/wishlist", json={"propertyId": pid, "note": "near the park"})
    assert added.status_code == 201
    item = added.json()
    assert item["title"] == "178 Pollerton Road, Carlow" and item["latestPriceEur"] == 240000
    again = alice.post("/api/v1/me/wishlist", json={"propertyId": pid})
    assert again.json()["id"] == item["id"]  # saved once
    area = alice.post("/api/v1/me/wishlist", json={"areaSlug": "carlow"})
    assert area.status_code == 201 and area.json()["kind"] == "area"

    assert [i["id"] for i in bob.get("/api/v1/me/wishlist").json()] == []
    assert bob.patch(f"/api/v1/me/wishlist/{item['id']}", json={"note": "mine"}).status_code == 404
    assert bob.delete(f"/api/v1/me/wishlist/{item['id']}").status_code == 404
    assert bob.get("/api/v1/me/wishlist/compare", params={"ids": pid}).status_code == 404

    noted = alice.patch(f"/api/v1/me/wishlist/{item['id']}", json={"note": "offer in"})
    assert noted.json()["note"] == "offer in"
    assert alice.delete(f"/api/v1/me/wishlist/{item['id']}").status_code == 204
    assert len(alice.get("/api/v1/me/wishlist").json()) == 1
    signed_out = browser(outbox, redis)
    assert signed_out.get("/api/v1/me/wishlist").status_code == 401


def test_compare_up_to_four(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "f@example.ie")
    addresses = [
        "178 Pollerton Road, Carlow",
        "8 Pollerton Road, Carlow",
        "143 Cois Dara, Chapelstown, Carlow",
        "1 Sherwood, Pollerton, Carlow",
        "4 The Downs, Pollerton, Carlow",
    ]
    ids = [property_id(db, a) for a in addresses]
    for pid in ids:
        client.post("/api/v1/me/wishlist", json={"propertyId": pid})
    res = client.get("/api/v1/me/wishlist/compare", params={"ids": ",".join(ids[:4])})
    assert [s["address"] for s in res.json()] == addresses[:4]
    too_many = client.get("/api/v1/me/wishlist/compare", params={"ids": ",".join(ids)})
    assert too_many.status_code == 422


def test_view_history(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "g@example.ie")
    pid = property_id(db, "178 Pollerton Road, Carlow")
    for _ in range(3):
        assert client.post("/api/v1/me/history/views", json={"propertyId": pid}).status_code == 204
    views = client.get("/api/v1/me/history/views").json()
    assert [v["propertyId"] for v in views] == [pid]  # one visit, not three
    assert client.delete(f"/api/v1/me/history/views/{views[0]['id']}").status_code == 204

    assert (
        client.patch("/api/v1/me", json={"historyEnabled": False}).json()["historyEnabled"] is False
    )
    client.post("/api/v1/me/history/views", json={"propertyId": pid})
    assert client.get("/api/v1/me/history/views").json() == []


def test_export_and_delete_account(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "h@example.ie")
    client.post(
        "/api/v1/me/wishlist", json={"propertyId": property_id(db, "178 Pollerton Road, Carlow")}
    )
    export = client.get("/api/v1/me/export")
    assert export.headers["content-disposition"].startswith("attachment")
    data = export.json()
    assert data["account"]["email"] == "h@example.ie"
    assert data["wishlist"][0]["address"] == "178 Pollerton Road, Carlow"
    assert data["accountDetails"][0]["lastLoginAt"] is not None
    assert {"documentVersion", "recordedAt", "ipHash"} <= set(data["consents"][0])
    assert "tokenHash" not in export.text and "token_hash" not in export.text
    assert {c["kind"] for c in data["consents"]} == {
        "terms",
        "privacy",
        "age_18_plus",
        "marketing_email",
    }
    assert "passwordHash" not in export.text and "password_hash" not in export.text

    assert client.request("DELETE", "/api/v1/me", json={"password": "wrong"}).status_code == 403
    assert client.request("DELETE", "/api/v1/me", json={"password": PASSWORD}).status_code == 204
    assert client.get("/api/v1/me").status_code == 401
    again = client.post("/api/v1/auth/login", json={"email": "h@example.ie", "password": PASSWORD})
    assert again.status_code == 401


def test_idle_sessions_expire(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "i@example.ie")
    redis.data.clear()  # no cached copy
    with db.begin() as conn:
        conn.execute(sa.text("UPDATE user_session SET last_seen_at = now() - interval '15 days'"))
    assert client.get("/api/v1/me").status_code == 401


def test_profile_changes_are_validated_and_partial(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    client = signed_in(outbox, redis, "j@example.ie")
    for bad in (
        {"fullName": None},
        {"fullName": "   "},
        {"fullName": "Aoife\nClick http://evil.example"},
        {"historyEnabled": None},
        {"profile": {"budgetMin": 1e13}},
        {"profile": {"budgetMin": 500000, "budgetMax": 300000}},
    ):
        res = client.patch("/api/v1/me", json=bad)
        assert res.status_code == 422, (bad, res.text)
    assert register(browser(outbox, redis), "k@example.ie", fullName="  ").status_code == 422

    full = {"userType": "first_time_buyer", "counties": ["carlow"], "budgetMax": 300000}
    assert client.patch("/api/v1/me", json={"profile": full}).status_code == 200
    me = client.patch("/api/v1/me", json={"profile": {"budgetMin": 200000}}).json()
    assert me["profile"]["counties"] == ["carlow"] and me["profile"]["budgetMax"] == 300000
    assert me["profile"]["budgetMin"] == 200000
    assert client.patch("/api/v1/me", json={"fullName": "  Aoife B  "}).json()["fullName"] == (
        "Aoife B"
    )

    def consents() -> int:
        with db.connect() as conn:
            return int(
                conn.execute(
                    sa.text(
                        "SELECT count(*) FROM consent_record c JOIN app_user u "
                        "ON u.id = c.user_id WHERE u.email = 'j@example.ie' "
                        "AND c.kind = 'marketing_email'"
                    )
                ).scalar_one()
            )

    before = consents()
    client.patch("/api/v1/me", json={"marketingOptIn": False})  # unchanged
    assert consents() == before
    client.patch("/api/v1/me", json={"marketingOptIn": True})
    assert consents() == before + 1


def test_nul_bytes_are_refused_not_500(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "l@example.ie")
    pid = property_id(db, "178 Pollerton Road, Carlow")
    assert client.post("/api/v1/me/wishlist", json={"propertyId": "a\x00b"}).status_code == 422
    assert (
        client.post("/api/v1/me/wishlist", json={"propertyId": pid, "note": "a\x00"}).status_code
        == 422
    )
    assert client.post("/api/v1/me/history/views", json={"propertyId": "\x00"}).status_code == 422
    assert client.get("/api/v1/me/wishlist/compare", params={"ids": "a\x00b"}).status_code == 422
    assert client.get("/api/v1/properties/%00/summary").status_code == 422
    assert register(browser(outbox, redis), "m@example.ie", fullName="a\x00b").status_code == 422


def test_wishlist_resave_and_withdrawn_properties(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    client = signed_in(outbox, redis, "n@example.ie")
    pid = property_id(db, "8 Pollerton Road, Carlow")
    first = client.post("/api/v1/me/wishlist", json={"propertyId": pid})
    assert first.status_code == 201
    again = client.post("/api/v1/me/wishlist", json={"propertyId": pid, "note": "viewing sat"})
    assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
    assert again.json()["note"] == "viewing sat"
    assert "T" in first.json()["createdAt"]  # ISO 8601
    client.post("/api/v1/me/history/views", json={"propertyId": pid})
    with db.begin() as conn:
        conn.execute(
            sa.text("UPDATE property SET is_suppressed = true WHERE public_id = :p"), {"p": pid}
        )
    try:
        assert client.get("/api/v1/me/wishlist").json() == []
        assert client.get("/api/v1/me/history/views").json() == []
        exported = client.get("/api/v1/me/export").json()
        assert exported["wishlist"][0]["property"] is None
        assert "8 Pollerton Road" not in client.get("/api/v1/me/export").text
    finally:
        with db.begin() as conn:
            conn.execute(
                sa.text("UPDATE property SET is_suppressed = false WHERE public_id = :p"),
                {"p": pid},
            )


def test_reset_link_dies_when_the_password_changes(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    client = signed_in(outbox, redis, "o@example.ie")
    client.post("/api/v1/auth/forgot-password", json={"email": "o@example.ie"})
    token = outbox.token_for("o@example.ie")
    body = {"currentPassword": PASSWORD, "newPassword": "another long passphrase"}
    assert client.post("/api/v1/me/password", json=body).status_code == 204
    reset = client.post(
        "/api/v1/auth/reset-password", json={"token": token, "password": "attacker passphrase"}
    )
    assert reset.status_code == 400


def test_closed_account_email_says_so(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "p@example.ie")
    assert client.request("DELETE", "/api/v1/me", json={"password": PASSWORD}).status_code == 204
    assert register(browser(outbox, redis), "P@example.ie").status_code == 202
    assert outbox.sent[-1].subject == "Your PPR Map account is closed"
    assert register(browser(outbox, redis), "q@example.ie").status_code == 202
    assert register(browser(outbox, redis), "q@example.ie").status_code == 202
    assert outbox.sent[-1].subject == "You already have a PPR Map account"


def test_signing_in_resets_the_limit(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "r@example.ie")
    for _ in range(12):
        res = client.post(
            "/api/v1/auth/login", json={"email": "r@example.ie", "password": PASSWORD}
        )
        assert res.status_code == 200
    assert not any("r@example.ie" in k for k in redis.data)  # the address is hashed


def test_logout_always_clears_the_cookie(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    client = signed_in(outbox, redis, "s@example.ie")
    other = browser(outbox, redis)
    other.cookies.update(client.cookies)
    other.headers["X-CSRF-Token"] = client.headers["X-CSRF-Token"]
    assert client.post("/api/v1/auth/logout-all").status_code == 204
    res = other.post("/api/v1/auth/logout")  # its session had already ended
    assert res.status_code == 204 and "ppr_session=" in res.headers["set-cookie"]


def test_a_revoked_session_is_not_served_from_the_cache(
    db: sa.Engine, outbox: Outbox, redis: FakeRedis
) -> None:
    client = signed_in(outbox, redis, "t@example.ie")
    token = client.cookies["ppr_session"]
    assert client.get("/api/v1/me").status_code == 200
    cached = {k: v for k, v in redis.data.items() if k.startswith("session:")}
    assert cached
    assert client.post("/api/v1/auth/logout-all").status_code == 204
    redis.data.update(cached)  # a lookup that raced the sign-out put its stale copy back
    stolen = browser(outbox, redis)
    stolen.cookies.set("ppr_session", token)
    assert stolen.get("/api/v1/me").status_code == 401


def test_csrf_survives_odd_cookies(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    from app.auth.csrf import valid

    assert valid("abc.\u00e9") is False  # non-ASCII: refused, not a TypeError (500)
    client = browser(outbox, redis)
    client.cookies.set("ppr_csrf", "stale.value")
    client.headers["X-CSRF-Token"] = "stale.value"
    refused = register(client, "u@example.ie")
    assert refused.status_code == 403
    assert "ppr_csrf=" in refused.headers["set-cookie"]  # a fresh token to retry with


def test_daily_purge(db: sa.Engine, outbox: Outbox, redis: FakeRedis) -> None:
    from typer.testing import CliRunner

    from app.cli import cli

    gone = signed_in(outbox, redis, "v@example.ie")
    pid = property_id(db, "178 Pollerton Road, Carlow")
    gone.post("/api/v1/me/wishlist", json={"propertyId": pid})
    assert gone.request("DELETE", "/api/v1/me", json={"password": PASSWORD}).status_code == 204
    kept = signed_in(outbox, redis, "w@example.ie")
    kept.post("/api/v1/me/history/views", json={"propertyId": pid})
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE app_user SET deleted_at = now() - interval '31 days' "
                "WHERE email = 'v@example.ie'"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO audit_log (actor_user_id, action, target_kind, target_id) "
                "SELECT id, 'purge-test', 'test', '1' FROM app_user WHERE email = 'v@example.ie'"
            )
        )
        conn.execute(sa.text("UPDATE view_history SET viewed_at = now() - interval '400 days'"))
    result = CliRunner().invoke(cli, ["purge-deleted"])
    assert result.exit_code == 0, result.output
    with db.connect() as conn:
        emails = conn.execute(sa.text("SELECT email FROM app_user")).scalars().all()
        views = conn.execute(sa.text("SELECT count(*) FROM view_history")).scalar_one()
    assert "v@example.ie" not in emails and "w@example.ie" in emails
    assert views == 0
    assert kept.get("/api/v1/me").status_code == 200
