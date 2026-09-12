"""Memory consolidation for SONIC AI — dedup, conflicts, decay, merging."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import db
from .models import (
    Memory, MemoryStatus, Importance, Confidence, _now_iso
)


def deduplicate(user_id: str) -> int:
    """Find and merge duplicate memories. Returns count of merges."""
    merges = 0
    memories = db.list_memories(user_id, limit=500)

    seen_content: dict[str, Memory] = {}
    for m in memories:
        if m.status != MemoryStatus.ACTIVE.value:
            continue
        # Normalize for comparison
        normalized = _normalize(m.content)
        if normalized in seen_content:
            # Duplicate found — reinforce the older one, supersede the newer
            existing = seen_content[normalized]
            db.update_memory_fields(
                existing.memory_id, user_id,
                reinforcement_count=existing.reinforcement_count + m.reinforcement_count + 1,
                access_count=max(existing.access_count, m.access_count),
                last_accessed_at=max(existing.last_accessed_at, m.last_accessed_at,
                                     key=lambda x: x or ""),
            )
            db.update_memory_fields(
                m.memory_id, user_id,
                status=MemoryStatus.SUPERSEDED.value,
                superseded_by=existing.memory_id,
            )
            merges += 1
        else:
            seen_content[normalized] = m

    return merges


def resolve_conflicts(user_id: str) -> int:
    """Resolve preference conflicts — newer explicit overrides older inferred."""
    resolutions = 0
    prefs = db.get_active_preferences(user_id)

    # Group by key
    by_key: dict[str, list] = {}
    for p in prefs:
        by_key.setdefault(p.key, []).append(p)

    for key, group in by_key.items():
        if len(group) <= 1:
            continue

        # Sort: explicit > inferred, newer > older
        def sort_key(p):
            source_weight = {"explicit": 3, "observed": 2, "inferred": 1}.get(p.source, 0)
            return (source_weight, p.updated_at)

        group.sort(key=sort_key, reverse=True)
        winner = group[0]

        for loser in group[1:]:
            if loser.preference_id == winner.preference_id:
                continue
            # Update the preference directly since it's in the preferences table
            _supersede_preference(loser.preference_id, user_id, winner.preference_id)
            resolutions += 1

    return resolutions


def _supersede_preference(pref_id: str, user_id: str, superseded_by: str):
    """Mark a preference as superseded."""
    with db._lock:
        conn = db._connect()
        try:
            conn.execute(
                """UPDATE preferences SET status='superseded', superseded_by=?, updated_at=?
                   WHERE preference_id=? AND user_id=?""",
                (superseded_by, _now_iso(), pref_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def apply_memory_decay(user_id: str) -> dict:
    """Apply decay to old inferred memories. Returns stats."""
    stats = {"decayed": 0, "expired": 0}

    # Decay inferred memories older than 30 days
    with db._lock:
        conn = db._connect()
        try:
            # Reduce reinforcement for old inferred memories
            conn.execute(
                """UPDATE memories
                   SET reinforcement_count = MAX(0, reinforcement_count - 1)
                   WHERE user_id=? AND status='active'
                   AND confidence IN ('inferred', 'guess')
                   AND reinforcement_count > 0
                   AND updated_at < datetime('now', '-30 days')""",
                (user_id,),
            )
            stats["decayed"] = conn.execute(
                """SELECT changes() FROM (SELECT 1) LIMIT 1"""
            ).fetchone()[0]

            # Expire memories past their expires_at
            now = _now_iso()
            conn.execute(
                """UPDATE memories SET status='expired'
                   WHERE user_id=? AND status='active'
                   AND expires_at != '' AND expires_at < ?""",
                (user_id, now),
            )
            stats["expired"] = conn.execute(
                """SELECT changes() FROM (SELECT 1) LIMIT 1"""
            ).fetchone()[0]

            # Remove old superseded/forgotten memories (>90 days)
            conn.execute(
                """DELETE FROM memories
                   WHERE user_id=? AND status IN ('superseded', 'forgotten')
                   AND updated_at < datetime('now', '-90 days')""",
                (user_id,),
            )

            conn.commit()
        finally:
            conn.close()

    return stats


def reinforce_memory(memory_id: str, user_id: str, amount: int = 1):
    """Explicitly reinforce a memory."""
    with db._lock:
        conn = db._connect()
        try:
            conn.execute(
                """UPDATE memories
                   SET reinforcement_count = reinforcement_count + ?,
                       last_accessed_at = ?,
                       updated_at = ?
                   WHERE memory_id=? AND user_id=?""",
                (amount, _now_iso(), _now_iso(), memory_id, user_id),
            )
            conn.commit()
        finally:
            conn.close()


def supersede_by_content(user_id: str, old_content_hint: str,
                         new_content: str, new_type: str = "preference") -> bool:
    """Find memory matching hint and supersede it with new content."""
    matches = db.search_memories(user_id, old_content_hint, limit=5)
    if not matches:
        matches = db.find_similar_content(user_id, old_content_hint)

    if not matches:
        return False

    old = matches[0]
    # Mark old as superseded
    db.update_memory_fields(
        old.memory_id, user_id,
        status=MemoryStatus.SUPERSEDED.value,
    )

    # Store new memory
    new_mem = Memory(
        user_id=user_id,
        memory_type=new_type,
        content=new_content,
        importance=old.importance,
        confidence=Confidence.FACT.value,
        tags=old.tags,
        superseded_by=old.memory_id,
    )
    db.store_memory(new_mem)
    return True


def consolidate(user_id: str) -> dict:
    """Run full consolidation cycle. Returns stats."""
    merges = deduplicate(user_id)
    resolutions = resolve_conflicts(user_id)
    decay = apply_memory_decay(user_id)

    return {
        "merges": merges,
        "conflict_resolutions": resolutions,
        "decayed": decay.get("decayed", 0),
        "expired": decay.get("expired", 0),
    }


def _normalize(text: str) -> str:
    """Normalize text for dedup comparison."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text
