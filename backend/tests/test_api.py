from fastapi.testclient import TestClient

from app.main import create_app
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


def test_problem_json_keeps_headers(client: TestClient) -> None:
    res = client.post("/api/v1/health")
    assert res.status_code == 405
    assert res.headers["content-type"] == "application/problem+json"
    assert res.headers["allow"] == "GET"
    assert res.json()["title"] == "Method Not Allowed"


def test_unhandled_errors_are_problem_json() -> None:
    app = create_app()

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as c:
        res = c.get("/api/v1/boom")
    assert res.status_code == 500
    assert res.headers["content-type"] == "application/problem+json"
    assert res.json() == {"type": "about:blank", "title": "Internal Server Error", "status": 500}


def test_committed_openapi_schema_is_current() -> None:
    """The frontend's types are generated from frontend/openapi.json: run `make api-types`."""
    import json

    from tests.conftest import REPO_ROOT

    committed = json.loads((REPO_ROOT / "frontend" / "openapi.json").read_text())
    assert committed == json.loads(json.dumps(create_app().openapi())), "run `make api-types`"
