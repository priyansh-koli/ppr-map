"""Area page shapes (docs/api.md, Areas; D-049)."""

from datetime import date
from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel, Money
from app.schemas.properties import AreaRef

PeriodKindName = Literal["month", "quarter", "year", "rolling_12m"]
SegmentName = Literal["all", "new", "second_hand"]


class Headline(ApiModel):
    """The latest complete 12 months (no provisional month in it)."""

    window_start: date
    window_end: date
    n: int
    median: Money | None
    p25: Money | None
    p75: Money | None
    change_pct: float | None = Field(
        None,
        description="Median against the 12 months a year earlier; null if either is suppressed",
    )


class AreaAttributeOut(ApiModel):
    label: str
    value: str
    source: str
    as_of: date
    licence: str


class SubArea(ApiModel):
    kind: str
    name: str
    slug: str
    n: int
    median: Money | None


class PriceIndex(ApiModel):
    """The CSO's index for the area's region: its change over the latest 12 months."""

    label: str
    month: date
    change12m_pct: float = Field(alias="change12mPct")
    source: str = "CSO Residential Property Price Index (CC BY 4.0)"


class AreaDetail(ApiModel):
    kind: str
    name: str
    name_ga: str | None
    slug: str
    code: str
    parents: list[AreaRef]
    bbox: list[float]
    geometry: dict[str, object] = Field(description="Simplified GeoJSON, for display only")
    headline: Headline | None
    national: Headline | None
    attributes: list[AreaAttributeOut]
    children: list[SubArea]
    children_kind: str | None
    period_kinds: list[PeriodKindName] = Field(description="Series this area has")
    price_index: PriceIndex | None = None
    point_based: bool = Field(
        description="True for Small Areas and EDs: only sales placed at their house or street "
        "can be counted in them"
    )
    source: str
    data_version: str


class SeriesPoint(ApiModel):
    period_start: date
    n: int
    median: Money | None
    p25: Money | None
    p75: Money | None
    provisional: bool
    suppressed: bool


class AreaStatsOut(ApiModel):
    area: AreaRef
    period_kind: PeriodKindName
    segment: SegmentName
    points: list[SeriesPoint]
    national: list[SeriesPoint] = Field(description="Ireland, same periods and segment")


class Bin(ApiModel):
    from_eur: Money
    to_eur: Money | None
    n: int | None = Field(description="null when fewer than 5 sales (suppressed)")


class Distribution(ApiModel):
    area: AreaRef
    window_start: date
    window_end: date
    n: int
    bins: list[Bin]
    national_share: list[float | None] = Field(
        description="Share of Ireland's sales in each bin, for comparison"
    )
