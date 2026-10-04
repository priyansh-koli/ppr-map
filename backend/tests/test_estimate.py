"""The price estimate, comparable sales and the area's CSO index (D-020, D-053), on the
real Carlow fixtures with a small made-up index: the fixture register has no CSO data."""

import math
from collections.abc import AsyncIterator, Iterator
from datetime import date

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.models.data import IngestRun
from app.models.enums import IngestKind, IngestStatus
from app.redis_client import get_redis
from tests.conftest import make_api, property_id

pytestmark = pytest.mark.db

POLLERTON = "178 Pollerton Road, Carlow"  # one plain market sale, placed on its street


async def no_cache() -> AsyncIterator[None]:
    yield None


def month(i: int) -> date:
    return date(2024 + i // 12, i % 12 + 1, 1)


@pytest.fixture
def db(carlow_db: sa.Engine) -> Iterator[sa.Engine]:
    """South-East houses rising 1% a month from Jan 2024 to Jul 2026, and a calibration,
    recorded as a benchmarks run as the pipeline does (area pages cache on it)."""
    with carlow_db.begin() as conn:
        conn.execute(
            sa.insert(IngestRun).values(kind=IngestKind.BENCHMARKS, status=IngestStatus.SUCCEEDED)
        )
        conn.execute(sa.text("DELETE FROM benchmark_series"))
        conn.execute(sa.text("DELETE FROM estimate_calibration"))
        conn.execute(
            sa.text(
                "INSERT INTO benchmark_series (source, series_key, period, value, unit, as_of) "
                "VALUES ('cso_rppi', 'rppi:24', :p, :v, 'index', '2026-09-30')"
            ),
            [{"p": month(i), "v": round(100 * 1.01**i, 4)} for i in range(31)],
        )
        conn.execute(
            sa.text(
                "INSERT INTO estimate_calibration (series_key, gap_band, n, p10, p50, p90) VALUES "
                "('rppi:24', '0-3y', 40, -0.5, 0, 0.5), ('all', '0-3y', 5000, -0.1, 0.02, 0.2)"
            )
        )
    yield carlow_db


@pytest.fixture
def api(db: sa.Engine) -> Iterator[TestClient]:
    with make_api({get_redis: no_cache}) as client:
        yield client


def test_estimate_moves_the_last_market_sale_by_the_index(api: TestClient, db: sa.Engine) -> None:
    pid = property_id(db, POLLERTON)
    with db.connect() as conn:
        sold_on, price = conn.execute(
            sa.text(
                "SELECT s.sale_date, s.price_eur FROM sale s JOIN property p "
                "ON p.id = s.property_id WHERE p.public_id = :p"
            ),
            {"p": pid},
        ).one()
    body = api.get(f"/api/v1/properties/{pid}/estimate").json()
    assert body["eligible"] is True
    months = (2026 - sold_on.year) * 12 + 7 - sold_on.month
    mid = float(price) * 1.01**months
    assert body["midEur"] == round(mid / 1000) * 1000
    assert body["basedOn"] == {"date": sold_on.isoformat(), "priceEur": float(price)}
    assert body["series"]["label"] == "South-East - houses"
    assert body["indexMonth"] == "2026-07-01"
    # The series has only 40 pairs (fewer than 150), so Ireland's pooled range is used.
    cal = body["calibration"]
    assert cal["pooled"] is True and cal["pairs"] == 5000
    assert body["lowEur"] == round(mid * math.exp(-0.1) / 1000) * 1000
    assert body["highEur"] == round(mid * math.exp(0.2) / 1000) * 1000
    assert cal["lowPct"] == -9.5 and cal["highPct"] == 22.1
    assert "not a valuation" in body["method"]


def test_no_estimate_without_a_precise_location_or_a_market_sale(
    api: TestClient, db: sa.Engine
) -> None:
    with db.connect() as conn:
        town_level = conn.execute(
            sa.text("SELECT public_id FROM property WHERE geocode_confidence = 'locality' LIMIT 1")
        ).scalar_one()
        vat_only = conn.execute(
            sa.text(
                "SELECT p.public_id FROM property p JOIN sale s ON s.property_id = p.id "
                "WHERE p.geocode_confidence IN ('exact', 'street') GROUP BY p.public_id "
                "HAVING bool_and(s.vat_exclusive) LIMIT 1"
            )
        ).scalar_one_or_none()
    body = api.get(f"/api/v1/properties/{town_level}/estimate").json()
    assert body["eligible"] is False and "house or street" in body["reason"]
    if vat_only:
        body = api.get(f"/api/v1/properties/{vat_only}/estimate").json()
        assert body["eligible"] is False and "VAT" in body["reason"]
    assert api.get("/api/v1/properties/nope/estimate").status_code == 404


def test_comparables(api: TestClient, db: sa.Engine) -> None:
    pid = property_id(db, POLLERTON)
    body = api.get(f"/api/v1/properties/{pid}/comparables", params={"radiusM": 2000}).json()
    assert body["available"] is True and body["total"] >= len(body["items"]) > 0
    items = body["items"]
    assert all(i["confidence"] in ("exact", "street") and i["id"] != pid for i in items)
    assert all(i["distanceM"] <= 2000 for i in items)
    ranked = [(not i["sameStreet"], i["distanceM"]) for i in items]
    assert ranked == sorted(ranked)  # same street first, then nearest
    assert body["medianEur"] is not None
    with db.connect() as conn:
        town_level = conn.execute(
            sa.text("SELECT public_id FROM property WHERE geocode_confidence = 'locality' LIMIT 1")
        ).scalar_one()
    far = api.get(f"/api/v1/properties/{town_level}/comparables").json()
    assert far["available"] is False and far["items"] == []
    assert (
        api.get(f"/api/v1/properties/{pid}/comparables", params={"radiusM": 5}).status_code == 422
    )


def test_comparables_median_needs_five_sales(api: TestClient, db: sa.Engine) -> None:
    """The median is of the sales filed with VAT, so it can be of fewer than `total`; under
    5 of them it is withheld, like every other aggregate (P1 #12)."""
    pid = property_id(db, POLLERTON)
    seen = set()
    for months, radius in ((6, 500), (24, 500), (24, 2000)):
        params = {"radiusM": radius, "months": months}
        c = api.get(f"/api/v1/properties/{pid}/comparables", params=params).json()
        assert c["medianN"] <= c["total"]
        assert (c["medianEur"] is None) == (c["medianN"] < 5), c
        seen.add(c["medianN"] >= 5)
    assert seen == {True, False}  # both sides of the threshold are exercised


def test_a_town_or_county_part_is_not_a_street(api: TestClient, db: sa.Engine) -> None:
    """In "…, carlow, co carlow" the town is not the last part; it named no street, yet every
    home in Carlow came out "on the same street" (P1 #15)."""
    pid = property_id(db, POLLERTON)
    url, params = f"/api/v1/properties/{pid}/comparables", {"radiusM": 2000, "limit": 50}
    before = api.get(url, params=params).json()["items"]
    same = {i["id"] for i in before if i["sameStreet"]}
    other = next(i["id"] for i in before if not i["sameStreet"])
    ids = [pid, other]
    with db.begin() as conn:
        saved = conn.execute(
            sa.text("SELECT id, address_normalised FROM property WHERE public_id = ANY(:ids)"),
            {"ids": ids},
        ).all()
        conn.execute(
            sa.text(
                "UPDATE property SET address_normalised = address_normalised || ', co carlow' "
                "WHERE public_id = ANY(:ids)"
            ),
            {"ids": ids},
        )
    try:
        after = {i["id"]: i["sameStreet"] for i in api.get(url, params=params).json()["items"]}
        assert after[other] is False
        assert {i for i, s in after.items() if s} == same
    finally:
        with db.begin() as conn:
            for row_id, address in saved:
                conn.execute(
                    sa.text("UPDATE property SET address_normalised = :a WHERE id = :i"),
                    {"a": address, "i": row_id},
                )
    with db.connect() as conn:
        parts = conn.execute(
            sa.text(
                "SELECT address_street_parts('8 annesley park, ranelagh, dublin 6'), "
                "address_street_parts('1 main st, sandyford dublin 18, dublin'), "
                "address_street_parts('2 the green, kilkee, co. clare, ireland'), "
                "address_street_parts('5 oak road, dublin 6w, dublin')"
            )
        ).one()
    assert list(parts) == [
        ["annesley park", "ranelagh"],  # ranelagh is left out by the place names nearby
        ["main st", "sandyford"],
        ["the green", "kilkee"],
        ["oak road"],
    ]


def test_area_pages_show_their_regions_index(api: TestClient) -> None:
    # test_areas.py may have cached Carlow's page before the index was loaded: the new
    # benchmarks run must replace it.
    index = api.get("/api/v1/areas/carlow").json()["priceIndex"]
    assert index["label"] == "South-East - houses" and index["month"] == "2026-07-01"
    assert index["change12mPct"] == round((1.01**12 - 1) * 100, 1)
