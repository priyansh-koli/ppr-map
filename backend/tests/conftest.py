import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.health import get_redis_ping
from app.db import get_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class FakeSession:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def execute(self, *_: Any, **__: Any) -> None:
        if self.fail:
            raise ConnectionError("database down")


def make_client(db_fail: bool = False, redis_fail: bool = False) -> TestClient:
    app = create_app()

    async def session_override() -> AsyncIterator[FakeSession]:
        yield FakeSession(fail=db_fail)

    async def redis_ping() -> None:
        if redis_fail:
            raise ConnectionError("redis down")

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_redis_ping] = lambda: redis_ping
    return TestClient(app)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with make_client() as c:
        yield c


@pytest.fixture
def database_url() -> str:
    """Tests marked `db` need TEST_DATABASE_URL pointing at a disposable PostGIS database."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set (start PostGIS with `make up`)")
    return url


# --- real data, built by the pipeline (tests that use these need TEST_DATABASE_URL) --------

PIPELINE_FIXTURES = REPO_ROOT / "pipeline" / "tests" / "fixtures"
# Carlow town, around Pollerton.
CARLOW_BBOX = "-6.95,52.80,-6.88,52.86"


@pytest.fixture(scope="module")
def test_db_url() -> Iterator[str]:
    """TEST_DATABASE_URL at the latest migration, with roles and permissions synced."""
    from alembic import command
    from alembic.config import Config

    from app.cli import sync_permissions
    from app.config import get_settings
    from app.db import get_engine, get_sessionmaker

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
    sync_permissions()
    yield url
    mp.undo()
    for cache in (get_settings, get_engine, get_sessionmaker):
        cache.cache_clear()


@pytest.fixture(scope="module")
def carlow_db(test_db_url: str) -> Iterator[Any]:
    """The real Carlow fixtures run through the pipeline: boundaries, PPR ingest, geocoding
    (recorded Nominatim answers), enrichment and aggregates, as in production."""
    pytest.importorskip("ppr_pipeline", reason="needs the pipeline package")
    import sqlalchemy as sa

    engine = sa.create_engine(test_db_url)
    _build_carlow(engine)
    yield engine
    engine.dispose()


def make_api(overrides: dict[Any, Any] | None = None) -> TestClient:
    """A client on a fresh app, with dependencies replaced as given."""
    from app.db import get_engine, get_sessionmaker

    app = create_app()
    app.dependency_overrides.update(overrides or {})
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    return TestClient(app)


def property_id(engine: Any, address: str) -> str:
    import sqlalchemy as sa

    with engine.connect() as conn:
        return str(
            conn.execute(
                sa.text("SELECT public_id FROM property WHERE address_display = :a"), {"a": address}
            ).scalar_one()
        )


def _build_carlow(engine: Any) -> None:
    import json
    from dataclasses import replace
    from datetime import date

    import httpx
    import sqlalchemy as sa
    from ppr_pipeline.aggregate import aggregate
    from ppr_pipeline.boundaries import LAYERS, load_boundaries
    from ppr_pipeline.enrich.pobal import ed_key, load_pobal
    from ppr_pipeline.enrich.pois import GTFS_SOURCE, OSM_SOURCE, read_gtfs, replace_pois
    from ppr_pipeline.enrich.vicinity import compute_vicinity
    from ppr_pipeline.geocode.runner import geocode_properties
    from ppr_pipeline.ppr.ingest import ingest_ppr

    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "TRUNCATE property, sale, ingest_run, area, poi, app_user RESTART IDENTITY CASCADE"
            )
        )
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    load_boundaries(engine, PIPELINE_FIXTURES / "boundaries", layers)
    ingest_ppr(
        engine, (PIPELINE_FIXTURES / "ppr_carlow_2025.csv").read_bytes(), "file:///carlow.csv"
    )
    recorded = json.loads((PIPELINE_FIXTURES / "nominatim" / "responses.json").read_text())

    def replay(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.params['q']}|{request.url.params['viewbox']}"
        return httpx.Response(200, json=recorded["responses"].get(key, []))

    geocode_properties(
        engine, "http://nominatim.test", client=httpx.Client(transport=httpx.MockTransport(replay))
    )
    osm = json.loads((PIPELINE_FIXTURES / "osm_pois_carlow.json").read_text())
    with engine.begin() as conn:
        as_of, stops = read_gtfs(PIPELINE_FIXTURES / "gtfs_carlow.zip")
        replace_pois(conn, GTFS_SOURCE, as_of, stops, "lonlat")
        rows = [(p["type"], p["name"], p["lon"], p["lat"], p["ref"], p["attrs"]) for p in osm]
        replace_pois(conn, OSM_SOURCE, date(2026, 9, 26), rows, "lonlat")
        load_pobal(
            conn,
            (PIPELINE_FIXTURES / "pobal_carlow_rural.csv").read_bytes(),
            {ed_key("017010"): "2ae19629-1857-13a3-e055-000000000001"},
        )
    compute_vicinity(engine)
    aggregate(engine)
