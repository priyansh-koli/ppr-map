"""The geocoding run against PostGIS: county check, fallbacks and spatial joins.

Needs TEST_DATABASE_URL. Uses the real Carlow boundary subset (tests/fixtures/boundaries)
and real Carlow PPR addresses; Nominatim is replaced by an empty responder, so every
property goes through the database fallbacks.
"""

from dataclasses import replace

import httpx
import pytest
import sqlalchemy as sa
from app.models.data import IngestRun
from app.models.enums import GeocodeConfidence, IngestKind, IngestStatus

from ppr_pipeline.address import normalise_address
from ppr_pipeline.boundaries import LAYERS, load_boundaries
from ppr_pipeline.geocode.rules import Candidate
from ppr_pipeline.geocode.runner import Attempt, Outcome, geocode_properties, write_outcomes
from tests.conftest import FIXTURES

pytestmark = pytest.mark.db

ADDRESSES = [
    "162 St Marys Park, carlow",  # "carlow" is the town: CSO settlement Carlow
    "Ballybannon, Milford, Co Carlow",  # an official townland
    "10 Woodlawn Park, Borris, Co. Carlow",  # Borris is not in the fixture: county point
]


@pytest.fixture
def carlow(engine: sa.Engine) -> sa.Engine:
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    load_boundaries(engine, FIXTURES / "boundaries", layers)
    with engine.begin() as conn:
        for i, raw in enumerate(ADDRESSES):
            a = normalise_address(raw, "carlow")
            conn.execute(
                sa.text(
                    "INSERT INTO property (public_id, address_display, address_normalised, "
                    "address_key, county, geocode_confidence) "
                    "VALUES (:pid, :display, :norm, :key, 'carlow', 'unmatched')"
                ),
                {"pid": f"t{i}", "display": raw, "norm": a.normalised, "key": a.key},
            )
    return engine


def _empty_nominatim() -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[])))


def _rows(engine: sa.Engine) -> dict[str, tuple[str, str, str | None, str | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT p.address_display, p.geocode_confidence::text, p.geocode_method, "
                "t.name, s.name FROM property p "
                "LEFT JOIN area t ON t.id = p.townland_id "
                "LEFT JOIN area s ON s.id = p.settlement_id"
            )
        ).all()
    return {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}


def test_fallbacks_place_every_property_in_its_county(carlow: sa.Engine) -> None:
    summary = geocode_properties(carlow, "http://nominatim.test", client=_empty_nominatim())
    assert summary["properties"] == 3
    rows = _rows(carlow)
    assert rows["162 St Marys Park, carlow"] == (
        "locality",
        "gazetteer:county_town",
        None,
        "Carlow",
    )
    assert rows["Ballybannon, Milford, Co Carlow"][:3] == (
        "locality",
        "gazetteer:townland",
        "Ballybannon",
    )
    assert rows["10 Woodlawn Park, Borris, Co. Carlow"][:2] == ("county", "county:point_on_surface")
    with carlow.connect() as conn:
        outside = conn.execute(
            sa.text(
                "SELECT count(*) FROM property p JOIN area c ON c.kind = 'county' "
                "AND c.code = 'carlow' WHERE NOT ST_Intersects(c.geom, p.geom)"
            )
        ).scalar_one()
        # Nothing precise, so no Small Area, ED or H3 cell was claimed.
        claimed = conn.execute(
            sa.text(
                "SELECT count(*) FROM property "
                "WHERE small_area_id IS NOT NULL OR ed_id IS NOT NULL OR h3_r8 IS NOT NULL"
            )
        ).scalar_one()
    assert (outside, claimed) == (0, 0)

    # Re-running redoes the fallbacks and changes nothing.
    geocode_properties(carlow, "http://nominatim.test", refresh=True, client=_empty_nominatim())
    assert _rows(carlow) == rows


def test_points_outside_the_county_are_rejected(carlow: sa.Engine) -> None:
    with carlow.connect() as conn:
        pid = conn.execute(
            sa.text("SELECT id FROM property WHERE address_display LIKE '162 %'")
        ).scalar_one()
        run_id = conn.execute(
            sa.insert(IngestRun)
            .values(kind=IngestKind.GEOCODE, status=IngestStatus.RUNNING)
            .returning(IngestRun.id)
        ).scalar_one()
        conn.commit()
    # A St Mary's Park in Dublin (Kimmage), 70 km outside County Carlow.
    dublin = Candidate(GeocodeConfidence.STREET, -6.2968, 53.3183, "highway/residential", "", {})
    outcome = Outcome(pid, dublin, [Attempt(1, "St Marys Park", dublin, None)])
    with carlow.begin() as conn:
        write_outcomes(conn, [outcome], run_id)
    with carlow.connect() as conn:
        attempt = conn.execute(
            sa.text("SELECT accepted, reject_reason FROM geocode_attempt WHERE property_id = :p"),
            {"p": pid},
        ).one()
        confidence = conn.execute(
            sa.text("SELECT geocode_confidence::text FROM property WHERE id = :p"), {"p": pid}
        ).scalar_one()
    assert tuple(attempt) == (False, "county_conflict")
    assert confidence == "unmatched"
