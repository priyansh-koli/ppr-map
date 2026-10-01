"""The map, hover and property endpoints, and the tile functions, on real data.

Needs TEST_DATABASE_URL and the pipeline package (CI installs both). The database is built
the way production is: see `carlow_db` in conftest.py.
"""

import json
from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.redis_client import get_redis
from tests.conftest import CARLOW_BBOX, make_api, property_id

pytestmark = pytest.mark.db


async def no_cache() -> AsyncIterator[None]:
    yield None


@pytest.fixture
def db(carlow_db: sa.Engine) -> sa.Engine:
    return carlow_db


@pytest.fixture
def api(carlow_db: sa.Engine) -> Iterator[TestClient]:
    with make_api({get_redis: no_cache}) as client:
        yield client


_id = property_id


def test_meta(api: TestClient) -> None:
    body = api.get("/api/v1/meta").json()
    assert body["pprMaxSaleDate"] == "2025-12-17"
    assert body["provisionalFrom"] == "2025-11-01"
    assert body["dataVersion"].startswith("2025-12-17.r")


def test_list_matches_the_map_filters(api: TestClient) -> None:
    body = api.get("/api/v1/properties", params={"bbox": CARLOW_BBOX}).json()
    items = body["items"]
    assert body["total"] == len(items) > 20
    dates = [i["latestSale"]["date"] for i in items]
    assert dates == sorted(dates, reverse=True)
    assert all(i["confidence"] in ("exact", "street", "locality") for i in items)
    assert isinstance(items[0]["latestSale"]["priceEur"], float)

    new = api.get("/api/v1/properties", params={"bbox": CARLOW_BBOX, "type": "new"}).json()
    assert new["items"] and all(i["latestSale"]["isNew"] for i in new["items"])
    cheap = api.get("/api/v1/properties", params={"bbox": CARLOW_BBOX, "priceMax": 200000})
    assert all(i["latestSale"]["priceEur"] <= 200000 for i in cheap.json()["items"])


def test_list_refuses_a_national_box(api: TestClient) -> None:
    res = api.get("/api/v1/properties", params={"bbox": "-10,51,-6,55"})
    assert res.status_code == 422
    assert res.json()["detail"] == "Zoom in to list sales"
    assert api.get("/api/v1/properties", params={"bbox": "a,b,c,d"}).status_code == 422


def test_hover_summary(api: TestClient, db: sa.Engine) -> None:
    body = api.get(f"/api/v1/properties/{_id(db, '178 Pollerton Road, Carlow')}/summary").json()
    assert body["latestSale"]["priceEur"] == 240000
    assert body["vicinity"]["nearestStop"]["source"] == "NTA GTFS"
    assert body["vicinity"]["distances"] == "straight line"
    res = api.get("/api/v1/properties/nope/summary")
    assert res.status_code == 404
    assert res.headers["content-type"] == "application/problem+json"


def test_property_page(api: TestClient, db: sa.Engine) -> None:
    body = api.get(f"/api/v1/properties/{_id(db, '178 Pollerton Road, Carlow')}").json()
    assert [s["priceEur"] for s in body["sales"]] == [240000]
    assert {"kind": "county", "name": "Carlow", "slug": "carlow"} in body["areas"]
    assert body["location"]["confidence"] in ("exact", "street")
    assert body["areaSeries"]["points"]
    assert "Eircode" not in json.dumps(body)  # only the routing key is shown
    approx = api.get(f"/api/v1/properties/{_id(db, '37 Dolman Gardens, Pollerton, Carlow')}").json()
    assert approx["location"]["confidence"] == "locality"
    assert any("approximate" in c for c in approx["caveats"])
    assert approx["vicinity"]["nearestStop"] is None  # no distances from a town centre
    vat = api.get(f"/api/v1/properties/{_id(db, '143 Cois Dara, Chapelstown, Carlow')}").json()
    assert any("without VAT" in c for c in vat["caveats"])


def test_tile_functions(db: sa.Engine) -> None:
    with db.connect() as conn:

        def tile(fn: str, z: int, x: int, y: int, params: str = "{}") -> bytes:
            sql = sa.text(f"SELECT {fn}(:z, :x, :y, CAST(:p AS json))")
            return bytes(conn.execute(sql, {"z": z, "x": x, "y": y, "p": params}).scalar_one())

        # Carlow town (52.83 N, 6.92 W): z8 123/83, z10 492/334, z14 7877/5349.
        assert b"cells" in tile("sales_tiles", 10, 492, 334)
        points = tile("sales_tiles", 14, 7877, 5349)
        assert b"sales" in points
        assert tile("sales_tiles", 14, 7877, 5349, '{"priceMin": "not a number"}') == points
        assert tile("sales_tiles", 14, 7877, 5349, '{"priceMin": "5000000"}') == b""
        assert b"hexes" in tile("price_hex_tiles", 8, 123, 83, '{"window": "rolling_36m"}')


def test_hover_fields_keep_their_names(api: TestClient, db: sa.Engine) -> None:
    """Pydantic's camelCase would turn shops_within1km into shopsWithin1Km and drop the value."""
    body = api.get(f"/api/v1/properties/{_id(db, '178 Pollerton Road, Carlow')}/summary").json()
    assert isinstance(body["vicinity"]["shopsWithin1km"]["value"], int)
    assert isinstance(body["area"]["median12m"], float)
    assert "change12mPct" in body["area"]


def test_hover_cards_survive_redis_being_down(db: sa.Engine) -> None:
    """redis-py raises its own ConnectionError; the cache is skipped, not a 500."""
    from redis.asyncio import Redis

    async def dead_redis() -> Redis:
        return Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)

    with make_api({get_redis: dead_redis}) as client:
        res = client.get(f"/api/v1/properties/{_id(db, '178 Pollerton Road, Carlow')}/summary")
    assert res.status_code == 200
    assert res.json()["latestSale"]["priceEur"] == 240000


def test_each_sale_is_counted_in_one_cell_of_one_tile(db: sa.Engine) -> None:
    """The four z11 tiles under a z10 tile hold exactly the z10 tile's sales."""
    with db.connect() as conn:

        def total(z: int, x: int, y: int) -> int:
            sql = sa.text("SELECT coalesce(sum(n), 0) FROM tile_sales_cells(:z, :x, :y, '{}')")
            return int(conn.execute(sql, {"z": z, "x": x, "y": y}).scalar_one())

        parent = total(10, 492, 334)
        children = sum(total(11, 2 * 492 + dx, 2 * 334 + dy) for dx in (0, 1) for dy in (0, 1))
    assert parent == children > 0


def test_cells_sit_on_their_sales_inside_a_coarse_grid(db: sa.Engine) -> None:
    """16 cells per tile side (32 px), each drawn at its sales' mean position, inside the cell."""
    with db.connect() as conn:
        sql = sa.text(
            "SELECT c.i, c.j, c.cx, c.cy, ST_XMin(e) AS x0, ST_YMin(e) AS y0,"
            " (ST_XMax(e) - ST_XMin(e)) / 16 AS cell"
            " FROM tile_sales_cells(10, 492, 334, '{}') c, ST_TileEnvelope(10, 492, 334) e"
        )
        cells = conn.execute(sql).all()
    assert cells
    for c in cells:
        assert 0 <= c.i < 16 and 0 <= c.j < 16
        assert c.x0 + c.i * c.cell <= c.cx <= c.x0 + (c.i + 1) * c.cell
        assert c.y0 + c.j * c.cell <= c.cy <= c.y0 + (c.j + 1) * c.cell


def test_impossible_dates_fall_back_to_the_default(db: sa.Engine) -> None:
    with db.connect() as conn:

        def tile(params: str) -> bytes:
            sql = sa.text("SELECT sales_tiles(14, 7877, 5349, CAST(:p AS json))")
            return bytes(conn.execute(sql, {"p": params}).scalar_one())

        assert tile('{"dateFrom": "2025-02-30"}') == tile("{}")


def test_area_tiles_stay_planned_with_their_filters(db: sa.Engine) -> None:
    """From a connection's sixth call a cached generic plan made an area's tiles take over
    30 s each, and Martin reuses its connections (D-054)."""
    with db.connect() as conn:
        config = conn.execute(
            sa.text("SELECT proconfig FROM pg_proc WHERE proname = 'sales_tiles'")
        ).scalar_one()
        assert "plan_cache_mode=force_custom_plan" in config
        slug = conn.execute(
            sa.text(
                "SELECT a.slug FROM area a JOIN property p ON p.settlement_id = a.id"
                " WHERE a.kind = 'settlement' GROUP BY a.slug ORDER BY count(*) DESC LIMIT 1"
            )
        ).scalar_one()
        sql = sa.text("SELECT sales_tiles(10, 492, 334, CAST(:p AS json))")
        params = json.dumps({"area": slug})
        tiles = {bytes(conn.execute(sql, {"p": params}).scalar_one()) for _ in range(8)}
    assert len(tiles) == 1 and b"cells" in tiles.pop()


async def test_api_connections_plan_with_their_parameters(test_db_url: str) -> None:
    """psycopg prepares repeated statements; the list and /search must still be planned with
    their filters (D-054)."""
    from app.db import get_engine

    engine = get_engine()
    try:
        async with engine.connect() as conn:
            mode = await conn.scalar(sa.text("SHOW plan_cache_mode"))
    finally:
        await engine.dispose()
    assert mode == "force_custom_plan"


def test_overview(api: TestClient) -> None:
    from app.api.v1 import stats

    stats._Shared.overview = None
    data = api.get("/api/v1/stats/overview").json()
    assert data["totalSales"] > 0 and data["totalProperties"] > 0
    months = [m["month"] for m in data["monthly"]]
    assert months == sorted(months) and len(months) <= 24
    assert data["monthly"][-1]["provisional"] is True  # the latest month is never complete
    carlow = next(c for c in data["counties"] if c["slug"] == "carlow")
    assert carlow["sales"] >= 0 and 52 < carlow["lat"] < 53 and -7.2 < carlow["lng"] < -6.5
    # The counties' window ends before the provisional months start.
    assert data["windowEnd"] < api.get("/api/v1/meta").json()["provisionalFrom"]


def test_vat_exclusive_sales_carry_labelled_estimates(api: TestClient, db: sa.Engine) -> None:
    with db.connect() as conn:
        pid, sold, price = conn.execute(
            sa.text(
                "SELECT p.public_id, s.sale_date, s.price_eur FROM sale s "
                "JOIN property p ON p.id = s.property_id WHERE s.vat_exclusive LIMIT 1"
            )
        ).one()
    body = api.get(f"/api/v1/properties/{pid}").json()
    sale = next(s for s in body["sales"] if s["vatExclusive"])
    first = sale["vatEstimates"][0]
    assert first["rate"] == 0.135 and first["appliesTo"] == "any"
    assert first["priceEur"] == round(float(price) * 1.135, 2)
    # 2025 fixture sales: before 8 Oct 2025 only 13.5%; from then also 9% for apartments.
    assert len(sale["vatEstimates"]) == (2 if str(sold) >= "2025-10-08" else 1)
    assert any("estimates" in c for c in body["caveats"])
    assert all(not s["vatEstimates"] for s in body["sales"] if not s["vatExclusive"])
