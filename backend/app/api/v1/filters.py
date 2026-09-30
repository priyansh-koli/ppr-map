"""The search filters as query parameters, shared by /properties and /search (D-047).

Lists are one comma-separated parameter (`county=cork,kerry`), as the tile server receives
them. Validation is `SalesFilter`'s, and a failure is an ordinary 422."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.models.enums import GeocodeConfidence
from app.schemas.properties import SalesFilter


def sales_filter(
    price_min: Annotated[Decimal | None, Query(alias="priceMin", ge=0)] = None,
    price_max: Annotated[Decimal | None, Query(alias="priceMax", ge=0)] = None,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    type_: Annotated[Literal["new", "second_hand", "any"], Query(alias="type")] = "any",
    exclude_non_market: Annotated[bool, Query(alias="excludeNonMarket")] = True,
    exclude_bulk: Annotated[bool, Query(alias="excludeBulk")] = True,
    min_confidence: Annotated[
        GeocodeConfidence, Query(alias="minConfidence")
    ] = GeocodeConfidence.LOCALITY,
    vat: Literal["exclusive", "inclusive", "any"] = "any",
    county: Annotated[str | None, Query(description="Counties, comma-separated")] = None,
    area: Annotated[str | None, Query(description="Area slugs, comma-separated")] = None,
    routing_key: Annotated[
        str | None, Query(alias="routingKey", description="Eircode routing keys, e.g. D08,A63")
    ] = None,
    near: Annotated[str | None, Query(description="lat,lng")] = None,
    radius_m: Annotated[
        int | None, Query(alias="radiusM", description="With near; 100 to 20,000, default 1,000")
    ] = None,
    max_stop_m: Annotated[
        int | None, Query(alias="maxStopM", description="Nearest stop within this many metres")
    ] = None,
    max_school_m: Annotated[
        int | None, Query(alias="maxSchoolM", description="Nearest school within this many metres")
    ] = None,
) -> SalesFilter:
    raw = {
        "priceMin": price_min,
        "priceMax": price_max,
        "dateFrom": date_from,
        "dateTo": date_to,
        "type": type_,
        "excludeNonMarket": exclude_non_market,
        "excludeBulk": exclude_bulk,
        "minConfidence": min_confidence,
        "vat": vat,
        "county": county,
        "area": area,
        "routingKey": routing_key,
        "near": near,
        "radiusM": radius_m,
        "maxStopM": max_stop_m,
        "maxSchoolM": max_school_m,
    }
    try:
        return SalesFilter.model_validate({k: v for k, v in raw.items() if v is not None})
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("query", *e["loc"])} for e in exc.errors(include_url=False)]
        ) from None
