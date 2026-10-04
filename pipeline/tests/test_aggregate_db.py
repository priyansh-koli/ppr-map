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


def test_hex_windows_are_the_area_windows(loaded: sa.Engine) -> None:
    """ "Last 12 months" is the 12 whole months ending with the latest one, as in area_stats;
    the hexes took in a 13th (P1 #16)."""
    with loaded.begin() as conn:
        # December 2024: 12 months before the register's latest month, December 2025.
        conn.execute(
            sa.text(
                "UPDATE sale SET sale_date = '2024-12-15' WHERE id = ("
                "SELECT s.id FROM sale s JOIN property p ON p.id = s.property_id "
                "WHERE p.geocode_confidence IN ('exact', 'street') ORDER BY s.id LIMIT 1)"
            )
        )
    aggregate(loaded)
    with loaded.connect() as conn:
        hexes = dict(
            conn.execute(
                sa.text(
                    'SELECT "window"::text, sum(n) FROM price_hex '
                    "WHERE segment = 'all' AND resolution = 8 GROUP BY 1"
                )
            ).all()
        )
        rolling = _stat(conn, "carlow", "rolling_12m", "2025-12-01", "all")
    assert hexes["rolling_36m"] - hexes["rolling_12m"] == 1
    assert rolling.n_sales == 29


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


COPY_SALE = """
INSERT INTO sale (property_id, source_row_hash, raw_date, raw_address, raw_county, raw_eircode,
                  raw_price, raw_nfmp, raw_vat, raw_description, raw_size, sale_date, price_eur,
                  not_full_market_price, vat_exclusive, is_new, size_band, is_possible_duplicate,
                  first_seen_run_id, last_seen_run_id)
SELECT s.property_id, :hash, raw_date, raw_address, raw_county, raw_eircode, raw_price,
       raw_nfmp, raw_vat, raw_description, raw_size, :sale_date, :price, :nfmp, vat_exclusive,
       is_new, size_band, :repeat, first_seen_run_id, last_seen_run_id
FROM sale s JOIN property p ON p.id = s.property_id WHERE p.address_display = :address
ORDER BY s.id LIMIT 1
"""


def _summary(conn: sa.Connection, address: str) -> dict[str, object]:
    payload: dict[str, object] = conn.execute(
        sa.text(
            "SELECT ps.payload FROM property_summary ps JOIN property p "
            "ON p.id = ps.property_id WHERE p.address_display = :a"
        ),
        {"a": address},
    ).scalar_one()
    return payload


def test_earlier_sales_carry_flags_and_leave_out_repeat_filings(loaded: sa.Engine) -> None:
    """P2 #46: the hover card's "Earlier" listed a refiled sale twice and gave no hint that a
    price was not a market one."""
    address = "143 Cois Dara, Chapelstown, Carlow"
    with loaded.begin() as conn:
        for n, repeat in enumerate((False, True)):
            conn.execute(
                sa.text(COPY_SALE),
                {
                    "hash": f"{n:064d}",
                    "sale_date": "2015-05-01",
                    "price": 150000,
                    "nfmp": True,
                    "repeat": repeat,
                    "address": address,
                },
            )
    aggregate(loaded)
    with loaded.connect() as conn:
        payload = _summary(conn, address)
    assert payload["previousSales"] == [
        {
            "date": "2015-05-01",
            "priceEur": 150000,
            "flags": {"notFullMarketPrice": True, "vatExclusive": True, "bulk": False},
        }
    ]


def test_a_hidden_property_still_counts_in_area_stats(loaded: sa.Engine) -> None:
    """P2 #47: D-052 keeps a hidden home's sales in area figures (the register is public);
    the aggregate dropped them."""
    with loaded.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE property SET is_suppressed = true "
                "WHERE address_display = '143 Cois Dara, Chapelstown, Carlow'"
            )
        )
    aggregate(loaded)
    with loaded.connect() as conn:
        year = _stat(conn, "carlow", "year", "2025-01-01", "all")
        hidden_summaries = conn.execute(
            sa.text(
                "SELECT count(*) FROM property_summary ps JOIN property p "
                "ON p.id = ps.property_id WHERE p.is_suppressed"
            )
        ).scalar_one()
    assert year.n_sales == 30
    assert hidden_summaries == 0  # the property itself stays hidden
