"""Load and validate config/sources.yaml (D-016, D-022)."""

from datetime import date
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, model_validator

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "sources.yaml"


class Source(BaseModel):
    name: str
    url: str
    licence: str
    use: bool
    format: str | None = None
    attribution: str | None = None
    cadence: str | None = None
    verified: bool = False
    checked_on: date | None = None
    reason: str | None = None
    out_fields: list[str] | None = None
    forbidden_fields: list[str] | None = None
    datasets: dict[str, str] | None = None  # pinned per-layer download URLs

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.use and not self.attribution:
            raise ValueError("sources in use need an attribution line")
        if not self.use and not self.reason:
            raise ValueError("unused sources must say why")
        if self.verified and self.checked_on is None:
            raise ValueError("verified sources need checked_on")
        if self.out_fields and self.forbidden_fields:
            leaked = set(self.out_fields) & set(self.forbidden_fields)
            if leaked:
                raise ValueError(f"forbidden fields requested: {sorted(leaked)}")
        return self


class SourcesFile(BaseModel):
    sources: dict[str, Source]


def load_sources(path: Path = DEFAULT_PATH) -> dict[str, Source]:
    return SourcesFile.model_validate(yaml.safe_load(path.read_text())).sources
