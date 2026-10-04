"""Reports from the public, and the admin area (D-052), on the real Carlow fixtures."""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from app import jobs
from app.cli import cli
from tests.conftest import PASSWORD, FakeRedis, Outbox, browser, property_id, register, signed_in

pytestmark = pytest.mark.db

POLLERTON = "178 Pollerton Road, Carlow"


@pytest.fixture
def db(carlow_db: sa.Engine) -> Iterator[sa.Engine]:
    yield carlow_db
    with carlow_db.begin() as conn:
        conn.execute(sa.text("DELETE FROM removal_request"))
        conn.execute(sa.text("DELETE FROM app_user"))
        conn.execute(sa.text("UPDATE property SET is_suppressed = false"))


def admin(outbox: Outbox, db: sa.Engine, email: str = "admin@example.ie") -> TestClient:
    client = browser(outbox, FakeRedis())
    assert register(client, email).status_code == 202
    assert CliRunner().invoke(cli, ["grant-role", email, "admin"]).exit_code == 0
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    return client


def test_admin_needs_the_permission(db: sa.Engine) -> None:
    anonymous = browser(Outbox(), FakeRedis())
    assert anonymous.get("/api/v1/admin/users").status_code == 401
    user = signed_in(Outbox(), FakeRedis(), "user@example.ie")
    for path in ("users", "audit-log", "ingest-runs", "removal-requests", "geocode/queue"):
        assert user.get(f"/api/v1/admin/{path}").status_code == 403, path


def test_reports_from_the_public(db: sa.Engine) -> None:
    outbox = Outbox()
    visitor = browser(outbox, FakeRedis())
    pid = property_id(db, POLLERTON)
    body = {
        "propertyId": pid,
        "address": POLLERTON,
        "requestType": "suppress_display",
        "relationship": "owner",
        "reason": "Please stop showing my home",
        "email": "owner@example.ie",
    }
    trap = visitor.post("/api/v1/reports", json={**body, "website": "http://spam"})
    assert trap.status_code == 202 and trap.json()["reference"] == "R-00000000"
    ok = visitor.post("/api/v1/reports", json=body)
    assert ok.status_code == 202 and ok.json()["reference"].startswith("R-")
    assert (
        outbox.sent[-1].to == "owner@example.ie" and ok.json()["reference"] in outbox.sent[-1].body
    )
    with db.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM removal_request")).scalar_one() == 1
    assert visitor.post("/api/v1/reports", json={**body, "propertyId": "nope"}).status_code == 404
    codes = [visitor.post("/api/v1/reports", json=body).status_code for _ in range(3)]
    assert codes[-1] == 429  # 5 an hour per IP, the trap and the 404 included


def test_approving_a_removal_hides_the_property(db: sa.Engine) -> None:
    outbox = Outbox()
    boss = admin(outbox, db)
    pid = property_id(db, POLLERTON)
    visitor = browser(Outbox(), FakeRedis())
    visitor.post(
        "/api/v1/reports",
        json={
            "propertyId": pid,
            "address": POLLERTON,
            "requestType": "suppress_display",
            "relationship": "occupant",
            "email": "occupant@example.ie",
        },
    )
    listed = boss.get("/api/v1/admin/removal-requests").json()
    assert listed["total"] == 1
    item = listed["items"][0]
    assert item["propertyId"] == pid and item["status"] == "new"
    url = f"/api/v1/admin/removal-requests/{item['id']}"
    assert boss.patch(url, json={"status": "in_review"}).json()["status"] == "in_review"
    tiles_before = boss.get("/api/v1/meta").json()["tilesVersion"]
    done = boss.patch(url, json={"status": "approved", "decisionNote": "Hidden."}).json()
    assert done["status"] == "approved" and done["propertySuppressed"] is True
    assert done["decidedBy"] == "admin@example.ie"
    assert boss.get(f"/api/v1/properties/{pid}").status_code == 404
    # Martin caches tiles by URL: the map's `v` must change so the point leaves the map now.
    meta = boss.get("/api/v1/meta").json()
    assert meta["tilesVersion"] != tiles_before
    assert meta["tilesVersion"].startswith(meta["dataVersion"] + ".e")
    assert boss.get("/api/v1/search", params={"county": "carlow"}).json()["total"] == 29
    assert outbox.sent[-1].to == "occupant@example.ie" and "approved" in outbox.sent[-1].subject
    assert boss.patch(url, json={"status": "rejected"}).status_code == 409
    log = boss.get("/api/v1/admin/audit-log", params={"targetKind": "removal_request"}).json()
    assert [e["action"] for e in log["items"]] == ["removal.approved", "removal.in_review"]
    assert "occupant@example.ie" not in str(log)  # no third-party personal data in the log


def test_correcting_a_location(db: sa.Engine) -> None:
    boss = admin(Outbox(), db)
    queue = boss.get("/api/v1/admin/geocode/queue", params={"kind": "locality"}).json()
    assert queue["total"] > 0 and all(i["confidence"] == "locality" for i in queue["items"])
    target = queue["items"][0]["id"]
    # A point inside the fixture's one Small Area: the correction joins it.
    with db.connect() as conn:
        lat, lng = conn.execute(
            sa.text(
                "SELECT ST_Y(p), ST_X(p) FROM (SELECT ST_PointOnSurface(geom) AS p FROM area "
                "WHERE kind = 'small_area' LIMIT 1) t"
            )
        ).one()
    fix = {
        "lat": lat,
        "lng": lng,
        "confidence": "exact",
        "note": "Checked on site plan",
    }
    tiles_before = boss.get("/api/v1/meta").json()["tilesVersion"]
    res = boss.put(f"/api/v1/admin/properties/{target}/geocode", json=fix)
    assert res.status_code == 200, res.text
    assert boss.get("/api/v1/meta").json()["tilesVersion"] != tiles_before
    assert res.json()["inReportedCounty"] is True
    assert any("small_area" in a for a in res.json()["areas"])
    page = boss.get(f"/api/v1/properties/{target}").json()
    assert (
        page["location"]["confidence"] == "exact" and page["location"]["method"] == "admin:manual"
    )
    assert boss.get(f"/api/v1/properties/{target}/summary").json()["confidence"] == "exact"
    locked = boss.get("/api/v1/admin/geocode/queue", params={"kind": "locked"}).json()
    assert [i["id"] for i in locked["items"]] == [target]
    assert (
        boss.put(f"/api/v1/admin/properties/{target}/geocode", json={**fix, "lat": 40}).status_code
        == 422
    )
    entry = boss.get("/api/v1/admin/audit-log", params={"target": target}).json()["items"][0]
    assert (
        entry["action"] == "property.geocode.correct"
        and entry["before"]["confidence"] == "locality"
    )


def test_managing_users(db: sa.Engine) -> None:
    boss = admin(Outbox(), db)
    other_outbox = Outbox()
    other = signed_in(other_outbox, FakeRedis(), "member@example.ie")
    users = boss.get("/api/v1/admin/users", params={"q": "member"}).json()
    assert users["total"] == 1
    uid = users["items"][0]["id"]
    url = f"/api/v1/admin/users/{uid}"
    assert boss.patch(url, json={"roles": ["pro"]}).status_code == 403  # needs the password
    assert boss.patch(url, json={"roles": ["pro"], "password": "wrong password"}).status_code == 403
    pro = boss.patch(url, json={"roles": ["pro"], "password": PASSWORD}).json()
    assert pro["roles"] == ["pro", "user"]  # everyone keeps the user role
    off = boss.patch(url, json={"isActive": False}).json()
    assert off["isActive"] is False
    assert other.get("/api/v1/me").status_code == 401  # signed out everywhere

    me = boss.get("/api/v1/me").json()
    mine = f"/api/v1/admin/users/{me['id']}"
    assert boss.patch(mine, json={"isActive": False}).status_code == 409
    last = boss.patch(mine, json={"roles": ["user"], "password": PASSWORD})
    assert last.status_code == 409 and "at least one active admin" in last.json()["detail"]
    actions = [e["action"] for e in boss.get("/api/v1/admin/audit-log").json()["items"]]
    assert actions[:2] == ["user.change", "user.change"] and "user.role.grant.cli" in actions


def test_user_search_matches_underscores_and_percents(db: sa.Engine) -> None:
    """ "jane_doe@" found nothing: `_` and `%` were deleted from the search (P1 #32)."""
    boss = admin(Outbox(), db, "boss2@example.ie")
    for email in ("jane_doe@example.ie", "janexdoe@example.ie", "100%@example.ie"):
        signed_in(Outbox(), FakeRedis(), email)

    def found(q: str) -> list[str]:
        items = boss.get("/api/v1/admin/users", params={"q": q}).json()["items"]
        return sorted(i["email"] for i in items)

    assert found("jane_doe@") == ["jane_doe@example.ie"]  # `_` is not "any character"
    assert found("100%") == ["100%@example.ie"]
    assert found("%") == ["100%@example.ie"]
    assert found("\\") == []


def test_ingest_runs_and_queueing(db: sa.Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    boss = admin(Outbox(), db)
    runs = boss.get("/api/v1/admin/ingest-runs").json()
    kinds = {r["kind"] for r in runs["items"]}
    assert {"ppr", "geocode", "aggregate"} <= kinds
    geocode = next(r for r in runs["items"] if r["kind"] == "geocode")
    assert set(geocode["stats"]["confidence"]) >= {"exact", "street", "locality"}
    detail = boss.get(f"/api/v1/admin/ingest-runs/{runs['items'][-1]['id']}").json()
    assert "rowErrors" in detail

    queued: list[Any] = []

    def fake_enqueue(step: str, by: str | None) -> Any:
        queued.append((step, by))
        return SimpleNamespace(id="job-1", description=f"pipeline: {step}")

    monkeypatch.setattr(jobs, "enqueue_pipeline", fake_enqueue)
    res = boss.post("/api/v1/admin/ingest-runs", json={"step": "aggregate"})
    assert res.status_code == 202 and res.json()["id"] == "job-1"
    assert queued[0][0] == "aggregate" and queued[0][1] == boss.get("/api/v1/me").json()["id"]
    assert boss.post("/api/v1/admin/ingest-runs", json={"step": "drop"}).status_code == 422

    def busy(step: str, by: str | None) -> Any:
        raise jobs.PipelineBusy("A pipeline step is already queued or running")

    monkeypatch.setattr(jobs, "enqueue_pipeline", busy)
    again = boss.post("/api/v1/admin/ingest-runs", json={"step": "aggregate"})
    assert again.status_code == 409 and "already queued or running" in again.json()["detail"]
    overview = boss.get("/api/v1/admin/overview").json()
    assert overview["users"] == 1 and "ppr" in {r["kind"] for r in overview["lastRuns"]}


def test_the_last_admin_cannot_close_their_account(db: sa.Engine) -> None:
    """P2 #45: closing your own account skipped the last-admin check."""
    boss = admin(Outbox(), db)
    closed = boss.request("DELETE", "/api/v1/me", json={"password": PASSWORD})
    assert closed.status_code == 409
    assert boss.get("/api/v1/me").status_code == 200


def test_two_admins_cannot_demote_each_other_at_once(db: sa.Engine) -> None:
    """P2 #45: each check counted the other as still an admin, so both demotions passed and
    no admin was left. The check now holds a lock until its change commits."""
    import threading
    import time

    a = admin(Outbox(), db, "a@example.ie")
    admin(Outbox(), db, "b@example.ie")
    ids = {
        u["email"]: u["id"] for u in a.get("/api/v1/admin/users", params={"q": "@"}).json()["items"]
    }
    # B demotes A: B's transaction has taken the lock, passed its check (A is not the last)
    # and removed A's role, but has not committed yet.
    b_tx = db.connect()
    tx = b_tx.begin()
    b_tx.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended('keep-an-admin', 0))"))
    b_tx.execute(
        sa.text(
            "DELETE FROM user_role WHERE user_id = :u "
            "AND role_id = (SELECT id FROM role WHERE name = 'admin')"
        ),
        {"u": ids["a@example.ie"]},
    )
    # Meanwhile A demotes B.
    answer: list[int] = []
    body = {"roles": ["user"], "password": PASSWORD}
    a_request = threading.Thread(
        target=lambda: answer.append(
            a.patch(f"/api/v1/admin/users/{ids['b@example.ie']}", json=body).status_code
        )
    )
    a_request.start()
    time.sleep(1)
    tx.commit()
    b_tx.close()
    a_request.join(timeout=30)
    assert answer == [409]
    with db.connect() as conn:
        admins = conn.execute(
            sa.text(
                "SELECT count(*) FROM user_role ur JOIN role r ON r.id = ur.role_id "
                "WHERE r.name = 'admin'"
            )
        ).scalar_one()
    assert admins == 1
