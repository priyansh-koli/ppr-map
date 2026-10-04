"""Geocoding rules (D-003), and the Nominatim step replayed from real recorded responses."""

import json
from typing import Any

import h3
import httpx
import pytest
from app.models.enums import GeocodeConfidence as C

from ppr_pipeline.geocode.rules import (
    classify,
    ladder,
    names_match,
    pick,
    query_parts,
    town_parts,
)
from ppr_pipeline.geocode.runner import (
    Geocoder,
    Nominatim,
    county_town_match,
    gazetteer_match,
    h3_r8,
    name_tokens,
    name_variants,
)
from tests.conftest import FIXTURES

RECORDED = json.loads((FIXTURES / "nominatim" / "responses.json").read_text())


def test_query_parts_drop_unit_county_and_postal_district() -> None:
    assert query_parts("Apt 11 Cartron Court, Rosses Point Road, Sligo", "sligo") == [
        "Cartron Court",
        "Rosses Point Road",
        "Sligo",  # a bare county name is kept: here it is the town
    ]
    assert query_parts("Apt 4, Main St, Rathcormac", "cork") == ["Main St", "Rathcormac"]
    assert query_parts("Meanus, Castlemain, Co. Kerry", "kerry") == ["Meanus", "Castlemain"]
    assert query_parts("362 Kimmage Rd Lower, Dublin 6W, Dublin", "dublin") == [
        "362 Kimmage Rd Lower",
        "Dublin",
    ]
    assert query_parts("4 Woodbine House, Stillorgan Rd, Donnybrook Dublin 4", "dublin")[-1] == (
        "Donnybrook"
    )
    assert query_parts("14 The Deanery, Station Rd, Kildare Town", "kildare")[-1] == "Kildare"
    assert query_parts("12 Slaney Meadows, Rathvilly Carlow, Carlow", "carlow") == [
        "12 Slaney Meadows",
        "Rathvilly",
        "Carlow",
    ]
    assert query_parts("68 Gurranabraher Avenue, Off Cathedral Road", "cork")[-1] == (
        "Cathedral Road"
    )


def test_ladder_tries_a_trailing_county_name_with_and_without() -> None:
    parts = ["5 Abbey Glen", "Athenry", "Galway"]
    assert ladder(parts, "galway") == [
        ("5 Abbey Glen, Athenry, Galway", 0),
        ("5 Abbey Glen, Athenry", 0),
        ("Athenry, Galway", 1),
        ("Athenry", 1),
    ]
    assert town_parts(parts, "galway") == ["Athenry", "Galway"]
    assert ladder(["Main St", "Rathcormac"], "cork") == [
        ("Main St, Rathcormac", 0),
        ("Rathcormac", 1),
    ]


def test_names_must_match_word_for_word() -> None:
    assert not names_match("Fenit", ["Fenit Road"])
    assert not names_match("Coosan", ["Coosan Heath"])
    assert names_match("Lelia St", ["Saint Lelia's Street"])
    assert names_match("Kimmage Rd Lower", ["Kimmage Road Lower"])
    assert names_match("Pollerton", ["Pollerton Big"])  # a townland division
    assert names_match("Dun Laoghaire", ["Dún Laoghaire"])


def _result(**kw: Any) -> dict[str, Any]:
    return {"lat": "53.0", "lon": "-7.0", "place_rank": 26, "address": {}, **kw}


def test_classify_levels() -> None:
    house = _result(
        category="building",
        type="house",
        name="",
        address={"house_number": "5", "road": "Abbey Glen"},
    )
    assert classify(house, "5 Abbey Glen") == (C.EXACT, "")
    assert classify(house, "5 Abbey Park") == (None, "house_number_other_street")
    road = _result(category="highway", type="residential", name="Abbey Glen")
    assert classify(road, "5 Abbey Glen") == (C.STREET, "")
    lamp = _result(category="highway", type="street_lamp", name="Abbey Glen")
    assert classify(lamp, "Abbey Glen") == (None, "implausible_type")
    village = _result(category="place", type="village", name="Fenit")
    assert classify(village, "Fenit") == (C.LOCALITY, "")
    city = _result(category="place", type="city", name="Galway")
    assert classify(city, "Galway") == (None, "too_coarse")
    shop = _result(category="shop", type="yes", name="Rathcormac Fireplaces")
    assert classify(shop, "Rathcormac") == (None, "name_mismatch")


def test_pick_rejects_far_and_ambiguous_matches() -> None:
    carlow_road = _result(category="highway", type="tertiary", name="Tullow Road", lon="-6.92")
    other_road = _result(category="highway", type="tertiary", name="Tullow Road", lon="-6.70")
    candidate, reasons = pick([carlow_road, other_road], "Tullow Rd", None)
    assert candidate is None and "ambiguous" in reasons
    town = (-6.70, 53.0, False)
    candidate, reasons = pick([carlow_road, other_road], "Tullow Rd", town)
    assert candidate is not None and candidate.lon == -6.70
    assert reasons == ["far_from_town"]


def test_a_town_query_never_lands_on_a_house_of_the_same_name() -> None:
    # Recorded case: "Coole West, Athea" put every Athea sale on a house in Limerick city.
    house = _result(category="building", type="house", name="Athea", lon="-8.6336")
    village = _result(category="place", type="village", name="Athea", lon="-9.2876")
    candidate, reasons = pick([house, village], "Athea", None, town_query=True)
    assert candidate is not None and candidate.confidence is C.LOCALITY
    assert candidate.lon == -9.2876 and reasons == ["building_named_like_town"]
    assert pick([house], "Athea", None, town_query=True) == (None, ["building_named_like_town"])
    # A town part that is a street keeps its street match.
    road = _result(category="highway", type="tertiary", name="Tullow Road", lon="-6.92")
    candidate, _ = pick([road], "Tullow Rd", None, town_query=True)
    assert candidate is not None and candidate.confidence is C.STREET
    # A house number matched on its street is still exact.
    numbered = _result(
        category="building", type="house", address={"house_number": "12", "road": "Main St"}
    )
    candidate, _ = pick([numbered], "12 Main St", None, town_query=True)
    assert candidate is not None and candidate.confidence is C.EXACT
    # Anywhere else in the address a named house is still a street-level match.
    candidate, _ = pick([house], "Athea", None)
    assert candidate is not None and candidate.confidence is C.STREET


@pytest.fixture
def geocoder() -> Geocoder:
    def replay(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.params['q']}|{request.url.params['viewbox']}"
        return httpx.Response(200, json=RECORDED["responses"].get(key, []))

    boxes = {k: tuple(v) for k, v in RECORDED["boxes"].items()}
    client = httpx.Client(transport=httpx.MockTransport(replay))
    return Geocoder(Nominatim("http://nominatim.test", boxes, client))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("address", "county", "confidence", "name"),
    [
        ("5 Abbey Glen, Athenry, Galway", "galway", C.EXACT, ""),
        # Nominatim's first answer is Fenit Road; the village is the right one.
        ("The Bungalow, Fenit, Tralee", "kerry", C.LOCALITY, "Fenit"),
        # "The Mall" in Templemore is not in Thurles; Thurles itself is kept.
        ("2 Pearse Terrace, The Mall, Thurles", "tipperary", C.LOCALITY, "Thurles"),
        ("24 Sherwood, Pollerton, Carlow", "carlow", C.LOCALITY, "Pollerton Big"),
        # OSM has no Rathcormac village in Cork (only a Rathcormack in Sligo): no match here,
        # the CSO settlement name places it later (gazetteer fallback).
        ("Apt 4, Main St, Rathcormac", "cork", None, None),
    ],
)
def test_geocoder_on_recorded_responses(
    geocoder: Geocoder, address: str, county: str, confidence: C | None, name: str | None
) -> None:
    outcome = geocoder.geocode(1, address, county)
    got = outcome.candidate
    assert (got.confidence if got else None) == confidence
    if got and name is not None:
        assert got.name == name
    assert outcome.attempts and all(a.query for a in outcome.attempts)


def test_gazetteer_prefers_a_unique_settlement_then_townland() -> None:
    index = {
        ("cork", name_tokens("Rathcormac")): [("settlement", 1), ("townland", 2)],
        ("carlow", name_tokens("Ballybannon")): [("townland", 3)],
        ("carlow", name_tokens("Carlow")): [("settlement", 4)],
        ("kerry", name_tokens("Meanus")): [("townland", 5), ("townland", 6)],
    }
    assert gazetteer_match(index, "Apt 4, Main St, Rathcormac", "cork") == (1, "Rathcormac")
    assert gazetteer_match(index, "Ballybannon, Milford, Co Carlow", "carlow") == (
        3,
        "Ballybannon",
    )
    assert gazetteer_match(index, "Meanus, Castlemain, Co. Kerry", "kerry") is None  # two
    # The county name is only taken as the town in the later county-town step.
    assert gazetteer_match(index, "162 St Marys Park, carlow", "carlow") is None
    assert county_town_match(index, "162 St Marys Park, carlow", "carlow") == (4, "carlow")


def test_gazetteer_name_variants() -> None:
    assert name_variants("Muinebeag (Bagenalstown)") == {
        "Muinebeag (Bagenalstown)",
        "Muinebeag",
        "Bagenalstown",
    }
    assert "Tinnahinch" in name_variants("Graiguenamanagh-Tinnahinch")


def test_h3_cells_fit_in_bigint() -> None:
    cell = h3_r8(53.3498, -6.2603)
    assert 0 < cell < 2**63
    assert h3.get_resolution(format(cell, "x")) == 8


def test_st_before_a_qualifier_is_street() -> None:
    """P2 #34: "Main St Lower" was read as "Main Saint Lower" and never matched."""
    assert names_match("Main St Lower", ["Main Street Lower"])
    assert names_match("St John's Road", ["Saint John's Road"])
    house = _result(
        category="building",
        type="house",
        name="",
        address={"house_number": "5", "road": "Main Street Lower"},
    )
    assert classify(house, "5 Main St Lower") == (C.EXACT, "")


def test_a_no_prefix_keeps_its_house_number() -> None:
    """P2 #35: "No. 5" was stripped as if it were a unit, so the address was never exact."""
    assert query_parts("No. 5 Main St, Naas", "kildare") == ["5 Main St", "Naas"]
    assert query_parts("No 12, Abbey Rd, Naas", "kildare") == ["12", "Abbey Rd", "Naas"]
    assert query_parts("Apt 4, Main St, Naas", "kildare") == ["Main St", "Naas"]


def test_an_estate_keeps_village_or_town_in_its_name() -> None:
    """P2 #49: "5 The Village" was queried as "5 The"."""
    assert query_parts("5 The Village, Ballinroad, Co Waterford", "waterford") == [
        "5 The Village",
        "Ballinroad",
    ]
    assert query_parts("The Village, Ballinroad", "waterford") == ["The Village", "Ballinroad"]
    assert query_parts("12 Ashbrook Village, Ennis", "clare")[0] == "12 Ashbrook Village"
    assert query_parts("14 The Deanery, Station Rd, Kildare Town", "kildare")[-1] == "Kildare"
