"""Memory retrieval engine for SONIC AI — ranks memories by relevance."""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Optional

from . import db
from .models import Memory, MemoryStatus, Importance


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _recency_score(updated_at: str) -> float:
    """More recent = higher score. Decays over 90 days."""
    dt = _parse_iso(updated_at)
    if not dt:
        return 0.5
    now = datetime.now(timezone.utc)
    days = max((now - dt).total_seconds() / 86400, 0)
    return math.exp(-days / 90)


def _importance_weight(importance: str) -> float:
    return {
        "critical": 2.0,
        "high": 1.5,
        "medium": 1.0,
        "low": 0.6,
        "ephemeral": 0.3,
    }.get(importance, 1.0)


def _confidence_weight(confidence: str) -> float:
    return {
        "fact": 1.5,
        "inferred": 1.0,
        "observation": 1.1,
        "lesson": 1.3,
        "guess": 0.5,
    }.get(confidence, 1.0)


def _keyword_overlap(query: str, content: str) -> float:
    """Simple token overlap score."""
    q_words = set(re.findall(r'\w{3,}', query.lower()))
    c_words = set(re.findall(r'\w{3,}', content.lower()))
    if not q_words:
        return 0.0
    overlap = q_words & c_words
    return len(overlap) / len(q_words)


def retrieve_context(user_id: str, query: str, limit: int = 20,
                     types: list[str] | None = None,
                     project_id: str = "") -> list[dict]:
    """Main retrieval: combines FTS + scoring. Returns ranked list of dicts."""
    # 1. FTS search
    fts_results = db.search_memories(user_id, query, limit=limit * 3)

    # 2. Keyword fallback if FTS returns too few
    if len(fts_results) < limit:
        all_mems = db.list_memories(user_id, limit=200)
        seen = {m.memory_id for m in fts_results}
        for m in all_mems:
            if m.memory_id not in seen and _keyword_overlap(query, m.content) > 0.2:
                fts_results.append(m)
                seen.add(m.memory_id)
            if len(fts_results) >= limit * 3:
                break

    # 3. Score and rank
    scored = []
    for m in fts_results:
        if types and m.memory_type not in types:
            continue
        if project_id and m.project_id and m.project_id != project_id:
            continue

        kw = _keyword_overlap(query, m.content)
        rec = _recency_score(m.updated_at)
        imp = _importance_weight(m.importance)
        conf = _confidence_weight(m.confidence)
        boost = 1.0 + min(m.reinforcement_count * 0.05, 0.5)
        penalty = 0.8 if m.status == MemoryStatus.SUPERSEDED.value else 1.0

        score = (kw * 0.35 + rec * 0.25) * imp * conf * boost * penalty

        # Bonus for type match in query
        type_hints = {
            "prefer": "preference", "language": "preference", "style": "preference",
            "project": "project", "repo": "project", "codebase": "project",
            "task": "task", "fix": "task", "bug": "task",
            "lesson": "lesson", "learned": "lesson", "mistake": "lesson",
            "error": "error", "failed": "error", "broke": "error",
            "remember": None, "what do you": None,
        }
        for hint, mtype in type_hints.items():
            if mtype and hint in query.lower() and m.memory_type == mtype:
                score *= 1.3
                break

        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 4. Mark accessed
    result = []
    for score, m in scored[:limit]:
        db.update_memory_fields(m.memory_id, user_id,
                                access_count=m.access_count + 1,
                                last_accessed_at=db._now_iso())
        result.append({
            "memory_id": m.memory_id,
            "type": m.memory_type,
            "content": m.content,
            "importance": m.importance,
            "confidence": m.confidence,
            "score": round(score, 4),
            "tags": m.tags,
        })

    return result


def retrieve_preferences(user_id: str, category: str = "") -> list[dict]:
    """Get active preferences, optionally filtered by category."""
    prefs = db.get_active_preferences(user_id, category)
    return [{"category": p.category, "key": p.key, "value": p.value,
             "confidence": p.confidence, "source": p.source,
             "reinforcements": p.reinforcement_count} for p in prefs]


def retrieve_project_context(user_id: str, project_name: str = "",
                             project_id: str = "") -> dict:
    """Get full project context including memories, tasks, entities."""
    project = None
    if project_id:
        project = db.get_project(project_id, user_id)
    elif project_name:
        project = db.find_project_by_name(user_id, project_name)

    if not project:
        return {}

    memories = db.list_memories(user_id, project_id=project.project_id, limit=30)
    tasks = db.list_tasks(user_id, project_id=project.project_id, limit=10)
    entities = db.list_entities(user_id, project_id=project.project_id)

    return {
        "project": project.to_dict(),
        "memories": [m.to_dict() for m in memories],
        "tasks": [t.to_dict() for t in tasks],
        "entities": [e.to_dict() for e in entities],
    }


def retrieve_tool_strategy(user_id: str, task_pattern: str) -> list[dict]:
    """Get historical tool experiences for a task pattern."""
    exps = db.get_tool_experiences(user_id, task_pattern=task_pattern)
    return [{"tool": e.tool_name, "success": e.success,
             "duration_ms": e.duration_ms, "failures": e.failures,
             "recovery": e.recovery_strategy} for e in exps]


def retrieve_unresolved_tasks(user_id: str, limit: int = 10) -> list[dict]:
    """Get tasks that were interrupted or pending."""
    tasks = db.list_tasks(user_id, status="in_progress", limit=limit)
    tasks += db.list_tasks(user_id, status="pending", limit=limit)
    return [{"task_id": t.task_id, "objective": t.objective,
             "status": t.status, "created_at": t.created_at,
             "project_id": t.project_id} for t in tasks[:limit]]
