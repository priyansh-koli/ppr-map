"""Address normalisation, on real PPR addresses."""

import pytest

from ppr_pipeline.address import (
    dublin_district_from_eircode,
    normalise_address,
    normalise_eircode,
)


def test_all_caps_becomes_title_case_but_abbreviations_stay_as_written() -> None:
    a = normalise_address("41 COLLINS SQ, BENBURB ST, DUBLIN 6W", "dublin")
    assert a.display == "41 Collins Sq, Benburb St, Dublin 6W"
    assert a.normalised == "41 collins square, benburb street, dublin 6w"
    assert a.house_number == "41"
    assert a.dublin_district == "D6W"


def test_mixed_case_text_is_trusted() -> None:
    a = normalise_address("18 D'Alton Drive, Salthill, Galway", "galway")
    assert a.display == "18 D'Alton Drive, Salthill, Galway"


@pytest.mark.parametrize(
    ("raw", "display"),
    [
        ("6 THE SYCAMORE, THE PARK, ATHLUMNEY WOOD", "6 The Sycamore, The Park, Athlumney Wood"),
        ("PARISH OF ANNE ST", "Parish of Anne St"),
        ("66 RORY O'CONNOR PLACE, ARKLOW", "66 Rory O'Connor Place, Arklow"),
        ("16 ST ENDA'S DRIVE, RATHFARNHAM", "16 St Enda's Drive, Rathfarnham"),
        ("2 MCDONAGH PARK, TUAM", "2 McDonagh Park, Tuam"),
    ],
)
def test_title_case(raw: str, display: str) -> None:
    assert normalise_address(raw, "dublin").display == display


def test_saint_versus_street() -> None:
    assert normalise_address("St. John's, 4 Cherrywood", "dublin").normalised.startswith(
        "saint john's"
    )
    assert normalise_address("5 MAIN ST, NAAS", "kildare").normalised == "5 main street, naas"
    assert normalise_address("5 MAIN ST LOWER, NAAS", "kildare").normalised.startswith(
        "5 main street lower"
    )


def test_county_suffix_variants_share_one_key() -> None:
    keys = {
        normalise_address(raw, "cork").key
        for raw in (
            "11 GRANGE TERRACE, DOUGLAS, CORK",
            "11 Grange Terrace, Douglas, Co. Cork",
            "11 GRANGE TCE, DOUGLAS, CO CORK",
            "11 Grange Terrace, Douglas, County Cork",
            "11 Grange Terrace, Douglas,Co.Cork",
        )
    }
    assert keys == {"11grangeterracedouglas"}


def test_county_word_is_only_shortened_before_a_county_name() -> None:
    assert "county hall" in normalise_address("1 COUNTY HALL, CORK", "cork").normalised


def test_unit_is_split_from_the_building_key() -> None:
    a = normalise_address(
        "Apartment 12  Block B, Corofin House  Clare Village, Dublin 17", "dublin"
    )
    b = normalise_address("APT 12, BLOCK B, COROFIN HOUSE CLARE VILLAGE, DUBLIN 17", "dublin")
    assert a.unit == b.unit == "apartment 12 block b"
    assert a.key == b.key == "corofinhouseclarevillagedublin17"
    assert a.house_number is None
    assert a.dublin_district == "D17"


def test_house_number_prefix_and_junk_parts() -> None:
    a = normalise_address("No. 11 Blackrock Court, Quay Road, Ballina", "mayo")
    assert a.house_number == "11"
    assert a.key == "11blackrockcourtquayroadballina"
    b = normalise_address("Drumacloughan, Ramelton, n/a", "donegal")
    assert b.display == "Drumacloughan, Ramelton"
    assert b.house_number is None


def test_irish_small_words_and_numbers() -> None:
    a = normalise_address("7 Cul Na Toinne, Bunbeg.", "donegal")
    assert a.display == "7 Cul Na Toinne, Bunbeg"  # mixed case: as filed
    assert normalise_address("7 CUL NA TOINNE, BUNBEG", "donegal").display == (
        "7 Cul na Toinne, Bunbeg"
    )


def test_address_with_no_usable_text_has_empty_key() -> None:
    a = normalise_address("NA, NA", "galway")
    assert a.key == ""
    assert a.display == "NA, NA"


def test_dublin_district_only_for_valid_districts() -> None:
    assert normalise_address("1 MAIN ST, DUBLIN 19", "dublin").dublin_district is None
    assert normalise_address("1 MAIN ST, DUBLIN 4", "dublin").dublin_district == "D4"
    assert normalise_address("1 DUBLIN RD, DUBLIN 4", "kildare").dublin_district is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("D13N5XF", "D13N5XF"),
        ("d6w ct92", "D6WCT92"),
        ("T45AE33", "T45AE33"),
        ("", None),
        ("B12ABCD", None),  # B is not a routing-key letter
        ("D13N5X", None),
    ],
)
def test_eircode_format(raw: str, expected: str | None) -> None:
    assert normalise_eircode(raw) == expected


def test_dublin_district_from_eircode() -> None:
    assert dublin_district_from_eircode("D6WCT92") == "D6W"
    assert dublin_district_from_eircode("D01AB12") == "D1"
    assert dublin_district_from_eircode("A94X2Y3") is None
