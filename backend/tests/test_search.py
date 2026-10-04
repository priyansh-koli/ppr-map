"""Search, the filters it shares with the map, autocomplete and search history (D-047).

Needs TEST_DATABASE_URL and the pipeline package: the real Carlow fixtures, built the way
production is (`carlow_db` in conftest.py).
"""

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.redis_client import get_redis
from tests.conftest import CARLOW_BBOX, FakeRedis, Outbox, make_api, property_id, signed_in

pytestmark = pytest.mark.db

POLLERTON = "178 Pollerton Road, Carlow"


async def no_cache() -> AsyncIterator[None]:
    yield None


@pytest.fixture
def db(carlow_db: sa.Engine) -> Iterator[sa.Engine]:
    yield carlow_db
    with carlow_db.begin() as conn:
        conn.execute(sa.text("DELETE FROM app_user"))


@pytest.fixture
def api(db: sa.Engine) -> Iterator[TestClient]:
    with make_api({get_redis: no_cache}) as client:
        yield client


def search(api: TestClient, **params: Any) -> Any:
    res = api.get("/api/v1/search", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def tile_count(db: sa.Engine, params: str) -> int:
    """Sales the map's tile function matches anywhere in Ireland with these parameters."""
    with db.connect() as conn:
        return int(
            conn.execute(
                sa.text(
                    "SELECT count(*) FROM tile_matching_sales("
                    "ST_MakeEnvelope(-11, 51, -5, 56, 4326), CAST(:p AS json))"
                ),
                {"p": params},
            ).scalar_one()
        )


def test_search_defaults_match_the_map(api: TestClient, db: sa.Engine) -> None:
    body = search(api)
    assert body["total"] == 30 == tile_count(db, "{}")
    assert body["query"] == {}
    dates = [i["latestSale"]["date"] for i in body["items"]]
    assert dates == sorted(dates, reverse=True)
    w, s, e, n = body["bbox"]
    assert -7.2 < w < e < -6.6 and 52.4 < s < n < 53.0
    listed = api.get("/api/v1/properties", params={"bbox": CARLOW_BBOX}).json()
    assert {i["id"] for i in listed["items"]} <= {i["id"] for i in body["items"]}


def test_place_filters(api: TestClient, db: sa.Engine) -> None:
    assert search(api, county="carlow")["total"] == 30
    assert search(api, county="Cork,KERRY")["total"] == 0
    assert tile_count(db, '{"county": "cork"}') == 0

    town = search(api, area="carlow-1f4955")
    assert 0 < town["total"] <= 30
    assert search(api, area="carlow")["total"] == 30  # a county's slug
    assert search(api, area="no-such-place")["total"] == 0

    assert search(api, routingKey="r93")["total"] > 0
    assert search(api, routingKey="D08")["total"] == 0

    pollerton = api.get(f"/api/v1/properties/{property_id(db, POLLERTON)}").json()["location"]
    near = f"{pollerton['lat']},{pollerton['lng']}"
    close = search(api, near=near, radiusM=150)
    assert POLLERTON in [i["address"] for i in close["items"]]
    assert close["total"] < search(api, near=near, radiusM=5000)["total"]


def test_sale_filters(api: TestClient) -> None:
    vatx = search(api, vat="exclusive")
    assert vatx["total"] == 2 and all(
        i["latestSale"]["flags"]["vatExclusive"] for i in vatx["items"]
    )
    assert search(api, vat="inclusive")["total"] == 28
    assert search(api, type="new")["total"] == 3
    cheap = search(api, priceMax=200000, sort="price")
    prices = [i["latestSale"]["priceEur"] for i in cheap["items"]]
    assert prices == sorted(prices) and all(p <= 200000 for p in prices)
    assert cheap["query"] == {"priceMax": "200000", "sort": "price"}
    # Exponent notation is the same filter, not a silently dropped one.
    sci = search(api, priceMax="2e5", sort="price")
    assert sci["total"] == cheap["total"] and sci["query"] == cheap["query"]


def test_distance_filters_use_precise_locations_only(api: TestClient) -> None:
    near_stop = search(api, maxStopM=10000)
    assert 0 < near_stop["total"] <= 20
    assert all(i["confidence"] in ("exact", "street") for i in near_stop["items"])
    assert search(api, maxSchoolM=50)["total"] < near_stop["total"]


def test_bad_filters_are_422(api: TestClient) -> None:
    for params in (
        {"county": "narnia"},
        {"routingKey": "B12"},
        {"near": "40.4,-3.7"},
        {"radiusM": 500},
        {"near": "52.8,-6.9", "radiusM": 50000},
        {"priceMin": 5, "priceMax": 1},
        {"area": "a/b"},
        {"sort": "address"},
    ):
        res = api.get("/api/v1/search", params=params)
        assert res.status_code == 422, params
        assert res.headers["content-type"] == "application/problem+json"


def test_sort_by_change(api: TestClient, db: sa.Engine) -> None:
    pid = property_id(db, POLLERTON)
    with db.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO sale (property_id, source_row_hash, raw_date, raw_address, "
                "raw_county, raw_eircode, raw_price, raw_nfmp, raw_vat, raw_description, "
                "raw_size, sale_date, price_eur, not_full_market_price, vat_exclusive, is_new, "
                "first_seen_run_id, last_seen_run_id) "
                "SELECT p.id, repeat('f', 64), '', '', '', '', '', '', '', '', '', "
                "'2015-06-01', 160000, false, false, false, s.first_seen_run_id, "
                "s.last_seen_run_id FROM property p JOIN sale s ON s.property_id = p.id "
                "WHERE p.public_id = :id"
            ),
            {"id": pid},
        )
    try:
        body = search(api, sort="-change")
        first = body["items"][0]
        assert first["id"] == pid and first["nSales"] == 2
        assert first["change"] == {
            "previousDate": "2015-06-01",
            "previousPriceEur": 160000.0,
            "changePct": 50.0,
        }
        assert all(i["change"] is None for i in body["items"][1:])
        by_date = search(api, routingKey="R93")
        assert next(i for i in by_date["items"] if i["id"] == pid)["change"]["changePct"] == 50.0
        # A date filter that leaves out the earlier sale still counts it and compares with it.
        recent = search(api, sort="-change", dateFrom="2016-01-01")
        assert recent["items"][0]["id"] == pid and recent["items"][0]["nSales"] == 2
        assert recent["items"][0]["change"]["changePct"] == 50.0
    finally:
        with db.begin() as conn:
            conn.execute(sa.text("DELETE FROM sale WHERE source_row_hash = repeat('f', 64)"))


def test_autocomplete(api: TestClient) -> None:
    def ask(q: str) -> list[dict[str, Any]]:
        res = api.get("/api/v1/geocode/autocomplete", params={"q": q})
        assert res.status_code == 200, res.text
        return list(res.json())

    carlow = ask("carl")
    assert carlow[0] == {**carlow[0], "kind": "county", "label": "Carlow", "slug": "carlow"}
    assert any(s["kind"] == "settlement" and s["detail"] == "Co. Carlow · town" for s in carlow)
    assert ask("r93")[0]["kind"] == "routing_key"
    address = ask("pollerton rd")
    assert any(s["kind"] == "property" and s["label"] == POLLERTON for s in address)
    assert ask("zzzzqqq") == []
    assert api.get("/api/v1/geocode/autocomplete", params={"q": "a"}).status_code == 422


def test_search_rate_limit(db: sa.Engine) -> None:
    redis = FakeRedis()

    async def cache() -> AsyncIterator[FakeRedis]:
        yield redis

    with make_api({get_redis: cache}) as api:
        codes = [
            api.get("/api/v1/search", params={"county": "cork"}).status_code for _ in range(61)
        ]
    assert codes[:60] == [200] * 60 and codes[60] == 429


def test_search_history(db: sa.Engine) -> None:
    client = signed_in(Outbox(), FakeRedis(), "sean@example.ie")
    url = "/api/v1/me/history/searches"
    record = {"query": {"county": "carlow", "sort": "price"}, "label": "Carlow"}
    assert client.post(url, json=record).status_code == 204
    assert client.post(url, json={"query": {"priceMax": "300000"}}).status_code == 204
    assert client.post(url, json=record).status_code == 204  # moves to the top, no copy
    body = client.get(url).json()
    assert body["total"] == 2
    assert body["items"][0]["query"] == {"county": "carlow", "sort": "price"}
    assert body["items"][0]["label"] == "Carlow"

    # The user's own location is never stored, only that the search was near it.
    mine = {"query": {"near": "52.83,-6.93", "radiusM": "800", "nearSource": "geolocation"}}
    assert client.post(url, json=mine).status_code == 204
    assert client.get(url).json()["items"][0]["query"] == {"near": "my-location", "radiusM": "800"}
    assert client.post(url, json={"query": {"county": "narnia"}}).status_code == 422

    page = client.get(url, params={"pageSize": 2, "page": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    oldest = page["items"][0]["id"]
    assert client.delete(f"{url}/{oldest}").status_code == 204
    assert client.delete(f"{url}/{oldest}").status_code == 404

    other = signed_in(Outbox(), FakeRedis(), "nuala@example.ie")
    newest = client.get(url).json()["items"][0]["id"]
    assert other.delete(f"{url}/{newest}").status_code == 404
    assert other.get(url).json()["total"] == 0

    assert client.patch("/api/v1/me", json={"historyEnabled": False}).status_code == 200
    assert client.post(url, json=record).status_code == 204
    assert client.get(url).json()["total"] == 2
    assert client.delete(url).status_code == 204
    assert client.get(url).json()["total"] == 0
