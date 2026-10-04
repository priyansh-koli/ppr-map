"""The search filter model and the autocomplete helpers, without a database."""

import re

import pytest
from pydantic import ValidationError

from app.schemas.properties import SalesFilter
from app.services.search import (
    address_words,
    near_box,
    normalise,
    routing_key_district,
    routing_key_for,
    search_sql,
)


def test_filters_round_trip_through_url_parameters() -> None:
    f = SalesFilter.model_validate(
        {
            "county": "Cork, kerry",
            "routingKey": ["t12,p31"],
            "near": "51.9,-8.47",
            "radiusM": "2000",
            "excludeBulk": "false",
            "priceMax": "450000",
        }
    )
    params = f.to_params()
    assert params == {
        "priceMax": "450000",
        "excludeBulk": "false",
        "county": "cork,kerry",
        "routingKey": "T12,P31",
        "near": "51.900000,-8.470000",
        "radiusM": "2000",
    }
    assert SalesFilter.model_validate(params) == f
    assert SalesFilter().to_params() == {}


@pytest.mark.parametrize(
    ("given", "sent"),
    [("1e6", "1000000"), ("1E+6", "1000000"), ("250000.00", "250000"), ("99.5", "99.5")],
)
def test_prices_reach_the_tile_functions_in_plain_notation(given: str, sent: str) -> None:
    # tile_param_number only reads ^\d{1,12}(\.\d{1,2})?$; anything else drops the filter.
    params = SalesFilter.model_validate({"priceMin": given, "priceMax": given}).to_params()
    assert params == {"priceMin": sent, "priceMax": sent}
    assert re.fullmatch(r"\d{1,12}(\.\d{1,2})?", params["priceMin"])


@pytest.mark.parametrize(
    "bad",
    [
        {"county": "narnia"},
        {"area": "sa-1/2"},
        {"routingKey": "B12"},
        {"near": "48.85,2.35"},
        {"radiusM": "900"},
        {"near": "53,-7", "radiusM": "30000"},
        {"dateFrom": "2025-02-01", "dateTo": "2025-01-01"},
        {"maxStopM": "5"},
        {"priceMin": "1.234"},
        {"priceMax": "1e-7"},
    ],
)
def test_filters_refuse_what_cannot_be_right(bad: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        SalesFilter.model_validate(bad)


def test_routing_keys_and_dublin_districts() -> None:
    assert routing_key_for("d08") == "D08"
    assert routing_key_for("dublin 8") == "D08"
    assert routing_key_for("d 6w") == "D6W"
    assert routing_key_for("a63") == "A63"
    assert routing_key_for("b63") is None  # no routing key starts with B
    assert routing_key_for("dublin") is None
    assert routing_key_district("D08") == "D8"
    assert routing_key_district("D6W") == "D6W"
    assert routing_key_district("A63") is None


def test_address_words_expand_short_forms() -> None:
    assert address_words(normalise("12 Pollerton Rd., Co. Carlow")) == [
        "12",
        "pollerton",
        "road",
        "carlow",
    ]


def test_near_box_covers_the_radius() -> None:
    _, s, e, n = near_box("53.0,-7.0", 1000)
    assert round(n - 53.0, 4) == round(53.0 - s, 4) == 0.009
    assert 0.014 < e - (-7.0) < 0.016  # a degree of longitude is shorter at 53° N


def test_sort_by_change_ranks_every_match() -> None:
    assert "LEFT JOIN LATERAL" in search_sql("-change").split("page AS")[1].split("SELECT")[1]
    assert "change_pct DESC NULLS LAST" in search_sql("-change")
    assert "ORDER BY sale_date DESC" in search_sql("-date")


def test_hidden_price_bands_cannot_be_worked_out_from_the_total() -> None:
    """P1 #14: with the total published, one hidden band was the total minus the rest."""
    from app.services.areas import suppress_bins

    assert suppress_bins([7, 12, 0, 30], 5) == [7, 12, 0, 30]  # nothing small: all shown
    # One small band: the empty one is hidden too, then the smallest shown (7), so the
    # hidden total (3 + 0 + 7) is at least 5 and spread over three bands.
    assert suppress_bins([7, 3, 0, 30], 5) == [None, None, None, 30]
    # Two small bands that already hold 5 between them are enough.
    assert suppress_bins([2, 3, 9, 30], 5) == [None, None, 9, 30]
    # A single small band among large ones takes the smallest one with it.
    assert suppress_bins([40, 4, 9, 30], 5) == [40, None, None, 30]
    assert suppress_bins([1, 1, 0], 5) == [None, None, None]  # all hidden is allowed
    for counts in ([7, 3, 0, 30], [2, 3, 9, 30], [40, 4, 9, 30], [6, 1, 8, 5, 0, 2]):
        out = suppress_bins(counts, 5)
        hidden = sum(counts) - sum(c for c in out if c is not None)
        assert hidden == 0 or (hidden >= 5 and out.count(None) >= 2), (counts, out)
