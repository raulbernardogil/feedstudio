"""Scheduler: starts the pipeline of every source whose next run is due.

Run as a process (Docker):   python -m feedstudio.scheduler
or embedded in the API process (local development, FEEDSTUDIO_SCHEDULER_MODE=embedded).

Each tick claims due sources with ``SELECT ... FOR UPDATE SKIP LOCKED`` on
PostgreSQL, so several scheduler processes never start the same run twice.
The next run is computed before the job is enqueued; if a pipeline is still
running for a source, that run is skipped (not queued twice).
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import select

from feedstudio.config import get_settings
from feedstudio.db import get_engine, session_scope
from feedstudio.jobs import get_runner
from feedstudio.models import ProcessingJob, Source
from feedstudio.scheduling import ScheduleConfig, next_run

log = logging.getLogger("feedstudio.scheduler")


def tick(now: datetime | None = None) -> list[int]:
    """Enqueue due pipelines. Returns the created job ids."""
    from feedstudio.services.automation import start_pipeline

    now = now or datetime.now(timezone.utc)
    created: list[int] = []
    with session_scope() as s:
        stmt = select(Source).where(Source.schedule != "manual", Source.next_run_at.is_not(None), Source.next_run_at <= now)
        if get_engine().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        for source in s.execute(stmt).scalars().all():
            config = ScheduleConfig.model_validate(source.schedule_config or {})
            source.next_run_at = next_run(config, now)
            running = s.scalar(select(ProcessingJob.id).where(
                ProcessingJob.source_id == source.id, ProcessingJob.kind.in_(("pipeline", "import")),
                ProcessingJob.status.in_(("queued", "running"))))
            if running:
                log.warning("source %s: previous run %s still active, skipping", source.id, running)
                continue
            source.last_scheduled_run_at = now
            created.append(start_pipeline(s, source, trigger="schedule").id)
    for job_id in created:
        get_runner().enqueue(job_id)
    return created


def run_forever(stop: threading.Event | None = None) -> None:
    interval = get_settings().scheduler_interval_seconds
    log.info("scheduler started (every %ss)", interval)
    while not (stop and stop.is_set()):
        try:
            jobs = tick()
            if jobs:
                log.info("scheduled pipelines started: %s", jobs)
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("scheduler tick failed")
        if stop:
            stop.wait(interval)
        else:
            time.sleep(interval)


_thread: threading.Thread | None = None
_stop = threading.Event()


def start_embedded() -> None:
    global _thread
    if _thread is None or not _thread.is_alive():
        _stop.clear()
        _thread = threading.Thread(target=run_forever, args=(_stop,), name="feedstudio-scheduler", daemon=True)
        _thread.start()


def stop_embedded() -> None:
    _stop.set()


if __name__ == "__main__":
    from feedstudio.logging import configure_logging

    configure_logging()
    run_forever()
