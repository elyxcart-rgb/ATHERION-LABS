"""Memory extraction from conversations for SONIC AI."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import db
from .models import (
    Memory, MemoryType, Importance, Confidence, MemoryStatus,
    Preference, _now_iso, _uuid
)

# ── explicit commands ───────────────────────────────────────────────

_REMEMBER_PATTERNS = [
    re.compile(r"remember\s+(?:that\s+)?(.+)", re.I),
    re.compile(r"(?:yaad\s+(?:rakh(?:o|na)?)|yaad\s+karo)\s+(.+)", re.I),
    re.compile(r"don'?t\s+forget\s+(.+)", re.I),
]

_FORGET_PATTERNS = [
    re.compile(r"forget\s+(?:that\s+|everything\s+about\s+|all\s+about\s+)?(.+)", re.I),
    re.compile(r"bhool\s+(?:jao|ja)\s+(.+)", re.I),
    re.compile(r"(?:don'?t\s+remember|remove)\s+(.+)", re.I),
]

_QUERY_PATTERNS = [
    re.compile(r"what\s+do\s+you\s+remember\s+(?:about\s+me|from|that)", re.I),
    re.compile(r"(?:kya\s+(?:yaad\s+hai|yaad\s+karo))", re.I),
    re.compile(r"what\s+(?:have\s+you\s+learned|did\s+we\s+do|was\s+my)", re.I),
]


def is_remember_command(text: str) -> bool:
    return any(p.search(text) for p in _REMEMBER_PATTERNS)


def is_forget_command(text: str) -> bool:
    return any(p.search(text) for p in _FORGET_PATTERNS)


def is_query_command(text: str) -> bool:
    return any(p.search(text) for p in _QUERY_PATTERNS)


def extract_remember_content(text: str) -> str | None:
    for p in _REMEMBER_PATTERNS:
        m = p.search(text)
        if m:
            return m.group(1).strip().rstrip(".")
    return None


def extract_forget_content(text: str) -> str | None:
    for p in _FORGET_PATTERNS:
        m = p.search(text)
        if m:
            return m.group(1).strip().rstrip(".")
    return None


# ── implicit extraction ────────────────────────────────────────────

_PREF_SIGNALS = {
    "prefer": "explicit",
    "i like": "explicit",
    "i want": "explicit",
    "use roman urdu": "explicit",
    "roman urdu": "explicit",
    "don't touch": "explicit",
    "don't modify": "explicit",
    "keep": "explicit",
    "freeze": "explicit",
    "always": "explicit",
    "never": "explicit",
    "my language": "explicit",
    "my name is": "explicit",
    "i am": "explicit",
    "i work": "explicit",
    "i use": "explicit",
    "mujhe": "explicit",
    "mera": "explicit",
    "meri": "explicit",
}

_FACT_SIGNALS = [
    re.compile(r"(?:my|mera|meri)\s+(?:name|project|language|city|job|role)\s+(?:is|hai|hoon?)\s+(.+)", re.I),
    re.compile(r"(?:i|main)\s+(?:am|hoon?|work\s+at|use)\s+(.+)", re.I),
    re.compile(r"(?:this|ye)\s+project\s+(?:is|hai)\s+(?:called|named)?\s*(.+)", re.I),
    re.compile(r"(?:built|using|uses|uses?|stack)\s+(.+)", re.I),
]

_LESSON_SIGNALS = [
    "lesson",
    "learned that",
    "turned out",
    "next time",
    "should have",
    "mistake was",
    "was wrong because",
    "kam kaam",
]


def extract_from_turn(user_text: str, assistant_text: str,
                      user_id: str, session_id: str = "",
                      project_id: str = "") -> list[dict]:
    """Analyze a conversation turn and extract candidate memories.

    Returns list of candidate dicts with:
        type, content, importance, confidence, tags, reason
    """
    candidates = []
    text = user_text.lower()
    now = _now_iso()

    # ── explicit preference/fact signals ──
    for signal, source in _PREF_SIGNALS.items():
        if signal in text:
            # Extract the sentence containing the signal
            sentence = _extract_sentence(user_text, signal)
            if sentence:
                mem_type = MemoryType.PREFERENCE.value
                if any(kw in text for kw in ("my name", "mera naam", "i am", "main")):
                    mem_type = MemoryType.FACT.value
                candidates.append({
                    "type": mem_type,
                    "content": sentence,
                    "importance": Importance.HIGH.value,
                    "confidence": Confidence.FACT.value if source == "explicit" else Confidence.INFERRED.value,
                    "tags": _auto_tags(sentence),
                    "reason": f"explicit signal: {signal}",
                })
            break

    # ── fact extraction ──
    for pattern in _FACT_SIGNALS:
        m = pattern.search(user_text)
        if m:
            sentence = _extract_sentence(user_text, m.group(0)[:20])
            if sentence:
                candidates.append({
                    "type": MemoryType.FACT.value,
                    "content": sentence,
                    "importance": Importance.HIGH.value,
                    "confidence": Confidence.FACT.value,
                    "tags": _auto_tags(sentence),
                    "reason": "fact pattern match",
                })
            break

    # ── lesson extraction from assistant response ──
    if assistant_text:
        for signal in _LESSON_SIGNALS:
            if signal in assistant_text.lower():
                sentence = _extract_sentence(assistant_text, signal)
                if sentence:
                    candidates.append({
                        "type": MemoryType.LESSON.value,
                        "content": sentence,
                        "importance": Importance.MEDIUM.value,
                        "confidence": Confidence.LESSON.value,
                        "tags": "lesson",
                        "reason": f"lesson signal: {signal}",
                    })
                break

    # ── project reference ──
    project_patterns = [
        re.compile(r"(?:project|repo|codebase)\s+(?:is|called|named)?\s*(?:sonic|mark|open\s*code)", re.I),
        re.compile(r"(?:sonic|mark\s*ii)\s+(?:ai|assistant|project)", re.I),
    ]
    for pp in project_patterns:
        if pp.search(user_text):
            candidates.append({
                "type": MemoryType.PROJECT.value,
                "content": _extract_sentence(user_text, "project") or user_text[:150],
                "importance": Importance.HIGH.value,
                "confidence": Confidence.FACT.value,
                "tags": "project,reference",
                "reason": "project reference detected",
            })
            break

    # ── correction / contradiction ──
    correction_signals = ["no,", "nahi,", "actually", "galat", "wrong", "i meant", "not that"]
    if any(s in text for s in correction_signals):
        candidates.append({
            "type": MemoryType.EPISODIC.value,
            "content": f"User corrected themselves: {_truncate(user_text, 150)}",
            "importance": Importance.MEDIUM.value,
            "confidence": Confidence.OBSERVATION.value,
            "tags": "correction",
            "reason": "correction signal detected",
        })

    return candidates


def _extract_sentence(text: str, hint: str) -> str | None:
    """Extract the sentence containing the hint, truncated to a reasonable length."""
    sentences = re.split(r'[.!?\n]', text)
    for s in sentences:
        if hint.lower() in s.lower():
            s = s.strip()
            if len(s) > 10:
                return s[:200]
    # Fallback: return first non-trivial sentence
    for s in sentences:
        s = s.strip()
        if len(s) > 15:
            return s[:200]
    return None


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] + "..." if len(text) > max_len else text


def _auto_tags(text: str) -> str:
    """Auto-generate tags from content."""
    tags = []
    text_lower = text.lower()
    tag_signals = {
        "language": ["urdu", "english", "roman urdu", "zaban", "language"],
        "preference": ["prefer", "like", "want", "don't like", "hate"],
        "project": ["project", "repo", "codebase", "sonic", "open code"],
        "tech": ["python", "pyqt", "javascript", "typescript", "react", "node"],
        "workflow": ["test", "deploy", "release", "commit", "branch"],
        "personal": ["name", "city", "job", "role", "work", "live"],
        "stt": ["stt", "speech", "transcri", "whisper", "microphone"],
        "tts": ["tts", "voice", "speech synthesis", "speak"],
        "ui": ["ui", "interface", "theme", "color", "orb", "animation"],
    }
    for tag, keywords in tag_signals.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)
    return ",".join(tags) if tags else ""


# ── process extracted candidates ───────────────────────────────────

def process_candidates(candidates: list[dict], user_id: str,
                       session_id: str = "", project_id: str = "") -> int:
    """Validate, deduplicate, and store candidate memories.
    Returns count of memories actually stored."""
    stored = 0
    for c in candidates:
        content = c.get("content", "").strip()
        if not content or len(content) < 10:
            continue

        # Validate
        if _is_sensitive(content):
            continue

        # Dedup check
        similar = db.find_similar_content(user_id, content)
        if similar:
            # Reinforce existing instead of creating duplicate
            best = similar[0]
            db.update_memory_fields(
                best.memory_id, user_id,
                reinforcement_count=best.reinforcement_count + 1,
                last_accessed_at=_now_iso(),
            )
            continue

        # Create new memory
        mem = Memory(
            user_id=user_id,
            memory_type=c.get("type", MemoryType.EPISODIC.value),
            content=content,
            importance=c.get("importance", Importance.MEDIUM.value),
            confidence=c.get("confidence", Confidence.OBSERVATION.value),
            tags=c.get("tags", ""),
            project_id=project_id,
            session_id=session_id,
        )
        db.store_memory(mem)
        stored += 1

    return stored


def handle_remember_command(text: str, user_id: str,
                            session_id: str = "",
                            project_id: str = "") -> str:
    """Process an explicit 'remember X' command. Returns response string."""
    content = extract_remember_content(text)
    if not content:
        return "Kya yaad rakhna hai? Batao."

    # Determine type
    mem_type = MemoryType.FACT.value
    if any(kw in content.lower() for kw in ("prefer", "like", "want", "use", "always", "never")):
        mem_type = MemoryType.PREFERENCE.value

    # Dedup
    similar = db.find_similar_content(user_id, content)
    if similar:
        best = similar[0]
        db.update_memory_fields(
            best.memory_id, user_id,
            reinforcement_count=best.reinforcement_count + 1,
            last_accessed_at=_now_iso(),
        )
        return f"Updated: {best.content[:80]}"

    mem = Memory(
        user_id=user_id,
        memory_type=mem_type,
        content=content,
        importance=Importance.HIGH.value,
        confidence=Confidence.FACT.value,
        tags=_auto_tags(content),
        project_id=project_id,
        session_id=session_id,
    )
    db.store_memory(mem)
    return f"Yaad rakh liya: {content[:80]}"


def handle_forget_command(text: str, user_id: str) -> str:
    """Process a 'forget X' command. Returns response string."""
    content = extract_forget_content(text)
    if not content:
        return "Kya bhoolna hai? Batao."

    # Find matching memories
    matches = db.find_similar_content(user_id, content)
    if not matches:
        # Try keyword search
        matches = db.search_memories(user_id, content, limit=5)

    if not matches:
        return f"Mujhe '{content[:50]}' ke baare mein kuch yaad nahi hai."

    forgotten = 0
    for m in matches:
        db.update_memory_fields(
            m.memory_id, user_id,
            status=MemoryStatus.FORGOTTEN.value,
        )
        forgotten += 1

    return f"Bhool gaya: {forgotten} cheezein delete ho gayi."


def handle_query_command(user_id: str) -> str:
    """Respond to 'what do you remember?' queries."""
    prefs = db.get_active_preferences(user_id)
    memories = db.list_memories(user_id, limit=10)
    projects = db.list_projects(user_id)
    tasks = db.list_tasks(user_id, status="in_progress")

    parts = []
    if prefs:
        pref_strs = [f"  • {p.key}: {p.value}" for p in prefs[:5]]
        parts.append("Preferences:\n" + "\n".join(pref_strs))
    if projects:
        proj_strs = [f"  • {p.name}" for p in projects[:5]]
        parts.append("Projects:\n" + "\n".join(proj_strs))
    if tasks:
        task_strs = [f"  • {t.objective[:60]}" for t in tasks[:5]]
        parts.append("Active tasks:\n" + "\n".join(task_strs))
    if memories:
        mem_strs = [f"  • [{m.memory_type}] {m.content[:80]}" for m in memories[:8]]
        parts.append("Memories:\n" + "\n".join(mem_strs))

    if not parts:
        return "Mujhe abhi tumhare baare mein kuch yaad nahi hai. Baat karte raho, seekhta rahunga."

    return "Mujhe ye yaad hai:\n\n" + "\n\n".join(parts)


def _is_sensitive(content: str) -> bool:
    """Reject memories that contain sensitive data."""
    sensitive = [
        "password", "api key", "token", "secret", "credential",
        "credit card", "ssn", "social security",
    ]
    lower = content.lower()
    return any(s in lower for s in sensitive)
