"""Geocode properties with the D-003 cascade (docs/ARCHITECTURE.md, Data flow steps 6-7).

1. **Nominatim** (self-hosted): each address is queried from its full form down to its
   town, bounded to the county's box, and `rules.pick` accepts or rejects each result.
2. **County check** in PostGIS: a point more than 2 km outside the reported county is
   rejected (`county_conflict`).
3. **Local street gazetteer** (D-046): each address part looked up on its own in
   `gazetteer_feature` (OSM streets, estates and address points, DHLGH surveyed estates),
   accepted only near a place named later in the address (`local.py`).
4. **Fallbacks** in the database for what is still not placed: official townland and
   CSO settlement names (`locality`), then the median of precise points sharing the Eircode
   routing key (`routing_key`), then a point inside the county (`county`).
5. **Spatial joins**: Small Area, ED, townland and settlement ids, and the H3 r8 cell.

Every query is logged in `geocode_attempt` and the run in `ingest_run`. Properties are
geocoded once (`geocoded_at`); `refresh=True` redoes all but the admin-locked ones.
"""

import collections
import concurrent.futures as cf
import json
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import h3
import httpx
import sqlalchemy as sa
from app.models.data import IngestRun
from app.models.enums import GeocodeConfidence, IngestKind, IngestStatus

from ppr_pipeline.geocode import local
from ppr_pipeline.geocode.gazetteer import load_index
from ppr_pipeline.geocode.rules import (
    RESIDENTIAL_BUILDINGS,
    Candidate,
    fold,
    km_between,
    ladder,
    name_tokens,
    name_variants,
    pick,
    query_parts,
    split_house_number,
    town_parts,
    town_point,
)
from ppr_pipeline.ppr.ingest import USER_AGENT

NOMINATIM_SOURCE = "OpenStreetMap contributors (Nominatim)"
CHUNK = 2000
WORKERS = 8
COUNTY_BUFFER_M = 2000
# Routing-key medians need enough precise points to mean something.
MIN_ROUTING_KEY_POINTS = 10
# A precise point this far from its routing key's median is flagged for review.
ROUTING_KEY_CONFLICT_M = 25_000
LOCAL_STEP = 80
GAZETTEER_STEP = 90

# Nominatim result fields kept for the rules and the attempt log.
KEEP_FIELDS = ("category", "type", "place_rank", "name", "namedetails", "lat", "lon")
KEEP_ADDRESS = ("house_number", "road", "residential", "neighbourhood")
LOG_FIELDS = ("osm_type", "osm_id", "display_name", "category", "type")

Town = tuple[float, float, bool]
Progress = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class Attempt:
    step: int
    query: str
    candidate: Candidate | None
    reject_reason: str | None


@dataclass(slots=True)
class Outcome:
    property_id: int
    candidate: Candidate | None = None
    attempts: list[Attempt] = field(default_factory=list)


def _trim(result: dict[str, Any]) -> dict[str, Any]:
    out = {k: result[k] for k in KEEP_FIELDS if k in result}
    address = result.get("address") or {}
    out["address"] = {k: address[k] for k in KEEP_ADDRESS if k in address}
    out["log"] = {k: result[k] for k in LOG_FIELDS if k in result}
    return out


class Nominatim:
    """Bounded /search against our own Nominatim; results trimmed to what the rules use."""

    def __init__(
        self,
        url: str,
        county_boxes: dict[str, tuple[float, float, float, float]],
        client: httpx.Client | None = None,
        max_connections: int = WORKERS * 2,
    ) -> None:
        self.url = url.rstrip("/")
        self.boxes = county_boxes
        self.client = client or httpx.Client(
            timeout=60,
            headers={"User-Agent": USER_AGENT},
            limits=httpx.Limits(max_connections=max_connections),
        )
        self.queries = 0

    def search(self, query: str, county: str) -> list[dict[str, Any]]:
        x0, y0, x1, y1 = self.boxes[county]
        pad = 0.03  # about 2-3 km, as the county check allows
        params: dict[str, str | int] = {
            "q": query,
            "format": "jsonv2",
            "countrycodes": "ie",
            "limit": 10,
            "addressdetails": 1,
            "namedetails": 1,
            "viewbox": f"{x0 - pad},{y1 + pad},{x1 + pad},{y0 - pad}",
            "bounded": 1,
        }
        for delay in (1, 5, 15, 0):
            try:
                resp = self.client.get(f"{self.url}/search", params=params)
                resp.raise_for_status()
                break
            except httpx.HTTPError:
                if not delay:
                    raise
                time.sleep(delay)
        self.queries += 1
        return [_trim(r) for r in resp.json()]


def _reason(reasons: Sequence[str]) -> str:
    if not reasons:
        return "no_result"
    return collections.Counter(reasons).most_common(1)[0][0]


class Geocoder:
    """The Nominatim step for one property at a time; thread-safe for the worker pool.

    Only the full-address query is unique to a property. Street, locality and town queries
    repeat across thousands of properties, so their outcomes are cached for the run."""

    def __init__(self, nominatim: Nominatim) -> None:
        self.nominatim = nominatim
        self.towns: dict[tuple[str, str], Town | None] = {}
        self.picks: dict[tuple[str, str, Town | None], tuple[Candidate | None, list[str]]] = {}

    def town(self, parts: Sequence[str], county: str) -> Town | None:
        for part in town_parts(parts, county):
            key = (part, county)
            if key not in self.towns:
                self.towns[key] = town_point(self.nominatim.search(part, county), part)
            if self.towns[key] is not None:
                return self.towns[key]
        return None

    def geocode(self, property_id: int, address_display: str, county: str) -> Outcome:
        outcome = Outcome(property_id)
        parts = query_parts(address_display, county)
        if not parts:
            return outcome
        town = self.town(parts, county)
        towns = set(town_parts(parts, county))
        for step, (query, i) in enumerate(ladder(parts, county), start=1):
            # The town itself is not checked against itself.
            anchor = None if query in towns else town
            key = (query, county, anchor)
            cached = self.picks.get(key) if i > 0 else None
            if cached is None:
                cached = pick(self.nominatim.search(query, county), parts[i], anchor)
                if i > 0:
                    self.picks[key] = cached
            candidate, reasons = cached
            reason = None if candidate else _reason(reasons)
            outcome.attempts.append(Attempt(step, query, candidate, reason))
            if candidate:
                outcome.candidate = candidate
                return outcome
        return outcome


# --- database -------------------------------------------------------------------------------

COUNTY_BOXES = """
SELECT code, ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
FROM (SELECT code, ST_Extent(geom)::box2d AS e FROM area WHERE kind = 'county' GROUP BY code) t
"""

NEXT_CHUNK = """
SELECT id, address_display, county::text FROM property
WHERE geocoded_at IS NULL AND NOT geocode_locked AND id > :after
ORDER BY id LIMIT :n
"""

CREATE_STAGE = """
CREATE TEMP TABLE geo_stage (
    property_id bigint, step smallint, query text, lon float8, lat float8, kind text,
    confidence geocode_confidence, accepted bool, reject_reason text, raw jsonb, final bool
) ON COMMIT DROP
"""

STAGE_COLUMNS = (
    "property_id",
    "step",
    "query",
    "lon",
    "lat",
    "kind",
    "confidence",
    "accepted",
    "reject_reason",
    "raw",
    "final",
)

# The county's own shape, not its box: a point more than 2 km outside it is wrong.
COUNTY_CHECK = """
UPDATE geo_stage s SET accepted = false, reject_reason = 'county_conflict'
FROM property p
WHERE s.final AND p.id = s.property_id AND NOT EXISTS (
    SELECT 1 FROM area a JOIN area_part ap ON ap.area_id = a.id
    WHERE a.kind = 'county' AND a.code = p.county::text
      AND ST_DWithin(ap.geom, ST_Transform(ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326), 2157),
                     :buffer)
)
"""

APPLY = """
UPDATE property p SET
    geom = ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326),
    geocode_confidence = s.confidence,
    geocode_method = 'nominatim:' || s.kind,
    geocode_source = :source,
    geocoded_at = now(), updated_at = now()
FROM geo_stage s
WHERE s.final AND s.accepted AND p.id = s.property_id
"""

MARK_TRIED = """
UPDATE property p SET
    geom = NULL, geocode_confidence = 'unmatched', geocode_method = 'nominatim:none',
    geocode_source = NULL, geocoded_at = now(), updated_at = now()
WHERE p.id = ANY(:ids)
  AND NOT EXISTS (SELECT 1 FROM geo_stage s WHERE s.final AND s.accepted AND s.property_id = p.id)
"""

LOG_ATTEMPTS = """
INSERT INTO geocode_attempt (property_id, run_id, step, method, query, candidate_geom,
                             candidate_type, confidence, accepted, reject_reason, raw_response)
SELECT property_id, :run_id, step, 'nominatim', query,
       CASE WHEN lon IS NOT NULL THEN ST_SetSRID(ST_MakePoint(lon, lat), 4326) END,
       kind, coalesce(confidence, 'unmatched'), accepted, reject_reason, raw
FROM geo_stage
"""


def _stage_rows(outcomes: Iterable[Outcome]) -> Iterator[tuple[Any, ...]]:
    for o in outcomes:
        for a in o.attempts:
            c = a.candidate
            final = c is not None and c is o.candidate
            yield (
                o.property_id,
                a.step,
                a.query,
                c.lon if c else None,
                c.lat if c else None,
                c.kind if c else None,
                c.confidence.value if c else None,
                c is not None,
                a.reject_reason,
                json.dumps(c.raw.get("log", {})) if final and c else None,
                final,
            )


def write_outcomes(conn: sa.Connection, outcomes: Sequence[Outcome], run_id: int) -> None:
    conn.execute(sa.text(CREATE_STAGE))
    raw = conn.connection.driver_connection
    assert raw is not None
    with (
        raw.cursor() as cur,
        cur.copy(f"COPY geo_stage ({', '.join(STAGE_COLUMNS)}) FROM STDIN") as copy,
    ):
        for row in _stage_rows(outcomes):
            copy.write_row(row)
    conn.execute(sa.text(COUNTY_CHECK), {"buffer": COUNTY_BUFFER_M})
    conn.execute(sa.text(APPLY), {"source": NOMINATIM_SOURCE})
    conn.execute(sa.text(MARK_TRIED), {"ids": [o.property_id for o in outcomes]})
    conn.execute(sa.text(LOG_ATTEMPTS), {"run_id": run_id})


def county_boxes(conn: sa.Connection) -> dict[str, tuple[float, float, float, float]]:
    rows = conn.execute(sa.text(COUNTY_BOXES)).all()
    return {r[0]: (float(r[1]), float(r[2]), float(r[3]), float(r[4])) for r in rows}


def nominatim_pass(
    engine: sa.Engine,
    geocoder: Geocoder,
    run_id: int,
    *,
    limit: int | None = None,
    workers: int = WORKERS,
    progress: Progress = lambda _: None,
) -> int:
    done, after, started = 0, 0, time.monotonic()
    with cf.ThreadPoolExecutor(workers) as pool:
        while limit is None or done < limit:
            n = CHUNK if limit is None else min(CHUNK, limit - done)
            with engine.connect() as conn:
                rows = conn.execute(sa.text(NEXT_CHUNK), {"after": after, "n": n}).all()
            if not rows:
                break
            outcomes = list(pool.map(lambda r: geocoder.geocode(r[0], r[1], r[2]), rows))
            with engine.begin() as conn:
                write_outcomes(conn, outcomes, run_id)
            done += len(rows)
            after = rows[-1][0]
            rate = done / max(time.monotonic() - started, 1e-6)
            progress(f"  nominatim: {done:,} properties ({rate:,.0f}/s)")
    return done


# --- fallbacks -----------------------------------------------------------------------------

GAZETTEER_NAMES = """
SELECT a.id, a.kind::text, a.name, a.name_ga, c.code
FROM area a JOIN area c ON c.id = a.parent_id AND c.kind = 'county'
WHERE a.kind IN ('settlement', 'townland')
"""

# Fallback results are recomputed on every run: routing-key medians improve as more
# points are placed, and the rules may have changed. Nominatim results are kept.
RESET_FALLBACKS = """
UPDATE property SET
    geom = NULL, geocode_confidence = 'unmatched', geocode_method = 'nominatim:none',
    geocode_source = NULL, townland_id = NULL, settlement_id = NULL, updated_at = now()
WHERE geocoded_at IS NOT NULL AND NOT geocode_locked AND geocode_method NOT LIKE 'nominatim:%'
"""

# Rules change (D-046: a railway station is not an address); a stored Nominatim result the
# current rules reject is dropped and the property goes through the later steps again.
RECHECK_BUILDINGS = """
UPDATE property SET
    geom = NULL, geocode_confidence = 'unmatched', geocode_method = 'nominatim:none',
    geocode_source = NULL, updated_at = now()
WHERE geocoded_at IS NOT NULL AND NOT geocode_locked AND geocode_confidence = 'street'
  AND geocode_method LIKE 'nominatim:building/%'
  AND substr(geocode_method, 20) <> ALL(:types)
"""

# The local pass may improve anything Nominatim placed at town level or not at all, and may
# turn a Nominatim street into the exact house on it, if the two agree.
STREET_TO_EXACT_KM = 1.5
LOCAL_CANDIDATES = """
SELECT id, address_display, county::text, geocode_confidence::text, ST_X(geom), ST_Y(geom)
FROM property
WHERE geocoded_at IS NOT NULL AND NOT geocode_locked
  AND (geocode_confidence = 'unmatched'
       OR (geocode_confidence IN ('locality', 'street') AND geocode_method LIKE 'nominatim:%'))
"""

CREATE_LOCAL_STAGE = """
CREATE TEMP TABLE local_stage (
    property_id bigint, lon float8, lat float8, confidence geocode_confidence, method text,
    source text, query text
) ON COMMIT DROP
"""

APPLY_LOCAL = """
WITH upd AS (
    UPDATE property p SET
        geom = ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326), geocode_confidence = s.confidence,
        geocode_method = s.method, geocode_source = s.source,
        geocoded_at = now(), updated_at = now()
    FROM local_stage s WHERE p.id = s.property_id
    RETURNING p.id
)
INSERT INTO geocode_attempt (property_id, run_id, step, method, query, candidate_geom,
                             candidate_type, confidence, accepted)
SELECT s.property_id, :run_id, :step, 'local', s.query,
       ST_SetSRID(ST_MakePoint(s.lon, s.lat), 4326), s.method, s.confidence, true
FROM local_stage s
"""

UNMATCHED = """
SELECT id, address_display, county::text FROM property
WHERE geocode_confidence = 'unmatched' AND geocoded_at IS NOT NULL AND NOT geocode_locked
"""

CREATE_GAZETTEER_STAGE = """
CREATE TEMP TABLE gaz_stage (
    property_id bigint, area_id bigint, query text, method text
) ON COMMIT DROP
"""

SET_GAZETTEER_METHOD = """
UPDATE gaz_stage g SET method = coalesce(:method, 'gazetteer:' || a.kind::text)
FROM area a WHERE a.id = g.area_id
"""

APPLY_GAZETTEER = """
WITH hit AS (
    SELECT g.property_id, g.query, g.method, a.id AS area_id, a.kind,
           ST_PointOnSurface(a.geom) AS pt
    FROM gaz_stage g JOIN area a ON a.id = g.area_id
), upd AS (
    UPDATE property p SET
        geom = h.pt, geocode_confidence = 'locality',
        geocode_method = h.method,
        geocode_source = CASE h.kind WHEN 'settlement' THEN 'CSO' ELSE 'Tailte Éireann' END,
        townland_id = CASE h.kind WHEN 'townland' THEN h.area_id ELSE p.townland_id END,
        settlement_id = CASE h.kind WHEN 'settlement' THEN h.area_id ELSE p.settlement_id END,
        geocoded_at = now(), updated_at = now()
    FROM hit h WHERE p.id = h.property_id
    RETURNING p.id
)
INSERT INTO geocode_attempt (property_id, run_id, step, method, query, candidate_geom,
                             candidate_type, confidence, accepted)
SELECT h.property_id, :run_id, :step, 'gazetteer', h.query, h.pt, h.kind::text, 'locality', true
FROM hit h
"""

# Median, not mean: one wrong point cannot drag it. Only if it lies in the property's county.
# MATERIALIZED: the medians are computed once, whatever join the planner picks.
APPLY_ROUTING_KEY = """
WITH med AS MATERIALIZED (
    SELECT eircode_routing_key AS rk,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_X(geom)) AS x,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_Y(geom)) AS y
    FROM property
    WHERE geocode_confidence IN ('exact', 'street') AND eircode_routing_key IS NOT NULL
    GROUP BY 1 HAVING count(*) >= :min_points
)
UPDATE property p SET
    geom = ST_SetSRID(ST_MakePoint(m.x, m.y), 4326), geocode_confidence = 'routing_key',
    geocode_method = CASE WHEN p.eircode_routing_key IS NOT NULL THEN 'routing_key:median'
                          ELSE 'dublin_district:median' END,
    geocode_source = 'median of geocoded sales',
    geocoded_at = now(), updated_at = now()
FROM med m
-- Dublin postal districts are the Eircode routing keys: "D8" is D08, "D6W" is D6W.
WHERE m.rk = coalesce(
    p.eircode_routing_key,
    CASE WHEN p.dublin_district = 'D6W' THEN 'D6W'
         WHEN p.dublin_district IS NOT NULL
         THEN 'D' || lpad(substr(p.dublin_district, 2), 2, '0') END)
  AND p.geocode_confidence = 'unmatched'
  AND p.geocoded_at IS NOT NULL AND NOT p.geocode_locked
  AND EXISTS (
    SELECT 1 FROM area a JOIN area_part ap ON ap.area_id = a.id
    WHERE a.kind = 'county' AND a.code = p.county::text
      AND ST_DWithin(ap.geom, ST_Transform(ST_SetSRID(ST_MakePoint(m.x, m.y), 4326), 2157),
                     :buffer)
  )
"""

APPLY_COUNTY = """
UPDATE property p SET
    geom = ST_PointOnSurface(a.geom), geocode_confidence = 'county',
    geocode_method = 'county:point_on_surface', geocode_source = 'Tailte Éireann',
    geocoded_at = now(), updated_at = now()
FROM area a
WHERE a.kind = 'county' AND a.code = p.county::text
  AND p.geocode_confidence = 'unmatched' AND p.geocoded_at IS NOT NULL AND NOT p.geocode_locked
"""

# Review signal only: PPR Eircodes are sometimes wrong (R-04), so neither side is trusted.
FLAG_ROUTING_KEY_CONFLICTS = """
WITH med AS MATERIALIZED (
    SELECT eircode_routing_key AS rk,
           ST_SetSRID(ST_MakePoint(
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_X(geom)),
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ST_Y(geom))), 4326) AS pt
    FROM property
    WHERE geocode_confidence IN ('exact', 'street') AND eircode_routing_key IS NOT NULL
    GROUP BY 1 HAVING count(*) >= :min_points
)
INSERT INTO geocode_attempt (property_id, run_id, step, method, query, candidate_geom,
                             candidate_type, confidence, accepted, reject_reason)
SELECT p.id, :run_id, 0, 'check:routing_key', p.eircode, m.pt, 'routing_key_median',
       p.geocode_confidence, false, 'routing_key_conflict'
FROM property p JOIN med m ON m.rk = p.eircode_routing_key
WHERE p.geocode_confidence IN ('exact', 'street', 'locality')
  AND ST_Distance(p.geom::geography, m.pt::geography) > :max_m
"""


def gazetteer_index(conn: sa.Connection) -> dict[tuple[str, frozenset[str]], list[tuple[str, int]]]:
    index: dict[tuple[str, frozenset[str]], list[tuple[str, int]]] = collections.defaultdict(list)
    for area_id, kind, name, name_ga, county in conn.execute(sa.text(GAZETTEER_NAMES)):
        for n in {name, name_ga} - {None}:
            for variant in name_variants(n):
                index[(county, name_tokens(variant))].append((kind, area_id))
    return index


def gazetteer_match(
    index: dict[tuple[str, frozenset[str]], list[tuple[str, int]]],
    address_display: str,
    county: str,
) -> tuple[int, str] | None:
    """(area id, matched part) of the most specific part that names exactly one settlement,
    or else exactly one townland, in the county."""
    for part in query_parts(address_display, county):
        _, name = split_house_number(part)
        tokens = name_tokens(name)
        if not tokens or fold(name) == county:
            continue
        hits = index.get((county, tokens), [])
        for kind in ("settlement", "townland"):
            ids = {area_id for k, area_id in hits if k == kind}
            if len(ids) == 1:
                return ids.pop(), part
    return None


def county_town_match(
    index: dict[tuple[str, frozenset[str]], list[tuple[str, int]]],
    address_display: str,
    county: str,
) -> tuple[int, str] | None:
    """ "..., St Marys Park, Carlow": when nothing more specific placed the address, a last
    part naming the county is taken as the town of that name, if the CSO has one."""
    parts = query_parts(address_display, county)
    if not parts or fold(parts[-1]) != county:
        return None
    ids = {i for k, i in index.get((county, name_tokens(parts[-1])), []) if k == "settlement"}
    return (ids.pop(), parts[-1]) if len(ids) == 1 else None


Matcher = Callable[
    [dict[tuple[str, frozenset[str]], list[tuple[str, int]]], str, str], tuple[int, str] | None
]


def _apply_gazetteer(
    conn: sa.Connection,
    index: dict[tuple[str, frozenset[str]], list[tuple[str, int]]],
    matcher: Matcher,
    method: str | None,
    run_id: int,
) -> int:
    hits = []
    for pid, display, county in conn.execute(sa.text(UNMATCHED)):
        match = matcher(index, display, county)
        if match:
            hits.append((pid, match[0], match[1]))
    conn.execute(sa.text(CREATE_GAZETTEER_STAGE))
    raw = conn.connection.driver_connection
    assert raw is not None
    with (
        raw.cursor() as cur,
        cur.copy("COPY gaz_stage (property_id, area_id, query) FROM STDIN") as copy,
    ):
        for row in hits:
            copy.write_row(row)
    conn.execute(sa.text(SET_GAZETTEER_METHOD), {"method": method})
    conn.execute(sa.text(APPLY_GAZETTEER), {"run_id": run_id, "step": GAZETTEER_STEP})
    conn.execute(sa.text("DROP TABLE gaz_stage"))
    return len(hits)


def local_pass(conn: sa.Connection, run_id: int) -> dict[str, int]:
    """Match against `gazetteer_feature`; a no-op until `ppr gazetteer` has filled it."""
    index = load_index(conn)
    if not index.named and not index.addresses:
        return {"local_exact": 0, "local_street": 0}
    hits = []
    for pid, display, county, current, lon, lat in conn.execute(sa.text(LOCAL_CANDIDATES)):
        m = local.match(index, display, county)
        if m is None:
            continue
        if current == "street" and (
            m.confidence is not GeocodeConfidence.EXACT
            or km_between(m.lon, m.lat, lon, lat) > STREET_TO_EXACT_KM
        ):
            continue
        hits.append((pid, m.lon, m.lat, m.confidence.value, m.method, m.source, m.part))
    conn.execute(sa.text(CREATE_LOCAL_STAGE))
    raw = conn.connection.driver_connection
    assert raw is not None
    columns = "property_id, lon, lat, confidence, method, source, query"
    with raw.cursor() as cur, cur.copy(f"COPY local_stage ({columns}) FROM STDIN") as copy:
        for row in hits:
            copy.write_row(row)
    conn.execute(sa.text(APPLY_LOCAL), {"run_id": run_id, "step": LOCAL_STEP})
    conn.execute(sa.text("DROP TABLE local_stage"))
    exact = sum(1 for h in hits if h[3] == GeocodeConfidence.EXACT.value)
    return {"local_exact": exact, "local_street": len(hits) - exact}


def fallbacks(engine: sa.Engine, run_id: int) -> dict[str, int]:
    with engine.begin() as conn:
        conn.execute(sa.text(RESET_FALLBACKS))
        rechecked = conn.execute(
            sa.text(RECHECK_BUILDINGS), {"types": sorted(RESIDENTIAL_BUILDINGS)}
        ).rowcount
        # The reset turned a third of all properties back to 'unmatched' in this transaction,
        # which the planner's statistics do not know: without this it planned the routing-key
        # step for one unmatched row and re-ran its median per row, for hours (2026-09-30).
        conn.execute(sa.text("ANALYZE property"))
        matched_locally = local_pass(conn, run_id)
        index = gazetteer_index(conn)
        gazetteer = _apply_gazetteer(conn, index, gazetteer_match, None, run_id)
        routing = conn.execute(
            sa.text(APPLY_ROUTING_KEY),
            {"min_points": MIN_ROUTING_KEY_POINTS, "buffer": COUNTY_BUFFER_M},
        ).rowcount
        county_town = _apply_gazetteer(
            conn, index, county_town_match, "gazetteer:county_town", run_id
        )
        county = conn.execute(sa.text(APPLY_COUNTY)).rowcount
        conn.execute(sa.text("DELETE FROM geocode_attempt WHERE method = 'check:routing_key'"))
        conflicts = conn.execute(
            sa.text(FLAG_ROUTING_KEY_CONFLICTS),
            {
                "run_id": run_id,
                "min_points": MIN_ROUTING_KEY_POINTS,
                "max_m": ROUTING_KEY_CONFLICT_M,
            },
        ).rowcount
    return {
        "rechecked_buildings": rechecked,
        **matched_locally,
        "gazetteer": gazetteer,
        "routing_key": routing,
        "county_town": county_town,
        "county": county,
        "routing_key_conflicts": conflicts,
    }


# --- spatial joins and H3 ------------------------------------------------------------------

JOIN_BATCH = 50_000

# Areas finer than the point's precision would be made up: a town centre says nothing about
# which Small Area a house is in. Exact and street points get every area; locality points
# only the settlement they fall in (and the townland the gazetteer named).
SPATIAL_JOIN = """
UPDATE property p SET
    small_area_id = CASE WHEN precise THEN (
        SELECT ap.area_id FROM area_part ap
        WHERE ap.kind = 'small_area' AND ST_Intersects(ap.geom, pt) LIMIT 1) END,
    ed_id = CASE WHEN precise THEN (
        SELECT ap.area_id FROM area_part ap
        WHERE ap.kind = 'electoral_division' AND ST_Intersects(ap.geom, pt) LIMIT 1) END,
    townland_id = CASE
        WHEN precise THEN (
            SELECT ap.area_id FROM area_part ap
            WHERE ap.kind = 'townland' AND ST_Intersects(ap.geom, pt) LIMIT 1)
        WHEN p.geocode_method = 'gazetteer:townland' THEN p.townland_id END,
    settlement_id = CASE WHEN precise OR p.geocode_confidence = 'locality' THEN (
        SELECT ap.area_id FROM area_part ap
        WHERE ap.kind = 'settlement' AND ST_Intersects(ap.geom, pt) LIMIT 1) END
FROM (
    SELECT id, ST_Transform(geom, 2157) AS pt,
           geocode_confidence IN ('exact', 'street') AS precise
    FROM property WHERE id >= :lo AND id < :hi AND geom IS NOT NULL
) q
WHERE p.id = q.id
"""

PRECISE_POINTS = """
SELECT id, ST_Y(geom), ST_X(geom) FROM property
WHERE geocode_confidence IN ('exact', 'street') AND geom IS NOT NULL
"""


APPLY_H3 = "UPDATE property p SET h3_r8 = s.h3 FROM h3_stage s WHERE p.id = s.id"


def h3_r8(lat: float, lon: float) -> int:
    return int(h3.latlng_to_cell(lat, lon, 8), 16)


def spatial_joins(engine: sa.Engine, progress: Progress = lambda _: None) -> dict[str, int]:
    with engine.connect() as conn:
        lo, hi = conn.execute(sa.text("SELECT min(id), max(id) FROM property")).one()
    if lo is None:
        return {"joined": 0, "h3": 0}
    joined = 0
    for start in range(lo, hi + 1, JOIN_BATCH):
        with engine.begin() as conn:
            joined += conn.execute(
                sa.text(SPATIAL_JOIN), {"lo": start, "hi": start + JOIN_BATCH}
            ).rowcount
        progress(f"  spatial joins: {joined:,}")
    with engine.begin() as conn:
        cells = [(pid, h3_r8(lat, lon)) for pid, lat, lon in conn.execute(sa.text(PRECISE_POINTS))]
        conn.execute(sa.text("UPDATE property SET h3_r8 = NULL WHERE h3_r8 IS NOT NULL"))
        conn.execute(sa.text("CREATE TEMP TABLE h3_stage (id bigint, h3 bigint) ON COMMIT DROP"))
        raw = conn.connection.driver_connection
        assert raw is not None
        with raw.cursor() as cur, cur.copy("COPY h3_stage (id, h3) FROM STDIN") as copy:
            for row in cells:
                copy.write_row(row)
        conn.execute(
            sa.text("UPDATE property p SET h3_r8 = s.h3 FROM h3_stage s WHERE p.id = s.id")
        )
    return {"joined": joined, "h3": len(cells)}


# --- run -----------------------------------------------------------------------------------

CONFIDENCE_COUNTS = "SELECT geocode_confidence::text, count(*) FROM property GROUP BY 1"


def geocode_properties(
    engine: sa.Engine,
    nominatim_url: str,
    *,
    refresh: bool = False,
    limit: int | None = None,
    workers: int = WORKERS,
    client: httpx.Client | None = None,
    progress: Progress = lambda _: None,
) -> dict[str, Any]:
    """Run the whole cascade and record it as an `ingest_run` of kind `geocode`."""
    with engine.begin() as conn:
        run_id: int = conn.execute(
            sa.insert(IngestRun)
            .values(kind=IngestKind.GEOCODE, status=IngestStatus.RUNNING, source_url=nominatim_url)
            .returning(IngestRun.id)
        ).scalar_one()
        if refresh:
            conn.execute(
                sa.text(
                    "UPDATE property SET geocoded_at = NULL, geom = NULL, "
                    "geocode_confidence = 'unmatched' WHERE NOT geocode_locked"
                )
            )
        boxes = county_boxes(conn)
    started = time.monotonic()
    try:
        nominatim = Nominatim(nominatim_url, boxes, client, max_connections=workers * 2)
        geocoder = Geocoder(nominatim)
        tried = nominatim_pass(
            engine, geocoder, run_id, limit=limit, workers=workers, progress=progress
        )
        progress("  fallbacks: gazetteer, routing key, county")
        stats: dict[str, Any] = {
            "properties": tried,
            "queries": nominatim.queries,
            **fallbacks(engine, run_id),
            **spatial_joins(engine, progress),
        }
        with engine.begin() as conn:
            stats["confidence"] = dict(conn.execute(sa.text(CONFIDENCE_COUNTS)).all())
            stats["seconds"] = round(time.monotonic() - started, 1)
            _finish(conn, run_id, status=IngestStatus.SUCCEEDED, rows_read=tried, stats=stats)
    except BaseException as exc:
        with engine.begin() as conn:
            _finish(conn, run_id, status=IngestStatus.FAILED, stats={"error": repr(exc)})
        raise
    return {"run_id": run_id, **stats}


def _finish(conn: sa.Connection, run_id: int, **values: Any) -> None:
    conn.execute(
        sa.update(IngestRun)
        .where(IngestRun.id == run_id)
        .values(finished_at=datetime.now(UTC), **values)
    )
