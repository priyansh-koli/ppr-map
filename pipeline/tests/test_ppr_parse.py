"""PPR CSV parsing, on real rows (tests/fixtures/ppr_sample.csv)."""

from datetime import date
from decimal import Decimal

import pytest
from app.models.enums import County, SizeBand

from ppr_pipeline.ppr.parse import (
    HeaderMismatchError,
    ParsedRow,
    RawRow,
    RowError,
    parse,
    parse_description,
    parse_size,
    read_rows,
)


def _parsed(sample_csv: bytes) -> list[ParsedRow]:
    items = list(parse(read_rows(sample_csv)))
    assert all(isinstance(i, ParsedRow) for i in items)
    return [i for i in items if isinstance(i, ParsedRow)]


def test_fixture_decodes_as_cp1252_and_keeps_raw_text(sample_csv: bytes) -> None:
    rows = _parsed(sample_csv)
    assert len(rows) == 26
    first = rows[0]
    assert first.raw[4] == "€228,500.00"  # byte 0x80 in the file
    assert first.raw[7] == "Teach/Árasán Cónaithe Atháimhe"
    assert first.sale_date == date(2010, 2, 1)
    assert first.county is County.LIMERICK
    assert first.price_eur == Decimal("228500.00")
    assert first.is_new is False


def test_irish_and_mojibake_descriptions(sample_csv: bytes) -> None:
    rows = _parsed(sample_csv)
    mojibake = next(r for r in rows if "?" in r.raw[7])
    assert mojibake.is_new is True
    assert mojibake.size_band is SizeBand.LT_38  # "n?os l? n? 38 m?adar cearnach"
    irish_new = next(r for r in rows if r.raw[7] == "Teach/Árasán Cónaithe Nua")
    assert irish_new.size_band is SizeBand.FROM_38_TO_125


@pytest.mark.parametrize(
    ("text", "band"),
    [
        ("", None),
        ("less than 38 sq metres", SizeBand.LT_38),
        (
            "greater than or equal to 38 sq metres and less than 125 sq metres",
            SizeBand.FROM_38_TO_125,
        ),
        ("greater than 125 sq metres", SizeBand.GTE_125),
        ("greater than or equal to 125 sq metres", SizeBand.GTE_125),
    ],
)
def test_size_bands(text: str, band: SizeBand | None) -> None:
    assert parse_size(text) is band


def test_unknown_values_are_errors_not_guesses() -> None:
    with pytest.raises(ValueError, match="description"):
        parse_description("Commercial")
    with pytest.raises(ValueError, match="size"):
        parse_size("about 90 m2")


def test_exact_duplicate_rows_get_distinct_hashes_and_the_repeat_is_flagged(
    sample_csv: bytes,
) -> None:
    rows = _parsed(sample_csv)
    dups = [r for r in rows if r.raw[1] == "29 KING STREET, BELLTREE, CLONGRIFFIN"]
    assert len(dups) == 2
    assert dups[0].source_row_hash != dups[1].source_row_hash
    assert [d.is_possible_duplicate for d in dups] == [False, True]
    assert sum(r.is_possible_duplicate for r in rows) == 1


def test_hash_ignores_whitespace_changes_only() -> None:
    a = RawRow(2, ("01/01/2020", "1  MAIN ST", "Cork", "", "€1.00", "No", "No", "New x", ""))
    b = RawRow(2, ("01/01/2020", "1 MAIN ST ", "Cork", "", "€1.00", "No", "No", "New x", ""))
    c = RawRow(2, ("01/01/2020", "2 MAIN ST", "Cork", "", "€1.00", "No", "No", "New x", ""))
    (ha, hb, hc) = [
        next(i for i in parse([r]) if isinstance(i, ParsedRow)).source_row_hash for r in (a, b, c)
    ]
    assert ha == hb != hc


def test_bad_rows_become_errors_with_line_numbers() -> None:
    good = (
        "01/01/2020",
        "1 MAIN ST",
        "Cork",
        "",
        "€100,000.00",
        "No",
        "No",
        "Second-Hand Dwelling house /Apartment",
        "",
    )
    rows = [
        RawRow(2, good),
        RawRow(3, good[:8]),
        RawRow(4, (*good[:4], "100000", *good[5:])),
        RawRow(5, (good[0], good[1], "Antrim", *good[3:])),
        RawRow(6, ("31/02/2020", *good[1:])),
    ]
    items = list(parse(rows))
    errors = [i for i in items if isinstance(i, RowError)]
    assert [e.line_no for e in errors] == [3, 4, 5, 6]
    assert "9 fields" in errors[0].error
    assert "price" in errors[1].error
    assert "county" in errors[2].error


def test_header_change_stops_the_run(sample_csv: bytes) -> None:
    changed = sample_csv.replace(b"Eircode", b"Postcode", 1)
    with pytest.raises(HeaderMismatchError):
        list(read_rows(changed))
