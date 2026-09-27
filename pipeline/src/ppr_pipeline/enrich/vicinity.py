"""Per-property vicinity values in `property_enrichment` (docs/data-model.md).

Only exact and street points get them: a distance measured from a town centre or a county
point would be made up. Distances are straight lines in metres (ITM), not walking routes,
and are labelled that way wherever they are shown.
"""

import json
import time
from collections.abc import Callable
from typing import Any

import sqlalchemy as sa

JOIN_BATCH = 50_000
AMENITY_TYPES = ("shop", "supermarket", "pharmacy", "park", "gym", "restaurant", "gp")
Progress = Callable[[str], None]

# One small ITM table with its own index per group: a nearest-school search should not
# wade through every shop in Dublin first.
GROUPS = {
    "near_stop": ("bus_stop", "luas_stop", "rail_station", "dart_station"),
    "near_rail": ("rail_station", "dart_station"),
    "near_primary": ("school_primary",),
    "near_post_primary": ("school_post_primary",),
    "near_amenity": AMENITY_TYPES,
}

INSERT = """
INSERT INTO property_enrichment (
    property_id, nearest_stop_id, nearest_stop_type, nearest_stop_m, nearest_rail_m,
    nearest_primary_school_id, nearest_primary_school_m,
    nearest_post_primary_school_id, nearest_post_primary_school_m,
    amenities_1km, deprivation_band, deprivation_level, provenance, computed_at)
SELECT p.id, st.id, st.type, st.m, rl.m, ps.id, ps.m, pp.id, pp.m,
       coalesce(am.counts, '{}'::jsonb), dep.value_text,
       CASE WHEN dep.value_text IS NOT NULL THEN 'ed' END,
       CAST(:provenance AS jsonb), now()
FROM (
    SELECT id, ed_id, ST_Transform(geom, 2157) AS pt FROM property
    WHERE geocode_confidence IN ('exact', 'street') AND id >= :lo AND id < :hi
) p
LEFT JOIN LATERAL (
    SELECT id, type, round(ST_Distance(g, p.pt))::int AS m FROM near_stop
    ORDER BY g <-> p.pt LIMIT 1) st ON true
LEFT JOIN LATERAL (
    SELECT round(ST_Distance(g, p.pt))::int AS m FROM near_rail
    ORDER BY g <-> p.pt LIMIT 1) rl ON true
LEFT JOIN LATERAL (
    SELECT id, round(ST_Distance(g, p.pt))::int AS m FROM near_primary
    ORDER BY g <-> p.pt LIMIT 1) ps ON true
LEFT JOIN LATERAL (
    SELECT id, round(ST_Distance(g, p.pt))::int AS m FROM near_post_primary
    ORDER BY g <-> p.pt LIMIT 1) pp ON true
LEFT JOIN LATERAL (
    SELECT jsonb_object_agg(type, n) AS counts
    FROM (SELECT type, count(*) AS n FROM near_amenity
          WHERE ST_DWithin(g, p.pt, 1000) GROUP BY type) x) am ON true
LEFT JOIN area_attribute dep ON dep.area_id = p.ed_id AND dep.source = 'pobal_hp_2022'
     AND dep.key = 'category'
"""

SOURCES = """
SELECT source, max(as_of)::text FROM poi GROUP BY source
"""


def provenance(conn: sa.Connection) -> dict[str, Any]:
    as_of: dict[str, str] = {r[0]: r[1] for r in conn.execute(sa.text(SOURCES))}
    return {
        "transport": {"source": "NTA GTFS", "asOf": as_of.get("NTA GTFS")},
        "schools": {"source": "OpenStreetMap", "asOf": as_of.get("OpenStreetMap")},
        "amenities": {"source": "OpenStreetMap", "asOf": as_of.get("OpenStreetMap")},
        "deprivation": {
            "source": "Pobal HP Deprivation Index 2022 (Electoral Division)",
            "asOf": "2022",
        },
        "distance": "straight line",
    }


def compute_vicinity(engine: sa.Engine, progress: Progress = lambda _: None) -> dict[str, Any]:
    started = time.monotonic()
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE property_enrichment"))
        lo, hi = conn.execute(sa.text("SELECT min(id), max(id) FROM property")).one()
        prov = provenance(conn)
    if lo is None:
        return {"enriched": 0}
    done = 0
    # One session: the ITM tables are built once and each batch commits on its own.
    with engine.connect() as conn:
        for name, types in GROUPS.items():
            # Pooled connections keep session temp tables: start clean, and drop at the end.
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {name}"))
            conn.execute(
                sa.text(
                    f"CREATE TEMP TABLE {name} AS "  # noqa: S608 (constant table names)
                    "SELECT id, type, ST_Transform(geom, 2157) AS g FROM poi "
                    "WHERE type::text = ANY(:types)"
                ),
                {"types": list(types)},
            )
            conn.execute(sa.text(f"CREATE INDEX ON {name} USING gist (g)"))
            conn.execute(sa.text(f"ANALYZE {name}"))
        conn.commit()
        for start in range(lo, hi + 1, JOIN_BATCH):
            done += conn.execute(
                sa.text(INSERT),
                {"lo": start, "hi": start + JOIN_BATCH, "provenance": json.dumps(prov)},
            ).rowcount
            conn.commit()
            progress(f"  vicinity: {done:,}")
        for name in GROUPS:
            conn.execute(sa.text(f"DROP TABLE {name}"))
        conn.commit()
    return {"enriched": done, "seconds": round(time.monotonic() - started, 1)}
