"""Map, hover-card and property-page shapes (docs/api.md). camelCase on the wire."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.models.enums import County, GeocodeConfidence, PoiType
from app.schemas.base import ApiModel, Money


class Meta(ApiModel):
    data_version: str
    tiles_version: str = Field(
        description="Changes with the data version and whenever an administrator hides or "
        "moves a property. The tile server caches by URL, so map tiles carry it as `v`."
    )
    ppr_max_sale_date: date
    provisional_from: date = Field(description="Sales on or after this date are provisional.")
    last_ingest_at: datetime | None


# --- filters shared by the map tiles and the list ------------------------------------------


ROUTING_KEY = re.compile(r"^(?:[AC-FHKNPRTV-Y]\d{2}|D6W)$")
SLUG = re.compile(r"^[a-z0-9_-]{1,80}$")
MAX_LIST = 50


def _split(value: object) -> object:
    """Lists travel as one comma-separated query parameter (`county=cork,kerry`), as the
    tile server receives them."""
    if isinstance(value, str):
        value = [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return [p.strip() for v in value for p in v.split(",") if p.strip()] or None
    return value


class SalesFilter(ApiModel):
    """What a search matches: the map tiles, the synced list, /search, saved searches and
    alerts all use these filters with these defaults (`tile_matching_sales`, D-047)."""

    price_min: Money | None = Field(None, ge=0, le=Decimal("9999999999.99"), decimal_places=2)
    price_max: Money | None = Field(None, ge=0, le=Decimal("9999999999.99"), decimal_places=2)
    date_from: date | None = None
    date_to: date | None = None
    type: Literal["new", "second_hand", "any"] = "any"
    exclude_non_market: bool = True
    exclude_bulk: bool = True
    min_confidence: GeocodeConfidence = GeocodeConfidence.LOCALITY
    vat: Literal["exclusive", "inclusive", "any"] = "any"
    county: list[County] | None = Field(None, max_length=26)
    area: list[str] | None = Field(None, max_length=MAX_LIST, description="Area slugs")
    routing_key: list[str] | None = Field(None, max_length=MAX_LIST)
    near: str | None = Field(None, description="lat,lng", examples=["53.3498,-6.2603"])
    radius_m: int | None = Field(None, ge=100, le=20_000, alias="radiusM")
    max_stop_m: int | None = Field(None, ge=50, le=10_000, alias="maxStopM")
    max_school_m: int | None = Field(None, ge=50, le=10_000, alias="maxSchoolM")

    _split_lists = field_validator("county", "area", "routing_key", mode="before")(_split)

    @field_validator("price_min", "price_max")
    @classmethod
    def _plain_price(cls, value: Decimal | None) -> Decimal | None:
        # "1e6" is a valid Decimal, but its str() is "1E+6", which tile_param_number does
        # not read: the filter would be dropped while echoed back as applied. Keep the
        # plain form ("1000000") so every consumer of to_params() sees the same number.
        return None if value is None else Decimal(format(value.normalize(), "f"))

    @field_validator("county", mode="before")
    @classmethod
    def _lower_counties(cls, value: object) -> object:
        if isinstance(value, str):
            return value.lower()
        if isinstance(value, list):
            return [v.lower() if isinstance(v, str) else v for v in value]
        return value

    @field_validator("area")
    @classmethod
    def _slugs(cls, value: list[str] | None) -> list[str] | None:
        if value and not all(SLUG.match(v) for v in value):
            raise ValueError("area must be area slugs")
        return value

    @field_validator("routing_key")
    @classmethod
    def _routing_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        keys = [v.upper() for v in value]
        if not all(ROUTING_KEY.match(k) for k in keys):
            raise ValueError("routingKey must be Eircode routing keys, such as D08 or A63")
        return keys

    @field_validator("near")
    @classmethod
    def _near(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            lat, lng = (float(v) for v in value.split(","))
        except ValueError:
            raise ValueError("near must be lat,lng") from None
        if not (51 <= lat <= 56 and -11 <= lng <= -5):
            raise ValueError("near must be a point in Ireland")
        return f"{lat:.6f},{lng:.6f}"

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        pmin, pmax = self.price_min, self.price_max
        if pmin is not None and pmax is not None and pmin > pmax:
            raise ValueError("priceMin must not be above priceMax")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("dateFrom must not be after dateTo")
        if self.radius_m is not None and self.near is None:
            raise ValueError("radiusM needs near")
        return self

    def to_params(self) -> dict[str, str]:
        """The non-default filters as query parameters: the URL of a search, the tile
        server's parameters and a saved search's stored query are all this dict."""
        out: dict[str, str] = {}
        defaults = SalesFilter()
        for name, field in type(self).model_fields.items():
            value = getattr(self, name)
            if value is None or value == getattr(defaults, name):
                continue
            key = field.alias or name
            if isinstance(value, list):
                out[key] = ",".join(str(v) for v in value)
            elif isinstance(value, bool):
                out[key] = str(value).lower()
            else:
                out[key] = str(value)
        return out


# --- hover card ----------------------------------------------------------------------------


class SaleFlags(ApiModel):
    not_full_market_price: bool
    vat_exclusive: bool
    bulk: bool


class LatestSale(ApiModel):
    date: date
    price_eur: Money
    is_new: bool
    flags: SaleFlags


class SaleBrief(ApiModel):
    date: date
    price_eur: Money


class AreaLine(ApiModel):
    name: str
    kind: str
    median12m: Money | None = Field(None, alias="median12m")
    n: int
    change12m_pct: float | None = Field(None, alias="change12mPct")
    provisional: bool


class StopValue(ApiModel):
    name: str | None = None
    type: PoiType
    distance_m: int


class SchoolValue(ApiModel):
    name: str | None = None
    distance_m: int


class Sourced[T](ApiModel):
    """Every enriched value carries where it came from and when."""

    value: T
    source: str
    as_of: str | None = None


class Flood(ApiModel):
    note: str
    link: str


class Vicinity(ApiModel):
    nearest_stop: Sourced[StopValue] | None = None
    nearest_primary_school: Sourced[SchoolValue] | None = None
    nearest_post_primary_school: Sourced[SchoolValue] | None = None
    shops_within1km: Sourced[int] | None = Field(None, alias="shopsWithin1km")
    deprivation: Sourced[str] | None = None
    distances: Literal["straight line"] | None = None
    flood: Flood


class PropertySummary(ApiModel):
    id: str
    address: str
    confidence: GeocodeConfidence
    latest_sale: LatestSale | None = None
    previous_sales: list[SaleBrief] = Field(default_factory=list)
    area: AreaLine | None = None
    vicinity: Vicinity
    data_version: str


# --- list ----------------------------------------------------------------------------------


class PriceChange(ApiModel):
    """Against the previous sale, only when both are plain market sales; not adjusted for
    inflation or for work done in between."""

    previous_date: date
    previous_price_eur: Money
    change_pct: float


class PropertyListItem(ApiModel):
    id: str
    address: str
    confidence: GeocodeConfidence
    lat: float
    lng: float
    latest_sale: LatestSale
    n_sales: int
    change: PriceChange | None = None


class PropertyList(ApiModel):
    items: list[PropertyListItem]
    total: int
    page: int
    page_size: int


class SearchResults(PropertyList):
    bbox: list[float] | None = Field(
        None, description="west, south, east, north of every match; null when none match"
    )
    query: dict[str, str] = Field(description="The filters applied, as URL parameters")
    places: list["AreaRef"] = Field(
        default_factory=list, description="The areas named by the `area` filter"
    )


# --- property page -------------------------------------------------------------------------


class Location(ApiModel):
    lat: float | None = Field(
        description="Null while the property has no point: before its first geocode, during "
        "a full re-geocode, or when it could not be located"
    )
    lng: float | None
    confidence: GeocodeConfidence
    method: str | None
    source: str | None


class VatEstimate(ApiModel):
    """A VAT-exclusive price with VAT added: an estimate, never the price paid (D-015)."""

    rate: float
    price_eur: Money
    applies_to: Literal["any", "qualifying_apartment"] = Field(
        description="'any' new dwelling, or only a qualifying apartment (9% from 8 Oct 2025)"
    )


class Sale(ApiModel):
    date: date
    price_eur: Money
    is_new: bool
    not_full_market_price: bool
    vat_exclusive: bool
    bulk_group_size: int | None
    size_band: str | None
    possible_duplicate: bool
    vat_estimates: list[VatEstimate] = Field(default_factory=list)


class AreaRef(ApiModel):
    kind: str
    name: str
    slug: str


class StatsPoint(ApiModel):
    period_start: date
    n: int
    median: Money | None
    provisional: bool
    suppressed: bool


class AreaSeries(ApiModel):
    area: AreaRef
    period_kind: Literal["rolling_12m"] = "rolling_12m"
    points: list[StatsPoint]


class PropertyDetail(ApiModel):
    id: str
    address: str
    county: str
    routing_key: str | None
    dublin_district: str | None
    location: Location
    sales: list[Sale]
    areas: list[AreaRef]
    vicinity: Vicinity
    area_series: AreaSeries | None
    caveats: list[str]
    data_version: str


# --- estimate and comparables (D-053) ------------------------------------------------------


class IndexSeries(ApiModel):
    key: str
    label: str
    source: str = "CSO Residential Property Price Index (CC BY 4.0)"


class Calibration(ApiModel):
    """How far repeat sales in this series landed from what the index implied."""

    years_between: Literal["0-3y", "3-7y", "7y+"]
    pairs: int
    pooled: bool = Field(description="True when the series had too few pairs: all of Ireland's")
    low_pct: float = Field(description="10th percentile, in % against the index")
    median_pct: float
    high_pct: float = Field(description="90th percentile, in % against the index")


class PriceEstimate(ApiModel):
    eligible: bool
    reason: str | None = None
    low_eur: Money | None = None
    mid_eur: Money | None = None
    high_eur: Money | None = None
    based_on: SaleBrief | None = None
    series: IndexSeries | None = None
    index_month: date | None = None
    index_change_pct: float | None = None
    calibration: Calibration | None = None
    method: str = Field(
        "The price at its last market sale, moved by the CSO's price index for its region and "
        "type from the month of that sale to the latest month published. The range is where "
        "8 in 10 repeat sales in that region landed against the same index. A home that was "
        "improved or run down since its sale will differ. Information, not a valuation."
    )


class Comparable(ApiModel):
    id: str
    address: str
    confidence: GeocodeConfidence
    date: date
    price_eur: Money
    is_new: bool
    vat_exclusive: bool
    distance_m: int
    same_street: bool


class Comparables(ApiModel):
    available: bool
    reason: str | None = None
    radius_m: int
    months: int
    total: int
    median_eur: Money | None = Field(
        None,
        description="Of the sales filed with VAT included; none when fewer than 5 of them",
    )
    median_n: int = Field(0, description="How many sales the median is of (VAT included)")
    items: list[Comparable]
