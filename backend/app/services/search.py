"""Search (D-047): the map's matching function over a box derived from the filters, and
autocomplete over our own places and addresses (D-006). Nothing here calls a third party."""

import json
import math
import re
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.properties import SalesFilter

Box = tuple[float, float, float, float]  # west, south, east, north
# Every property point lies inside this box.
IRELAND: Box = (-11.0, 51.0, -5.0, 56.0)
# Display shapes are simplified by up to 50 m (D-033), so their boxes are widened a little.
# A property may lie up to 2 km outside the county it was filed under (D-035), so county
# boxes are widened by more (0.05 degrees is over 3 km in Ireland).
AREA_MARGIN_DEG = 0.01
COUNTY_MARGIN_DEG = 0.05

AREA_BOX = """
SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
FROM (SELECT ST_Extent(geom) AS e FROM area WHERE {where}) t WHERE e IS NOT NULL
"""
ROUTING_KEY_BOX = """
SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)
FROM (SELECT ST_Extent(geom) AS e FROM property
      WHERE eircode_routing_key = ANY(:keys)
         OR (eircode_routing_key IS NULL
             AND dublin_district = ANY(ARRAY(SELECT routing_key_district(k)
                                             FROM unnest(CAST(:keys AS text[])) k)))) t
WHERE e IS NOT NULL
"""


def _intersect(a: Box, b: Box) -> Box | None:
    w, s, e, n = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (w, s, e, n) if w <= e and s <= n else None


def _widen(box: Box | None, margin: float) -> Box | None:
    if box is None:
        return None
    return (box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin)


def near_box(near: str, radius_m: int) -> Box:
    lat, lng = (float(v) for v in near.split(","))
    dlat = radius_m / 111_320
    dlng = radius_m / (111_320 * math.cos(math.radians(lat)))
    return (lng - dlng, lat - dlat, lng + dlng, lat + dlat)


async def _box(session: AsyncSession, sql: str, params: dict[str, Any]) -> Box | None:
    row = (await session.execute(sa.text(sql), params)).one_or_none()
    return (row[0], row[1], row[2], row[3]) if row else None


async def envelope(session: AsyncSession, f: SalesFilter, bbox: Box | None) -> Box | None:
    """The smallest box that can hold every match, so the spatial index does the first cut.
    None when the filters cannot match anything (an unknown area, disjoint places)."""
    box: Box | None = IRELAND
    boxes: list[Box | None] = [bbox] if bbox else []
    if f.county:
        where = "kind = 'county' AND code = ANY(:c)"
        found = await _box(session, AREA_BOX.format(where=where), {"c": list(f.county)})
        boxes.append(_widen(found, COUNTY_MARGIN_DEG))
    if f.area:
        found = await _box(session, AREA_BOX.format(where="slug = ANY(:s)"), {"s": f.area})
        counties = await _box(
            session, AREA_BOX.format(where="slug = ANY(:s) AND kind = 'county'"), {"s": f.area}
        )
        boxes.append(_widen(found, COUNTY_MARGIN_DEG if counties else AREA_MARGIN_DEG))
    if f.routing_key:
        boxes.append(await _box(session, ROUTING_KEY_BOX, {"keys": f.routing_key}))
    if f.near:
        boxes.append(near_box(f.near, f.radius_m or 1000))
    for b in boxes:
        if b is None or box is None:
            return None
        box = _intersect(box, b)
    return box


# The latest matching sale per property, the page asked for, the total and the results' box.
# A price change is shown only between two plain market sales (as on the property page):
# not "not full market price", not VAT-exclusive, not bulk and not a possible repeat filing.
# Only constant SQL fragments are formatted into these statements; values are bound.
# A property with one sale has no earlier one, so the lookup finds nothing for it.
def _previous(alias: str) -> str:
    return f"""
LEFT JOIN LATERAL (
    SELECT s2.sale_date, s2.price_eur FROM sale s2
    WHERE s2.property_id = {alias}.property_id AND s2.sale_date < {alias}.sale_date
      AND s2.withdrawn_at IS NULL AND NOT s2.not_full_market_price AND NOT s2.vat_exclusive
      AND s2.bulk_group_id IS NULL AND NOT s2.is_possible_duplicate
    ORDER BY s2.sale_date DESC, s2.id DESC LIMIT 1
) prev ON NOT ({alias}.nfmp OR {alias}.vatx OR {alias}.bulk)
"""  # noqa: S608


def _change(alias: str) -> str:
    return f"round(({alias}.price_eur / nullif(prev.price_eur, 0) - 1) * 100, 1)"


# Every match is materialised, so `n_sales` (a lookup per property) is left out here and
# counted for the page only, as `tile_matching_sales` counts it (migration 0012).
MATCHES = """
WITH m AS MATERIALIZED (
    SELECT property_id, public_id, geom, confidence, sale_date, price_eur, is_new, nfmp, vatx,
           bulk
    FROM tile_matching_sales(ST_MakeEnvelope(:w, :s, :e, :n, 4326), CAST(:params AS json))
), agg AS (
    SELECT count(*) AS total, ST_Extent(geom) AS box FROM m
)"""
COLUMNS = """page.public_id, p.address_display, page.confidence::text, ST_Y(page.geom),
       ST_X(page.geom), page.sale_date, page.price_eur, page.is_new, page.nfmp, page.vatx,
       page.bulk, (SELECT count(*) FROM sale a
                   WHERE a.property_id = page.property_id AND a.withdrawn_at IS NULL)"""
TOTALS = "agg.total, ST_XMin(agg.box), ST_YMin(agg.box), ST_XMax(agg.box), ST_YMax(agg.box)"

# Sorting by date or price: the previous sale is looked up for the page only.
SEARCH = f"""{MATCHES}, page AS (
    SELECT * FROM m ORDER BY {{order}}, property_id LIMIT :limit OFFSET :offset
)
SELECT {COLUMNS}, prev.sale_date, prev.price_eur, {_change("page")}, {TOTALS}
FROM agg LEFT JOIN page ON true
LEFT JOIN property p ON p.id = page.property_id
{_previous("page")}
ORDER BY page.{{order}}, page.property_id
"""  # noqa: S608
# Sorting by change needs every match's previous sale.
SEARCH_BY_CHANGE = f"""{MATCHES}, page AS (
    SELECT m.*, prev.sale_date AS prev_date, prev.price_eur AS prev_price,
           {_change("m")} AS change_pct
    FROM m {_previous("m")}
    ORDER BY change_pct {{direction}} NULLS LAST, m.property_id LIMIT :limit OFFSET :offset
)
SELECT {COLUMNS}, page.prev_date, page.prev_price, page.change_pct, {TOTALS}
FROM agg LEFT JOIN page ON true
LEFT JOIN property p ON p.id = page.property_id
ORDER BY page.change_pct {{direction}} NULLS LAST, page.property_id
"""  # noqa: S608
ORDERS = {
    "-date": "sale_date DESC",
    "date": "sale_date ASC",
    "-price": "price_eur DESC",
    "price": "price_eur ASC",
}
SORTS = (*ORDERS, "-change", "change")


def search_sql(sort: str) -> str:
    if sort == "-change":
        return SEARCH_BY_CHANGE.format(direction="DESC")
    if sort == "change":
        return SEARCH_BY_CHANGE.format(direction="ASC")
    return SEARCH.format(order=ORDERS[sort])


async def search(
    session: AsyncSession, f: SalesFilter, box: Box, sort: str, page: int, page_size: int
) -> list[Any]:
    w, s, e, n = box
    return list(
        (
            await session.execute(
                sa.text(search_sql(sort)),
                {
                    "w": w,
                    "s": s,
                    "e": e,
                    "n": n,
                    "params": json.dumps(f.to_params()),
                    "limit": page_size,
                    "offset": (page - 1) * page_size,
                },
            )
        ).all()
    )


async def places(session: AsyncSession, slugs: list[str] | None) -> list[Any]:
    if not slugs:
        return []
    rows = await session.execute(
        sa.text("SELECT kind::text, name, slug FROM area WHERE slug = ANY(:s)"), {"s": slugs}
    )
    found = {r[2]: r for r in rows}
    return [found[s] for s in slugs if s in found]


# --- autocomplete (D-006) -------------------------------------------------------------------

AREA_KINDS = ("county", "settlement", "electoral_division", "townland")
AREAS = """
SELECT a.kind::text, a.name, a.slug, c.name AS county,
       ST_Y(ST_PointOnSurface(a.geom)), ST_X(ST_PointOnSurface(a.geom)),
       ST_XMin(a.geom), ST_YMin(a.geom), ST_XMax(a.geom), ST_YMax(a.geom)
FROM area a LEFT JOIN area c ON c.id = a.parent_id AND c.kind = 'county'
WHERE a.kind = ANY(CAST(:kinds AS area_kind[]))
  AND (a.name ILIKE :prefix OR a.name ILIKE :word OR a.name_ga ILIKE :prefix)
ORDER BY lower(a.name) = :q DESC, a.name ILIKE :prefix DESC,
         array_position(CAST(:kinds AS area_kind[]), a.kind), length(a.name), a.name
LIMIT :limit
"""
# Each word of the query must appear in the address; best matches first.
PROPERTIES = """
SELECT p.public_id, p.address_display, p.county::text, ST_Y(p.geom), ST_X(p.geom),
       p.geocode_confidence::text
FROM property p
WHERE NOT p.is_suppressed AND p.geom IS NOT NULL AND {words}
ORDER BY similarity(p.address_normalised, :q) DESC, p.address_display
LIMIT :limit
"""
ROUTING_KEY = """
SELECT count(*), ST_Y(ST_Centroid(ST_Collect(geom))), ST_X(ST_Centroid(ST_Collect(geom)))
FROM property WHERE eircode_routing_key = :key
  AND geocode_confidence IN ('exact', 'street', 'locality')
"""
# The PPR spells these out; people type the short forms.
ABBREVIATIONS = {
    "rd": "road",
    "ave": "avenue",
    "st": "street",
    "sq": "square",
    "pk": "park",
    "dr": "drive",
    "cres": "crescent",
    "ct": "court",
    "tce": "terrace",
    "co": "",
}
DUBLIN_DISTRICT = re.compile(r"^(?:dublin|d)\s*(\d{1,2}w?)$")
ROUTING = re.compile(r"^[ac-fhknprtv-y]\d{2}$|^d6w$")


def normalise(q: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s'-]", " ", q.lower())).strip()


def routing_key_for(q: str) -> str | None:
    """'D08', 'd8', 'Dublin 8' and 'dublin 6w' name routing keys; so does 'a63'."""
    if ROUTING.match(q):
        return q.upper()
    if m := DUBLIN_DISTRICT.match(q):
        d = m.group(1).upper()
        return "D6W" if d == "6W" else f"D{int(d):02d}" if d.isdigit() else None
    return None


def routing_key_district(key: str) -> str | None:
    """D08 -> D8, as the PPR writes Dublin postal districts (SQL: routing_key_district)."""
    if key == "D6W":
        return key
    return f"D{int(key[1:])}" if re.fullmatch(r"D\d{2}", key) else None


def address_words(q: str) -> list[str]:
    words = [ABBREVIATIONS.get(w, w) for w in q.replace(",", " ").split()]
    return [w for w in words if w][:6]


async def areas(session: AsyncSession, q: str, limit: int) -> list[Any]:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    params = {
        "q": q,
        "prefix": f"{esc}%",
        "word": f"% {esc}%",
        "kinds": list(AREA_KINDS),
        "limit": limit,
    }
    return list((await session.execute(sa.text(AREAS), params)).all())


async def properties(session: AsyncSession, q: str, limit: int) -> list[Any]:
    words = address_words(q)
    if not words or sum(len(w) for w in words) < 3:
        return []
    clauses = " AND ".join(f"p.address_normalised ILIKE :w{i}" for i in range(len(words)))
    params: dict[str, Any] = {"q": " ".join(words), "limit": limit}
    for i, w in enumerate(words):
        params[f"w{i}"] = (
            "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        )
    return list((await session.execute(sa.text(PROPERTIES.format(words=clauses)), params)).all())


async def routing_key(session: AsyncSession, key: str) -> Any:
    row = (await session.execute(sa.text(ROUTING_KEY), {"key": key})).one()
    return row if row[0] else None
