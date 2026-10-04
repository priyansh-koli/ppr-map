"""Aggregates against PostGIS: area stats, price hexes and hover summaries.

Needs TEST_DATABASE_URL. The data is real: 27 Pollerton sales and 3 new builds in Carlow in
2025 (tests/fixtures/ppr_carlow_2025.csv), the Carlow boundary subset, and Nominatim answers
recorded for those addresses (tests/fixtures/nominatim/responses.json).
"""

import csv
import io
import json
import statistics
from dataclasses import replace
from decimal import Decimal

import httpx
import pytest
import sqlalchemy as sa

from ppr_pipeline import aggregate as aggregate_module
from ppr_pipeline.aggregate import aggregate
from ppr_pipeline.boundaries import LAYERS, load_boundaries
from ppr_pipeline.geocode.runner import geocode_properties
from ppr_pipeline.ppr.ingest import ingest_ppr
from tests.conftest import FIXTURES

pytestmark = pytest.mark.db

CSV = FIXTURES / "ppr_carlow_2025.csv"
RECORDED = json.loads((FIXTURES / "nominatim" / "responses.json").read_text())


def _prices(new: bool | None = None) -> list[Decimal]:
    rows = list(csv.reader(io.StringIO(CSV.read_bytes().decode("cp1252"))))[1:]
    return [
        Decimal(r[4].lstrip("€").replace(",", ""))
        for r in rows
        if new is None or r[7].startswith("New") == new
    ]


@pytest.fixture
def loaded(engine: sa.Engine) -> sa.Engine:
    layers = [replace(la, filename=la.filename.replace(".zip", ".gpkg")) for la in LAYERS]
    load_boundaries(engine, FIXTURES / "boundaries", layers)
    ingest_ppr(engine, CSV.read_bytes(), "file:///fixtures/ppr_carlow_2025.csv")

    def replay(request: httpx.Request) -> httpx.Response:
        key = f"{request.url.params['q']}|{request.url.params['viewbox']}"
        return httpx.Response(200, json=RECORDED["responses"].get(key, []))

    client = httpx.Client(transport=httpx.MockTransport(replay))
    geocode_properties(engine, "http://nominatim.test", client=client)
    return engine


def _stat(conn: sa.Connection, area: str, kind: str, start: str, segment: str) -> sa.Row:
    return conn.execute(
        sa.text(
            "SELECT st.n_sales, st.median_price, st.suppressed, st.provisional "
            "FROM area_stats st JOIN area a ON a.id = st.area_id "
            "WHERE a.kind = 'county' AND a.code = :area AND st.period_kind = CAST(:kind AS "
            "period_kind) AND st.period_start = :start AND st.segment = CAST(:seg AS segment)"
        ),
        {"area": area, "kind": kind, "start": start, "seg": segment},
    ).one()


def test_area_stats(loaded: sa.Engine) -> None:
    summary = aggregate(loaded)
    assert summary["max_sale_date"] == "2025-12-17"
    assert summary["provisional_from"] == "2025-11-01"
    with loaded.connect() as conn:
        year = _stat(conn, "carlow", "year", "2025-01-01", "all")
        rolling = _stat(conn, "carlow", "rolling_12m", "2025-12-01", "all")
        new = _stat(conn, "carlow", "year", "2025-01-01", "new")
        september = _stat(conn, "carlow", "month", "2025-09-01", "all")
        december = _stat(conn, "carlow", "month", "2025-12-01", "all")
    everything = _prices()
    assert (year.n_sales, year.median_price) == (30, statistics.median(everything))
    assert year.provisional and not year.suppressed
    assert rolling.n_sales == 30 and rolling.provisional
    # Three new builds: the count is shown, the prices are not.
    assert (new.n_sales, new.median_price, new.suppressed) == (3, None, True)
    assert (september.n_sales, september.provisional) == (4, False)
    assert (december.n_sales, december.provisional) == (4, True)


def test_price_hexes_use_precise_points_only(loaded: sa.Engine) -> None:
    aggregate(loaded)
    with loaded.connect() as conn:
        by_res = dict(
            conn.execute(
                sa.text(
                    "SELECT resolution, sum(n) FROM price_hex "
                    "WHERE \"window\" = 'rolling_36m' AND segment = 'all' GROUP BY 1"
                )
            ).all()
        )
        precise = conn.execute(
            sa.text(
                "SELECT count(*) FROM sale s JOIN property p ON p.id = s.property_id "
                "WHERE p.geocode_confidence IN ('exact', 'street')"
            )
        ).scalar_one()
        valid = conn.execute(sa.text("SELECT bool_and(ST_IsValid(geom)) FROM price_hex")).scalar()
    assert precise > 0
    assert by_res == {6: precise, 7: precise, 8: precise}
    assert valid


def test_hover_summaries(loaded: sa.Engine) -> None:
    aggregate(loaded)
    with loaded.connect() as conn:
        count = conn.execute(sa.text("SELECT count(*) FROM property_summary")).scalar_one()
        payload = conn.execute(
            sa.text(
                "SELECT ps.payload FROM property_summary ps JOIN property p "
                "ON p.id = ps.property_id WHERE p.address_display = :a"
            ),
            {"a": "143 Cois Dara, Chapelstown, Carlow"},
        ).scalar_one()
        properties = conn.execute(sa.text("SELECT count(*) FROM property")).scalar_one()
    assert count == properties
    assert payload["latestSale"]["priceEur"] == 299559
    assert payload["latestSale"]["flags"]["vatExclusive"] is True
    assert payload["previousSales"] == []
    # The most local area with enough sales: Carlow town (CSO settlement). Two of the 30
    # sales (Old Leighlin, and one on the Castledermot Road) are outside its boundary.
    assert (payload["area"]["kind"], payload["area"]["name"]) == ("settlement", "Carlow")
    assert payload["area"]["n"] == 28
    assert payload["dataVersion"].startswith("2025-12-17.r")


def test_a_failed_run_leaves_the_previous_tables_whole(
    loaded: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    aggregate(loaded)
    count = (
        "SELECT (SELECT count(*) FROM area_stats), (SELECT count(*) FROM price_hex), "
        "(SELECT count(*) FROM property_summary)"
    )
    with loaded.connect() as conn:
        before = conn.execute(sa.text(count)).one()
    assert all(before)

    def fail_halfway(conn: sa.Connection, *args: object) -> int:
        # By now area stats and hexes are rebuilt and the summaries are deleted.
        conn.execute(sa.text("DELETE FROM property_summary"))
        raise RuntimeError("disk full")

    monkeypatch.setattr(aggregate_module, "summaries", fail_halfway)
    with pytest.raises(RuntimeError):
        aggregate(loaded)
    with loaded.connect() as conn:
        assert conn.execute(sa.text(count)).one() == before
        runs = conn.execute(
            sa.text("SELECT status::text FROM ingest_run WHERE kind = 'aggregate' ORDER BY id")
        ).scalars()
        assert list(runs) == ["succeeded", "failed"]
