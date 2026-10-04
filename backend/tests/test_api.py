import pytest
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
    client.get("/api/v1/health")  # any API response sets the CSRF cookie
    res = client.post("/api/v1/health", headers={"X-CSRF-Token": client.cookies["ppr_csrf"]})
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


def test_access_log_keeps_no_ip_or_query() -> None:
    """P2 #44: uvicorn logged every client IP and full query string."""
    import logging

    from app.logs import PrivateAccessLog

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("203.0.113.9:51234", "GET", "/api/v1/search?q=me%40example.ie", "1.1", 200),
        None,
    )
    assert PrivateAccessLog().filter(record)
    assert record.getMessage() == '- - "GET /api/v1/search HTTP/1.1" 200'
    create_app()
    assert any(isinstance(f, PrivateAccessLog) for f in logging.getLogger("uvicorn.access").filters)


def test_a_failed_email_is_logged_without_the_address(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """P2 #44: email addresses went into the app's logs."""
    import asyncio
    import smtplib

    from app.services import email as mail

    def down(*_: object, **__: object) -> None:
        raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP", down)
    asyncio.run(mail.SmtpMailer().send(mail.password_changed("niamh@example.ie", "Niamh")))
    assert "could not send" in caplog.text and "niamh@example.ie" not in caplog.text
