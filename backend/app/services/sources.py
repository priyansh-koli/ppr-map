"""The data sources behind the site, from config/sources.yaml (D-016, D-022, D-055).

The pipeline validates the whole file (ppr_pipeline.sources); this reads only what the
/sources page shows, so the API image does not need the pipeline package.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from app.services.config_files import ConfigFile


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    url: str
    licence: str
    use: bool
    loaded: bool = False
    attribution: str | None = None
    cadence: str | None = None
    verified: bool = False
    checked_on: date | None = None
    reason: str | None = None


class SourcesFile(BaseModel):
    sources: dict[str, Source]


load_sources = ConfigFile("sources.yaml", lambda data: SourcesFile.model_validate(data).sources)
