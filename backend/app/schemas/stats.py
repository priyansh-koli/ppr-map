"""National overview for the home page (D-043): counts and medians the pipeline already
computed in `area_stats` (market sales only, n < 5 suppressed, D-037)."""

from datetime import date

from pydantic import Field

from app.schemas.base import ApiModel, Money


class MonthCount(ApiModel):
    month: date = Field(description="First day of the month.")
    sales: int = Field(description="Market sales filed for this month, all counties.")
    provisional: bool = Field(description="Late filings still arrive for this month.")


class CountyStat(ApiModel):
    slug: str
    name: str
    sales: int = Field(description="Market sales in the 12 months to `Overview.windowEnd`.")
    median_price_eur: Money | None = Field(description="None when fewer than 5 sales.")
    lat: float = Field(description="A point inside the county, for centring the map.")
    lng: float


class Overview(ApiModel):
    data_version: str
    total_sales: int = Field(description="Every sale on the register, market or not.")
    total_properties: int
    first_sale_date: date
    monthly: list[MonthCount] = Field(description="The last 24 months, oldest first.")
    window_start: date = Field(description="First month of the counties' 12-month window.")
    window_end: date = Field(description="Last month of that window: the latest complete one.")
    counties: list[CountyStat] = Field(description="Most sales first.")
