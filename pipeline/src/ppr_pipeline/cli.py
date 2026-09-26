"""`ppr` command-line entry point. Steps are implemented from Phase 2 onwards."""

from typing import Annotated

import typer

from ppr_pipeline.sources import load_sources

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
) -> None:
    """Download and load one source (idempotent)."""
    src = load_sources().get(kind)
    if src is None:
        raise typer.BadParameter(f"unknown source '{kind}'")
    if not src.use:
        typer.echo(f"Refusing to ingest '{kind}': {src.reason}", err=True)
        raise typer.Exit(code=1)
    _todo()


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
