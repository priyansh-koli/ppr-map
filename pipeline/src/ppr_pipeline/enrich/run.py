"""`ppr enrich`: reload transport stops, amenities and deprivation, then recompute the
per-property vicinity values. Each source load is recorded as its own `ingest_run`."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from app.models.data import IngestRun
from app.models.enums import IngestKind, IngestStatus

from ppr_pipeline.enrich.pobal import ed_ids, load_pobal
from ppr_pipeline.enrich.pois import (
    GTFS_SOURCE,
    OSM_SOURCE,
    read_gtfs,
    read_osm,
    replace_pois,
)
from ppr_pipeline.enrich.vicinity import compute_vicinity
from ppr_pipeline.ppr.ingest import USER_AGENT
from ppr_pipeline.sources import Source

Progress = Callable[[str], None]
OSM_PBF = "osm/ireland-and-northern-ireland-latest.osm.pbf"


def download(url: str, dest: Path) -> Path:
    """Stream to `dest.part`, then rename: a failed download never looks complete."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    headers = {"User-Agent": USER_AGENT}
    with httpx.stream("GET", url, follow_redirects=True, timeout=600, headers=headers) as resp:
        resp.raise_for_status()
        with part.open("wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)
    part.replace(dest)
    return dest


def _run(
    engine: sa.Engine, kind: IngestKind, url: str, step: Callable[[sa.Connection], dict[str, Any]]
) -> dict[str, Any]:
    with engine.begin() as conn:
        run_id: int = conn.execute(
            sa.insert(IngestRun)
            .values(kind=kind, status=IngestStatus.RUNNING, source_url=url)
            .returning(IngestRun.id)
        ).scalar_one()
    started = time.monotonic()
    try:
        with engine.begin() as conn:
            stats = step(conn)
            stats["seconds"] = round(time.monotonic() - started, 1)
            _finish(conn, run_id, status=IngestStatus.SUCCEEDED, stats=stats)
    except BaseException as exc:
        with engine.begin() as conn:
            _finish(conn, run_id, status=IngestStatus.FAILED, stats={"error": repr(exc)})
        raise
    return stats


def enrich(
    engine: sa.Engine,
    sources: dict[str, Source],
    data_dir: Path,
    *,
    refresh_downloads: bool = False,
    progress: Progress = lambda _: None,
) -> dict[str, Any]:
    gtfs = data_dir / "raw" / "gtfs" / "GTFS_All.zip"
    pobal = data_dir / "raw" / "pobal" / "hp-deprivation-index-scores-2022.csv"
    pbf = data_dir / OSM_PBF
    ed_layer = data_dir / "raw" / "boundaries" / "electoral_division_2022.zip"
    if not pbf.exists():
        raise FileNotFoundError(f"{pbf}: run `make osm-extract` first")
    if not ed_layer.exists():
        raise FileNotFoundError(f"{ed_layer}: run `ppr ingest tailte_boundaries` first")
    if refresh_downloads or not gtfs.exists():
        progress(f"Downloading {sources['gtfs'].url}")
        download(sources["gtfs"].url, gtfs)
    pobal_url = (sources["pobal_hp_2022"].datasets or {})["csv"]
    if refresh_downloads or not pobal.exists():
        progress(f"Downloading {pobal_url}")
        download(pobal_url, pobal)

    # The vicinity rows point at POIs that are about to be replaced; they are rebuilt below.
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE property_enrichment"))

    def load_gtfs(conn: sa.Connection) -> dict[str, Any]:
        as_of, rows = read_gtfs(gtfs)
        return {
            "feed_date": as_of.isoformat(),
            "stops": replace_pois(conn, GTFS_SOURCE, as_of, rows, "lonlat"),
        }

    def load_osm(conn: sa.Connection) -> dict[str, Any]:
        as_of, rows = read_osm(pbf, data_dir / "work")
        return {
            "extract_date": as_of.isoformat(),
            "pois": replace_pois(conn, OSM_SOURCE, as_of, rows, "wkb"),
        }

    progress("  transport stops (GTFS)")
    stats = {"gtfs": _run(engine, IngestKind.GTFS, str(gtfs), load_gtfs)}
    progress("  amenities and schools (OSM)")
    stats["osm"] = _run(engine, IngestKind.OSM, str(pbf), load_osm)
    progress("  deprivation (Pobal)")
    stats["pobal"] = _run(
        engine,
        IngestKind.POBAL,
        pobal_url,
        lambda conn: load_pobal(conn, pobal.read_bytes(), ed_ids(ed_layer)),
    )
    with engine.connect() as conn:
        stats["poi_types"] = dict(
            conn.execute(
                sa.text("SELECT type::text, count(*) FROM poi GROUP BY 1 ORDER BY 1")
            ).all()
        )
    stats["vicinity"] = compute_vicinity(engine, progress)
    return stats


def _finish(conn: sa.Connection, run_id: int, **values: Any) -> None:
    conn.execute(
        sa.update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(finished_at=datetime.now(UTC), **values)
    )
