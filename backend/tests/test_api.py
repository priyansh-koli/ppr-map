from fastapi.testclient import TestClient

from tests.conftest import make_client


def test_health_ok(client: TestClient) -> None:
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "database": "ok", "redis": "ok"}


def test_health_reports_each_failing_dependency() -> None:
    with make_client(db_fail=True) as c:
        res = c.get("/api/v1/health")
    assert res.status_code == 503
    assert res.json() == {"status": "error", "database": "error", "redis": "ok"}

    with make_client(redis_fail=True) as c:
        res = c.get("/api/v1/health")
    assert res.status_code == 503
    assert res.json()["redis"] == "error"


def test_unknown_route_returns_problem_json(client: TestClient) -> None:
    res = client.get("/api/v1/does-not-exist")
    assert res.status_code == 404
    assert res.headers["content-type"] == "application/problem+json"
    assert res.json() == {"type": "about:blank", "title": "Not Found", "status": 404}


def test_openapi_is_served_under_v1(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/health" in spec["paths"]
    assert "Property Services Regulatory Authority" in spec["info"]["description"]
    assert client.get("/api/v1/docs").status_code == 200
