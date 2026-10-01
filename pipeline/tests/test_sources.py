from pathlib import Path

import pytest
from typer.testing import CliRunner

from ppr_pipeline.cli import app
from ppr_pipeline.sources import REPO_CONFIG_DIR, load_sources

runner = CliRunner()


def test_sources_file_is_valid() -> None:
    sources = load_sources()
    assert sources["ppr"].use and sources["ppr"].verified


def test_blocked_sources_stay_blocked() -> None:
    """D-010 / D-016 / D-023: these must never be switched on silently."""
    sources = load_sources()
    for key in ("opw_flood", "daft", "landdirect", "propertymap_ie", "opw_state_property"):
        assert sources[key].use is False, key
        assert sources[key].loaded is False, key


def test_unverified_sources_are_not_shown_as_loaded() -> None:
    """The /sources page lists loaded sources as in use (D-055); a licence still to confirm
    must not appear there."""
    for key, src in load_sources().items():
        if src.loaded:
            assert src.verified, key


def test_planning_never_requests_applicant_fields() -> None:
    planning = load_sources()["planning"]
    assert planning.out_fields
    assert not [f for f in planning.out_fields if "applicant" in f.lower()]


def test_cli_lists_sources_and_refuses_blocked_ones() -> None:
    listed = runner.invoke(app, ["sources"])
    assert listed.exit_code == 0 and "ppr" in listed.output and "daft" not in listed.output

    refused = runner.invoke(app, ["ingest", "daft"])
    assert refused.exit_code == 1
    assert "Refusing" in refused.output


def test_unimplemented_steps_exit_with_code_2() -> None:
    result = runner.invoke(app, ["ingest", "planning"])
    assert result.exit_code == 2


def test_config_dir_can_be_set_for_installed_packages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Docker image installs the pipeline into site-packages and sets PPR_CONFIG_DIR."""
    (tmp_path / "sources.yaml").write_text((REPO_CONFIG_DIR / "sources.yaml").read_text())
    monkeypatch.setenv("PPR_CONFIG_DIR", str(tmp_path))
    assert "ppr" in load_sources()
    monkeypatch.setenv("PPR_CONFIG_DIR", str(tmp_path / "missing"))
    with pytest.raises(FileNotFoundError):
        load_sources()
