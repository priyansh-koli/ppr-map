"""End-to-end PPR ingest against PostGIS (needs TEST_DATABASE_URL; `make up`)."""

import csv
import io

import pytest
import sqlalchemy as sa
from app.models.enums import IngestStatus

from ppr_pipeline.ppr.ingest import csv_bytes, ingest_ppr
from ppr_pipeline.ppr.load import TooFewRowsError
from tests.conftest import FIXTURES

pytestmark = pytest.mark.db
URL = "file:///fixtures/ppr_sample.csv"


def _count(engine: sa.Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(sa.text(sql)).scalar_one())


def _without_line(data: bytes, needle: bytes) -> bytes:
    lines = data.split(b"\r\n")
    return b"\r\n".join(line for line in lines if needle not in line)


def test_first_load(engine: sa.Engine, sample_csv: bytes) -> None:
    run = ingest_ppr(engine, sample_csv, URL)
    assert run.status is IngestStatus.SUCCEEDED
    assert (run.rows_read, run.rows_inserted, run.rows_withdrawn, run.rows_failed) == (26, 26, 0, 0)
    # 26 sales -> 24 properties: one exact duplicate filing and one repeat sale merge;
    # the two "Knockroe, Castlerea" sales (no house number) stay apart (D-030).
    assert run.stats["properties_total"] == 24
    assert run.stats["possible_duplicates"] == 1
    assert run.stats["max_sale_date"] == "2026-02-12"

    with engine.connect() as conn:
        elms = conn.execute(
            sa.text(
                "SELECT p.address_display, p.eircode, p.eircode_routing_key, count(s.id) "
                "FROM property p JOIN sale s ON s.property_id = p.id "
                "WHERE p.address_key = '9theelmscastlejanewoodglanmire' "
                "GROUP BY p.id"
            )
        ).one()
        # Latest sale shown (title-cased); its Eircode is kept though the 2015 sale had none.
        assert tuple(elms) == ("9 The Elms, Castlejane Wood, Glanmire", "T45AE33", "T45", 2)

        apt = conn.execute(
            sa.text("SELECT unit, dublin_district FROM property WHERE unit LIKE '%block 11'")
        ).one()
        assert tuple(apt) == ("apartment 3 block 11", "D13")

        townland = conn.execute(
            sa.text(
                "SELECT count(DISTINCT p.id), count(*) FROM property p "
                "JOIN sale s ON s.property_id = p.id "
                "WHERE p.address_key LIKE 'knockroecastlerea~%'"
            )
        ).one()
        assert tuple(townland) == (2, 2)

        raw_price = conn.execute(
            sa.text("SELECT raw_price FROM sale WHERE raw_address LIKE '247 GLANNTAN%'")
        ).scalar_one()
        assert raw_price == "€228,500.00"


def test_same_file_twice_is_skipped(engine: sa.Engine, sample_csv: bytes) -> None:
    ingest_ppr(engine, sample_csv, URL)
    again = ingest_ppr(engine, sample_csv, URL)
    assert again.status is IngestStatus.SKIPPED_UNCHANGED
    assert _count(engine, "SELECT count(*) FROM sale") == 26


def test_forced_reload_is_idempotent(engine: sa.Engine, sample_csv: bytes) -> None:
    ingest_ppr(engine, sample_csv, URL)
    forced = ingest_ppr(engine, sample_csv, URL, force=True)
    assert forced.status is IngestStatus.SUCCEEDED
    assert (forced.rows_inserted, forced.rows_withdrawn) == (0, 0)
    assert _count(engine, "SELECT count(*) FROM sale") == 26
    assert _count(engine, "SELECT count(*) FROM property") == 24


def test_vanished_rows_are_withdrawn_then_restored(engine: sa.Engine, sample_csv: bytes) -> None:
    ingest_ppr(engine, sample_csv, URL)
    smaller = _without_line(sample_csv, b"No. 11 Blackrock Court")
    run = ingest_ppr(engine, smaller, URL)
    assert (run.rows_inserted, run.rows_withdrawn) == (0, 1)
    assert _count(engine, "SELECT count(*) FROM sale WHERE withdrawn_at IS NOT NULL") == 1
    assert _count(engine, "SELECT count(*) FROM sale") == 26  # never hard-deleted

    back = ingest_ppr(engine, sample_csv, URL)
    assert back.rows_withdrawn == 0
    assert _count(engine, "SELECT count(*) FROM sale WHERE withdrawn_at IS NOT NULL") == 0


def test_bad_rows_are_logged_and_the_rest_load(engine: sa.Engine, sample_csv: bytes) -> None:
    broken = sample_csv.replace(b'"\x80210,000.00"', b'"210000"', 1)
    run = ingest_ppr(engine, broken, URL)
    assert (run.rows_read, run.rows_inserted, run.rows_failed) == (26, 25, 1)
    with engine.connect() as conn:
        err = conn.execute(sa.text("SELECT line_no, error FROM ingest_row_error")).one()
    assert "bad price" in err.error


def test_a_truncated_file_fails_without_withdrawing(engine: sa.Engine, sample_csv: bytes) -> None:
    ingest_ppr(engine, sample_csv, URL)
    lines = sample_csv.split(b"\r\n")
    truncated = b"\r\n".join(lines[:6])
    with pytest.raises(TooFewRowsError):
        ingest_ppr(engine, truncated, URL)
    assert _count(engine, "SELECT count(*) FROM sale WHERE withdrawn_at IS NOT NULL") == 0
    assert _count(engine, "SELECT count(*) FROM ingest_run WHERE status = 'failed'") == 1


def test_zip_payloads_are_unpacked(sample_csv: bytes) -> None:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("PPR-ALL.csv", sample_csv)
    assert csv_bytes(buf.getvalue()) == sample_csv
    assert next(csv.reader(io.StringIO(csv_bytes(sample_csv).decode("cp1252"))))[0].startswith(
        "Date of Sale"
    )


def test_bulk_groups(engine: sa.Engine, sample_csv: bytes) -> None:
    """The fixture's five EUR 180,000 sales on 11/01/2019 are in five different counties:
    a coincidence, not a portfolio, so nothing is flagged."""
    run = ingest_ppr(engine, sample_csv, URL)
    assert (run.stats["bulk_sales"], run.stats["bulk_groups"]) == (0, 0)


def test_bulk_rule(engine: sa.Engine) -> None:
    """Three real Dublin groups (tests/fixtures/ppr_bulk_sample.csv): four flats at
    59 Patrick St at a round price, three Mount Argus flats at an apportioned price, and
    three unrelated homes (Swords, Dublin 8, Santry) at EUR 400,000 on the same day."""
    run = ingest_ppr(engine, (FIXTURES / "ppr_bulk_sample.csv").read_bytes(), URL)
    assert (run.stats["bulk_sales"], run.stats["bulk_groups"]) == (7, 2)
    with engine.connect() as conn:
        unflagged = (
            conn.execute(
                sa.text("SELECT raw_address FROM sale WHERE bulk_group_id IS NULL ORDER BY 1")
            )
            .scalars()
            .all()
        )
    assert unflagged == [
        "12 THORNLEIGH SQ, SWORDS, DUBLIN",
        "30 CANNON COURT, BRIDE ST, DUBLIN 8",
        "33 MAGENTA HALL, SANTRY, DUBLIN",
    ]
