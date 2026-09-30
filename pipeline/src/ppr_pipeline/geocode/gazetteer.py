"""Build `gazetteer_feature`, the local street gazetteer for geocoding (D-046).

Sources, all open and already on disk or pinned in config/sources.yaml:
- **OpenStreetMap** (the Geofabrik extract Nominatim uses, read locally with GDAL's OSM
  driver): named streets, named residential estates and apartment buildings, address points
  (`addr:housenumber` + `addr:street`) and place nodes.
- **Official places** already loaded from Tailte Éireann and the CSO: townlands and
  settlements, with a reach derived from their area.
- **DHLGH National Housing Development Surveys 2011 and 2012**: about 3,000 named estates
  with ITM coordinates, many of them built in 2005-2012 and never mapped in OSM.

Same-named street segments within 250 m of each other are merged into one feature placed on
the street nearest its middle. Every feature gets the county its point lies in; features in
Northern Ireland get none and are dropped.
"""

import csv
import io
import re
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pyogrio
import sqlalchemy as sa

from ppr_pipeline.geocode.local import Feature, Index, place_radius_km
from ppr_pipeline.geocode.rules import RESIDENTIAL_BUILDINGS, STREET_HIGHWAYS, name_variants
from ppr_pipeline.ppr.ingest import USER_AGENT
from ppr_pipeline.sources import Source

OSM_SOURCE = "OpenStreetMap contributors"
NHDS_SOURCE = "DHLGH National Housing Development Survey"

# Streets people live on, and ones still being built (new estates are mapped early).
NAMED_HIGHWAYS = STREET_HIGHWAYS | {"construction", "residential_link"}
# Cities are too coarse to anchor a street (local.py).
PLACE_TYPES = {
    "town", "suburb", "village", "quarter", "neighbourhood", "townland", "hamlet",
    "locality", "isolated_dwelling", "farm",
}  # fmt: skip
# A city's reach, for the consistency check only (cities never anchor a street).
CITY_RADIUS_M = 8000
CLUSTER_M = 250

LINE_TAGS = ("name", "alt_name", "old_name", "name:ga", "highway")
POINT_TAGS = ("name", "place", "addr:housenumber", "addr:street")
POLYGON_TAGS = ("name", "place", "landuse", "building", "addr:housenumber", "addr:street")

Progress = Callable[[str], None]
Row = tuple[str, str, str | None, str | None, str, str, int | None, str]


def osm_conf(directory: Path) -> Path:
    """GDAL's osmconf.ini with the tags we read exposed as columns (`addr:street` becomes
    the column `addr_street`)."""
    src = Path(pyogrio.__file__).parent / "gdal_data" / "osmconf.ini"
    text = src.read_text()
    for layer, tags in (
        ("lines", LINE_TAGS),
        ("points", POINT_TAGS),
        ("multipolygons", POLYGON_TAGS),
    ):
        attributes = "attributes=" + ",".join(tags)
        # The tag list holds no backslashes, so it is safe as a replacement template.
        text = re.sub(rf"(\[{layer}\][^\[]*?)attributes=[^\n]*", r"\g<1>" + attributes, text)
    out = directory / "osmconf-gazetteer.ini"
    out.write_text(text)
    return out


def house_numbers(raw: str | None) -> list[str]:
    """ "12" -> ["12"]; "12;14" -> ["12", "14"]; "5 B" -> ["5b"]. Ranges stay whole."""
    if not raw:
        return []
    return [re.sub(r"\s+", "", n).lower() for n in raw.split(";") if n.strip()]


def _col(name: str) -> str:
    return name.replace(":", "_")


def _value(col: dict[str, Any], tag: str, i: int) -> Any:
    return col[_col(tag)][i]


def read_osm(pbf: Path, work_dir: Path) -> Iterator[Row]:
    """(kind, name, house_number, detail, wkb hex, source_ref, radius_m, source)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    pyogrio.set_gdal_config_options({"OSM_CONFIG_FILE": str(osm_conf(work_dir))})

    meta, _, geoms, values = pyogrio.raw.read(
        str(pbf),
        layer="lines",
        where="highway IS NOT NULL",
        columns=["osm_id", *map(_col, LINE_TAGS)],
    )
    col = dict(zip(meta["fields"], values, strict=True))
    for i, wkb in enumerate(geoms):
        if wkb is None or col["highway"][i] not in NAMED_HIGHWAYS:
            continue
        names = {col[_col(t)][i] for t in LINE_TAGS[:-1]} - {None, ""}
        for name in names:
            yield (
                "street",
                name,
                None,
                col["highway"][i],
                bytes(wkb).hex(),
                f"w{col['osm_id'][i]}",
                None,
                OSM_SOURCE,
            )

    for layer, tags in (("points", POINT_TAGS), ("multipolygons", POLYGON_TAGS)):
        ids = ["osm_id"] if layer == "points" else ["osm_id", "osm_way_id"]
        where = "place IS NOT NULL OR addr_housenumber IS NOT NULL"
        if layer == "multipolygons":
            where += " OR (name IS NOT NULL AND (landuse = 'residential' OR building IS NOT NULL))"
        meta, _, geoms, values = pyogrio.raw.read(
            str(pbf), layer=layer, where=where, columns=[*ids, *map(_col, tags)]
        )
        col = dict(zip(meta["fields"], values, strict=True))
        for i, wkb in enumerate(geoms):
            if wkb is None:
                continue
            g = bytes(wkb).hex()
            if layer == "points":
                ref = f"n{col['osm_id'][i]}"
            else:
                ref = f"w{col['osm_way_id'][i]}" if col["osm_way_id"][i] else f"r{col['osm_id'][i]}"
            name, place = _value(col, "name", i), _value(col, "place", i)
            if name and place in PLACE_TYPES:
                radius = round(place_radius_km(place) * 1000)
                yield ("place", name, None, place, g, ref, radius, OSM_SOURCE)
            elif name and place == "city":
                yield ("city", name, None, place, g, ref, CITY_RADIUS_M, OSM_SOURCE)
            street = _value(col, "addr:street", i)
            for hn in house_numbers(_value(col, "addr:housenumber", i)) if street else []:
                yield ("address", street, hn, None, g, ref, None, OSM_SOURCE)
            if name and layer == "multipolygons" and not place:
                landuse, building = _value(col, "landuse", i), _value(col, "building", i)
                if landuse == "residential":
                    yield ("estate", name, None, "landuse/residential", g, ref, None, OSM_SOURCE)
                elif building in RESIDENTIAL_BUILDINGS:
                    yield ("estate", name, None, f"building/{building}", g, ref, None, OSM_SOURCE)


# --- DHLGH housing-development surveys ------------------------------------------------------


def download(url: str, target: Path, refresh: bool = False) -> Path:
    if target.exists() and not refresh:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as c:
        resp = c.get(url)
        resp.raise_for_status()
    target.write_bytes(resp.content)
    return target


def _itm(value: str) -> float | None:
    """ "687,267 " -> 687267.0 (the surveys write ITM metres with thousands separators)."""
    digits = re.sub(r"[,\s]", "", value or "")
    try:
        return float(digits)
    except ValueError:
        return None


def read_nhds(files: list[Path]) -> Iterator[Row]:
    """One estate per survey reference, from the latest survey that places it. Earlier
    files first; later ones overwrite."""
    estates: dict[str, tuple[str, float, float]] = {}
    for path in files:
        text = path.read_bytes().decode("cp1252")
        for r in csv.DictReader(io.StringIO(text)):
            ref, name = (r.get("DRef") or "").strip(), (r.get("Development") or "").strip()
            x, y = _itm(r.get("GIS X", "")), _itm(r.get("GIS Y", ""))
            # ITM over Ireland: easting 400-800 km, northing 500-1000 km.
            if ref and name and x and y and 400_000 < x < 800_000 and 500_000 < y < 1_000_000:
                estates[ref] = (name, x, y)
    for ref, (name, x, y) in estates.items():
        # EWKT, so the loader can tell ITM points from OSM's WGS84 WKB.
        yield (
            "estate",
            name,
            None,
            "nhds",
            f"SRID=2157;POINT({x} {y})",
            f"DRef {ref}",
            None,
            NHDS_SOURCE,
        )


# --- loading -------------------------------------------------------------------------------

CREATE_STAGE = """
CREATE TEMP TABLE gaz_feature_stage (
    kind text, name text, house_number text, detail text, geom text, source_ref text,
    radius_m int, source text
) ON COMMIT DROP
"""
STAGE_COLUMNS = "kind, name, house_number, detail, geom, source_ref, radius_m, source"

# Streets: segments of one name merged within CLUSTER_M, placed on the street nearest the
# middle of the merged stretch. Everything else: a point on the feature.
BUILD = """
CREATE TEMP TABLE gaz_feature_built ON COMMIT DROP AS
WITH g AS (
    SELECT kind, name, house_number, detail, source_ref, radius_m, source,
           ST_Transform(CASE WHEN geom LIKE 'SRID=%' THEN ST_GeomFromEWKT(geom)
                             ELSE ST_SetSRID(ST_GeomFromWKB(decode(geom, 'hex')), 4326) END,
                        2157) AS g
    FROM gaz_feature_stage
), streets AS (
    SELECT name, detail, source_ref, g,
           ST_ClusterDBSCAN(g, :cluster_m, 1) OVER (PARTITION BY lower(name)) AS cid
    FROM g WHERE kind = 'street'
), merged AS (
    SELECT min(name) AS name, mode() WITHIN GROUP (ORDER BY detail) AS detail,
           min(source_ref) AS source_ref, ST_Collect(g) AS g
    FROM streets GROUP BY lower(name), cid
)
SELECT 'street'::text AS kind, name, NULL::text AS house_number, detail, source_ref,
       NULL::int AS radius_m, :osm AS source, ST_ClosestPoint(g, ST_Centroid(g)) AS pt
FROM merged
UNION ALL
SELECT kind, name, house_number, detail, source_ref, radius_m, source,
       CASE WHEN GeometryType(g) = 'POINT' THEN g ELSE ST_PointOnSurface(g) END
FROM g WHERE kind <> 'street' AND NOT ST_IsEmpty(g)
"""

INSERT = """
INSERT INTO gazetteer_feature (kind, name, house_number, detail, county, geom, radius_m,
                               source, source_ref, as_of)
SELECT b.kind, b.name, b.house_number, b.detail, c.code::county, ST_Transform(b.pt, 4326),
       b.radius_m, b.source, b.source_ref,
       CASE WHEN b.source = :osm THEN :osm_as_of ELSE :nhds_as_of END
FROM gaz_feature_built b
CROSS JOIN LATERAL (
    SELECT a.code FROM area_part ap JOIN area a ON a.id = ap.area_id
    WHERE ap.kind = 'county' AND ST_Intersects(ap.geom, b.pt) LIMIT 1
) c
"""

# Official townlands and settlements as places, reaching as far as their size suggests.
OFFICIAL_PLACES = """
SELECT a.kind::text, a.name, a.name_ga, c.code, a.source,
       ST_AsText(ST_PointOnSurface(a.geom)), ST_Area(a.geom_full) / 1e6
FROM area a JOIN area c ON c.id = a.parent_id AND c.kind = 'county'
WHERE a.kind IN ('settlement', 'townland')
"""
INSERT_PLACE = """
INSERT INTO gazetteer_feature (kind, name, detail, county, geom, radius_m, source, source_ref,
                               as_of)
VALUES ('place', :name, :detail, CAST(:county AS county), ST_GeomFromText(:wkt, 4326),
        :radius_m, :source, NULL, :as_of)
"""


def _copy(conn: sa.Connection, rows: Iterator[Row]) -> int:
    raw = conn.connection.driver_connection
    assert raw is not None
    n = 0
    with (
        raw.cursor() as cur,
        cur.copy(f"COPY gaz_feature_stage ({STAGE_COLUMNS}) FROM STDIN") as cp,
    ):
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def load_gazetteer(
    engine: sa.Engine,
    osm_rows: Iterator[Row],
    nhds_rows: Iterator[Row],
    *,
    osm_as_of: date,
    nhds_as_of: date,
    progress: Progress = lambda _: None,
) -> dict[str, int]:
    """Replace the whole gazetteer in one transaction."""
    with engine.begin() as conn:
        conn.execute(sa.text(CREATE_STAGE))
        staged = _copy(conn, osm_rows)
        progress(f"  staged {staged:,} OSM features")
        staged_nhds = _copy(conn, nhds_rows)
        progress(f"  staged {staged_nhds:,} surveyed estates")
        conn.execute(sa.text(BUILD), {"cluster_m": CLUSTER_M, "osm": OSM_SOURCE})
        conn.execute(sa.text("DELETE FROM gazetteer_feature"))
        conn.execute(
            sa.text(INSERT),
            {"osm": OSM_SOURCE, "osm_as_of": osm_as_of, "nhds_as_of": nhds_as_of},
        )
        places = []
        for kind, name, name_ga, county, source, wkt, km2 in conn.execute(sa.text(OFFICIAL_PLACES)):
            radius = round(place_radius_km(None, float(km2 or 0)) * 1000)
            for n in {name, name_ga} - {None, ""}:
                for variant in name_variants(n):
                    places.append(
                        {"name": variant, "detail": kind, "county": county, "wkt": wkt,
                         "radius_m": radius, "source": source, "as_of": osm_as_of}
                    )  # fmt: skip
        if places:
            conn.execute(sa.text(INSERT_PLACE), places)
        rows = conn.execute(sa.text("SELECT kind, count(*) FROM gazetteer_feature GROUP BY 1"))
        return {str(k): int(v) for k, v in rows}


def build_gazetteer(
    engine: sa.Engine,
    pbf: Path,
    nhds: Source,
    data_dir: Path,
    *,
    refresh: bool = False,
    progress: Progress = lambda _: None,
) -> dict[str, int]:
    """Read the OSM extract and the surveys, then replace `gazetteer_feature`."""
    files = []
    for key, url in sorted((nhds.datasets or {}).items()):
        files.append(download(url, data_dir / "raw" / "nhds" / f"{key}.csv", refresh))
    osm_as_of = datetime.fromtimestamp(pbf.stat().st_mtime, UTC).date()
    nhds_as_of = nhds.checked_on or osm_as_of
    return load_gazetteer(
        engine,
        read_osm(pbf, data_dir / "work"),
        read_nhds(files),
        osm_as_of=osm_as_of,
        nhds_as_of=nhds_as_of,
        progress=progress,
    )


# --- the index the matcher uses ------------------------------------------------------------

INDEX_ROWS = """
SELECT kind, name, house_number, county::text, ST_X(geom), ST_Y(geom), radius_m, source
FROM gazetteer_feature
"""


def load_index(conn: sa.Connection) -> Index:
    index = Index()
    for kind, name, hn, county, lon, lat, radius_m, source in conn.execute(sa.text(INDEX_ROWS)):
        radius = (radius_m or 0) / 1000
        index.add(county, name, Feature(kind, lon, lat, source, radius), hn)
    return index
