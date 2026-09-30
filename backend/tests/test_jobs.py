"""The scheduler's timetable and pipeline job queueing (D-051), without Redis."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import jobs
from app.config import get_settings

DUBLIN = ZoneInfo("Europe/Dublin")


def next_run(job_id: str, after: datetime) -> datetime:
    s = jobs.build_scheduler()
    job = next(j for j in s.get_jobs() if j.id == job_id)
    fire: datetime = job.trigger.get_next_fire_time(None, after)
    return fire


def test_timetable_in_irish_time() -> None:
    monday_noon = datetime(2026, 10, 5, 12, 0, tzinfo=DUBLIN)
    assert next_run("alerts-weekly", monday_noon) == datetime(2026, 10, 12, 7, 0, tzinfo=DUBLIN)
    assert next_run("housekeeping", monday_noon) == datetime(2026, 10, 6, 3, 30, tzinfo=DUBLIN)
    just_after = datetime(2026, 10, 5, 12, 1, tzinfo=DUBLIN)
    assert next_run("alerts-on-update", just_after) == datetime(2026, 10, 5, 12, 15, tzinfo=DUBLIN)


def test_monthly_pipeline_only_when_switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "pipeline-monthly" not in {j.id for j in jobs.build_scheduler().get_jobs()}
    monkeypatch.setattr(get_settings(), "schedule_pipeline", True)
    assert "pipeline-monthly" in {j.id for j in jobs.build_scheduler().get_jobs()}


def test_unknown_pipeline_steps_are_refused() -> None:
    with pytest.raises(ValueError, match="unknown pipeline step"):
        jobs.enqueue_pipeline("drop-tables", None)
