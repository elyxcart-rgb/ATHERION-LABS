"""Context builder for SONIC AI — assembles relevant memory into prompt context."""
from __future__ import annotations

from . import db, retrieval
from .models import Importance


# Token budget: ~2000 chars for memory context (roughly 500 tokens)
_TOKEN_BUDGET = 2000
_PROFILE_BUDGET = 400
_PROJECT_BUDGET = 500
_PREF_BUDGET = 300
_TASK_BUDGET = 300
_EXPERIENCE_BUDGET = 200
_SESSION_BUDGET = 300


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def build_context(user_id: str, user_message: str,
                  current_project_id: str = "",
                  session_id: str = "") -> str:
    """Build concise memory context block for the system prompt.

    Returns a string like:

    ── USER PROFILE ──
    Language: Roman Urdu
    ...

    ── ACTIVE PROJECT: SONIC AI ──
    Architecture: Python/PyQt6...

    ── RELEVANT MEMORIES ──
    • User prefers existing systems frozen during changes (high confidence)
    ...

    ── ACTIVE TASKS ──
    • Fix STT fallback (in_progress)

    ── PREFERENCES ──
    • response_language: Roman Urdu (fact, reinforced 5x)
    """
    sections = []

    # 1. User preferences (compact)
    prefs = retrieval.retrieve_preferences(user_id)
    if prefs:
        pref_lines = []
        budget = _PREF_BUDGET
        for p in prefs:
            line = f"• {p['key']}: {p['value']} ({p['confidence']}, {p['source']})"
            if len(line) > 120:
                line = line[:117] + "..."
            if budget - len(line) < 0:
                pref_lines.append("• ...")
                break
            pref_lines.append(line)
            budget -= len(line) + 1
        if pref_lines:
            sections.append("── PREFERENCES ──\n" + "\n".join(pref_lines))

    # 2. Retrieved memories based on query
    memories = retrieval.retrieve_context(
        user_id, user_message, limit=12,
        project_id=current_project_id,
    )
    if memories:
        mem_lines = []
        budget = _TOKEN_BUDGET - _PREF_BUDGET
        for m in memories:
            conf_prefix = ""
            if m["confidence"] == "fact":
                conf_prefix = "[fact] "
            elif m["confidence"] == "inferred":
                conf_prefix = "[inferred] "
            line = f"• {conf_prefix}{_truncate(m['content'], 140)} ({m['importance']})"
            if budget - len(line) < 0:
                break
            mem_lines.append(line)
            budget -= len(line) + 1
        if mem_lines:
            sections.append("── RELEVANT MEMORIES ──\n" + "\n".join(mem_lines))

    # 3. Active project context
    project_ctx = retrieval.retrieve_project_context(user_id, project_id=current_project_id)
    if project_ctx.get("project"):
        p = project_ctx["project"]
        proj_lines = []
        if p.get("name"):
            proj_lines.append(f"Name: {p['name']}")
        if p.get("technology_stack"):
            proj_lines.append(f"Stack: {_truncate(p['technology_stack'], 100)}")
        if p.get("architecture_summary"):
            proj_lines.append(f"Arch: {_truncate(p['architecture_summary'], 150)}")
        if p.get("known_constraints"):
            proj_lines.append(f"Constraints: {_truncate(p['known_constraints'], 100)}")
        if p.get("known_bugs"):
            proj_lines.append(f"Bugs: {_truncate(p['known_bugs'], 100)}")
        if p.get("conventions"):
            proj_lines.append(f"Conventions: {_truncate(p['conventions'], 100)}")
        if proj_lines:
            name = p.get("name", "Active Project")
            sections.append(f"── PROJECT: {name} ──\n" + "\n".join(proj_lines))

    # 4. Unresolved tasks
    tasks = retrieval.retrieve_unresolved_tasks(user_id, limit=5)
    if tasks:
        task_lines = []
        for t in tasks:
            line = f"• {_truncate(t['objective'], 80)} ({t['status']})"
            task_lines.append(line)
        sections.append("── UNRESOLVED TASKS ──\n" + "\n".join(task_lines))

    # 5. Recent session summaries
    sessions = db.list_session_summaries(user_id, limit=3)
    if sessions:
        sess_lines = []
        for s in sessions:
            topic = s.topic or "general"
            line = f"• [{topic}] {_truncate(s.summary, 120)}"
            sess_lines.append(line)
        sections.append("── RECENT SESSIONS ──\n" + "\n".join(sess_lines))

    if not sections:
        return ""

    return "\n\n".join(sections)
