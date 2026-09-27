"""The map, hover and property endpoints, and the tile functions, on real data.

Needs TEST_DATABASE_URL and the pipeline package (CI installs both). The database is built
the way production is: the real Carlow fixtures from pipeline/tests/fixtures go through the
pipeline's own boundary load, PPR ingest, geocoder (replaying recorded Nominatim answers),
enrichment and aggregates.
"""

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace
from datetime import date

import httpx
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.api.v1.properties import get_redis
from app.config import get_settings
from app.db import get_engine, get_sessionmaker
from app.main import create_app
from tests.conftest import BACKEND_DIR, REPO_ROOT

pipeline = pytest.importorskip("ppr_pipeline", reason="needs the pipeline package")

from ppr_pipeline.aggregate import aggregate  # noqa: E402
from ppr_pipeline.boundaries import LAYERS, load_boundaries  # noqa: E402
from ppr_pipeline.enrich.pobal import ed_key, load_pobal  # noqa: E402
from ppr_pipeline.enrich.pois import (  # noqa: E402
    GTFS_SOURCE,
    OSM_SOURCE,
    read_gtfs,
    replace_pois,
)
from ppr_pipeline.enrich.vicinity import compute_vicinity  # noqa: E402
from ppr_pipeline.geocode.runner import geocode_properties  # noqa: E402
from ppr_pipeline.ppr.ingest import ingest_ppr  # noqa: E402

pytestmark = pytest.mark.db

FIXTURES = REPO_ROOT / "pipeline" / "tests" / "fixtures"
# Carlow town, around Pollerton.
CARLOW_BBOX = "-6.95,52.80,-6.88,52.86"


def _build(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text("TRUNCATE property, sale, ingest_run, area, poi RESTART IDENTITY CASCADE")
        )
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    load_boundaries(engine, FIXTURES / "boundaries", layers)
    ingest_ppr(engine, (FIXTURES / "ppr_carlow_2025.csv").read_bytes(), "file:///carlow.csv")
    recorded = json.loads((FIXTURES / "nominatim" / "responses.json").read_text())

    def replay(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.params['q']}|{request.url.params['viewbox']}"
        return httpx.Response(200, json=recorded["responses"].get(key, []))

    geocode_properties(
        engine, "http://nominatim.test", client=httpx.Client(transport=httpx.MockTransport(replay))
    )
    osm = json.loads((FIXTURES / "osm_pois_carlow.json").read_text())
    with engine.begin() as conn:
        as_of, stops = read_gtfs(FIXTURES / "gtfs_carlow.zip")
        replace_pois(conn, GTFS_SOURCE, as_of, stops, "lonlat")
        rows = [(p["type"], p["name"], p["lon"], p["lat"], p["ref"], p["attrs"]) for p in osm]
        replace_pois(conn, OSM_SOURCE, date(2026, 9, 26), rows, "lonlat")
        load_pobal(
            conn,
            (FIXTURES / "pobal_carlow_rural.csv").read_bytes(),
            {ed_key("017010"): "2ae19629-1857-13a3-e055-000000000001"},
        )
    compute_vicinity(engine)
    aggregate(engine)


@pytest.fixture(scope="module")
def db(database_url_module: str) -> Iterator[sa.Engine]:
    engine = sa.create_engine(database_url_module)
    _build(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def database_url_module() -> Iterator[str]:
    import os

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set (start PostGIS with `make up`)")
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield url
    mp.undo()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture
def api(db: sa.Engine) -> Iterator[TestClient]:
    app = create_app()

    async def no_cache() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_redis] = no_cache
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    with TestClient(app) as client:
        yield client


def _id(db: sa.Engine, address: str) -> str:
    with db.connect() as conn:
        return str(
            conn.execute(
                sa.text("SELECT public_id FROM property WHERE address_display = :a"), {"a": address}
            ).scalar_one()
        )


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
