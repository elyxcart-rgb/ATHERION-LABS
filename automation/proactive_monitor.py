"""SONIC AI — Proactive Monitor.

Event-driven automation:
- **File watcher**: runs a callback whenever files change in a directory
- **Scheduled tasks**: cron-like schedules (every N seconds, daily at H:M, …)

Uses ``watchdog`` if available (preferred), falls back to a polling loop
otherwise. All work runs in background threads.

Public surface (stable, opt-in):
    - ``watch(path, callback, *, pattern=None)`` — file watcher
    - ``schedule(callback, *, every_seconds=60, at=None, …)`` — scheduled task
    - ``cancel_watch(token)`` / ``cancel_schedule(token)`` — stop
    - ``list_watches()`` / ``list_schedules()`` — introspect

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("PROACTIVE_MONITOR")


# ═════════════════════════════════════════════════════════════════════════════
# File watcher
# ═════════════════════════════════════════════════════════════════════════════

_WATCHES: dict[str, dict] = {}
_WATCHES_LOCK = threading.Lock()


def _make_handler(callback: Callable[[str, str], None]):
    """Build a watchdog handler that calls ``callback(event_type, path)``."""
    from watchdog.events import FileSystemEventHandler
    class _H(FileSystemEventHandler):
        def on_any_event(self, event):
            try:
                if event.is_directory:
                    return
                callback(event.event_type, str(event.src_path))
            except Exception as e:
                logger.debug(f"watch handler raised: {e}")
    return _H()


def watch(path: str, callback: Callable[[str, str], None], *,
          pattern: Optional[str] = None) -> str:
    """Watch a directory. Calls ``callback(event_type, path)`` on changes.

    Args:
        path:      Directory to watch.
        callback:  ``(event_type, path)`` — ``event_type`` is one of
                   ``created | modified | deleted | moved``.
        pattern:   Optional glob filter (e.g. ``"*.pdf"``).

    Returns a token (use ``cancel_watch(token)`` to stop).
    """
    p = Path(path).expanduser()
    if not p.is_dir():
        raise NotADirectoryError(p)
    token = uuid.uuid4().hex[:10]

    observer = None
    try:
        from watchdog.observers import Observer
        handler = _make_handler(callback)
        observer = Observer()
        if pattern:
            observer.schedule(handler, str(p), recursive=False)
        else:
            observer.schedule(handler, str(p), recursive=True)
        observer.daemon = True
        observer.start()
    except ImportError:
        # Fallback: polling watcher
        logger.info("watchdog not available — falling back to polling watcher")
        observer = _PollingObserver(p, callback, pattern)
        observer.start()

    with _WATCHES_LOCK:
        _WATCHES[token] = {
            "token": token, "path": str(p), "pattern": pattern,
            "started_at": time.time(), "observer": observer,
        }
    logger.info(f"watch started: {token} on {p}")
    return token


def cancel_watch(token: str) -> bool:
    with _WATCHES_LOCK:
        info = _WATCHES.pop(token, None)
    if info is None:
        return False
    obs = info["observer"]
    try:
        if isinstance(obs, _PollingObserver):
            obs.stop()
        else:
            obs.stop()
            obs.join(timeout=2)
    except Exception as e:
        logger.debug(f"cancel_watch: {e}")
    return True


def list_watches() -> list[dict]:
    with _WATCHES_LOCK:
        return [
            {"token": info["token"], "path": info["path"],
             "pattern": info["pattern"],
             "started_at": info["started_at"]}
            for info in _WATCHES.values()
        ]


class _PollingObserver:
    """Polling fallback when watchdog isn't installed."""
    def __init__(self, path: Path,
                 callback: Callable[[str, str], None],
                 pattern: Optional[str]):
        self.path = path
        self.callback = callback
        self.pattern = pattern
        self._state: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _poll(self):
        try:
            for p in self.path.rglob("*"):
                if self.pattern and not p.match(self.pattern):
                    continue
                if p.is_file():
                    key = str(p)
                    mtime = p.stat().st_mtime
                    if key not in self._state:
                        self._state[key] = mtime
                        self.callback("created", key)
                    elif self._state[key] != mtime:
                        self._state[key] = mtime
                        self.callback("modified", key)
        except Exception:
            pass

    def start(self):
        def _loop():
            while not self._stop_event.is_set():
                self._poll()
                self._stop_event.wait(2.0)
        self._thread = threading.Thread(target=_loop, daemon=True,
                                       name="PollingObserver")
        self._thread.start()

    def stop(self):
        self._stop_event.set()


# ═════════════════════════════════════════════════════════════════════════════
# Scheduled tasks
# ═════════════════════════════════════════════════════════════════════════════

_SCHEDULES: dict[str, dict] = {}
_SCHEDULES_LOCK = threading.Lock()


def schedule(callback: Callable[..., Any], *,
             every_seconds: Optional[float] = None,
             at: Optional[str] = None,         # "HH:MM" daily
             run_immediately: bool = False,
             name: Optional[str] = None) -> str:
    """Schedule a callback to run periodically.

    Two modes:
        - ``every_seconds=N``  → run every N seconds
        - ``at="HH:MM"``       → run daily at HH:MM

    Returns a token (use ``cancel_schedule(token)``).
    """
    if not every_seconds and not at:
        raise ValueError("specify either every_seconds= or at=")
    if every_seconds and at:
        raise ValueError("specify only one of every_seconds= / at=")

    token = uuid.uuid4().hex[:10]
    info: dict[str, Any] = {
        "token": token, "callback": callback,
        "name": name or getattr(callback, "__name__", "scheduled"),
        "started_at": time.time(), "last_run": 0.0, "run_count": 0,
    }
    if every_seconds:
        info["mode"] = "interval"
        info["every_seconds"] = float(every_seconds)
    else:
        info["mode"] = "daily"
        info["at"] = at
        h, m = at.split(":")
        info["at_hour"] = int(h)
        info["at_minute"] = int(m)
        info["last_fired_day"] = None  # track day to fire once per day

    info["run_immediately"] = run_immediately

    stop_event = threading.Event()
    info["stop_event"] = stop_event

    def _should_run(now: float) -> bool:
        if info["mode"] == "interval":
            return now - info["last_run"] >= info["every_seconds"]
        # daily mode
        target = now
        # compute seconds since midnight
        secs = info["at_hour"] * 3600 + info["at_minute"] * 60
        today = datetime.now().date().isoformat()
        # run if we haven't fired today and current time >= target
        if info["last_fired_day"] != today and int(time.localtime(now)[3]) * 3600 + int(time.localtime(now)[4]) * 60 >= secs:
            return True
        return False

    def _loop():
        if run_immediately:
            try:
                callback()
                info["last_run"] = time.time()
                info["run_count"] += 1
                if info["mode"] == "daily":
                    info["last_fired_day"] = datetime.now().date().isoformat()
            except Exception as e:
                logger.warning(f"schedule {token} initial run failed: {e}")
        while not stop_event.is_set():
            now = time.time()
            if _should_run(now):
                try:
                    callback()
                    info["last_run"] = now
                    info["run_count"] += 1
                    if info["mode"] == "daily":
                        info["last_fired_day"] = datetime.now().date().isoformat()
                except Exception as e:
                    logger.warning(f"schedule {token} run failed: {e}")
            # Sleep a small amount so we can react to stop
            sleep_for = 1.0 if info["mode"] == "interval" else 30.0
            stop_event.wait(sleep_for)

    thread = threading.Thread(target=_loop, daemon=True,
                              name=f"Schedule-{token}")
    info["thread"] = thread
    thread.start()

    with _SCHEDULES_LOCK:
        _SCHEDULES[token] = info
    return token


def cancel_schedule(token: str) -> bool:
    with _SCHEDULES_LOCK:
        info = _SCHEDULES.pop(token, None)
    if info is None:
        return False
    info["stop_event"].set()
    return True


def list_schedules() -> list[dict]:
    with _SCHEDULES_LOCK:
        return [
            {"token": info["token"], "name": info["name"],
             "mode": info["mode"],
             "every_seconds": info.get("every_seconds"),
             "at": info.get("at"),
             "last_run": info["last_run"], "run_count": info["run_count"]}
            for info in _SCHEDULES.values()
        ]


__all__ = [
    "watch", "cancel_watch", "list_watches",
    "schedule", "cancel_schedule", "list_schedules",
]
