"""The search filter model and the autocomplete helpers, without a database."""

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
