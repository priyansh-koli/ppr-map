import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.health import get_redis_ping
from app.db import get_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class FakeSession:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def execute(self, *_: Any, **__: Any) -> None:
        if self.fail:
            raise ConnectionError("database down")


def make_client(db_fail: bool = False, redis_fail: bool = False) -> TestClient:
    app = create_app()

    async def session_override() -> AsyncIterator[FakeSession]:
        yield FakeSession(fail=db_fail)

    async def redis_ping() -> None:
        if redis_fail:
            raise ConnectionError("redis down")

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_redis_ping] = lambda: redis_ping
    return TestClient(app)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with make_client() as c:
        yield c


@pytest.fixture
def database_url() -> str:
    """Tests marked `db` need TEST_DATABASE_URL pointing at a disposable PostGIS database."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set (start PostGIS with `make up`)")
    return url
