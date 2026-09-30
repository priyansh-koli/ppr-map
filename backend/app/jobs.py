"""Background jobs and the scheduler that queues them (D-007, D-051).

- RQ workers (`rq worker pipeline default`) run the jobs: long pipeline steps on the
  `pipeline` queue, short ones (alerts, housekeeping) on `default`.
- One scheduler process (`python -m app.cli scheduler`) only queues jobs on a timetable, in
  Irish time, so a slow job never delays the timetable:
  - every 15 minutes: alerts for searches set to "on each data update" (cheap when nothing
    is due);
  - Mondays 07:00: weekly alerts;
  - daily 03:30: housekeeping (purge-deleted);
  - the 2nd of each month at 02:00: the monthly pipeline, only with SCHEDULE_PIPELINE=true.
- Admins queue pipeline steps from /admin (the job is the pipeline's `ppr_pipeline.jobs.run`,
  queued by name, so the API does not import the pipeline).
"""

import asyncio
import logging
from functools import lru_cache
from typing import Any

from redis import Redis
from rq import Queue
from rq.job import Job

from app.config import get_settings

log = logging.getLogger(__name__)
TIMEZONE = "Europe/Dublin"
PIPELINE_STEPS = ("ppr", "gazetteer", "geocode", "enrich", "aggregate", "monthly")
PIPELINE_TIMEOUT_S = 6 * 3600


@lru_cache
def connection() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def queue(name: str) -> Queue:
    return Queue(name, connection=connection())


# --- jobs (run by the worker) -------------------------------------------------------------


def send_alerts_job(frequency: str) -> dict[str, int]:
    from app.db import get_engine, get_sessionmaker
    from app.services import alerts
    from app.services.email import SmtpMailer

    async def go() -> alerts.Result:
        # A job runs in a fresh event loop: the async engine must be made in it.
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()
        try:
            async with get_sessionmaker()() as session:
                return await alerts.send_alerts(session, SmtpMailer(), frequency)
        finally:
            await get_engine().dispose()

    return vars(asyncio.run(go()))


def housekeeping_job() -> dict[str, int]:
    from app.services.housekeeping import purge_expired

    return purge_expired()


# --- queueing -----------------------------------------------------------------------------


def enqueue_pipeline(step: str, triggered_by: str | None) -> Job:
    if step not in PIPELINE_STEPS:
        raise ValueError(f"unknown pipeline step {step!r}")
    return queue("pipeline").enqueue(
        "ppr_pipeline.jobs.run",
        step,
        triggered_by,
        job_timeout=PIPELINE_TIMEOUT_S,
        result_ttl=7 * 24 * 3600,
        failure_ttl=30 * 24 * 3600,
        description=f"pipeline: {step}",
    )


def job_status(job_id: str) -> dict[str, Any] | None:
    try:
        job = Job.fetch(job_id, connection=connection())
    except Exception:  # rq raises NoSuchJobError, or a Redis error if Redis is down
        return None
    return {
        "id": job.id,
        "status": str(job.get_status()),
        "description": job.description,
        "enqueuedAt": job.enqueued_at.isoformat() if job.enqueued_at else None,
        "endedAt": job.ended_at.isoformat() if job.ended_at else None,
    }


def recent_jobs(limit: int = 20) -> list[dict[str, Any]]:
    """Queued, running, finished and failed pipeline jobs, newest first."""
    q = queue("pipeline")
    ids: list[str] = [
        *q.job_ids,
        *q.started_job_registry.get_job_ids(),
        *q.finished_job_registry.get_job_ids(),
        *q.failed_job_registry.get_job_ids(),
    ]
    out = [s for i in dict.fromkeys(ids) if (s := job_status(i))]
    return sorted(out, key=lambda j: j["enqueuedAt"] or "", reverse=True)[:limit]


def build_scheduler() -> Any:
    """The timetable, not yet started."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    s = BlockingScheduler(timezone=TIMEZONE)
    default = queue("default")

    def put(func: str, *args: Any) -> None:
        default.enqueue(func, *args, result_ttl=24 * 3600, failure_ttl=7 * 24 * 3600)

    s.add_job(
        put,
        CronTrigger(minute="*/15", timezone=TIMEZONE),
        args=["app.jobs.send_alerts_job", "on_data_update"],
        id="alerts-on-update",
        coalesce=True,
    )
    s.add_job(
        put,
        CronTrigger(day_of_week="mon", hour=7, timezone=TIMEZONE),
        args=["app.jobs.send_alerts_job", "weekly"],
        id="alerts-weekly",
        coalesce=True,
    )
    s.add_job(
        put,
        CronTrigger(hour=3, minute=30, timezone=TIMEZONE),
        args=["app.jobs.housekeeping_job"],
        id="housekeeping",
        coalesce=True,
    )
    if get_settings().schedule_pipeline:
        s.add_job(
            enqueue_pipeline,
            CronTrigger(day=2, hour=2, timezone=TIMEZONE),
            args=["monthly", None],
            id="pipeline-monthly",
            coalesce=True,
        )
    return s


def scheduler() -> None:
    """Queue jobs on the timetable until stopped."""
    s = build_scheduler()
    log.info("scheduler: %s", ", ".join(j.id for j in s.get_jobs()))
    s.start()
