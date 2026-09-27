"""Pobal HP Deprivation Index 2022 at Electoral Division level (D-011; CC BY 4.0).

The index is published per ED by the CSO's numeric ED id (`ED_ID_STR`, slash-joined for
merged EDs); our ED areas are keyed by `ED_GUID`. The CSO boundary layer carries both, so
the downloaded boundary file maps one to the other.
"""

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import pyogrio
import sqlalchemy as sa

from ppr_pipeline.boundaries import gdb_path

SOURCE = "pobal_hp_2022"
LICENCE = "CC BY 4.0"
AS_OF = date(2022, 4, 3)  # Census 2022 night, which the index is built on


def _number(text: str) -> Decimal | None:
    text = text.replace(",", "").strip()
    return Decimal(text) if text else None


def read_pobal(payload: bytes) -> list[dict[str, str]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = payload.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text)))


def ed_key(ed_id: str) -> str:
    """Comparable ED id: Pobal drops leading zeros ("48039" is the CSO's "048039"), and
    merged EDs list their parts ("027058/027085") in no fixed order."""
    return "/".join(sorted(part.strip().lstrip("0") for part in ed_id.split("/")))


def ed_ids(boundary_zip: Path) -> dict[str, str]:
    """CSO `ED_ID_STR` -> `ED_GUID` from the Electoral Divisions layer."""
    meta, _fids, _geoms, values = pyogrio.raw.read(
        gdb_path(boundary_zip), columns=["ED_ID_STR", "ED_GUID"], read_geometry=False
    )
    col = dict(zip(meta["fields"], values, strict=True))
    return {ed_key(str(k)): str(v) for k, v in zip(col["ED_ID_STR"], col["ED_GUID"], strict=True)}


def attribute_rows(
    rows: list[dict[str, str]], guid_by_id: dict[str, str]
) -> tuple[list[tuple[str, str, Decimal | None, str | None]], list[str]]:
    """(ED_GUID, key, value, value_text) rows, and the ED ids that did not match."""
    out: list[tuple[str, str, Decimal | None, str | None]] = []
    missing = []
    for r in rows:
        guid = guid_by_id.get(ed_key(r["ED_ID_STR"]))
        if guid is None:
            missing.append(r["ED_ID_STR"])
            continue
        out.append((guid, "relative_index", _number(r["Index22_ED_std_rel_wt"]), None))
        out.append((guid, "absolute_index", _number(r["Index22_ED_std_abs_wt"]), None))
        out.append(
            (guid, "category", _number(r["Index22_ED_rel_wt_cat"]), r["Index22_ED_rel_wt_lab"])
        )
    return out, missing


REPLACE = """
INSERT INTO area_attribute (area_id, source, key, as_of, value, value_text, licence)
SELECT a.id, :source, s.key, :as_of, s.value, s.value_text, :licence
FROM pobal_stage s JOIN area a ON a.kind = 'electoral_division' AND a.code = s.guid
"""


def load_pobal(conn: sa.Connection, payload: bytes, guid_by_id: dict[str, str]) -> dict[str, int]:
    """`guid_by_id` maps `ed_key(ED_ID_STR)` to ED_GUID; see `ed_ids`."""
    rows, missing = attribute_rows(read_pobal(payload), guid_by_id)
    conn.execute(
        sa.text(
            "CREATE TEMP TABLE pobal_stage (guid text, key text, value numeric, value_text text) "
            "ON COMMIT DROP"
        )
    )
    raw = conn.connection.driver_connection
    assert raw is not None
    with (
        raw.cursor() as cur,
        cur.copy("COPY pobal_stage (guid, key, value, value_text) FROM STDIN") as copy,
    ):
        for row in rows:
            copy.write_row(row)
    conn.execute(sa.text("DELETE FROM area_attribute WHERE source = :s"), {"s": SOURCE})
    loaded = conn.execute(
        sa.text(REPLACE), {"source": SOURCE, "as_of": AS_OF, "licence": LICENCE}
    ).rowcount
    return {"pobal_values": loaded, "pobal_unmatched_eds": len(missing)}
