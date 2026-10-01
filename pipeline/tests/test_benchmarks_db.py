"""Loading the CSO RPPI and calibrating the estimate against PostGIS (D-053).

Needs TEST_DATABASE_URL. The data is real: two Carlow homes that sold twice
(tests/fixtures/ppr_carlow_repeats.csv) and the South-East index for those months
(tests/fixtures/hpm09_sample.csv). Geocoding is not under test here, so the two homes are
marked as placed on their street directly.
"""

import math

import pytest
import sqlalchemy as sa

from ppr_pipeline.benchmarks import load_rppi
from ppr_pipeline.ppr.ingest import ingest_ppr
from tests.conftest import FIXTURES

pytestmark = pytest.mark.db

INDEX = (FIXTURES / "hpm09_sample.csv").read_bytes()
URL = "file:///fixtures/hpm09_sample.csv"
# South-East houses (rppi:24) in the months of the sales.
SANDHILLS = math.log(323_000 / (130_000 * 233.9 / 83))  # Apr 2014 -> Nov 2025
# The 2014 sale of 103 Browneshill Wood was VAT-exclusive, so the pair is Dec 2020 -> Aug 2025.
BROWNESHILL = math.log(330_000 / (205_000 * 229.4 / 149.5))


@pytest.fixture
def repeats(engine: sa.Engine) -> sa.Engine:
    payload = (FIXTURES / "ppr_carlow_repeats.csv").read_bytes()
    ingest_ppr(engine, payload, "file:///fixtures/ppr_carlow_repeats.csv")
    return engine


def _place_on_street(engine: sa.Engine) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE property SET geocode_confidence = 'street'"))


def _calibration(engine: sa.Engine) -> dict[tuple[str, str], tuple[int, float]]:
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text("SELECT series_key, gap_band, n, p50 FROM estimate_calibration")
        )
        return {(r[0], r[1]): (r[2], float(r[3])) for r in rows}


def test_load_replaces_the_index_and_records_a_run(repeats: sa.Engine) -> None:
    first = load_rppi(repeats, INDEX, URL)
    second = load_rppi(repeats, INDEX, URL)
    assert second["values"] == first["values"] == 10
    assert second["series"] == 2
    assert (second["first_month"], second["last_month"]) == ("2010-01-01", "2026-07-01")
    with repeats.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM benchmark_series")).scalar() == 10
        runs = conn.execute(
            sa.text("SELECT kind::text, status::text, source_url FROM ingest_run WHERE id = :id"),
            {"id": second["run_id"]},
        ).one()
    assert runs == ("benchmarks", "succeeded", URL)


def test_calibration_uses_only_precisely_placed_repeat_sales(repeats: sa.Engine) -> None:
    # As ingested, neither home has a location: nothing to calibrate on.
    assert load_rppi(repeats, INDEX, URL)["calibration_pairs"] == 0
    assert _calibration(repeats) == {}

    _place_on_street(repeats)
    assert load_rppi(repeats, INDEX, URL)["calibration_pairs"] == 2
    found = _calibration(repeats)
    assert set(found) == {("rppi:24", "7y+"), ("rppi:24", "3-7y"), ("all", "7y+"), ("all", "3-7y")}
    for key in ("rppi:24", "all"):
        n, p50 = found[(key, "7y+")]
        assert n == 1 and p50 == pytest.approx(SANDHILLS)
        n, p50 = found[(key, "3-7y")]
        assert n == 1 and p50 == pytest.approx(BROWNESHILL)


def test_a_bad_file_fails_the_run_and_keeps_the_old_index(repeats: sa.Engine) -> None:
    load_rppi(repeats, INDEX, URL)
    with pytest.raises(ValueError):
        load_rppi(repeats, b"not,the,cso,file\n1,2,3,4\n", URL)
    with repeats.connect() as conn:
        assert conn.execute(sa.text("SELECT count(*) FROM benchmark_series")).scalar() == 10
        status = conn.execute(
            sa.text("SELECT status::text FROM ingest_run ORDER BY id DESC LIMIT 1")
        ).scalar()
    assert status == "failed"
