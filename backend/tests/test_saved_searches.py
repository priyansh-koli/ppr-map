"""Saved searches, alerts, CSV export and unsubscribe (D-050), on the real Carlow fixtures."""

import asyncio
import csv
import io
import re
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.services import alerts
from tests.conftest import FakeRedis, Outbox, signed_in

pytestmark = pytest.mark.db

URL = "/api/v1/me/saved-searches"
NEW_HASH = "e" * 64


@pytest.fixture
def db(carlow_db: sa.Engine) -> Iterator[sa.Engine]:
    yield carlow_db
    with carlow_db.begin() as conn:
        conn.execute(sa.text("DELETE FROM app_user"))
        conn.execute(sa.text("DELETE FROM sale WHERE source_row_hash = :h"), {"h": NEW_HASH})


def verified(outbox: Outbox, email: str) -> TestClient:
    client = signed_in(outbox, FakeRedis(), email)
    token = outbox.token_for(email)
    assert client.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 200
    return client


def run_alerts(frequency: str = "on_data_update") -> tuple[alerts.Result, Outbox]:
    from app.db import get_engine, get_sessionmaker

    outbox = Outbox()

    async def go() -> alerts.Result:
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()
        try:
            async with get_sessionmaker()() as session:
                return await alerts.send_alerts(session, outbox, frequency)
        finally:
            await get_engine().dispose()

    return asyncio.run(go()), outbox


RUN = (
    "INSERT INTO ingest_run (kind, status, started_at, finished_at, rows_read, rows_inserted, "
    "rows_withdrawn, rows_failed) VALUES (CAST(:kind AS ingest_kind), 'succeeded', "
    "clock_timestamp(), clock_timestamp(), 0, 0, 0, 0) RETURNING id"
)


def pipeline_step(db: sa.Engine, kind: str) -> int:
    with db.begin() as conn:
        return int(conn.execute(sa.text(RUN), {"kind": kind}).scalar_one())


def new_register_update(
    db: sa.Engine, address: str, price: int, steps: tuple[str, ...] = ("geocode", "aggregate")
) -> None:
    """A later PPR run that files one more sale of an existing Carlow property, then the
    pipeline steps that complete the update (geocoding, then the aggregate)."""
    with db.begin() as conn:
        run = conn.execute(sa.text(RUN), {"kind": "ppr"}).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO sale (property_id, source_row_hash, raw_date, raw_address, "
                "raw_county, raw_eircode, raw_price, raw_nfmp, raw_vat, raw_description, "
                "raw_size, sale_date, price_eur, not_full_market_price, vat_exclusive, is_new, "
                "first_seen_run_id, last_seen_run_id) "
                "SELECT id, :h, '', '', '', '', '', '', '', '', '', '2025-12-01', :price, false, "
                "false, false, :run, :run FROM property WHERE address_display = :a"
            ),
            {"h": NEW_HASH, "price": price, "run": run, "a": address},
        )
    for kind in steps:
        pipeline_step(db, kind)


def test_saving_and_editing_searches(db: sa.Engine) -> None:
    client = signed_in(Outbox(), FakeRedis(), "orla@example.ie")
    body = {
        "name": "  Carlow under 300k ",
        "query": {"county": "Carlow", "priceMax": "300000", "sort": "price", "page": "3"},
        "alertFrequency": "on_data_update",
    }
    res = client.post(URL, json=body)
    assert res.status_code == 201, res.text
    saved = res.json()
    assert saved["name"] == "Carlow under 300k"
    assert saved["query"] == {"county": "carlow", "priceMax": "300000", "sort": "price"}
    assert saved["alertsActive"] is False  # not verified yet: nothing will be sent

    bad = client.post(URL, json={**body, "query": {"county": "narnia"}})
    assert bad.status_code == 422 and "not a valid search" in str(bad.json())

    sid = saved["id"]
    changed = client.patch(f"{URL}/{sid}", json={"name": "Carlow", "alertFrequency": "weekly"})
    assert changed.json()["alertFrequency"] == "weekly" and changed.json()["name"] == "Carlow"
    assert client.patch(f"{URL}/{sid}", json={"name": None}).status_code == 422
    assert [s["id"] for s in client.get(URL).json()] == [sid]

    other = signed_in(Outbox(), FakeRedis(), "pat@example.ie")
    assert other.get(f"{URL}/{sid}").status_code == 404
    assert other.delete(f"{URL}/{sid}").status_code == 404
    assert client.delete(f"{URL}/{sid}").status_code == 204
    assert client.get(URL).json() == []


def test_alerts_report_each_new_sale_once(db: sa.Engine) -> None:
    outbox = Outbox()
    client = verified(outbox, "aine@example.ie")
    unverified = signed_in(Outbox(), FakeRedis(), "ciara@example.ie")
    search = {"name": "Carlow", "query": {"county": "carlow"}, "alertFrequency": "on_data_update"}
    assert client.post(URL, json=search).status_code == 201
    assert unverified.post(URL, json=search).status_code == 201
    weekly = {**search, "name": "Weekly", "alertFrequency": "weekly"}
    assert client.post(URL, json=weekly).status_code == 201

    # Nothing new since the searches were saved.
    nothing, sent = run_alerts()
    assert (nothing.sent, sent.sent) == (0, [])

    new_register_update(db, "178 Pollerton Road, Carlow", 255000)
    result, sent = run_alerts()
    assert (result.checked, result.sent) == (1, 1)  # the unverified account gets nothing
    email = sent.sent[0]
    assert email.to == "aine@example.ie"
    assert email.subject == "1 new sale: Carlow"
    assert "178 Pollerton Road, Carlow" in email.body and "€255,000" in email.body
    assert "/search?county=carlow" in email.body
    assert dict(email.headers)["List-Unsubscribe"].startswith("<http")

    again, sent_again = run_alerts()
    assert (again.checked, sent_again.sent) == (0, [])  # reported once
    listed = {s["name"]: s for s in client.get(URL).json()}
    assert listed["Carlow"]["lastAlertMatches"] == 1 and listed["Carlow"]["lastAlertedAt"]

    weekly_run, weekly_sent = run_alerts("weekly")
    assert weekly_run.sent == 1 and weekly_sent.sent[0].subject == "1 new sale: Weekly"


def test_alerts_wait_for_new_homes_to_be_placed(db: sa.Engine) -> None:
    """An aggregate run before geocoding used to mark the update as alerted while its new
    homes had no location, so their sales were never reported (P1 #19)."""
    outbox = Outbox()
    client = verified(outbox, "fiona@example.ie")
    search = {"name": "Carlow", "query": {"county": "carlow"}, "alertFrequency": "on_data_update"}
    assert client.post(URL, json=search).status_code == 201
    address = "178 Pollerton Road, Carlow"
    with db.begin() as conn:
        placed = conn.execute(
            sa.text(
                "SELECT geom, geocode_confidence, geocoded_at FROM property "
                "WHERE address_display = :a"
            ),
            {"a": address},
        ).one()
        # As a home first seen in this update: not placed yet.
        conn.execute(
            sa.text(
                "UPDATE property SET geom = NULL, geocode_confidence = 'unmatched', "
                "geocoded_at = NULL WHERE address_display = :a"
            ),
            {"a": address},
        )
    try:
        new_register_update(db, address, 262000, steps=("aggregate",))
        early, sent = run_alerts()
        assert (early.checked, sent.sent) == (0, [])  # not ready: nothing checked or sent
        with db.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE property SET geom = :g, geocode_confidence = :c, geocoded_at = :t "
                    "WHERE address_display = :a"
                ),
                {"g": placed[0], "c": placed[1], "t": placed[2], "a": address},
            )
        pipeline_step(db, "geocode")
        waiting, sent = run_alerts()
        assert (waiting.checked, sent.sent) == (0, [])  # placed, but not aggregated since
        pipeline_step(db, "aggregate")
        result, sent = run_alerts()
        assert result.sent == 1 and "€262,000" in sent.sent[0].body
    finally:
        with db.begin() as conn:
            conn.execute(
                sa.text(
                    "UPDATE property SET geom = :g, geocode_confidence = :c, geocoded_at = :t "
                    "WHERE address_display = :a"
                ),
                {"g": placed[0], "c": placed[1], "t": placed[2], "a": address},
            )


def test_unsubscribe_link(db: sa.Engine) -> None:
    outbox = Outbox()
    client = verified(outbox, "eoin@example.ie")
    body = {"name": "Mine", "query": {}, "alertFrequency": "weekly"}
    sid = client.post(URL, json=body).json()["id"]
    token = alerts.unsubscribe_token(__import__("uuid").UUID(sid))
    stranger = signed_in(Outbox(), FakeRedis(), "stranger@example.ie")
    assert (
        stranger.post("/api/v1/alerts/unsubscribe", json={"token": token[:-1] + "0"}).status_code
        == 400
    )
    res = stranger.post("/api/v1/alerts/unsubscribe", json={"token": token})
    assert res.json() == {"name": "Mine"}
    assert client.get(f"{URL}/{sid}").json()["alertFrequency"] == "off"


def read_csv(text: str) -> tuple[list[str], list[dict[str, Any]]]:
    notes = [line for line in text.splitlines() if line.startswith("#")]
    rows = list(
        csv.DictReader(
            io.StringIO("\n".join(x for x in text.splitlines() if not x.startswith("#")))
        )
    )
    return notes, rows


def test_csv_export(db: sa.Engine) -> None:
    redis = FakeRedis()
    client = signed_in(Outbox(), redis, "fiona@example.ie")
    sid = client.post(URL, json={"name": "All", "query": {"sort": "-price"}}).json()["id"]
    res = client.get(f"{URL}/{sid}/export.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert re.search(r'filename="ppr-map-search-\d{8}\.csv"', res.headers["content-disposition"])
    notes, rows = read_csv(res.text)
    assert any("OpenStreetMap" in n for n in notes) and any(
        "PSRA" in n or "Property Services" in n for n in notes
    )
    assert len(rows) == 30
    prices = [float(r["price_eur"]) for r in rows]
    assert prices == sorted(prices, reverse=True)
    assert rows[0]["url"].startswith("http") and rows[0]["location_precision"] in (
        "exact",
        "street",
        "locality",
    )
    for _ in range(9):
        assert client.get(f"{URL}/{sid}/export.csv").status_code == 200
    assert client.get(f"{URL}/{sid}/export.csv").status_code == 429  # 10 a day for a user
