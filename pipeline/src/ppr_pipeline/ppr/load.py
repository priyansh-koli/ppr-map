"""Load parsed PPR rows into `property` and `sale` (docs/ARCHITECTURE.md, Data flow steps 3-5).

Everything runs set-based inside one transaction: rows are COPYed into a temporary stage
table, then properties are upserted, sales inserted or re-seen, and vanished rows withdrawn.
Properties merge only on the exact (county, address_key, unit) key. Eircode and fuzzy
merges are left for the review queue, because PPR Eircodes are sometimes wrong (R-04, R-11).
Addresses with no house number and no unit are never merged across sales (D-030).
"""

import base64
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

import sqlalchemy as sa
from app.models.enums import County

from ppr_pipeline.address import (
    dublin_district_from_eircode,
    normalise_address,
    normalise_eircode,
)
from ppr_pipeline.ppr.parse import ParsedRow

# Refuse to withdraw sales when the new file is much smaller than what we hold:
# that is a truncated download or an upstream accident, not 10% of Irish sales vanishing.
MIN_ROWS_RATIO = 0.9

STAGE_COLUMNS = (
    "line_no",
    "source_row_hash",
    "raw_date",
    "raw_address",
    "raw_county",
    "raw_eircode",
    "raw_price",
    "raw_nfmp",
    "raw_vat",
    "raw_description",
    "raw_size",
    "sale_date",
    "price_eur",
    "not_full_market_price",
    "vat_exclusive",
    "is_new",
    "size_band",
    "is_possible_duplicate",
    "county",
    "public_id",
    "address_display",
    "address_normalised",
    "address_key",
    "unit",
    "house_number",
    "dublin_district",
    "eircode",
    "eircode_routing_key",
)

CREATE_STAGE = """
CREATE TEMP TABLE ppr_stage (
    line_no int, source_row_hash char(64),
    raw_date text, raw_address text, raw_county text, raw_eircode text, raw_price text,
    raw_nfmp text, raw_vat text, raw_description text, raw_size text,
    sale_date date, price_eur numeric(12,2), not_full_market_price bool, vat_exclusive bool,
    is_new bool, size_band size_band, is_possible_duplicate bool,
    county county, public_id text, address_display text, address_normalised text,
    address_key text, unit text, house_number text, dublin_district text,
    eircode char(7), eircode_routing_key char(3)
) ON COMMIT DROP
"""

# Latest sale wins for display fields; the latest non-null value wins for Eircode and district.
UPSERT_PROPERTIES = """
INSERT INTO property AS p (
    public_id, address_display, address_normalised, address_key, unit, house_number,
    county, dublin_district, eircode, eircode_routing_key, geocode_confidence
)
SELECT
    min(public_id),
    (array_agg(address_display ORDER BY sale_date DESC, line_no DESC))[1],
    (array_agg(address_normalised ORDER BY sale_date DESC, line_no DESC))[1],
    address_key,
    unit,
    (array_agg(house_number ORDER BY sale_date DESC, line_no DESC))[1],
    county,
    (array_agg(dublin_district ORDER BY sale_date DESC, line_no DESC)
        FILTER (WHERE dublin_district IS NOT NULL))[1],
    (array_agg(eircode ORDER BY sale_date DESC, line_no DESC)
        FILTER (WHERE eircode IS NOT NULL))[1],
    (array_agg(eircode_routing_key ORDER BY sale_date DESC, line_no DESC)
        FILTER (WHERE eircode IS NOT NULL))[1],
    'unmatched'
FROM ppr_stage
GROUP BY county, address_key, unit
ON CONFLICT (county, address_key, (coalesce(unit, ''))) DO UPDATE SET
    address_display = EXCLUDED.address_display,
    address_normalised = EXCLUDED.address_normalised,
    house_number = EXCLUDED.house_number,
    dublin_district = EXCLUDED.dublin_district,
    eircode = EXCLUDED.eircode,
    eircode_routing_key = EXCLUDED.eircode_routing_key,
    updated_at = now()
WHERE (p.address_display, p.address_normalised, p.house_number, p.dublin_district,
       p.eircode, p.eircode_routing_key)
    IS DISTINCT FROM
      (EXCLUDED.address_display, EXCLUDED.address_normalised, EXCLUDED.house_number,
       EXCLUDED.dublin_district, EXCLUDED.eircode, EXCLUDED.eircode_routing_key)
"""

UPSERT_SALES = """
INSERT INTO sale (
    property_id, source_row_hash,
    raw_date, raw_address, raw_county, raw_eircode, raw_price, raw_nfmp, raw_vat,
    raw_description, raw_size,
    sale_date, price_eur, not_full_market_price, vat_exclusive, is_new, size_band,
    is_possible_duplicate, first_seen_run_id, last_seen_run_id
)
SELECT
    p.id, s.source_row_hash,
    s.raw_date, s.raw_address, s.raw_county, s.raw_eircode, s.raw_price, s.raw_nfmp, s.raw_vat,
    s.raw_description, s.raw_size,
    s.sale_date, s.price_eur, s.not_full_market_price, s.vat_exclusive, s.is_new, s.size_band,
    s.is_possible_duplicate, :run_id, :run_id
FROM ppr_stage s
JOIN property p
  ON p.county = s.county
 AND p.address_key = s.address_key
 AND coalesce(p.unit, '') = coalesce(s.unit, '')
ON CONFLICT (source_row_hash) DO UPDATE SET
    last_seen_run_id = EXCLUDED.last_seen_run_id,
    is_possible_duplicate = EXCLUDED.is_possible_duplicate,
    withdrawn_at = NULL
"""

WITHDRAW_MISSING = """
UPDATE sale SET withdrawn_at = now()
WHERE withdrawn_at IS NULL AND last_seen_run_id <> :run_id
"""


class TooFewRowsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LoadResult:
    rows_loaded: int
    sales_inserted: int
    sales_withdrawn: int
    properties_inserted: int
    properties_total: int
    sales_active: int
    possible_duplicates: int
    max_sale_date: str | None


def public_id(county: County, key: str, unit: str | None) -> str:
    """Stable 12-character URL slug for a Property (60 bits; collisions are negligible)."""
    digest = hashlib.sha256(f"{county.value}|{key}|{unit or ''}".encode()).digest()
    return base64.b32encode(digest).decode("ascii")[:12].lower()


def sale_identity(row: ParsedRow) -> str:
    date_, address, _c, _e, price = (" ".join(f.split()) for f in row.raw[:5])
    return hashlib.sha256(f"{date_}|{address.casefold()}|{price}".encode()).hexdigest()[:12]


def stage_record(row: ParsedRow) -> tuple[object, ...]:
    addr = normalise_address(row.raw[1], row.county.value)
    key = addr.key
    if not key or (addr.house_number is None and addr.unit is None):
        # D-030: "Knockroe, Castlerea" names a townland, not a dwelling, so each sale keeps a
        # property of its own. Repeat filings of one sale (same date, address, price) still
        # share it. The part before "~" stays the address key for review-queue matching.
        key = f"{key}~{sale_identity(row)}"
    eircode = normalise_eircode(row.raw[3])
    district = addr.dublin_district
    if district is None and eircode and row.county is County.DUBLIN:
        district = dublin_district_from_eircode(eircode)
    return (
        row.line_no,
        row.source_row_hash,
        *row.raw,
        row.sale_date,
        row.price_eur,
        row.not_full_market_price,
        row.vat_exclusive,
        row.is_new,
        row.size_band.value if row.size_band else None,
        row.is_possible_duplicate,
        row.county.value,
        public_id(row.county, key, addr.unit),
        addr.display,
        addr.normalised,
        key,
        addr.unit,
        addr.house_number,
        district,
        eircode,
        eircode[:3] if eircode else None,
    )


def _scalar(conn: sa.Connection, sql: str, **params: object) -> int:
    return int(conn.execute(sa.text(sql), params).scalar_one())


def load(conn: sa.Connection, rows: Iterable[ParsedRow], run_id: int) -> LoadResult:
    """Load one full PPR file. `conn` must be inside a transaction owned by the caller."""
    conn.execute(sa.text(CREATE_STAGE))
    raw = conn.connection.driver_connection
    assert raw is not None
    loaded = 0
    with raw.cursor() as cur:
        with cur.copy(f"COPY ppr_stage ({', '.join(STAGE_COLUMNS)}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row(stage_record(row))
                loaded += 1
        cur.execute("ANALYZE ppr_stage")

    active = _scalar(conn, "SELECT count(*) FROM sale WHERE withdrawn_at IS NULL")
    if active and loaded < MIN_ROWS_RATIO * active:
        raise TooFewRowsError(
            f"file has {loaded} rows but {active} sales are active; refusing to withdraw"
        )

    properties_before = _scalar(conn, "SELECT count(*) FROM property")
    conn.execute(sa.text(UPSERT_PROPERTIES))
    conn.execute(sa.text(UPSERT_SALES), {"run_id": run_id})
    withdrawn = conn.execute(sa.text(WITHDRAW_MISSING), {"run_id": run_id}).rowcount

    properties_total = _scalar(conn, "SELECT count(*) FROM property")
    return LoadResult(
        rows_loaded=loaded,
        sales_inserted=_scalar(
            conn, "SELECT count(*) FROM sale WHERE first_seen_run_id = :r", r=run_id
        ),
        sales_withdrawn=withdrawn,
        properties_inserted=properties_total - properties_before,
        properties_total=properties_total,
        sales_active=_scalar(conn, "SELECT count(*) FROM sale WHERE withdrawn_at IS NULL"),
        possible_duplicates=_scalar(
            conn,
            "SELECT count(*) FROM sale WHERE is_possible_duplicate AND withdrawn_at IS NULL",
        ),
        max_sale_date=conn.execute(
            sa.text("SELECT max(sale_date)::text FROM sale WHERE withdrawn_at IS NULL")
        ).scalar_one(),
    )
