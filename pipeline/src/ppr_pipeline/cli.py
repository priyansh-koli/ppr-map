"""`ppr` command-line entry point. Steps are implemented from Phase 2 onwards."""

import os
from pathlib import Path
from typing import Annotated

import typer

from ppr_pipeline import boundaries
from ppr_pipeline.db import get_engine
from ppr_pipeline.ppr import ingest as ppr_ingest
from ppr_pipeline.sources import load_sources

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))

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
    if kind == "tailte_boundaries":
        directory = file or DATA_DIR / "raw" / "boundaries"
        if file is None:
            typer.echo(f"Downloading boundary layers to {directory}")
            boundaries.download(src, directory, refresh=force)
        counts = boundaries.ingest_boundaries(get_engine(), directory, src.url)
        for name, n in counts.items():
            typer.echo(f"  {name}: {n}")
        return
    if kind != "ppr":
        _todo()

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


@app.command()
def geocode() -> None:
    """Geocode new or changed properties with the D-003 cascade."""
    _todo()


@app.command()
def enrich() -> None:
    """Recompute per-property enrichment."""
    _todo()


@app.command()
def aggregate() -> None:
    """Rebuild area stats, price hexes and hover summaries."""
    _todo()
