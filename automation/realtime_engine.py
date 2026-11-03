"""SONIC AI — Realtime Automation Engine.

A live job queue with:
- Per-job status tracking (queued / running / done / failed / cancelled)
- Per-job progress (0.0–1.0) + log lines
- Thread-safe job submission + state inspection
- Optional subscriber callbacks for live UI updates (e.g., web dashboard)
- SSE-friendly snapshot serialisation

Why this matters:
    - Without it, every action runs in isolation and there's no way for
      the UI to show *what SONIC is doing right now*.
    - The engine gives SONIC a heartbeat — a single source of truth for
      "jobs in flight" that both the UI and other modules can query.

Public surface (stable, opt-in):
    - ``RealtimeEngine()``              — manager
    - ``engine.submit(job_id, fn, *args, **kwargs)``
    - ``engine.status(job_id)``         — current status snapshot
    - ``engine.list_jobs()``            — all jobs
    - ``engine.subscribe(callback)``    — live update hook
    - ``engine.snapshot()``             — JSON-serialisable state
    - ``Job`` / ``JobStatus`` dataclasses

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("REALTIME_ENGINE")


# ═════════════════════════════════════════════════════════════════════════════
# Data classes
# ═════════════════════════════════════════════════════════════════════════════

class JobStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    name: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    log: list[str] = field(default_factory=list)
    error: str = ""
    result: Any = None
    metadata: dict = field(default_factory=dict)

    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        start = self.started_at or self.created_at
        return max(0, end - start)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, JobStatus) else self.status,
            "progress": self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": self.elapsed(),
            "log": list(self.log),
            "error": self.error,
            "result": self.result,
            "metadata": self.metadata,
        }


# ═════════════════════════════════════════════════════════════════════════════
# Engine
# ═════════════════════════════════════════════════════════════════════════════

class RealtimeEngine:
    """Threaded job queue with subscriber broadcast."""

    def __init__(self, *, max_workers: int = 4):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[Job], None]] = []
        self._max_workers = max_workers
        self._semaphore = threading.BoundedSemaphore(max_workers)
        self._complete_signal = threading.Event()

    # ── Subscriber management ───────────────────────────────────────────
    def subscribe(self, callback: Callable[[Job], None]) -> Callable[[], None]:
        """Register a callback invoked on every job state change.

        Returns an ``unsubscribe`` function.
        """
        with self._lock:
            self._subscribers.append(callback)
        def _unsub():
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)
        return _unsub

    def _broadcast(self, job: Job) -> None:
        with self._lock:
            subs = list(self._subscribers)
        for cb in subs:
            try:
                cb(job)
            except Exception as e:
                logger.debug(f"subscriber raised: {e}")

    # ── Job submission ──────────────────────────────────────────────────
    def submit(self, fn: Callable[..., Any], *args,
               job_id: Optional[str] = None,
               name: Optional[str] = None,
               metadata: Optional[dict] = None,
               on_log: Optional[Callable[[str], None]] = None,
               on_progress: Optional[Callable[[float], None]] = None,
               **kwargs) -> str:
        """Submit ``fn(*args, **kwargs)`` to run in a worker thread.

        Returns the job id (also stored on the Job object).
        """
        jid = job_id or uuid.uuid4().hex[:12]
        job = Job(
            id=jid,
            name=name or getattr(fn, "__name__", "anonymous"),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._jobs[jid] = job
        self._broadcast(job)

        def _runner():
            with self._semaphore:
                job.started_at = time.time()
                job.status = JobStatus.RUNNING
                self._broadcast(job)
                # Wire log + progress into the fn through a context
                _ctx_log = on_log or (lambda line: job.log.append(line))
                _ctx_progress = on_progress or (lambda p: setattr(job, "progress", p))
                try:
                    result = fn(*args, _ctx_log=_ctx_log,
                                _ctx_progress=_ctx_progress, **kwargs)
                    job.result = result
                    job.status = JobStatus.DONE
                    job.progress = 1.0
                except Exception as e:
                    job.error = repr(e) + "\n" + traceback.format_exc(limit=3)
                    job.status = JobStatus.FAILED
                    logger.warning(f"job {jid} failed: {e}")
                finally:
                    job.finished_at = time.time()
                    self._broadcast(job)
                    self._complete_signal.set()

        threading.Thread(target=_runner, daemon=True,
                         name=f"RealtimeJob-{jid}").start()
        return jid

    # ── Status inspection ──────────────────────────────────────────────
    def status(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, *, status: Optional[JobStatus] = None,
                  limit: int = 100) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return jobs[:limit]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING)

    # ── Cancellation ────────────────────────────────────────────────────
    def cancel(self, job_id: str) -> bool:
        """Best-effort cancellation (marks the job, but Python can't truly
        interrupt a thread mid-function)."""
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return False
        job.status = JobStatus.CANCELLED
        job.finished_at = time.time()
        self._broadcast(job)
        return True

    # ── Snapshot (JSON-serialisable for dashboard / SSE) ───────────────
    def snapshot(self) -> dict:
        with self._lock:
            jobs = [j.to_dict() for j in self._jobs.values()]
        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        return {
            "ts": time.time(),
            "active": sum(1 for j in jobs if j["status"] == "running"),
            "queued": sum(1 for j in jobs if j["status"] == "queued"),
            "done":   sum(1 for j in jobs if j["status"] == "done"),
            "failed": sum(1 for j in jobs if j["status"] == "failed"),
            "jobs": jobs[:200],
            "max_workers": self._max_workers,
        }

    def clear_finished(self, *, keep_recent: int = 50) -> int:
        """Drop completed jobs older than the most recent ``keep_recent``.
        Useful to keep the dashboard snappy over long sessions."""
        with self._lock:
            finished = [(jid, j) for jid, j in self._jobs.items()
                        if j.status in (JobStatus.DONE, JobStatus.FAILED,
                                        JobStatus.CANCELLED)]
        finished.sort(key=lambda x: x[1].finished_at, reverse=True)
        for jid, _ in finished[keep_recent:]:
            with self._lock:
                self._jobs.pop(jid, None)
        return max(0, len(finished) - keep_recent)


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[RealtimeEngine] = None


def realtime() -> RealtimeEngine:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = RealtimeEngine()
    return _INSTANCE


__all__ = [
    "RealtimeEngine", "Job", "JobStatus",
    "realtime",
]
