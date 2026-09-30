"""The local street gazetteer matcher (D-046), on real OSM and survey coordinates.

Coordinates are copied from `gazetteer_feature` as built from the 2026-09-26 Geofabrik
extract; addresses are real PPR addresses that Nominatim left at town level.
"""

import math

from app.models.enums import GeocodeConfidence as C

from ppr_pipeline.geocode.local import Feature, Index, match, place_radius_km
from ppr_pipeline.geocode.rules import classify, km_between

OSM = "OpenStreetMap contributors"
NHDS = "DHLGH National Housing Development Survey"


def place(lon: float, lat: float, km: float = 1.5) -> Feature:
    return Feature("place", lon, lat, OSM, km)


def street(lon: float, lat: float, source: str = OSM) -> Feature:
    return Feature("street", lon, lat, source)


def estate(lon: float, lat: float, source: str = OSM) -> Feature:
    return Feature("estate", lon, lat, source)


def index() -> Index:
    idx = Index()
    # Waterford: Knightswood Crescent, in the townland of Williamstown (and a second
    # Williamstown 25 km west).
    idx.add("waterford", "Knightswood Crescent", street(-7.09396, 52.24059))
    idx.add("waterford", "Williamstown", place(-7.09105, 52.23398, 1.341))
    idx.add("waterford", "Williamstown", place(-7.43960, 52.14605, 1.131))
    # Meath: Ratoath and Steeplechase Hill, with two of its house numbers.
    idx.add("meath", "Ratoath", place(-6.46407, 53.50727, 3.0))
    idx.add("meath", "Steeplechase Hill", street(-6.47170, 53.50993))
    idx.add("meath", "Steeplechase Hill", Feature("address", -6.47013, 53.50911, OSM), "18")
    idx.add("meath", "Steeplechase Hill", Feature("address", -6.47255, 53.51043, OSM), "45")
    # Carlow: Borris and the Woodlawn Park estate.
    idx.add("carlow", "Borris", place(-6.92021, 52.59880))
    idx.add("carlow", "Woodlawn Park", estate(-6.93494, 52.60392))
    idx.add("carlow", "Woodlawn Park", Feature("address", -6.93606, 52.60477, OSM), "54")
    return idx


def test_a_street_is_found_past_an_unknown_middle_part() -> None:
    """Nominatim gave up at "Knightswood" and fell back to a town: no result."""
    m = match(index(), "24 Knightswood Crescent, Knightswood, Williamstown", "waterford")
    assert m is not None
    assert (m.confidence, m.method, m.part) == (C.STREET, "osm:street", "24 Knightswood Crescent")
    assert km_between(m.lon, m.lat, -7.09396, 52.24059) < 0.01


def test_a_house_number_on_the_street_is_exact() -> None:
    m = match(index(), "54 Woodlawn Park, Borris, Co. Carlow", "carlow")
    assert m is not None and (m.confidence, m.method) == (C.EXACT, "osm:address")
    assert (m.lon, m.lat) == (-6.93606, 52.60477)
    # A number OSM does not have: the estate, at street level.
    m = match(index(), "10 Woodlawn Park, Borris, Co. Carlow", "carlow")
    assert m is not None and (m.confidence, m.method) == (C.STREET, "osm:estate")


def test_nothing_is_accepted_without_a_place_to_anchor_it() -> None:
    assert match(index(), "24 Knightswood Crescent, Tramore", "waterford") is None
    assert match(index(), "24 Knightswood Crescent", "waterford") is None


def test_a_street_far_from_the_named_place_is_rejected() -> None:
    idx = index()
    idx.add("waterford", "Dunmore East", place(-6.9923, 52.1511))
    # Knightswood Crescent is 11 km from Dunmore East.
    assert match(idx, "3 Knightswood Crescent, Dunmore East", "waterford") is None


def test_two_streets_of_one_name_near_the_place_are_ambiguous() -> None:
    idx = index()
    idx.add("meath", "Main Street", street(-6.4640, 53.5073))
    idx.add("meath", "Main Street", street(-6.4850, 53.5010))  # 1.5 km away
    assert match(idx, "5 Main St, Ratoath", "meath") is None


def test_a_one_letter_misspelling_is_forgiven_in_a_long_word() -> None:
    m = match(index(), "18 Steplechase Hill, Ratoath, Meath", "meath")
    assert m is not None
    assert (m.confidence, m.method) == (C.STREET, "osm:street_fuzzy")


def test_misspellings_are_not_forgiven_in_street_words_or_one_word_names() -> None:
    idx = index()
    idx.add("meath", "The Paddocks", street(-6.4600, 53.5080))
    idx.add("meath", "Killoo", estate(-6.4620, 53.5070))
    assert match(idx, "34 The Paddock, Ratoath", "meath") is None
    assert match(idx, "Kiloo, Ratoath", "meath") is None


def test_a_street_word_name_is_anchored_only_by_its_estate() -> None:
    """ "The Park" is in every town: only the part right after it can place it."""
    idx = Index()
    idx.add("donegal", "Ballybofey", place(-7.7900, 54.7990, 3.0))
    idx.add("donegal", "The Park", Feature("address", -7.80295, 54.79703, OSM), "17")
    idx.add("donegal", "The Park", street(-7.80295, 54.79703))
    assert match(idx, "17 The Park, Blue Cedars, Ballybofey", "donegal") is None
    idx.add("donegal", "Blue Cedars", estate(-7.8030, 54.7972))
    m = match(idx, "17 The Park, Blue Cedars, Ballybofey", "donegal")
    assert m is not None and m.confidence is C.EXACT


def test_a_part_that_names_a_place_is_left_to_the_locality_steps() -> None:
    idx = Index()
    idx.add("kilkenny", "Thomastown", place(-7.1370, 52.5270, 3.0))
    idx.add("kilkenny", "Jerpoint West", place(-7.1580, 52.5250, 1.2))
    idx.add("kilkenny", "Jerpoint West", estate(-7.15873, 52.52486, NHDS))
    assert match(idx, "Jerpoint West, Thomastown, Co Kilkenny", "kilkenny") is None


def test_every_later_place_must_agree() -> None:
    """ "7 Waverly Avenue, Waverly, Blacklion": the street is near a Waverly, 59 km from
    the Blacklion the address names."""
    idx = Index()
    idx.add("wicklow", "Waverly Avenue", street(-6.08648, 53.15006))
    idx.add("wicklow", "Waverly", place(-6.0870, 53.1490, 1.0))
    idx.add("wicklow", "Blacklion", place(-6.1080, 52.6250, 1.0))
    assert match(idx, "7 Waverly Avenue, Waverly, Blacklion", "wicklow") is None
    # A post town 14 km away is normal ("28 Firies Close, Firies, Killarney").
    idx.add("wicklow", "Arklow", place(-6.1400, 53.0250, 3.0))
    m = match(idx, "7 Waverly Avenue, Waverly, Arklow", "wicklow")
    assert m is not None and m.method == "osm:street"


def test_a_city_is_checked_but_never_anchors() -> None:
    idx = Index()
    idx.add("dublin", "Oak Park", street(-6.2480, 53.3920))
    idx.add("dublin", "Dublin", Feature("city", -6.2603, 53.3498, OSM, 8.0))
    assert match(idx, "12 Oak Park, Dublin 9", "dublin") is None


def test_surveyed_estates_are_labelled_with_their_source() -> None:
    idx = Index()
    idx.add("louth", "Tallanstown", place(-6.5440, 53.9240, 1.5))
    idx.add("louth", "Dundalk", place(-6.4050, 54.0010, 3.0))
    idx.add("louth", "Tallonsfield Manor", estate(-6.5460, 53.9220, NHDS))
    m = match(idx, "31 Tallonsfield Manor, Tallanstown, Dundalk", "louth")
    assert m is not None and (m.method, m.source) == ("nhds:estate", NHDS)


def test_place_reach() -> None:
    assert place_radius_km("town") == 3.0
    assert place_radius_km(None, area_km2=math.pi) == 1.5
    assert place_radius_km(None, area_km2=5000) == 4.0  # capped


def test_only_residential_buildings_count_as_streets() -> None:
    """ "Adamstown" matched Adamstown railway station and moved a suburb onto it."""
    station = {"category": "building", "type": "train_station", "name": "Adamstown"}
    flats = {"category": "building", "type": "apartments", "name": "The Benson Building"}
    assert classify(station, "Adamstown") == (None, "implausible_type")
    assert classify(flats, "The Benson Building") == (C.STREET, "")
