"""Map, hover-card and property-page shapes (docs/api.md). camelCase on the wire."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.models.enums import GeocodeConfidence, PoiType
from app.schemas.base import ApiModel, Money


class Meta(ApiModel):
    data_version: str
    ppr_max_sale_date: date
    provisional_from: date = Field(description="Sales on or after this date are provisional.")
    last_ingest_at: datetime | None


# --- filters shared by the map tiles and the list ------------------------------------------


class SalesFilter(ApiModel):
    """The same filters, with the same defaults, as `/tiles/sales`."""

    price_min: Money | None = Field(None, ge=0)
    price_max: Money | None = Field(None, ge=0)
    date_from: date | None = None
    date_to: date | None = None
    type: Literal["new", "second_hand", "any"] = "any"
    exclude_non_market: bool = True
    exclude_bulk: bool = True
    min_confidence: GeocodeConfidence = GeocodeConfidence.LOCALITY


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


class PropertyListItem(ApiModel):
    id: str
    address: str
    confidence: GeocodeConfidence
    lat: float
    lng: float
    latest_sale: LatestSale
    n_sales: int


class PropertyList(ApiModel):
    items: list[PropertyListItem]
    total: int
    page: int
    page_size: int


# --- property page -------------------------------------------------------------------------


class Location(ApiModel):
    lat: float
    lng: float
    confidence: GeocodeConfidence
    method: str | None
    source: str | None


class Sale(ApiModel):
    date: date
    price_eur: Money
    is_new: bool
    not_full_market_price: bool
    vat_exclusive: bool
    bulk_group_size: int | None
    size_band: str | None
    possible_duplicate: bool


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
