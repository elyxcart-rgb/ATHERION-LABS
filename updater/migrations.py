"""SONIC AI — Database/Schema Migration Framework.

Detects old schema versions and safely migrates data forward.
Each migration is reversible for rollback support.
"""
from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("UPDATER")

_SCHEMA_META_TABLE = "_schema_meta"
_CURRENT_SCHEMA_VERSION = 1


class Migration:
    """A single schema migration."""

    def __init__(
        self,
        version: int,
        description: str,
        up_fn: Callable[[sqlite3.Connection], None],
        down_fn: Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        self.version = version
        self.description = description
        self.up = up_fn
        self.down = down_fn


# ── Registry ─────────────────────────────────────────────────────────────────

_MIGRATIONS: list[Migration] = []


def register_migration(
    version: int,
    description: str,
    up_fn: Callable[[sqlite3.Connection], None],
    down_fn: Callable[[sqlite3.Connection], None] | None = None,
) -> None:
    _MIGRATIONS.append(Migration(version, description, up_fn, down_fn))
    _MIGRATIONS.sort(key=lambda m: m.version)


# ── Built-in migrations ─────────────────────────────────────────────────────

def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS {_SCHEMA_META_TABLE} (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()


def _get_schema_version(conn: sqlite3.Connection) -> int:
    _ensure_meta_table(conn)
    row = conn.execute(
        f"SELECT value FROM {_SCHEMA_META_TABLE} WHERE key = 'schema_version'"
    ).fetchone()
    return int(row[0]) if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    _ensure_meta_table(conn)
    conn.execute(
        f"INSERT OR REPLACE INTO {_SCHEMA_META_TABLE} (key, value) VALUES ('schema_version', ?)",
        (str(version),),
    )
    conn.commit()


# ── Migration runner ─────────────────────────────────────────────────────────

def migrate_database(db_path: Path, backup: bool = True) -> dict[str, Any]:
    """
    Run all pending migrations on the given database.

    Returns a dict with migration results.
    """
    if not db_path.exists():
        logger.info("[MIGRATION] Database does not exist yet: %s", db_path)
        return {"ok": True, "migrated": False, "reason": "new_database"}

    conn = sqlite3.connect(str(db_path))
    try:
        current = _get_schema_version(conn)
        pending = [m for m in _MIGRATIONS if m.version > current]

        if not pending:
            logger.info("[MIGRATION] Database up to date (schema v%d)", current)
            return {"ok": True, "migrated": False, "from_version": current, "to_version": current}

        # Backup before migration
        if backup:
            backup_path = db_path.with_suffix(f".v{current}.bak")
            shutil.copy2(db_path, backup_path)
            logger.info("[MIGRATION] Backup: %s", backup_path)

        # Run migrations in order
        for migration in pending:
            logger.info("[MIGRATION] Running v%d: %s", migration.version, migration.description)
            try:
                migration.up(conn)
                _set_schema_version(conn, migration.version)
                logger.info("[MIGRATION] v%d complete", migration.version)
            except Exception as e:
                logger.error("[MIGRATION] v%d FAILED: %s", migration.version, e)
                conn.close()
                return {
                    "ok": False,
                    "error": str(e),
                    "failed_at_version": migration.version,
                    "from_version": current,
                }

        conn.close()
        return {
            "ok": True,
            "migrated": True,
            "from_version": current,
            "to_version": _MIGRATIONS[-1].version if _MIGRATIONS else current,
        }
    except Exception as e:
        conn.close()
        return {"ok": False, "error": str(e)}


def rollback_migration(db_path: Path, to_version: int) -> dict[str, Any]:
    """Rollback database to a specific schema version."""
    if not db_path.exists():
        return {"ok": False, "error": "Database not found"}

    conn = sqlite3.connect(str(db_path))
    try:
        current = _get_schema_version(conn)
        rollback_migrations = [m for m in _MIGRATIONS if to_version < m.version <= current]
        rollback_migrations.sort(key=lambda m: m.version, reverse=True)

        for migration in rollback_migrations:
            if migration.down is None:
                logger.warning("[MIGRATION] No rollback for v%d — skipping", migration.version)
                continue
            logger.info("[MIGRATION] Rolling back v%d: %s", migration.version, migration.description)
            try:
                migration.down(conn)
                _set_schema_version(conn, migration.version - 1)
            except Exception as e:
                logger.error("[MIGRATION] Rollback v%d FAILED: %s", migration.version, e)
                conn.close()
                return {"ok": False, "error": str(e), "failed_at_version": migration.version}

        conn.close()
        return {"ok": True, "rolled_back_to": to_version}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": e}


# ── Example migrations ───────────────────────────────────────────────────────
# Add future migrations here. Example:
#
# register_migration(
#     version=2,
#     description="Add priority column to memories",
#     up_fn=lambda conn: (
#         conn.execute("ALTER TABLE memories ADD COLUMN priority INTEGER DEFAULT 0"),
#         conn.commit(),
#     ),
#     down_fn=lambda conn: (
#         # SQLite doesn't support DROP COLUMN directly, so we'd recreate the table
#         conn.commit(),
#     ),
# )
