"""Stage records: property keys and public ids (no database needed)."""

from ppr_pipeline.ppr.load import STAGE_COLUMNS, public_id, stage_record
from ppr_pipeline.ppr.parse import ParsedRow, RawRow, parse

KEY = STAGE_COLUMNS.index("address_key")
PUBLIC_ID = STAGE_COLUMNS.index("public_id")
DISTRICT = STAGE_COLUMNS.index("dublin_district")
SH = "Second-Hand Dwelling house /Apartment"


def _records(*rows: tuple[str, ...]) -> list[tuple[object, ...]]:
    parsed = parse(RawRow(i + 2, r) for i, r in enumerate(rows))
    return [stage_record(p) for p in parsed if isinstance(p, ParsedRow)]


def test_numbered_addresses_merge_across_sales() -> None:
    a, b = _records(
        (
            "08/01/2015",
            "9 The Elms, Castlejane Wood, Glanmire",
            "Cork",
            "",
            "€199,000.00",
            "No",
            "No",
            SH,
            "",
        ),
        (
            "24/11/2023",
            "9 THE ELMS, CASTLEJANE WOOD, GLANMIRE",
            "Cork",
            "T45AE33",
            "€320,000.00",
            "Yes",
            "No",
            SH,
            "",
        ),
    )
    assert a[KEY] == b[KEY] == "9theelmscastlejanewoodglanmire"
    assert a[PUBLIC_ID] == b[PUBLIC_ID]


def test_numberless_addresses_do_not_merge_but_repeat_filings_do() -> None:
    first = (
        "20/10/2014",
        "KNOCKROE, CASTLEREA, CO ROSCOMMON",
        "Roscommon",
        "",
        "€145,400.00",
        "No",
        "No",
        SH,
        "",
    )
    other = (
        "04/12/2014",
        "KNOCKROE, CASTLEREA, CO. ROSCOMMON",
        "Roscommon",
        "",
        "€56,000.00",
        "No",
        "No",
        SH,
        "",
    )
    a, repeat, b = _records(first, first, other)
    assert a[KEY] == repeat[KEY] != b[KEY]
    assert str(a[KEY]).startswith("knockroecastlerea~")
    assert str(b[KEY]).startswith("knockroecastlerea~")


def test_dublin_district_falls_back_to_the_eircode() -> None:
    (rec,) = _records(
        (
            "29/04/2021",
            "12 SOME ROAD, HAROLDS CROSS",
            "Dublin",
            "D6WCT92",
            "€1.00",
            "No",
            "No",
            SH,
            "",
        ),
    )
    assert rec[DISTRICT] == "D6W"


def test_public_id_is_stable_and_url_safe() -> None:
    from app.models.enums import County

    pid = public_id(County.CORK, "9theelmscastlejanewoodglanmire", None)
    assert pid == public_id(County.CORK, "9theelmscastlejanewoodglanmire", None)
    assert len(pid) == 12 and pid.isalnum() and pid.islower()
    assert pid != public_id(County.CORK, "9theelmscastlejanewoodglanmire", "apartment 1")
