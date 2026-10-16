"""Background job execution.

Port: ``JobRunner.enqueue(job_id)``. Adapters:
- ``ThreadJobRunner``: in-process thread pool. Used for local development on
  any OS (including Windows) and tests.
- ``RqJobRunner``: Redis Queue workers (Docker / Linux deployments). Workers
  run ``feedstudio.jobs.run_job``.

Job state lives in the database (``processing_jobs``), so the UI polls the API
and the work never depends on a browser staying open.
"""

from __future__ import annotations

import logging
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Protocol

from feedstudio.db import session_scope
from feedstudio.models import ProcessingJob, utcnow

log = logging.getLogger("feedstudio.jobs")

Handler = Callable[[int], dict]
HANDLERS: dict[str, Handler] = {}


class JobFailed(Exception):
    def __init__(self, message: str, code: str = "job_failed", detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail or {}


def handler(kind: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[kind] = fn
        return fn

    return deco


def report(job_id: int, progress: float | None = None, message: str | None = None) -> None:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        if job is None:
            return
        if progress is not None:
            job.progress = round(min(1.0, max(0.0, progress)), 4)
        if message:
            job.message = message
            job.events = [*(job.events or []), {"at": utcnow().isoformat(), "message": message, "progress": job.progress}][-200:]


def run_job(job_id: int) -> None:
    from feedstudio import services  # noqa: F401  (registers handlers)

    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        if job is None or job.status not in ("queued",):
            return
        job.status = "running"
        job.started_at = utcnow()
        kind = job.kind
    report(job_id, 0.0, "Trabajo iniciado")
    try:
        result = HANDLERS[kind](job_id)
    except JobFailed as exc:
        _finish(job_id, "failed", error={"code": exc.code, "message": exc.message, **exc.detail})
    except Exception as exc:  # noqa: BLE001 - job boundary
        log.exception("job %s crashed", job_id)
        _finish(job_id, "failed", error={"code": "internal_error", "message": str(exc)[:500],
                                         "trace": traceback.format_exc()[-2000:]})
    else:
        _finish(job_id, "succeeded", result=result)


def _finish(job_id: int, status: str, result: dict | None = None, error: dict | None = None) -> None:
    with session_scope() as s:
        job = s.get(ProcessingJob, job_id)
        if job is None:
            return
        job.status = status
        job.finished_at = utcnow()
        job.result = result
        job.error = error
        if status == "succeeded":
            job.progress = 1.0
        msg = "Trabajo completado" if status == "succeeded" else f"Error: {(error or {}).get('message', '')}"
        job.message = msg
        job.events = [*(job.events or []), {"at": utcnow().isoformat(), "message": msg, "progress": job.progress}][-200:]


class JobRunner(Protocol):
    def enqueue(self, job_id: int) -> None: ...


class ThreadJobRunner:
    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="feedstudio-job")
        self.futures: dict[int, Future] = {}

    def enqueue(self, job_id: int) -> None:
        self.futures[job_id] = self._pool.submit(run_job, job_id)

    def wait(self, job_id: int, timeout: float = 300) -> None:
        future = self.futures.get(job_id)
        if future:
            future.result(timeout=timeout)


class SyncJobRunner:
    """Runs jobs inline; used by tests for determinism."""

    def enqueue(self, job_id: int) -> None:
        run_job(job_id)


class RqJobRunner:
    def __init__(self, redis_url: str):
        from redis import Redis
        from rq import Queue

        self._queue = Queue("feedstudio", connection=Redis.from_url(redis_url), default_timeout=3600)

    def enqueue(self, job_id: int) -> None:
        self._queue.enqueue("feedstudio.jobs.run_job", job_id, job_timeout=3600)


_runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        from feedstudio.config import get_settings

        settings = get_settings()
        _runner = RqJobRunner(settings.redis_url) if settings.job_backend == "rq" else ThreadJobRunner()
    return _runner


def set_runner(runner: JobRunner) -> None:
    global _runner
    _runner = runner
