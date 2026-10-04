"""`ppr` command-line entry point. Steps are implemented from Phase 2 onwards."""

import functools
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

import typer
from app.config import get_settings

from ppr_pipeline import benchmarks, boundaries
from ppr_pipeline.aggregate import aggregate as rebuild_aggregates
from ppr_pipeline.db import PipelineBusy, get_engine, pipeline_lock
from ppr_pipeline.enrich.run import enrich as enrich_all
from ppr_pipeline.geocode.gazetteer import build_gazetteer
from ppr_pipeline.geocode.runner import geocode_properties
from ppr_pipeline.ppr import ingest as ppr_ingest
from ppr_pipeline.sources import Source, load_sources

DATA_DIR = Path(os.environ.get("DATA_DIR") or "data")

app = typer.Typer(no_args_is_help=True, help="PPR Map data pipeline.")

NOT_YET = "Not implemented yet: planned for Phase 2 (see docs/ARCHITECTURE.md, Data flow)."


@app.command()
def sources(
    all_: Annotated[bool, typer.Option("--all", help="Include sources we must not use.")] = False,
) -> None:
    """List configured data sources with licence and verification status."""
    for key, src in load_sources().items():
        if not src.use and not all_:
            continue
        status = "in use" if src.use else "NOT USED"
        checked = "verified" if src.verified else "unverified"
        typer.echo(f"{key:20} {status:9} {checked:10} {src.licence}")


@contextmanager
def _one_at_a_time() -> Iterator[None]:
    """Steps that write the data run one at a time (`pipeline_lock`)."""
    try:
        with pipeline_lock(get_engine()):
            yield
    except PipelineBusy as exc:
        typer.echo(f"Not started: {exc}.", err=True)
        raise typer.Exit(code=1) from exc


def locked[**P, R](command: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(command)
    def run(*args: P.args, **kwargs: P.kwargs) -> R:
        with _one_at_a_time():
            return command(*args, **kwargs)

    return run


def _todo() -> None:
    typer.echo(NOT_YET, err=True)
    raise typer.Exit(code=2)


@app.command()
def ingest(
    kind: Annotated[str, typer.Argument(help="Source key from config/sources.yaml")],
    file: Annotated[
        Path | None,
        typer.Option(
            help="Load this local file (or folder, for boundaries) instead of downloading."
        ),
    ] = None,
    force: Annotated[bool, typer.Option(help="Reload even if the file is unchanged.")] = False,
) -> None:
    """Download and load one source (idempotent)."""
    src = load_sources().get(kind)
    if src is None:
        raise typer.BadParameter(f"unknown source '{kind}'")
    if not src.use:
        typer.echo(f"Refusing to ingest '{kind}': {src.reason}", err=True)
        raise typer.Exit(code=1)
    if kind not in ("tailte_boundaries", "cso_rppi", "ppr"):
        _todo()
    with _one_at_a_time():
        _ingest(kind, src, file, force)


def _ingest(kind: str, src: Source, file: Path | None, force: bool) -> None:
    if kind == "tailte_boundaries":
        directory = file or DATA_DIR / "raw" / "boundaries"
        if file is None:
            typer.echo(f"Downloading boundary layers to {directory}")
            boundaries.download(src, directory, refresh=force)
        counts = boundaries.ingest_boundaries(get_engine(), directory, src.url)
        for name, n in counts.items():
            typer.echo(f"  {name}: {n}")
        return
    if kind == "cso_rppi":
        payload = file.read_bytes() if file else benchmarks.download(src.url)
        summary_ = benchmarks.load_rppi(get_engine(), payload, src.url, progress=typer.echo)
        for name, value in summary_.items():
            typer.echo(f"  {name}: {value}")
        return
    url = ppr_ingest.source_url()
    if file is not None:
        payload, url = file.read_bytes(), file.resolve().as_uri()
    else:
        typer.echo(f"Downloading {url}")
        payload = ppr_ingest.download(url, DATA_DIR / "raw" / "ppr" / "PPR-ALL.zip")
    summary = ppr_ingest.ingest_ppr(get_engine(), payload, url, force=force)
    typer.echo(
        f"run {summary.run_id}: {summary.status.value}; read {summary.rows_read}, "
        f"inserted {summary.rows_inserted}, withdrawn {summary.rows_withdrawn}, "
        f"failed {summary.rows_failed}"
    )
    for name, value in summary.stats.items():
        typer.echo(f"  {name}: {value}")


OSM_PBF = Path("osm") / "ireland-and-northern-ireland-latest.osm.pbf"


@app.command()
@locked
def gazetteer(
    refresh: Annotated[
        bool, typer.Option(help="Download the housing-development surveys again.")
    ] = False,
) -> None:
    """Build the local street gazetteer from the OSM extract, official places and the DHLGH
    housing-development surveys (needs `make osm-extract` and the boundaries)."""
    pbf = DATA_DIR / OSM_PBF
    if not pbf.exists():
        typer.echo(f"{pbf} is missing: run `make osm-extract` first", err=True)
        raise typer.Exit(code=1)
    summary = build_gazetteer(
        get_engine(), pbf, load_sources()["nhds"], DATA_DIR, refresh=refresh, progress=typer.echo
    )
    for name, value in summary.items():
        typer.echo(f"  {name}: {value}")


@app.command()
@locked
def geocode(
    refresh: Annotated[
        bool, typer.Option(help="Redo every property, except admin-locked ones.")
    ] = False,
    limit: Annotated[
        int | None, typer.Option(help="Send at most this many properties to Nominatim.")
    ] = None,
    workers: Annotated[int, typer.Option(help="Parallel Nominatim requests.")] = 8,
) -> None:
    """Geocode new properties with the D-003 cascade (needs `make geocoder`)."""
    summary = geocode_properties(
        get_engine(),
        get_settings().nominatim_url,
        refresh=refresh,
        limit=limit,
        workers=workers,
        progress=typer.echo,
    )
    for name, value in summary.items():
        typer.echo(f"  {name}: {value}")


@app.command()
@locked
def enrich(
    refresh: Annotated[
        bool, typer.Option(help="Download GTFS and Pobal again even if present.")
    ] = False,
) -> None:
    """Reload stops, amenities and deprivation, then recompute vicinity values."""
    summary = enrich_all(
        get_engine(), load_sources(), DATA_DIR, refresh_downloads=refresh, progress=typer.echo
    )
    for name, value in summary.items():
        typer.echo(f"  {name}: {value}")


@app.command()
@locked
def aggregate() -> None:
    """Rebuild area stats, price hexes and hover summaries."""
    summary = rebuild_aggregates(get_engine(), progress=typer.echo)
    for name, value in summary.items():
        typer.echo(f"  {name}: {value}")
