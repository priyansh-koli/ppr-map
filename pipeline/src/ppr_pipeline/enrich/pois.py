"""Points of interest for the vicinity values (docs/ARCHITECTURE.md, Enrichment refresh).

- Transport stops from the NTA GTFS feed (CC BY 4.0), typed by the routes that serve them.
- Amenities and schools from the Geofabrik OSM extract already used by Nominatim (ODbL),
  read locally with GDAL's OSM driver: no Overpass calls.

Schools come from OSM because the Department of Education lists cannot be fetched
automatically (gov.ie answers 403). A school is typed primary, post-primary or special only
when its tags or name say so; otherwise it is left out rather than guessed.
"""

import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pyogrio
import sqlalchemy as sa
from app.models.enums import PoiType

GTFS_SOURCE = "NTA GTFS"
OSM_SOURCE = "OpenStreetMap"

# GTFS route_type: 0 tram (Luas), 2 rail, 3 bus. DART runs as its own rail route.
TRAM, RAIL, BUS = "0", "2", "3"


def stop_types(route_types: set[str], dart: bool) -> list[PoiType]:
    out = []
    if BUS in route_types:
        out.append(PoiType.BUS_STOP)
    if TRAM in route_types:
        out.append(PoiType.LUAS_STOP)
    if dart:
        out.append(PoiType.DART_STATION)
    if RAIL in route_types and not dart:
        out.append(PoiType.RAIL_STATION)
    return out


def _csv(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    with z.open(name) as fh:
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig"))


def read_gtfs(path: Path) -> tuple[date, list[tuple[Any, ...]]]:
    """(feed date, rows of (type, name, lon, lat, source_ref, attrs)) for every served stop."""
    with zipfile.ZipFile(path) as z:
        info = next(_csv(z, "feed_info.txt"), {})
        as_of = datetime.strptime(info.get("feed_start_date", ""), "%Y%m%d").date()
        routes = {r["route_id"]: r for r in _csv(z, "routes.txt")}
        trip_route = {t["trip_id"]: t["route_id"] for t in _csv(z, "trips.txt")}
        served: dict[str, set[str]] = defaultdict(set)
        with z.open("stop_times.txt") as fh:
            reader = csv.reader(io.TextIOWrapper(fh, "utf-8-sig"))
            header = next(reader)
            trip_i, stop_i = header.index("trip_id"), header.index("stop_id")
            for row in reader:
                route_id = trip_route.get(row[trip_i])
                if route_id:
                    served[row[stop_i]].add(route_id)
        rows = []
        for stop in _csv(z, "stops.txt"):
            route_ids = served.get(stop["stop_id"])
            if not route_ids:
                continue
            kinds = {routes[r]["route_type"] for r in route_ids}
            dart = any(routes[r]["route_short_name"] == "DART" for r in route_ids)
            for t in stop_types(kinds, dart):
                rows.append(
                    (
                        t.value,
                        stop["stop_name"],
                        float(stop["stop_lon"]),
                        float(stop["stop_lat"]),
                        f"{stop['stop_id']}:{t.value}",
                        {"stopCode": stop.get("stop_code") or None},
                    )
                )
    return as_of, rows


# --- OpenStreetMap -------------------------------------------------------------------------

OSM_TAGS = ("name", "amenity", "shop", "leisure", "healthcare", "school")
OSM_WHERE = (
    "amenity IN ('pharmacy','school','doctors','restaurant','cafe','fast_food') "
    "OR shop IS NOT NULL OR leisure IN ('park','fitness_centre') "
    "OR healthcare IN ('doctor','pharmacy')"
)
# Shops that are not somewhere you walk to for everyday shopping.
NOT_SHOPS = {
    "vacant",
    "car",
    "car_repair",
    "car_parts",
    "tyres",
    "motorcycle",
    "boat",
    "caravan",
    "trade",
    "agrarian",
    "funeral_directors",
    "storage_rental",
    "fuel",
}

POST_PRIMARY_NAME = re.compile(
    r"\b(secondary|community school|community college|college|col[aá]iste|gaelchol[aá]iste|"
    r"comprehensive|vocational|high school|grammar|post[- ]primary)\b",
    re.I,
)
PRIMARY_NAME = re.compile(
    r"\b(national school|n\.?\s?s\.?|scoil|primary|gaelscoil|infant|junior school)\b", re.I
)
SPECIAL_NAME = re.compile(r"\bspecial school\b", re.I)


def school_type(name: str | None, school_tag: str | None) -> PoiType | None:
    tag = (school_tag or "").lower()
    text = name or ""
    if SPECIAL_NAME.search(text) or tag in ("special", "special_education_needs"):
        return PoiType.SCHOOL_SPECIAL
    if tag in ("secondary", "post_primary") or POST_PRIMARY_NAME.search(text):
        return PoiType.SCHOOL_POST_PRIMARY
    if tag == "primary" or PRIMARY_NAME.search(text):
        return PoiType.SCHOOL_PRIMARY
    return None


def osm_type(tags: Mapping[str, str | None]) -> PoiType | None:
    amenity, shop = tags.get("amenity"), tags.get("shop")
    leisure, healthcare = tags.get("leisure"), tags.get("healthcare")
    if amenity == "school":
        return school_type(tags.get("name"), tags.get("school"))
    if amenity == "pharmacy" or healthcare == "pharmacy":
        return PoiType.PHARMACY
    if amenity == "doctors" or healthcare == "doctor":
        return PoiType.GP
    if amenity in ("restaurant", "cafe", "fast_food"):
        return PoiType.RESTAURANT
    if shop == "supermarket":
        return PoiType.SUPERMARKET
    if shop and shop not in NOT_SHOPS:
        return PoiType.SHOP
    if leisure == "park":
        return PoiType.PARK
    if leisure == "fitness_centre":
        return PoiType.GYM
    return None


def osm_conf(directory: Path) -> Path:
    """GDAL's osmconf.ini with the tags we filter on exposed as columns."""
    src = Path(pyogrio.__file__).parent / "gdal_data" / "osmconf.ini"
    text = src.read_text()
    attributes = "attributes=" + ",".join(OSM_TAGS)
    for layer in ("points", "multipolygons"):
        text = re.sub(
            rf"(\[{layer}\][^\[]*?)attributes=[^\n]*", lambda m: m.group(1) + attributes, text
        )
    out = directory / "osmconf.ini"
    out.write_text(text)
    return out


def read_osm(pbf: Path, work_dir: Path) -> tuple[date, list[tuple[Any, ...]]]:
    """(extract date, rows of (type, name, wkb, source_ref, attrs)). Polygons are reduced to
    a point on their surface in the database."""
    work_dir.mkdir(parents=True, exist_ok=True)
    pyogrio.set_gdal_config_options({"OSM_CONFIG_FILE": str(osm_conf(work_dir))})
    as_of = datetime.fromtimestamp(pbf.stat().st_mtime, UTC).date()
    rows = []
    for layer, ids in (("points", ("osm_id",)), ("multipolygons", ("osm_id", "osm_way_id"))):
        meta, _fids, geoms, values = pyogrio.raw.read(
            str(pbf), layer=layer, where=OSM_WHERE, columns=[*ids, *OSM_TAGS]
        )
        col = dict(zip(meta["fields"], values, strict=True))
        for i, wkb in enumerate(geoms):
            if wkb is None:
                continue
            tags = {k: col[k][i] for k in OSM_TAGS}
            t = osm_type(tags)
            if t is None:
                continue
            if layer == "points":
                ref = f"n{col['osm_id'][i]}"
            elif col["osm_way_id"][i]:
                ref = f"w{col['osm_way_id'][i]}"
            else:
                ref = f"r{col['osm_id'][i]}"
            attrs = {k: v for k in ("amenity", "shop", "leisure") if (v := tags[k])}
            rows.append((t.value, tags["name"], bytes(wkb), ref, attrs))
    return as_of, rows


# --- loading -------------------------------------------------------------------------------

CREATE_STAGE = """
CREATE TEMP TABLE poi_stage (
    type poi_type, name text, geom geometry, source_ref text, attrs jsonb
) ON COMMIT DROP
"""

REPLACE = """
INSERT INTO poi (type, name, geom, source, source_ref, attrs, as_of)
SELECT DISTINCT ON (source_ref) type, name,
       CASE WHEN GeometryType(geom) = 'POINT' THEN ST_SetSRID(geom, 4326)
            ELSE ST_PointOnSurface(ST_SetSRID(geom, 4326)) END,
       :source, source_ref, attrs, :as_of
FROM poi_stage
ORDER BY source_ref
"""


def replace_pois(
    conn: sa.Connection, source: str, as_of: date, rows: list[tuple[Any, ...]], geometry: str
) -> int:
    """Swap in all POIs of one source. `geometry` is "lonlat" (GTFS) or "wkb" (OSM)."""
    conn.execute(sa.text(CREATE_STAGE))
    raw = conn.connection.driver_connection
    assert raw is not None
    columns = "type, name, geom, source_ref, attrs"
    with raw.cursor() as cur, cur.copy(f"COPY poi_stage ({columns}) FROM STDIN") as copy:
        for row in rows:
            if geometry == "lonlat":
                t, name, lon, lat, ref, attrs = row
                geom = f"POINT({lon} {lat})"
            else:
                t, name, wkb, ref, attrs = row
                geom = wkb.hex()
            copy.write_row((t, name, geom, ref, json.dumps(attrs)))
    conn.execute(sa.text("DELETE FROM poi WHERE source = :s"), {"s": source})
    loaded = conn.execute(sa.text(REPLACE), {"source": source, "as_of": as_of}).rowcount
    conn.execute(sa.text("DROP TABLE poi_stage"))
    return int(loaded)
