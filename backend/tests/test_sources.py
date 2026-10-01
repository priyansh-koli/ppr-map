"""GET /sources: what the /sources page lists (D-016, D-055)."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app.config import REPO_CONFIG_DIR, get_settings
from app.services import sources as s


def test_lists_loaded_planned_and_ruled_out_sources(client: TestClient) -> None:
    res = client.get("/api/v1/sources")
    assert res.status_code == 200
    body = res.json()
    in_use = {x["key"]: x for x in body["inUse"]}
    planned = {x["key"] for x in body["planned"]}
    not_used = {x["key"]: x for x in body["notUsed"]}

    assert "Property Services Regulatory Authority" in in_use["ppr"]["attribution"]
    assert {"osm_extract", "gtfs", "tailte_boundaries"} <= in_use.keys()
    # Allowed but not loaded, or with a licence still to confirm: never shown as in use.
    assert {"planning", "epa_noise_round4"} <= planned
    assert not planned & in_use.keys()
    assert all(x["attribution"] for x in in_use.values())
    assert not_used["daft"]["reason"]
    assert "opw_flood" in not_used


def test_an_unverified_source_has_no_check_date(client: TestClient) -> None:
    body = client.get("/api/v1/sources").json()
    noise = next(x for x in body["planned"] if x["key"] == "epa_noise_round4")
    assert noise["checkedOn"] is None
    assert next(x for x in body["inUse"] if x["key"] == "ppr")["checkedOn"]


def test_a_broken_file_is_a_503(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = yaml.safe_load((REPO_CONFIG_DIR / "sources.yaml").read_text())
    del data["sources"]["ppr"]["licence"]
    (tmp_path / "sources.yaml").write_text(yaml.safe_dump(data))
    monkeypatch.setenv("PPR_CONFIG_DIR", str(tmp_path))
    get_settings.cache_clear()
    s.load_sources.cache_clear()
    try:
        assert client.get("/api/v1/sources").status_code == 503
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        s.load_sources.cache_clear()
