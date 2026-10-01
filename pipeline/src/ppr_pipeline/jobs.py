"""Pipeline steps as background jobs (D-007, D-051). The RQ worker runs these by name
(`ppr_pipeline.jobs.run`), so the backend can queue them without importing the pipeline.

Every step records its own `ingest_run`; a run started for an admin is marked with them.
"""

import uuid
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from app.config import get_settings

from ppr_pipeline import cli
from ppr_pipeline.aggregate import aggregate
from ppr_pipeline.benchmarks import download as benchmark_download
from ppr_pipeline.benchmarks import load_rppi
from ppr_pipeline.db import get_engine
from ppr_pipeline.enrich.run import enrich
from ppr_pipeline.geocode.gazetteer import build_gazetteer
from ppr_pipeline.geocode.runner import geocode_properties
from ppr_pipeline.ppr import ingest as ppr_ingest
from ppr_pipeline.sources import load_sources


def _ppr() -> dict[str, Any]:
    url = ppr_ingest.source_url()
    payload = ppr_ingest.download(url, cli.DATA_DIR / "raw" / "ppr" / "PPR-ALL.zip")
    summary = ppr_ingest.ingest_ppr(get_engine(), payload, url)
    return {"run_id": summary.run_id, "status": summary.status.value, **summary.stats}


def _gazetteer() -> dict[str, Any]:
    pbf = cli.DATA_DIR / cli.OSM_PBF
    if not pbf.exists():
        raise FileNotFoundError(f"{pbf} is missing: run `make osm-extract` first")
    return build_gazetteer(get_engine(), pbf, load_sources()["nhds"], cli.DATA_DIR, progress=print)


def _geocode() -> dict[str, Any]:
    return geocode_properties(get_engine(), get_settings().nominatim_url, progress=print)


def _enrich() -> dict[str, Any]:
    return enrich(get_engine(), load_sources(), cli.DATA_DIR, progress=print)


def _benchmarks() -> dict[str, Any]:
    src = load_sources()["cso_rppi"]
    return load_rppi(get_engine(), benchmark_download(src.url), src.url, progress=print)


def _aggregate() -> dict[str, Any]:
    return aggregate(get_engine(), progress=print)


STEPS: dict[str, Callable[[], dict[str, Any]]] = {
    "ppr": _ppr,
    "gazetteer": _gazetteer,
    "geocode": _geocode,
    "enrich": _enrich,
    "benchmarks": _benchmarks,
    "aggregate": _aggregate,
}
# The monthly run, in order (the Makefile's `make pipeline`).
MONTHLY = ["ppr", "gazetteer", "geocode", "enrich", "benchmarks", "aggregate"]


def run(step: str, triggered_by: str | None = None) -> dict[str, Any]:
    """Run one step, or `monthly` for all of them in order."""
    names = MONTHLY if step == "monthly" else [step]
    if any(n not in STEPS for n in names):
        raise ValueError(f"unknown pipeline step {step!r}")
    engine = get_engine()
    with engine.connect() as conn:
        before: int = conn.execute(
            sa.text("SELECT coalesce(max(id), 0) FROM ingest_run")
        ).scalar_one()
    results: dict[str, Any] = {}
    try:
        for name in names:
            print(f"pipeline step: {name}")
            results[name] = STEPS[name]()
    finally:
        if triggered_by:
            with engine.begin() as conn:
                conn.execute(
                    sa.text(
                        "UPDATE ingest_run SET triggered_by = :u "
                        "WHERE id > :before AND triggered_by IS NULL"
                    ),
                    {"u": uuid.UUID(triggered_by), "before": before},
                )
    return results
