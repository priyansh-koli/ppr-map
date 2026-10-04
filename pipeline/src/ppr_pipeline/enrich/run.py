"""`ppr enrich`: reload transport stops, amenities and deprivation, then recompute the
per-property vicinity values. Each source load is recorded as its own `ingest_run`.

The sources are read first; then the POIs, the deprivation values and the vicinity values
that point at them are replaced in one transaction, so a failure anywhere (a bad download,
an unreadable extract) leaves the previous ones whole instead of every property without
vicinity values (P1 #21)."""

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
from ppr_pipeline.enrich.vicinity import vacuum, vicinity
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

    runs = {
        "gtfs": _start(engine, IngestKind.GTFS, str(gtfs)),
        "osm": _start(engine, IngestKind.OSM, str(pbf)),
        "pobal": _start(engine, IngestKind.POBAL, pobal_url),
    }
    stats: dict[str, Any] = {}
    try:
        # Read before the transaction: parsing the OSM extract takes minutes and locks nothing.
        progress("  reading transport stops (GTFS)")
        gtfs_date, stops = read_gtfs(gtfs)
        progress("  reading amenities and schools (OSM)")
        osm_date, amenities = read_osm(pbf, data_dir / "work")
        progress("  reading deprivation (Pobal)")
        pobal_csv, eds = pobal.read_bytes(), ed_ids(ed_layer)
        with engine.begin() as conn:
            # First: the vicinity rows point at the POIs about to be replaced.
            conn.execute(sa.text("DELETE FROM property_enrichment"))
            started = time.monotonic()
            stats["gtfs"] = {
                "feed_date": gtfs_date.isoformat(),
                "stops": replace_pois(conn, GTFS_SOURCE, gtfs_date, stops, "lonlat"),
            }
            stats["osm"] = {
                "extract_date": osm_date.isoformat(),
                "pois": replace_pois(conn, OSM_SOURCE, osm_date, amenities, "wkb"),
            }
            stats["pobal"] = load_pobal(conn, pobal_csv, eds)
            stats["poi_types"] = dict(
                conn.execute(
                    sa.text("SELECT type::text, count(*) FROM poi GROUP BY 1 ORDER BY 1")
                ).all()
            )
            seconds = round(time.monotonic() - started, 1)
            stats["vicinity"] = vicinity(conn, progress)
            for name, run_id in runs.items():
                _finish(
                    conn,
                    run_id,
                    status=IngestStatus.SUCCEEDED,
                    stats={**stats[name], "seconds": seconds},
                )
    except BaseException as exc:
        with engine.begin() as conn:
            for run_id in runs.values():
                _finish(conn, run_id, status=IngestStatus.FAILED, stats={"error": repr(exc)})
        raise
    vacuum(engine)
    return stats


def _start(engine: sa.Engine, kind: IngestKind, url: str) -> int:
    with engine.begin() as conn:
        run_id: int = conn.execute(
            sa.insert(IngestRun)
            .values(kind=kind, status=IngestStatus.RUNNING, source_url=url)
            .returning(IngestRun.id)
        ).scalar_one()
    return run_id


def _finish(conn: sa.Connection, run_id: int, **values: Any) -> None:
    conn.execute(
        sa.update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(finished_at=datetime.now(UTC), **values)
    )
