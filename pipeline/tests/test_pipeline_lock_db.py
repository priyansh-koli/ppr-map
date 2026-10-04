"""One pipeline step at a time (P1 #22). Needs TEST_DATABASE_URL."""

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from ppr_pipeline import cli
from ppr_pipeline.db import PipelineBusy, pipeline_lock

pytestmark = pytest.mark.db


def test_a_second_run_is_refused_while_one_holds_the_lock(
    engine: sa.Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    monkeypatch.setattr(cli, "rebuild_aggregates", lambda *_, **__: called.append("x") or {})
    with pipeline_lock(engine):
        with pytest.raises(PipelineBusy), pipeline_lock(engine):
            pass  # pragma: no cover
        # From another process, `ppr aggregate` (or the worker) stops before touching data.
        result = CliRunner().invoke(cli.app, ["aggregate"])
        assert result.exit_code == 1 and "another pipeline step is running" in result.output
        assert called == []
    # Released: the next run goes ahead, and frees the lock again.
    assert CliRunner().invoke(cli.app, ["aggregate"]).exit_code == 0
    assert called == ["x"]
    with pipeline_lock(engine):
        pass
