"""Load Tailte Éireann / CSO boundaries into `area` (docs/data-model.md, `area`).

Layers are File Geodatabases in ITM (EPSG:2157). `geom_full` keeps the ungeneralised shape
in ITM for point-in-polygon joins; `geom` is a simplified WGS84 copy for display.
Parents: Small Area -> ED by the CSO's ED_GUID; ED, townland and settlement -> county by
the county containing a point on their surface (CSO EDs use 34 local-authority "counties"
such as FINGAL, so a spatial parent is simpler and exact).
"""

import hashlib
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyogrio
import sqlalchemy as sa
from app.models.data import IngestRun
from app.models.enums import AreaKind, County, IngestKind, IngestStatus

from ppr_pipeline.sources import Source

SOURCE = "Tailte Éireann"


@dataclass(frozen=True, slots=True)
class Layer:
    kind: AreaKind
    filename: str
    source_version: str
    code: str  # field holding a stable unique code
    name: str
    name_ga: str | None
    parent_code: str | None  # field holding the parent's code (Small Area -> ED)
    simplify_m: float  # display tolerance in metres


LAYERS = [
    Layer(
        AreaKind.COUNTY,
        "county_2026.zip",
        "Counties statutory ungeneralised 2026",
        "ENG_NAME_VALUE",
        "ENG_NAME_VALUE",
        "GLE_NAME_VALUE",
        None,
        50,
    ),
    Layer(
        AreaKind.ELECTORAL_DIVISION,
        "electoral_division_2022.zip",
        "CSO EDs 2022 ungeneralised",
        "ED_GUID",
        "ED_ENGLISH",
        "ED_GAEILGE",
        None,
        20,
    ),
    Layer(
        AreaKind.SMALL_AREA,
        "small_area_2022.zip",
        "CSO Small Areas 2022 ungeneralised",
        "SA_GEOGID_2022",
        "SA_PUB2022",
        None,
        "ED_GUID",
        5,
    ),
    Layer(
        AreaKind.TOWNLAND,
        "townland_2026.zip",
        "Townlands statutory ungeneralised 2026",
        "GUID",
        "ENG_NAME_VALUE",
        "GLE_NAME_VALUE",
        None,
        10,
    ),
    Layer(
        AreaKind.SETTLEMENT,
        "urban_area_2022.zip",
        "CSO Urban Areas 2022 ungeneralised",
        "URBAN_AREA_CODE",
        "URBAN_AREA_NAME",
        None,
        None,
        10,
    ),
]
DATASET_KEYS = {layer.kind: layer.kind.value for layer in LAYERS}


def area_name(text: str) -> str:
    """'KILLINAGH/TEEBANE' -> 'Killinagh/Teebane'; 'CILL (TUATH)' -> 'Cill (Tuath)'."""
    text = text.strip()
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isupper() for c in letters) < 0.8 * len(letters):
        return text  # already cased by the publisher: "Dún na nGall", "Tom na Gráinneoige"
    titled = re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), text.lower())
    return re.sub(r"'S\b", "'s", titled)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def gdb_path(zip_path: Path) -> str:
    """GDAL path to the .gdb folder inside a hub download (a .gpkg is used as it is)."""
    if zip_path.suffix == ".gpkg":
        return str(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        gdb = next(n.split("/")[0] for n in zf.namelist() if ".gdb/" in n)
    return f"/vsizip/{zip_path}/{gdb}"


def read_layer(path: str, layer: Layer) -> Iterator[tuple[str, str, str | None, str | None, bytes]]:
    """Yield (code, name, name_ga, parent_code, wkb) per feature."""
    fields = [f for f in (layer.code, layer.name, layer.name_ga, layer.parent_code) if f]
    fields = list(dict.fromkeys(fields))
    meta, _fids, geometries, values = pyogrio.raw.read(path, columns=fields)
    col = dict(zip(meta["fields"], values, strict=True))
    for i, wkb in enumerate(geometries):
        if wkb is None:
            continue
        code = str(col[layer.code][i]).strip()
        name = str(col[layer.name][i]).strip()
        name_ga = str(col[layer.name_ga][i]).strip() if layer.name_ga else None
        parent = str(col[layer.parent_code][i]).strip() if layer.parent_code else None
        yield code, name, name_ga or None, parent, bytes(wkb)


CREATE_STAGE = """
CREATE TEMP TABLE area_stage (
    code text, name text, name_ga text, parent_code text, slug text, wkb bytea
) ON COMMIT DROP
"""

# Counties arrive as thousands of parts (islands); everything else is one feature per area.
UPSERT = """
INSERT INTO area AS a (kind, code, name, name_ga, geom, geom_full, source, source_version, slug)
SELECT
    CAST(:kind AS area_kind), code, name, name_ga,
    ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(
        ST_SimplifyPreserveTopology(full_geom, :tolerance), 4326)), 3)),
    full_geom, :source, :version, slug
FROM (
    SELECT code, min(name) AS name, min(name_ga) AS name_ga, min(slug) AS slug,
           ST_Multi(ST_CollectionExtract(ST_MakeValid(
               ST_Union(ST_Force2D(ST_SetSRID(ST_GeomFromWKB(wkb), 2157)))), 3)) AS full_geom
    FROM area_stage GROUP BY code
) g
ON CONFLICT (kind, code) DO UPDATE SET
    name = EXCLUDED.name, name_ga = EXCLUDED.name_ga, geom = EXCLUDED.geom,
    geom_full = EXCLUDED.geom_full, source_version = EXCLUDED.source_version,
    slug = EXCLUDED.slug
"""

SA_PARENTS = """
UPDATE area sa SET parent_id = ed.id
FROM area_stage s JOIN area ed ON ed.kind = 'electoral_division' AND ed.code = s.parent_code
WHERE sa.kind = 'small_area' AND sa.code = s.code AND sa.parent_id IS DISTINCT FROM ed.id
"""

COUNTY_PARENTS = """
UPDATE area a SET parent_id = p.area_id
FROM area_part p
WHERE a.kind = CAST(:kind AS area_kind) AND p.kind = 'county'
  AND ST_Intersects(p.geom, ST_PointOnSurface(a.geom_full))
  AND a.parent_id IS DISTINCT FROM p.area_id
"""

# Pieces of at most 256 vertices: point-in-polygon against a GIST index becomes cheap even
# for Donegal's thousands of islands.
REBUILD_PARTS = """
DELETE FROM area_part WHERE kind = CAST(:kind AS area_kind);
INSERT INTO area_part (area_id, kind, geom)
SELECT id, kind, ST_Multi(ST_Subdivide(geom_full, 256))
FROM area WHERE kind = CAST(:kind AS area_kind);
"""

# CSO shapes along the coast run over harbour and foreshore past the statutory county line
# (Dún Laoghaire, Clontarf, Ringsend, Dundalk, Dungarvan), so their interior point can land
# 20-150 m offshore. Those take the nearest county within 2 km.
COUNTY_PARENTS_NEAREST = """
UPDATE area a SET parent_id = (
    SELECT p.area_id FROM area_part p
    WHERE p.kind = 'county' AND ST_DWithin(p.geom, ST_PointOnSurface(a.geom_full), 2000)
    ORDER BY p.geom <-> ST_PointOnSurface(a.geom_full) LIMIT 1
)
WHERE a.kind = CAST(:kind AS area_kind) AND a.parent_id IS NULL
"""

SLUG_PREFIX = {
    AreaKind.ELECTORAL_DIVISION: "ed-",
    AreaKind.TOWNLAND: "townland-",
    AreaKind.SETTLEMENT: "",
}


def area_slug(kind: AreaKind, code: str, name: str) -> str:
    """'cork'; 'sa-017010016'; 'ed-carlow-rural-1a2b3c'. A short hash of the code keeps
    same-named townlands and EDs apart while staying stable between runs."""
    if kind is AreaKind.COUNTY:
        return code
    if kind is AreaKind.SMALL_AREA:
        return f"sa-{name}"
    suffix = hashlib.sha1(code.encode(), usedforsecurity=False).hexdigest()[:6]
    return f"{SLUG_PREFIX[kind]}{slugify(name)}-{suffix}"


def _stage(
    conn: sa.Connection,
    rows: Iterator[tuple[str, str, str | None, str | None, bytes]],
    layer: Layer,
) -> int:
    conn.execute(sa.text("DROP TABLE IF EXISTS area_stage"))
    conn.execute(sa.text(CREATE_STAGE))
    raw = conn.connection.driver_connection
    assert raw is not None
    n = 0
    with (
        raw.cursor() as cur,
        cur.copy(
            "COPY area_stage (code, name, name_ga, parent_code, slug, wkb) FROM STDIN"
        ) as copy,
    ):
        for code, name, name_ga, parent, wkb in rows:
            if layer.kind is AreaKind.COUNTY:
                county = County(name.lower())  # fails loudly on an unknown county
                code, name = county.value, county.value.capitalize()
            else:
                name = area_name(name) if layer.kind is not AreaKind.SMALL_AREA else name
            ga = area_name(name_ga) if name_ga else None
            copy.write_row((code, name, ga, parent, area_slug(layer.kind, code, name), wkb))
            n += 1
    return n


def _parents(conn: sa.Connection, kind: AreaKind) -> None:
    if kind is AreaKind.SMALL_AREA:
        conn.execute(sa.text(SA_PARENTS))
    elif kind is not AreaKind.COUNTY:
        conn.execute(sa.text(COUNTY_PARENTS), {"kind": kind.value})
        conn.execute(sa.text(COUNTY_PARENTS_NEAREST), {"kind": kind.value})


def load_boundaries(
    engine: sa.Engine, directory: Path, layers: list[Layer] = LAYERS
) -> dict[str, int]:
    """Load every layer from `directory` (downloaded hub zips). Returns features per kind."""
    counts: dict[str, int] = {}
    for layer in layers:
        path = gdb_path(directory / layer.filename)
        with engine.begin() as conn:
            n = _stage(conn, read_layer(path, layer), layer)
            conn.execute(
                sa.text(UPSERT),
                {
                    "kind": layer.kind.value,
                    "tolerance": layer.simplify_m,
                    "source": SOURCE,
                    "version": layer.source_version,
                },
            )
            for statement in REBUILD_PARTS.strip().split(";\n"):
                conn.execute(sa.text(statement), {"kind": layer.kind.value})
            _parents(conn, layer.kind)
            counts[layer.kind.value] = n
    with engine.begin() as conn:
        conn.execute(sa.text("ANALYZE area"))
        conn.execute(sa.text("ANALYZE area_part"))
    return counts


def download(source: Source, directory: Path, *, refresh: bool = False) -> None:
    """Fetch each pinned layer (skipping files already present unless `refresh`)."""
    import httpx

    assert source.datasets, "tailte_boundaries needs pinned datasets in sources.yaml"
    directory.mkdir(parents=True, exist_ok=True)
    for layer in LAYERS:
        dest = directory / layer.filename
        if dest.exists() and not refresh:
            continue
        url = source.datasets[layer.kind.value]
        with httpx.stream("GET", url, follow_redirects=True, timeout=600) as resp:
            resp.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)


def ingest_boundaries(engine: sa.Engine, directory: Path, source_url: str) -> dict[str, int]:
    """Load all layers and record an `ingest_run` of kind `boundaries`."""
    with engine.begin() as conn:
        run_id = conn.execute(
            sa.insert(IngestRun)
            .values(kind=IngestKind.BOUNDARIES, status=IngestStatus.RUNNING, source_url=source_url)
            .returning(IngestRun.id)
        ).scalar_one()
    try:
        counts = load_boundaries(engine, directory)
    except Exception as exc:
        with engine.begin() as conn:
            conn.execute(
                sa.update(IngestRun)
                .where(IngestRun.id == run_id)
                .values(
                    status=IngestStatus.FAILED,
                    finished_at=datetime.now(UTC),
                    stats={"error": f"{type(exc).__name__}: {exc}"},
                )
            )
        raise
    with engine.begin() as conn:
        conn.execute(
            sa.update(IngestRun)
            .where(IngestRun.id == run_id)
            .values(
                status=IngestStatus.SUCCEEDED,
                finished_at=datetime.now(UTC),
                rows_read=sum(counts.values()),
                rows_inserted=sum(counts.values()),
                stats=counts,
            )
        )
    return counts
