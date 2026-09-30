"""Autocomplete and search history shapes (docs/api.md, Search)."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.base import ApiModel


class Suggestion(ApiModel):
    """One autocomplete answer: a place to filter by, or a property to open."""

    kind: Literal[
        "county", "settlement", "electoral_division", "townland", "routing_key", "property"
    ]
    label: str
    detail: str | None = None
    slug: str | None = Field(None, description="Area slug, for area kinds")
    property_id: str | None = None
    routing_key: str | None = None
    lat: float | None = None
    lng: float | None = None
    bbox: list[float] | None = None


class SearchHistoryIn(ApiModel):
    query: dict[str, str] = Field(description="The search's URL parameters")
    label: str | None = Field(None, max_length=200, description="What the user searched for")


class SearchHistoryOut(ApiModel):
    id: int
    query: dict[str, str]
    label: str | None
    searched_at: datetime


class Page[T](ApiModel):
    items: list[T]
    total: int
    page: int
    page_size: int
