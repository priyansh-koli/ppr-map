"""Where the data comes from, for the /sources page (docs/api.md, Meta; D-055)."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.schemas.base import ApiModel
from app.services import sources as s

router = APIRouter(tags=["meta"])


class SourceOut(ApiModel):
    key: str
    name: str
    url: str
    licence: str
    attribution: str | None
    cadence: str | None
    checked_on: date | None


class NotUsedOut(ApiModel):
    key: str
    name: str
    url: str
    licence: str
    reason: str


class Sources(ApiModel):
    in_use: list[SourceOut]
    """Loaded by the pipeline: the site shows data from these."""
    planned: list[SourceOut]
    """Allowed but not loaded yet, some with a licence still to confirm."""
    not_used: list[NotUsedOut]
    """Ruled out, each with the reason."""


@router.get("/sources", response_model=Sources)
def sources() -> Sources:
    """Each data source, its licence and attribution, and the ones we will not use."""
    try:
        all_ = s.load_sources()
    except (OSError, ValidationError) as exc:
        raise HTTPException(503, "The list of sources is not available") from exc

    def out(key: str, src: s.Source) -> SourceOut:
        return SourceOut(
            key=key,
            name=src.name,
            url=src.url,
            licence=src.licence,
            attribution=src.attribution,
            cadence=src.cadence,
            checked_on=src.checked_on if src.verified else None,
        )

    return Sources(
        in_use=[out(k, v) for k, v in all_.items() if v.use and v.loaded],
        planned=[out(k, v) for k, v in all_.items() if v.use and not v.loaded],
        not_used=[
            NotUsedOut(key=k, name=v.name, url=v.url, licence=v.licence, reason=v.reason or "")
            for k, v in all_.items()
            if not v.use
        ],
    )
