"""Vicinity values against PostGIS, on real Carlow data.

Needs TEST_DATABASE_URL. Stops are a real GTFS subset around Carlow town
(tests/fixtures/gtfs_carlow.zip), amenities and schools are the OSM points of interest
there (tests/fixtures/osm_pois_carlow.json), and deprivation is Pobal's row for the Carlow
Rural ED (tests/fixtures/pobal_carlow_rural.csv).
"""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa

from ppr_pipeline.aggregate import aggregate
from ppr_pipeline.boundaries import LAYERS, load_boundaries
from ppr_pipeline.enrich.pobal import ed_key, load_pobal
from ppr_pipeline.enrich.pois import GTFS_SOURCE, OSM_SOURCE, read_gtfs, replace_pois
from ppr_pipeline.enrich.vicinity import compute_vicinity
from ppr_pipeline.geocode.runner import geocode_properties
from ppr_pipeline.ppr.ingest import ingest_ppr
from tests.conftest import FIXTURES

pytestmark = pytest.mark.db

RECORDED = json.loads((FIXTURES / "nominatim" / "responses.json").read_text())
CARLOW_RURAL = ("017010", "2ae19629-1857-13a3-e055-000000000001")


@pytest.fixture
def enriched(engine: sa.Engine) -> sa.Engine:
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    load_boundaries(engine, FIXTURES / "boundaries", layers)
    csv_bytes = (FIXTURES / "ppr_carlow_2025.csv").read_bytes()
    ingest_ppr(engine, csv_bytes, "file:///fixtures/ppr_carlow_2025.csv")

    def replay(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.params['q']}|{request.url.params['viewbox']}"
        return httpx.Response(200, json=RECORDED["responses"].get(key, []))

    geocode_properties(
        engine, "http://nominatim.test", client=httpx.Client(transport=httpx.MockTransport(replay))
    )
    osm = json.loads((FIXTURES / "osm_pois_carlow.json").read_text())
    osm_rows = [(p["type"], p["name"], p["lon"], p["lat"], p["ref"], p["attrs"]) for p in osm]
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM poi"))
        as_of, gtfs_rows = read_gtfs(FIXTURES / "gtfs_carlow.zip")
        replace_pois(conn, GTFS_SOURCE, as_of, gtfs_rows, "lonlat")
        replace_pois(conn, OSM_SOURCE, date(2026, 9, 26), osm_rows, "lonlat")
        load_pobal(
            conn,
            (FIXTURES / "pobal_carlow_rural.csv").read_bytes(),
            {ed_key(CARLOW_RURAL[0]): CARLOW_RURAL[1]},
        )
    compute_vicinity(engine)
    return engine


def test_only_precise_points_get_vicinity_values(enriched: sa.Engine) -> None:
    with enriched.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT p.geocode_confidence::text, e.property_id IS NOT NULL "
                "FROM property p LEFT JOIN property_enrichment e ON e.property_id = p.id"
            )
        ).all()
    assert rows
    for confidence, enriched_row in rows:
        assert enriched_row == (confidence in ("exact", "street")), confidence


def test_vicinity_values(enriched: sa.Engine) -> None:
    with enriched.connect() as conn:
        row = conn.execute(
            sa.text(
                "SELECT e.nearest_stop_type::text, e.nearest_stop_m, e.nearest_rail_m, "
                "e.nearest_primary_school_m, e.nearest_post_primary_school_m, e.amenities_1km, "
                "e.provenance, ST_Distance(ST_Transform(p.geom, 2157), "
                "ST_Transform(s.geom, 2157)) AS check_m "
                "FROM property_enrichment e JOIN property p ON p.id = e.property_id "
                "JOIN poi s ON s.id = e.nearest_stop_id "
                "WHERE p.address_display = '178 Pollerton Road, Carlow'"
            )
        ).one()
    stop_type, stop_m, rail_m, primary_m, post_m, amenities, prov, check_m = row
    assert stop_type == "bus_stop"
    assert abs(stop_m - check_m) <= 1
    assert 0 < stop_m < rail_m < 5000  # Carlow station is further than the nearest bus stop
    assert 0 < primary_m < 3000 and 0 < post_m < 3000
    assert set(amenities) <= {"shop", "supermarket", "pharmacy", "park", "gym", "restaurant", "gp"}
    assert prov["transport"] == {"source": "NTA GTFS", "asOf": "2026-09-26"}
    assert prov["distance"] == "straight line"


def test_pobal_values_and_hover_vicinity(enriched: sa.Engine) -> None:
    aggregate(enriched)
    with enriched.connect() as conn:
        band = conn.execute(
            sa.text(
                "SELECT value_text FROM area_attribute aa JOIN area a ON a.id = aa.area_id "
                "WHERE a.code = :guid AND aa.key = 'category'"
            ),
            {"guid": CARLOW_RURAL[1]},
        ).scalar_one()
        payload = conn.execute(
            sa.text(
                "SELECT ps.payload FROM property_summary ps JOIN property p "
                "ON p.id = ps.property_id WHERE p.address_display = '178 Pollerton Road, Carlow'"
            )
        ).scalar_one()
        coarse = conn.execute(
            sa.text(
                "SELECT ps.payload FROM property_summary ps JOIN property p "
                "ON p.id = ps.property_id WHERE p.geocode_confidence = 'locality' LIMIT 1"
            )
        ).scalar_one()
    assert band == "Marginally Below Average"
    vicinity = payload["vicinity"]
    assert vicinity["nearestStop"]["source"] == "NTA GTFS"
    assert vicinity["nearestStop"]["value"]["distanceM"] > 0
    assert vicinity["shopsWithin1km"]["source"] == "OpenStreetMap"
    assert vicinity["distances"] == "straight line"
    assert vicinity["flood"]["link"].startswith("https://www.floodinfo.ie/")
    # A town-centre point gets no distances: they would be made up.
    assert set(coarse["vicinity"]) == {"flood"}


def _point_wkb(lon: float, lat: float) -> bytes:
    import struct

    return struct.pack("<BIdd", 1, 1, lon, lat)


def test_a_failed_enrich_keeps_the_previous_values(
    enriched: sa.Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Enrich emptied the vicinity table first, so any later failure left every property
    without vicinity values (P1 #21). Now nothing changes until all of it succeeds."""
    from ppr_pipeline.enrich import run
    from ppr_pipeline.sources import load_sources

    for src, dest in (
        (FIXTURES / "gtfs_carlow.zip", "raw/gtfs/GTFS_All.zip"),
        (FIXTURES / "pobal_carlow_rural.csv", "raw/pobal/hp-deprivation-index-scores-2022.csv"),
    ):
        (tmp_path / dest).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / dest).write_bytes(src.read_bytes())
    for placeholder in (run.OSM_PBF, "raw/boundaries/electoral_division_2022.zip"):
        (tmp_path / placeholder).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / placeholder).write_bytes(b"")
    monkeypatch.setattr(run, "ed_ids", lambda _: {ed_key(CARLOW_RURAL[0]): CARLOW_RURAL[1]})
    osm = json.loads((FIXTURES / "osm_pois_carlow.json").read_text())

    def snapshot() -> tuple[int, int, int]:
        with enriched.connect() as conn:
            return tuple(  # type: ignore[return-value]
                conn.execute(
                    sa.text(
                        "SELECT (SELECT count(*) FROM property_enrichment), "
                        "(SELECT count(*) FROM poi), "
                        "(SELECT count(*) FROM property_enrichment WHERE nearest_stop_m > 0)"
                    )
                ).one()
            )

    before = snapshot()
    assert before[0] > 0 and before[2] > 0

    def broken_extract(*_: object) -> None:
        raise OSError("the OSM extract is truncated")

    monkeypatch.setattr(run, "read_osm", broken_extract)
    with pytest.raises(OSError, match="truncated"):
        run.enrich(enriched, load_sources(), tmp_path)
    assert snapshot() == before
    with enriched.connect() as conn:
        statuses = (
            conn.execute(
                sa.text(
                    "SELECT DISTINCT status::text FROM ingest_run "
                    "WHERE kind IN ('gtfs', 'osm', 'pobal') "
                    "AND stats ->> 'error' LIKE '%truncated%'"
                )
            )
            .scalars()
            .all()
        )
    assert statuses == ["failed"]

    rows = [
        (p["type"], p["name"], _point_wkb(p["lon"], p["lat"]), p["ref"], p["attrs"]) for p in osm
    ]
    monkeypatch.setattr(run, "read_osm", lambda *_: (date(2026, 9, 26), rows))
    stats = run.enrich(enriched, load_sources(), tmp_path)
    assert stats["vicinity"]["enriched"] == before[0]
    assert snapshot() == before
