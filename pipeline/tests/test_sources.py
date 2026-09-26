from typer.testing import CliRunner

from ppr_pipeline.cli import app
from ppr_pipeline.sources import load_sources

runner = CliRunner()


def test_sources_file_is_valid() -> None:
    sources = load_sources()
    assert sources["ppr"].use and sources["ppr"].verified


def test_blocked_sources_stay_blocked() -> None:
    """D-010 / D-016 / D-023: these must never be switched on silently."""
    sources = load_sources()
    for key in ("opw_flood", "daft", "landdirect", "propertymap_ie", "opw_state_property"):
        assert sources[key].use is False, key


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
    result = runner.invoke(app, ["geocode"])
    assert result.exit_code == 2
