"""Enrichment rules: stop types, OSM categories, school levels and Pobal ED ids."""

from decimal import Decimal
from pathlib import Path

from app.models.enums import PoiType as P

from ppr_pipeline.enrich.pobal import attribute_rows, ed_key, read_pobal
from ppr_pipeline.enrich.pois import osm_type, read_gtfs, school_type, stop_types
from tests.conftest import FIXTURES


def test_stop_types() -> None:
    assert stop_types({"3"}, dart=False) == [P.BUS_STOP]
    assert stop_types({"0"}, dart=False) == [P.LUAS_STOP]
    assert stop_types({"2"}, dart=True) == [P.DART_STATION]
    assert stop_types({"2", "3"}, dart=False) == [P.BUS_STOP, P.RAIL_STATION]


def test_gtfs_subset_types_served_stops() -> None:
    as_of, rows = read_gtfs(FIXTURES / "gtfs_carlow.zip")
    assert as_of.isoformat() == "2026-09-26"
    by_type = {r[0] for r in rows}
    assert by_type == {"bus_stop", "rail_station"}
    assert [r[1] for r in rows if r[0] == "rail_station"] == ["Carlow"]


def test_osm_categories() -> None:
    assert osm_type({"amenity": "pharmacy"}) is P.PHARMACY
    assert osm_type({"healthcare": "doctor"}) is P.GP
    assert osm_type({"shop": "supermarket"}) is P.SUPERMARKET
    assert osm_type({"shop": "convenience"}) is P.SHOP
    assert osm_type({"shop": "car_repair"}) is None
    assert osm_type({"leisure": "park"}) is P.PARK
    assert osm_type({"amenity": "fast_food"}) is P.RESTAURANT


def test_school_levels_only_when_stated() -> None:
    assert school_type("Saint Fiacc's NS", None) is P.SCHOOL_PRIMARY
    assert school_type("Carlow Educate Together National School", None) is P.SCHOOL_PRIMARY
    assert school_type("Gaelcholáiste Cheatharlach", None) is P.SCHOOL_POST_PRIMARY
    assert school_type("Presentation College Carlow", None) is P.SCHOOL_POST_PRIMARY
    assert school_type("Bishop Foley School", "primary") is P.SCHOOL_PRIMARY
    assert school_type("St Mary's Special School", None) is P.SCHOOL_SPECIAL
    assert school_type("Bishop Foley School", None) is None  # not guessed
    # P1 #17: Irish names of post-primary schools also say "scoil".
    for name in (
        "Scoil Phobail Bhéara",
        "Pobalscoil Inbhear Scéine",
        "Pobail Scoil Inbhear Sceine",
        "Meánscoil Gharman",
        "Scoil Chuimsitheach Chiaráin",
        "Gairmscoil Éinde",
        "Ardscoil Rís",
    ):
        assert school_type(name, None) is P.SCHOOL_POST_PRIMARY, name
    assert school_type("Scoil Mhuire", None) is P.SCHOOL_PRIMARY
    assert school_type("Bunscoil Chríost Rí", None) is P.SCHOOL_PRIMARY
    # OSM's tag wins over the name: a "Scoil" tagged secondary is post-primary.
    assert school_type("Scoil Mhuire", "secondary") is P.SCHOOL_POST_PRIMARY
    assert school_type("Ardscoil na Mara", "primary") is P.SCHOOL_PRIMARY


def test_pobal_ed_ids_ignore_leading_zeros_and_part_order() -> None:
    assert ed_key("017010") == ed_key("17010") == "17010"
    assert ed_key("027085/027058") == ed_key("27058/27085")
    rows = read_pobal((FIXTURES / "pobal_carlow_rural.csv").read_bytes())
    out, missing = attribute_rows(rows, {ed_key("017010"): "guid-carlow-rural"})
    assert missing == []
    assert ("guid-carlow-rural", "category", Decimal(4), "Marginally Below Average") in out
    assert ("guid-carlow-rural", "relative_index", Decimal("-2.21"), None) in out


def test_fixture_paths_exist() -> None:
    assert Path(FIXTURES / "osm_pois_carlow.json").exists()
