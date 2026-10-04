"""Area pages on the real Carlow fixtures (D-049). In the fixture Ireland is only County
Carlow, so the national figures must equal the county's."""

from collections.abc import AsyncIterator, Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.redis_client import get_redis
from tests.conftest import make_api

pytestmark = pytest.mark.db


async def no_cache() -> AsyncIterator[None]:
    yield None


@pytest.fixture
def api(carlow_db: sa.Engine) -> Iterator[TestClient]:
    with make_api({get_redis: no_cache}) as client:
        yield client


def slug_of(db: sa.Engine, kind: str) -> str:
    with db.connect() as conn:
        return str(
            conn.execute(
                sa.text("SELECT slug FROM area WHERE kind = CAST(:k AS area_kind) LIMIT 1"),
                {"k": kind},
            ).scalar_one()
        )


def test_county_page(api: TestClient) -> None:
    body = api.get("/api/v1/areas/carlow").json()
    assert (body["kind"], body["name"]) == ("county", "Carlow")
    assert body["parents"] == [{"kind": "country", "name": "Ireland", "slug": "ireland"}]
    # The fixture's register ends on 17 Dec 2025, so Nov and Dec are provisional and the latest
    # complete window is the 12 months to October.
    h = body["headline"]
    assert (h["windowStart"], h["windowEnd"]) == ("2024-11-01", "2025-10-31")
    assert h["n"] > 5 and h["median"] is not None
    assert body["national"]["median"] == h["median"]  # Ireland is Carlow here
    assert body["childrenKind"] == "settlement"
    assert body["children"][0]["slug"] == "carlow-1f4955"
    assert body["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert "rolling_12m" in body["periodKinds"]
    assert body["pointBased"] is False


def test_small_area_uses_years_and_its_eds_deprivation(
    api: TestClient, carlow_db: sa.Engine
) -> None:
    sa_slug = slug_of(carlow_db, "small_area")
    body = api.get(f"/api/v1/areas/{sa_slug}").json()
    assert body["pointBased"] is True
    assert [p["kind"] for p in body["parents"]] == ["electoral_division", "county", "country"]
    assert body["periodKinds"] == ["quarter", "year"]
    if body["headline"]:
        assert body["headline"]["windowStart"].endswith("-01-01")
    labels = [a["label"] for a in body["attributes"]]
    assert labels and all("its Electoral Division" in label for label in labels)
    assert (
        api.get(f"/api/v1/areas/{sa_slug}/stats", params={"periodKind": "rolling_12m"}).status_code
        == 422
    )
    assert api.get(f"/api/v1/areas/{sa_slug}/stats").json()["periodKind"] == "year"


def test_stats_series_come_with_the_national_one(api: TestClient) -> None:
    body = api.get("/api/v1/areas/carlow/stats", params={"periodKind": "month"}).json()
    assert body["points"] and len(body["points"]) == len(body["national"])
    assert body["points"][-1]["provisional"] is True
    small = [p for p in body["points"] if p["n"] < 5]
    assert all(p["suppressed"] and p["median"] is None for p in small)
    new = api.get("/api/v1/areas/carlow/stats", params={"segment": "new"}).json()
    assert new["segment"] == "new"


def test_distribution_counts_the_headline_sales(api: TestClient) -> None:
    head = api.get("/api/v1/areas/carlow").json()["headline"]
    dist = api.get("/api/v1/areas/carlow/distribution").json()
    assert dist["n"] == head["n"]
    assert (dist["windowStart"], dist["windowEnd"]) == (head["windowStart"], head["windowEnd"])
    shown = [b["n"] for b in dist["bins"]]
    assert all(n is None or n == 0 or n >= 5 for n in shown)  # small bands are not given
    assert sum(n for n in shown if n) <= dist["n"]
    hidden = dist["n"] - sum(n for n in shown if n)
    assert hidden == 0 or (hidden >= 5 and shown.count(None) >= 2)
    assert abs(sum(dist["nationalShare"]) - 1) < 0.001
    assert dist["bins"][-1]["toEur"] is None


def test_unknown_and_malformed_slugs(api: TestClient) -> None:
    assert api.get("/api/v1/areas/no-such-place").status_code == 404
    assert api.get("/api/v1/areas/Bad%20Slug").status_code == 422


def test_rolling_windows_start_when_the_register_has_twelve_months() -> None:
    from datetime import date

    from app.api.v1.areas import _points

    row = (date(2010, 6, 1), 10, None, None, None, False, False)
    later = (date(2010, 12, 1), 10, None, None, None, False, False)
    assert [p.period_start for p in _points([row, later], "rolling_12m")] == [date(2010, 12, 1)]
    assert len(_points([row, later], "month")) == 2
