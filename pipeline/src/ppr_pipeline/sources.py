"""Load and validate config/sources.yaml (D-016, D-022)."""

import os
from datetime import date
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, model_validator

# The repo's config/ is found relative to the source in the editable dev install; an installed
# package (the Docker image) lives in site-packages, so it sets PPR_CONFIG_DIR instead.
REPO_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def default_path() -> Path:
    return Path(os.environ.get("PPR_CONFIG_DIR") or REPO_CONFIG_DIR) / "sources.yaml"


class Source(BaseModel):
    name: str
    url: str
    licence: str
    use: bool
    loaded: bool = False  # the site shows data from it (the /sources page, D-055)
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
        if self.loaded and not self.use:
            raise ValueError("a source we must not use cannot be loaded")
        if self.verified and self.checked_on is None:
            raise ValueError("verified sources need checked_on")
        if self.out_fields and self.forbidden_fields:
            leaked = set(self.out_fields) & set(self.forbidden_fields)
            if leaked:
                raise ValueError(f"forbidden fields requested: {sorted(leaked)}")
        return self


class SourcesFile(BaseModel):
    sources: dict[str, Source]


def load_sources(path: Path | None = None) -> dict[str, Source]:
    path = path or default_path()
    return SourcesFile.model_validate(yaml.safe_load(path.read_text())).sources
