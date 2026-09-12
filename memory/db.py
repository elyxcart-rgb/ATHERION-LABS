"""SQLite storage layer for SONIC memory with FTS5 full-text search."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    Memory, Project, Task, ToolExperience, Preference,
    SessionSummary, Entity, MemoryStatus, _now_iso
)

_DB_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "memory"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "sonic_brain.db"
_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables and FTS5 indexes if they don't exist."""
    with _lock:
        conn = _connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()


# ── schema ──────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'episodic',
    content TEXT NOT NULL,
    importance TEXT NOT NULL DEFAULT 'medium',
    confidence TEXT NOT NULL DEFAULT 'observation',
    status TEXT NOT NULL DEFAULT 'active',
    tags TEXT DEFAULT '',
    project_id TEXT DEFAULT '',
    task_id TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    source_message TEXT DEFAULT '',
    access_count INTEGER DEFAULT 0,
    reinforcement_count INTEGER DEFAULT 0,
    contradiction_count INTEGER DEFAULT 0,
    superseded_by TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT DEFAULT '',
    expires_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_mem_user ON memories(user_id);
CREATE INDEX IF NOT EXISTS idx_mem_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_mem_status ON memories(status);
CREATE INDEX IF NOT EXISTS idx_mem_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_mem_project ON memories(project_id);
CREATE INDEX IF NOT EXISTS idx_mem_updated ON memories(updated_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, tags,
    content=memories,
    content_rowid=rowid
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.rowid, old.content, old.tags);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, tags) VALUES ('delete', old.rowid, old.content, old.tags);
    INSERT INTO memories_fts(rowid, content, tags) VALUES (new.rowid, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    root_path TEXT DEFAULT '',
    technology_stack TEXT DEFAULT '',
    architecture_summary TEXT DEFAULT '',
    important_files TEXT DEFAULT '',
    conventions TEXT DEFAULT '',
    current_status TEXT DEFAULT 'active',
    known_bugs TEXT DEFAULT '',
    known_constraints TEXT DEFAULT '',
    past_changes TEXT DEFAULT '',
    project_preferences TEXT DEFAULT '',
    last_activity TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_proj_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_proj_name ON projects(name);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT DEFAULT '',
    session_id TEXT DEFAULT '',
    objective TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    steps TEXT DEFAULT '',
    tools_used TEXT DEFAULT '',
    files_changed TEXT DEFAULT '',
    result TEXT DEFAULT '',
    failures TEXT DEFAULT '',
    lessons_learned TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    completed_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_task_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_task_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status);

CREATE TABLE IF NOT EXISTS tool_experiences (
    experience_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_pattern TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    outcome TEXT DEFAULT '',
    success INTEGER DEFAULT 1,
    duration_ms INTEGER DEFAULT 0,
    failures INTEGER DEFAULT 0,
    recovery_strategy TEXT DEFAULT '',
    project_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    last_used TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_te_user ON tool_experiences(user_id);
CREATE INDEX IF NOT EXISTS idx_te_tool ON tool_experiences(tool_name);

CREATE TABLE IF NOT EXISTS preferences (
    preference_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'observation',
    source TEXT DEFAULT 'observed',
    reinforcement_count INTEGER DEFAULT 1,
    superseded_by TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_confirmed_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_pref_user ON preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_pref_cat ON preferences(category);
CREATE INDEX IF NOT EXISTS idx_pref_key ON preferences(key);
CREATE INDEX IF NOT EXISTS idx_pref_status ON preferences(status);

CREATE TABLE IF NOT EXISTS session_summaries (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    started_at TEXT DEFAULT '',
    ended_at TEXT DEFAULT '',
    summary TEXT NOT NULL,
    topic TEXT DEFAULT '',
    tools_used TEXT DEFAULT '',
    files_touched TEXT DEFAULT '',
    decisions TEXT DEFAULT '',
    unresolved TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ss_user ON session_summaries(user_id);

CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    related_to TEXT DEFAULT '',
    project_id TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ent_user ON entities(user_id);
CREATE INDEX IF NOT EXISTS idx_ent_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_ent_name ON entities(name);
"""


# ── memory CRUD ─────────────────────────────────────────────────────

def store_memory(m: Memory) -> str:
    with _lock:
        conn = _connect()
        try:
            d = m.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO memories ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return m.memory_id
        finally:
            conn.close()


def get_memory(memory_id: str, user_id: str) -> Optional[Memory]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM memories WHERE memory_id=? AND user_id=?",
                (memory_id, user_id),
            ).fetchone()
            return Memory.from_row(dict(row)) if row else None
        finally:
            conn.close()


def update_memory_fields(memory_id: str, user_id: str, **fields):
    with _lock:
        conn = _connect()
        try:
            fields["updated_at"] = _now_iso()
            sets = ", ".join(f"{k}=?" for k in fields)
            vals = list(fields.values()) + [memory_id, user_id]
            conn.execute(
                f"UPDATE memories SET {sets} WHERE memory_id=? AND user_id=?",
                vals,
            )
            conn.commit()
        finally:
            conn.close()


def delete_memory(memory_id: str, user_id: str):
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "DELETE FROM memories WHERE memory_id=? AND user_id=?",
                (memory_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def list_memories(user_id: str, memory_type: str = "", status: str = "active",
                  limit: int = 100) -> list[Memory]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM memories WHERE user_id=? AND status=?"
            params: list = [user_id, status or MemoryStatus.ACTIVE.value]
            if memory_type:
                q += " AND memory_type=?"
                params.append(memory_type)
            q += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [Memory.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


def _sanitize_fts_query(query: str) -> str:
    """Sanitize query for FTS5 MATCH — remove special chars, handle edge cases."""
    import re
    # Remove FTS5 special characters
    query = re.sub(r'[^\w\s]', ' ', query)
    # Split into words and filter short ones
    words = [w for w in query.split() if len(w) > 1]
    if not words:
        return ""
    # Join with OR for broader matching
    return " OR ".join(words)


def search_memories(user_id: str, query: str, limit: int = 20) -> list[Memory]:
    """FTS5 search with case-insensitive LIKE fallback."""
    fts_query = _sanitize_fts_query(query)

    # Try FTS5 first
    if fts_query:
        with _lock:
            conn = _connect()
            try:
                rows = conn.execute(
                    """SELECT m.* FROM memories m
                       JOIN memories_fts f ON m.rowid = f.rowid
                       WHERE memories_fts MATCH ? AND m.user_id=? AND m.status='active'
                       ORDER BY rank
                       LIMIT ?""",
                    (fts_query, user_id, limit),
                ).fetchall()
                if rows:
                    return [Memory.from_row(dict(r)) for r in rows]
            except Exception:
                pass
            finally:
                conn.close()

    # Fallback: case-insensitive LIKE search
    import re
    words = [re.sub(r'[^\w]', '', w).lower() for w in query.split()]
    words = [w for w in words if len(w) > 2]
    if not words:
        return []

    with _lock:
        conn = _connect()
        try:
            # Build LIKE conditions for each word
            conditions = " OR ".join(["LOWER(content) LIKE ?" for _ in words])
            params = [f"%{w}%" for w in words] + [user_id, limit]
            rows = conn.execute(
                f"""SELECT * FROM memories
                    WHERE user_id=? AND status='active'
                    AND ({conditions})
                    ORDER BY updated_at DESC
                    LIMIT ?""",
                params,
            ).fetchall()
            return [Memory.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


def count_memories(user_id: str, memory_type: str = "", status: str = "active") -> int:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT COUNT(*) FROM memories WHERE user_id=? AND status=?"
            params: list = [user_id, status]
            if memory_type:
                q += " AND memory_type=?"
                params.append(memory_type)
            return conn.execute(q, params).fetchone()[0]
        finally:
            conn.close()


def find_similar_content(user_id: str, content: str, exclude_id: str = "",
                         threshold: float = 0.5) -> list[Memory]:
    """Find memories with overlapping content for deduplication.
    Requires significant word overlap to avoid false positives."""
    import re
    words = [w for w in re.findall(r'\w{3,}', content.lower())]
    if not words:
        return []
    # Build AND query for stricter matching — require most words to match
    terms = " AND ".join(words[:6])
    with _lock:
        conn = _connect()
        try:
            q = """SELECT m.* FROM memories m
                   JOIN memories_fts f ON m.rowid = f.rowid
                   WHERE memories_fts MATCH ? AND m.user_id=? AND m.status='active'"""
            params: list = [terms, user_id]
            if exclude_id:
                q += " AND m.memory_id!=?"
                params.append(exclude_id)
            q += " ORDER BY rank LIMIT 10"
            rows = conn.execute(q, params).fetchall()
            return [Memory.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


# ── project CRUD ────────────────────────────────────────────────────

def store_project(p: Project) -> str:
    with _lock:
        conn = _connect()
        try:
            d = p.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO projects ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return p.project_id
        finally:
            conn.close()


def get_project(project_id: str, user_id: str) -> Optional[Project]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id=? AND user_id=?",
                (project_id, user_id),
            ).fetchone()
            return Project.from_row(dict(row)) if row else None
        finally:
            conn.close()


def find_project_by_name(user_id: str, name: str) -> Optional[Project]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM projects WHERE user_id=? AND name=? COLLATE NOCASE",
                (user_id, name),
            ).fetchone()
            return Project.from_row(dict(row)) if row else None
        finally:
            conn.close()


def list_projects(user_id: str) -> list[Project]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM projects WHERE user_id=? ORDER BY last_activity DESC",
                (user_id,),
            ).fetchall()
            return [Project.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


# ── task CRUD ───────────────────────────────────────────────────────

def store_task(t: Task) -> str:
    with _lock:
        conn = _connect()
        try:
            d = t.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO tasks ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return t.task_id
        finally:
            conn.close()


def get_task(task_id: str, user_id: str) -> Optional[Task]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=? AND user_id=?",
                (task_id, user_id),
            ).fetchone()
            return Task.from_row(dict(row)) if row else None
        finally:
            conn.close()


def list_tasks(user_id: str, status: str = "", limit: int = 50) -> list[Task]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM tasks WHERE user_id=?"
            params: list = [user_id]
            if status:
                q += " AND status=?"
                params.append(status)
            q += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [Task.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


# ── tool experience CRUD ───────────────────────────────────────────

def store_tool_experience(te: ToolExperience) -> str:
    with _lock:
        conn = _connect()
        try:
            d = te.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO tool_experiences ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return te.experience_id
        finally:
            conn.close()


def get_tool_experiences(user_id: str, task_pattern: str = "",
                         tool_name: str = "") -> list[ToolExperience]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM tool_experiences WHERE user_id=?"
            params: list = [user_id]
            if task_pattern:
                q += " AND task_pattern=?"
                params.append(task_pattern)
            if tool_name:
                q += " AND tool_name=?"
                params.append(tool_name)
            q += " ORDER BY last_used DESC LIMIT 20"
            rows = conn.execute(q, params).fetchall()
            return [ToolExperience.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


# ── preference CRUD ────────────────────────────────────────────────

def store_preference(p: Preference) -> str:
    with _lock:
        conn = _connect()
        try:
            d = p.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO preferences ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return p.preference_id
        finally:
            conn.close()


def get_active_preferences(user_id: str, category: str = "") -> list[Preference]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM preferences WHERE user_id=? AND status='active'"
            params: list = [user_id]
            if category:
                q += " AND category=?"
                params.append(category)
            q += " ORDER BY updated_at DESC"
            rows = conn.execute(q, params).fetchall()
            return [Preference.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


def find_preference(user_id: str, category: str, key: str) -> Optional[Preference]:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute(
                """SELECT * FROM preferences
                   WHERE user_id=? AND category=? AND key=? AND status='active'""",
                (user_id, category, key),
            ).fetchone()
            return Preference.from_row(dict(row)) if row else None
        finally:
            conn.close()


# ── session summary CRUD ───────────────────────────────────────────

def store_session_summary(s: SessionSummary) -> str:
    with _lock:
        conn = _connect()
        try:
            d = s.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO session_summaries ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return s.session_id
        finally:
            conn.close()


def list_session_summaries(user_id: str, limit: int = 10) -> list[SessionSummary]:
    with _lock:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM session_summaries WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            return [SessionSummary.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


# ── entity CRUD ────────────────────────────────────────────────────

def store_entity(e: Entity) -> str:
    with _lock:
        conn = _connect()
        try:
            d = e.to_dict()
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            conn.execute(
                f"INSERT OR REPLACE INTO entities ({cols}) VALUES ({placeholders})",
                list(d.values()),
            )
            conn.commit()
            return e.entity_id
        finally:
            conn.close()


def find_entity(user_id: str, name: str, entity_type: str = "") -> Optional[Entity]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM entities WHERE user_id=? AND name=? COLLATE NOCASE"
            params: list = [user_id, name]
            if entity_type:
                q += " AND entity_type=?"
                params.append(entity_type)
            row = conn.execute(q, params).fetchone()
            return Entity.from_row(dict(row)) if row else None
        finally:
            conn.close()


def list_entities(user_id: str, entity_type: str = "", limit: int = 100) -> list[Entity]:
    with _lock:
        conn = _connect()
        try:
            q = "SELECT * FROM entities WHERE user_id=?"
            params: list = [user_id]
            if entity_type:
                q += " AND entity_type=?"
                params.append(entity_type)
            q += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(q, params).fetchall()
            return [Entity.from_row(dict(r)) for r in rows]
        finally:
            conn.close()


# ── maintenance ─────────────────────────────────────────────────────

def supersede_memory(memory_id: str, user_id: str, superseded_by: str):
    """Mark a memory as superseded by another."""
    update_memory_fields(
        memory_id, user_id,
        status=MemoryStatus.SUPERSEDED.value,
        superseded_by=superseded_by,
    )


def expire_old_memories(user_id: str):
    """Mark expired memories."""
    now = _now_iso()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """UPDATE memories SET status='expired'
                   WHERE user_id=? AND status='active' AND expires_at!='' AND expires_at<?""",
                (user_id, now),
            )
            conn.commit()
        finally:
            conn.close()


def apply_decay(user_id: str, decay_factor: float = 0.95):
    """Reduce reinforcement_count for old inferred memories."""
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """UPDATE memories SET reinforcement_count = MAX(0, CAST(reinforcement_count * ? AS INTEGER))
                   WHERE user_id=? AND status='active'
                   AND confidence IN ('inferred', 'guess')
                   AND updated_at < datetime('now', '-30 days')""",
                (decay_factor, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def get_db_stats(user_id: str) -> dict:
    """Return counts by type for observability."""
    with _lock:
        conn = _connect()
        try:
            stats = {}
            for table in ("memories", "projects", "tasks", "tool_experiences",
                          "preferences", "session_summaries", "entities"):
                row = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                stats[table] = row[0]
            return stats
        finally:
            conn.close()
