"""Parsing the CSO RPPI (table HPM09, D-053) from rows of the real file."""

from datetime import date

import pytest

from ppr_pipeline.benchmarks import parse_rppi
from tests.conftest import FIXTURES

SAMPLE = (FIXTURES / "hpm09_sample.csv").read_bytes()


def test_parse_keeps_only_published_index_values() -> None:
    rows = parse_rppi(SAMPLE)
    # 6 national and South-East values for 2010, 2025 and 2026, 4 more South-East months;
    # the blank Dublin City value of 2005 and the 12-month change are left out.
    assert len(rows) == 10
    assert ("rppi:00", date(2010, 1, 1), 113.2) in rows  # "-" is the national series
    assert ("rppi:24", date(2026, 7, 1), 246.9) in rows
    assert {k for k, _, _ in rows} == {"rppi:00", "rppi:24"}
    assert not any(v == 8.8 for _, _, v in rows)


def test_parse_fails_loudly_on_a_changed_layout() -> None:
    renamed = SAMPLE.replace(b'"C02803V03373"', b'"C99999V99999"', 1)
    with pytest.raises(ValueError, match="layout changed"):
        parse_rppi(renamed)
    header_only = SAMPLE.split(b"\n", 1)[0] + b"\n"
    with pytest.raises(ValueError, match="no index values"):
        parse_rppi(header_only)
