"""SONIC AI Cloud Sync — bridges local SQLite brain with Firestore.

Strategy: offline-first with eventual consistency.
- On login: pull from Firestore → merge into local SQLite
- On memory store: push to Firestore (async, non-blocking)
- Periodic background sync (every 5 min when idle)
- On logout: final push to Firestore
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import db
from .models import (
    Memory, Preference, Project, Task, SessionSummary,
    _now_iso
)

logger = logging.getLogger(__name__)

# Import Firestore singleton
try:
    from auth.firestore_sync import get_firestore
    HAS_FIRESTORE = True
except ImportError:
    HAS_FIRESTORE = False

_sync_lock = threading.Lock()
_sync_timer: Optional[threading.Timer] = None
_last_sync: float = 0.0
SYNC_INTERVAL = 300  # 5 minutes


def _now_ts() -> float:
    return time.time()


def _to_dict(obj) -> dict:
    """Convert dataclass to dict for Firestore."""
    if hasattr(obj, "__dict__"):
        d = {}
        for k, v in obj.__dict__.items():
            if k.startswith("_"):
                continue
            if isinstance(v, datetime):
                d[k] = v.isoformat()
            else:
                d[k] = v
        return d
    return {}


# ── Pull: Firestore → Local SQLite ────────────────────────────────

def pull_from_cloud(uid: str) -> dict:
    """Download user data from Firestore and merge into local SQLite.

    Returns summary: {"memories": N, "preferences": N, "projects": N, "tasks": N}
    """
    if not HAS_FIRESTORE or not uid:
        return {}

    fs = get_firestore()
    if not fs.initialize():
        return {}

    stats = {"memories": 0, "preferences": 0, "projects": 0, "tasks": 0}

    try:
        # Pull memories
        cloud_memories = fs.load_memories(uid, limit=500)
        for cm in cloud_memories:
            mem_id = cm.get("memory_id", "")
            if not mem_id:
                continue
            # Skip if local copy exists and is newer
            local = db.get_memory(mem_id, uid)
            if local:
                local_updated = local.updated_at or ""
                cloud_updated = cm.get("updated_at", "")
                if local_updated >= cloud_updated:
                    continue

            memory = Memory(
                memory_id=mem_id,
                user_id=uid,
                memory_type=cm.get("memory_type", "episodic"),
                content=cm.get("content", ""),
                importance=cm.get("importance", "medium"),
                confidence=cm.get("confidence", "observation"),
                status=cm.get("status", "active"),
                tags=cm.get("tags", ""),
                project_id=cm.get("project_id", ""),
                task_id=cm.get("task_id", ""),
                session_id=cm.get("session_id", ""),
                created_at=cm.get("created_at", _now_iso()),
                updated_at=cm.get("updated_at", _now_iso()),
            )
            db.store_memory(memory)
            stats["memories"] += 1

        # Pull preferences
        cloud_prefs = fs.load_preferences(uid)
        if isinstance(cloud_prefs, dict):
            for key, value in cloud_prefs.items():
                if isinstance(value, dict):
                    v = value.get("value", "")
                    cat = value.get("category", "general")
                else:
                    v = str(value)
                    cat = "general"
                if not v:
                    continue
                existing = db.find_preference(uid, cat, key)
                if existing:
                    continue
                pref = Preference(
                    user_id=uid,
                    category=cat,
                    key=key,
                    value=v,
                    source="cloud_sync",
                )
                db.store_preference(pref)
                stats["preferences"] += 1

        # Pull projects
        cloud_projects = fs.load_projects(uid)
        for cp in cloud_projects:
            proj_id = cp.get("project_id", "")
            if not proj_id:
                continue
            existing = db.get_project(proj_id, uid)
            if existing:
                continue
            project = Project(
                project_id=proj_id,
                user_id=uid,
                name=cp.get("name", ""),
                root_path=cp.get("root_path", ""),
                technology_stack=cp.get("technology_stack", ""),
                architecture_summary=cp.get("architecture_summary", ""),
                conventions=cp.get("conventions", ""),
                current_status=cp.get("current_status", "active"),
                known_bugs=cp.get("known_bugs", ""),
                known_constraints=cp.get("known_constraints", ""),
                past_changes=cp.get("past_changes", ""),
                project_preferences=cp.get("project_preferences", ""),
                last_activity=cp.get("last_activity", _now_iso()),
                created_at=cp.get("created_at", _now_iso()),
            )
            db.store_project(project)
            stats["projects"] += 1

        # Pull tasks
        cloud_tasks = fs.load_tasks(uid)
        for ct in cloud_tasks:
            task_id = ct.get("task_id", "")
            if not task_id:
                continue
            existing = db.get_task(task_id, uid)
            if existing:
                continue
            task = Task(
                task_id=task_id,
                user_id=uid,
                project_id=ct.get("project_id", ""),
                session_id=ct.get("session_id", ""),
                objective=ct.get("objective", ""),
                status=ct.get("status", "pending"),
                plan=ct.get("plan", ""),
                tools_used=ct.get("tools_used", ""),
                output=ct.get("output", ""),
                errors=ct.get("errors", ""),
                created_at=ct.get("created_at", _now_iso()),
                updated_at=ct.get("updated_at", _now_iso()),
                completed_at=ct.get("completed_at", ""),
            )
            db.store_task(task)
            stats["tasks"] += 1

        logger.info("[CloudSync] Pulled from Firestore: %s", stats)
        return stats

    except Exception as e:
        logger.error("[CloudSync] Pull failed: %s", e)
        return stats


# ── Push: Local SQLite → Firestore ────────────────────────────────

def push_to_cloud(uid: str) -> dict:
    """Upload local data to Firestore.

    Returns summary: {"memories": N, "preferences": N, "projects": N, "tasks": N}
    """
    if not HAS_FIRESTORE or not uid:
        return {}

    fs = get_firestore()
    if not fs.initialize():
        return {}

    stats = {"memories": 0, "preferences": 0, "projects": 0, "tasks": 0}

    try:
        # Push memories (batch)
        memories = db.list_memories(uid, limit=500)
        mem_dicts = [_to_dict(m) for m in memories]
        if mem_dicts:
            fs.save_memories(uid, mem_dicts)
            stats["memories"] = len(mem_dicts)

        # Push preferences
        prefs = db.get_active_preferences(uid)
        pref_dict = {}
        for p in prefs:
            pref_dict[p.key] = {"value": p.value, "category": p.category}
        if pref_dict:
            fs.save_preferences(uid, pref_dict)
            stats["preferences"] = len(pref_dict)

        # Push projects
        projects = db.list_projects(uid)
        for proj in projects:
            fs.save_project(uid, _to_dict(proj))
            stats["projects"] += 1

        # Push tasks
        tasks = db.list_tasks(uid)
        for task in tasks:
            fs.save_task(uid, _to_dict(task))
            stats["tasks"] += 1

        logger.info("[CloudSync] Pushed to Firestore: %s", stats)
        return stats

    except Exception as e:
        logger.error("[CloudSync] Push failed: %s", e)
        return stats


# ── Full Sync (bidirectional) ─────────────────────────────────────

def sync_cloud(uid: str) -> dict:
    """Full bidirectional sync. Returns {"pull": {...}, "push": {...}}."""
    global _last_sync
    if not uid:
        return {}

    with _sync_lock:
        try:
            pull_stats = pull_from_cloud(uid)
            push_stats = push_to_cloud(uid)
            _last_sync = _now_ts()
            result = {"pull": pull_stats, "push": push_stats}
            logger.info("[CloudSync] Full sync complete: %s", result)
            return result
        except Exception as e:
            logger.error("[CloudSync] Full sync failed: %s", e)
            return {}


# ── Background Sync Timer ─────────────────────────────────────────

def _periodic_sync(uid: str):
    """Background thread that syncs periodically."""
    global _sync_timer
    if not uid:
        return
    try:
        sync_cloud(uid)
    finally:
        # Reschedule
        _sync_timer = threading.Timer(SYNC_INTERVAL, _periodic_sync, args=(uid,))
        _sync_timer.daemon = True
        _sync_timer.start()


def start_background_sync(uid: str) -> None:
    """Start periodic background sync every SYNC_INTERVAL seconds."""
    global _sync_timer
    stop_background_sync()
    if uid:
        _sync_timer = threading.Timer(SYNC_INTERVAL, _periodic_sync, args=(uid,))
        _sync_timer.daemon = True
        _sync_timer.start()
        logger.info("[CloudSync] Background sync started (interval=%ds)", SYNC_INTERVAL)


def stop_background_sync() -> None:
    """Stop background sync timer."""
    global _sync_timer
    if _sync_timer is not None:
        _sync_timer.cancel()
        _sync_timer = None


# ── Lifecycle Hooks ────────────────────────────────────────────────

def on_login(uid: str) -> dict:
    """Called after successful login. Pull cloud → local, start bg sync."""
    if not uid:
        return {}
    logger.info("[CloudSync] Login hook: pulling cloud data for %s", uid)
    result = pull_from_cloud(uid)
    start_background_sync(uid)
    return result


def on_logout(uid: str) -> dict:
    """Called before logout. Push local → cloud, stop bg sync."""
    if not uid:
        return {}
    logger.info("[CloudSync] Logout hook: pushing local data for %s", uid)
    stop_background_sync()
    result = push_to_cloud(uid)
    return result


def on_memory_changed(uid: str) -> None:
    """Called after a new memory is stored. Triggers async push."""
    if not uid:
        return
    # Debounce: don't push more than once per 10 seconds
    threading.Timer(10.0, _push_single, args=(uid,)).start()


def _push_single(uid: str) -> None:
    """Push latest memory to Firestore."""
    if not HAS_FIRESTORE:
        return
    try:
        fs = get_firestore()
        if not fs.initialize():
            return
        memories = db.list_memories(uid, limit=50)
        mem_dicts = [_to_dict(m) for m in memories]
        if mem_dicts:
            fs.save_memories(uid, mem_dicts)
    except Exception as e:
        logger.error("[CloudSync] Single push failed: %s", e)


# ── Status ─────────────────────────────────────────────────────────

def get_sync_status() -> dict:
    """Return sync status for UI."""
    return {
        "firestore_available": HAS_FIRESTORE,
        "last_sync": datetime.fromtimestamp(_last_sync, tz=timezone.utc).isoformat() if _last_sync else None,
        "background_active": _sync_timer is not None and _sync_timer.is_alive(),
        "sync_interval": SYNC_INTERVAL,
    }
