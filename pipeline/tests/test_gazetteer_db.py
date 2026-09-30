"""Building `gazetteer_feature` and the local pass of a geocoding run (D-046).

Needs TEST_DATABASE_URL. Uses the real Carlow boundary subset and real OSM coordinates in
Borris; Nominatim is replaced by a responder that finds nothing.
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

import httpx
import pytest
import sqlalchemy as sa

from ppr_pipeline.address import normalise_address
from ppr_pipeline.boundaries import LAYERS, load_boundaries
from ppr_pipeline.geocode.gazetteer import (
    NHDS_SOURCE,
    OSM_SOURCE,
    Row,
    load_gazetteer,
    read_nhds,
)
from ppr_pipeline.geocode.rules import km_between
from ppr_pipeline.geocode.runner import geocode_properties
from tests.conftest import FIXTURES

pytestmark = pytest.mark.db

EWKT = "SRID=4326;"
OSM_ROWS: list[Row] = [
    # Two segments of Woodlawn Park 60 m apart: one street. A third in Tullow, 20 km off.
    ("street", "Woodlawn Park", None, "residential",
     EWKT + "LINESTRING(-6.9360 52.6040, -6.9350 52.6040)", "w1", None, OSM_SOURCE),
    ("street", "Woodlawn Park", None, "residential",
     EWKT + "LINESTRING(-6.9341 52.6040, -6.9330 52.6043)", "w2", None, OSM_SOURCE),
    ("street", "Woodlawn Park", None, "residential",
     EWKT + "LINESTRING(-6.7370 52.8010, -6.7360 52.8010)", "w3", None, OSM_SOURCE),
    ("address", "Woodlawn Park", "54", None, EWKT + "POINT(-6.93606 52.60477)", "n1", None,
     OSM_SOURCE),
    ("place", "Borris", None, "village", EWKT + "POINT(-6.92021 52.59880)", "n2", 1500,
     OSM_SOURCE),
    # Kilkenny city, outside County Carlow: dropped.
    ("street", "Parliament Street", None, "primary",
     EWKT + "LINESTRING(-7.2540 52.6540, -7.2530 52.6550)", "w4", None, OSM_SOURCE),
]  # fmt: skip


def _load(engine: sa.Engine, nhds: list[Row] | None = None) -> dict[str, int]:
    return load_gazetteer(
        engine,
        iter(OSM_ROWS),
        iter(nhds or []),
        osm_as_of=date(2026, 9, 26),
        nhds_as_of=date(2026, 9, 29),
    )


@pytest.fixture
def carlow(engine: sa.Engine) -> sa.Engine:
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    load_boundaries(engine, FIXTURES / "boundaries", layers)
    return engine


def test_streets_merge_and_features_get_their_county(carlow: sa.Engine) -> None:
    counts = _load(carlow)
    with carlow.connect() as conn:
        streets = conn.execute(
            sa.text(
                "SELECT county::text, ST_X(geom), ST_Y(geom) FROM gazetteer_feature "
                "WHERE kind = 'street' ORDER BY ST_Y(geom)"
            )
        ).all()
        official = conn.execute(
            sa.text("SELECT count(*) FROM gazetteer_feature WHERE source <> :osm"),
            {"osm": OSM_SOURCE},
        ).scalar_one()
    # Borris's two segments merged; Tullow's kept apart; Kilkenny's dropped.
    assert [s[0] for s in streets] == ["carlow", "carlow"]
    lon, lat = streets[0][1], streets[0][2]
    assert -6.9360 <= lon <= -6.9330 and 52.6039 < lat < 52.6044  # on the street
    assert counts["address"] == 1
    # The fixture's townlands and settlements are places too.
    assert official > 0 and counts["place"] == official + 1


def test_survey_estates_are_read_from_itm(carlow: sa.Engine, tmp_path: Path) -> None:
    csv = tmp_path / "2011.csv"
    csv.write_bytes(
        "DRef,Development,Address,County,GIS X,GIS Y\r\n"
        '71,Ard Bhaile,Tullow Road,Carlow,"687,267 ","681,220 "\r\n'
        '72,No Coordinates,Somewhere,Carlow,,\r\n'.encode("cp1252")
    )  # fmt: skip
    rows = list(read_nhds([csv]))
    assert [(r[1], r[5], r[7]) for r in rows] == [("Ard Bhaile", "DRef 71", NHDS_SOURCE)]
    _load(carlow, rows)
    with carlow.connect() as conn:
        lon, lat, as_of = conn.execute(
            sa.text(
                "SELECT ST_X(geom), ST_Y(geom), as_of FROM gazetteer_feature WHERE source = :s"
            ),
            {"s": NHDS_SOURCE},
        ).one()
    # On the edge of Rathvilly, Co. Carlow.
    assert km_between(lon, lat, -6.6966, 52.8795) < 1
    assert as_of == date(2026, 9, 29)


def _empty_nominatim() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))


def _add(conn: sa.Connection, raw: str) -> None:
    a = normalise_address(raw, "carlow")
    conn.execute(
        sa.text(
            "INSERT INTO property (public_id, address_display, address_normalised, "
            "address_key, county, geocode_confidence) "
            "VALUES (:pid, :display, :norm, :key, 'carlow', 'unmatched')"
        ),
        {"pid": raw[:20], "display": raw, "norm": a.normalised, "key": a.key},
    )


def test_the_local_pass_places_what_nominatim_could_not(carlow: sa.Engine) -> None:
    _load(carlow)
    with carlow.begin() as conn:
        _add(conn, "54 Woodlawn Park, Borris, Co. Carlow")
        _add(conn, "10 Woodlawn Park, Borris, Co. Carlow")
        # Stored from an earlier run: a railway station taken for the village.
        _add(conn, "3 Station Road, Borris, Co Carlow")
        conn.execute(
            sa.text(
                "UPDATE property SET geocoded_at = now(), geocode_confidence = 'street', "
                "geocode_method = 'nominatim:building/train_station', "
                "geom = ST_SetSRID(ST_MakePoint(-6.9180, 52.5990), 4326) "
                "WHERE address_display LIKE '3 Station%'"
            )
        )
    summary = geocode_properties(carlow, "http://nominatim.test", client=_empty_nominatim())
    assert summary["rechecked_buildings"] == 1
    with carlow.connect() as conn:
        rows = dict(
            conn.execute(
                sa.text(
                    "SELECT address_display, geocode_confidence::text || ' ' || geocode_method "
                    "FROM property"
                )
            ).all()
        )
        logged = conn.execute(
            sa.text("SELECT count(*) FROM geocode_attempt WHERE method = 'local'")
        ).scalar_one()
    assert rows["54 Woodlawn Park, Borris, Co. Carlow"] == "exact osm:address"
    assert rows["10 Woodlawn Park, Borris, Co. Carlow"] == "street osm:street"
    assert not rows["3 Station Road, Borris, Co Carlow"].endswith("train_station")
    assert logged == 2

    # A second run recomputes the local results and changes nothing.
    geocode_properties(carlow, "http://nominatim.test", client=_empty_nominatim())
    with carlow.connect() as conn:
        again = dict(
            conn.execute(
                sa.text(
                    "SELECT address_display, geocode_confidence::text || ' ' || geocode_method "
                    "FROM property"
                )
            ).all()
        )
    assert again == rows
