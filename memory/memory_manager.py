"""SONIC AI Memory Manager — bridges legacy JSON store with new SQLite brain.

The legacy long_term.json store is preserved for backward compatibility.
The new SQLite store provides user isolation, FTS5 search, and structured
memory types. Both systems coexist; the new system is the primary brain.
"""
import json
import re
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys

from . import db
from .models import (
    Memory, MemoryType, Importance, Confidence, MemoryStatus,
    Preference, _now_iso, _uuid
)
from . import extractor
from . import consolidation
from . import retrieval
from .context_builder import build_context


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR         = get_base_dir()
MEMORY_PATH      = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380

MEMORY_MAX_CHARS  = 200_000
PROMPT_CORE_CHARS = 900
PROMPT_INDEX_CHARS = 420
PROMPT_MAX_PER_CATEGORY = 6

# ── user isolation ──────────────────────────────────────────────────

_current_user_id: str = ""

def set_user_id(user_id: str):
    global _current_user_id
    _current_user_id = user_id
    print(f"[Memory] 🔐 Active user: {user_id}")

def get_user_id() -> str:
    return _current_user_id


# ── init ────────────────────────────────────────────────────────────

def init_memory_system():
    """Initialize the new SQLite memory brain. Call once at startup."""
    db.init_db()
    print("[Memory] ✅ SQLite brain initialized")


# ── legacy JSON store (preserved for backward compat) ───────────────

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries

_trim_notifier = None

def set_trim_notifier(fn) -> None:
    global _trim_notifier
    _trim_notifier = fn

def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    dropped = []
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        dropped.append(f"{cat}/{key}")
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    if dropped and _trim_notifier:
        try:
            _trim_notifier(
                f"SYS: Memory full — forgot {len(dropped)} oldest entries "
                f"({', '.join(dropped[:3])}{'…' if len(dropped) > 3 else ''})"
            )
        except Exception:
            pass
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val

def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed

def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory

def _entry_value(entry) -> str:
    if isinstance(entry, dict):
        return str(entry.get("value", "") or "").strip()
    return str(entry or "").strip()

def _pretty(key: str) -> str:
    return key.replace("_", " ").strip()

_CATEGORY_LABELS = {
    "preferences":   "Preferences",
    "projects":      "Active projects / goals",
    "relationships": "People in their life",
    "wishes":        "Wishes / plans",
    "notes":         "Notes",
}

_IDENTITY_FIELDS = ["name", "age", "birthday", "city", "job",
                    "language", "school", "nationality"]

def format_memory_for_prompt(memory: dict | None) -> str:
    """Legacy prompt formatter — used when new system has no user_id yet."""
    if not memory:
        return ""
    core_lines: list[str] = []
    identity = memory.get("identity", {}) or {}
    for field in _IDENTITY_FIELDS:
        val = _entry_value(identity.get(field))
        if not val:
            continue
        if field == "language":
            core_lines.append(
                f"Has spoken to you in: {val} (an observation about the past — "
                f"always answer in the language of their CURRENT message)")
        else:
            core_lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in _IDENTITY_FIELDS:
            continue
        val = _entry_value(entry)
        if val:
            core_lines.append(f"{_pretty(key).title()}: {val}")

    rest: list[tuple[str, str, str, str]] = []
    for cat in _CATEGORY_LABELS:
        for key, entry in (memory.get(cat, {}) or {}).items():
            val = _entry_value(entry)
            if not val:
                continue
            updated = (entry.get("updated", "") if isinstance(entry, dict) else "") or "0000-00-00"
            rest.append((updated, cat, key, val))
    rest.sort(key=lambda t: t[0], reverse=True)

    used    = sum(len(l) + 1 for l in core_lines)
    shown: dict[str, list[str]] = {}
    overflow: dict[str, list[str]] = {}
    per_cat_used: dict[str, int] = {}
    for _updated, cat, key, val in rest:
        line = f"  - {_pretty(key).title()}: {val}"
        if (per_cat_used.get(cat, 0) < PROMPT_MAX_PER_CATEGORY
                and used + len(line) + 1 <= PROMPT_CORE_CHARS):
            shown.setdefault(cat, []).append(line)
            per_cat_used[cat] = per_cat_used.get(cat, 0) + 1
            used += len(line) + 1
        else:
            overflow.setdefault(cat, []).append(_pretty(key))

    indexed: list[str] = []
    if overflow:
        cats  = [c for c in _CATEGORY_LABELS if overflow.get(c)]
        cursor = {c: 0 for c in cats}
        while cats:
            for cat in list(cats):
                i = cursor[cat]
                if i >= len(overflow[cat]):
                    cats.remove(cat)
                    continue
                indexed.append(overflow[cat][i])
                cursor[cat] = i + 1

    for cat, label in _CATEGORY_LABELS.items():
        if shown.get(cat):
            core_lines.append("")
            core_lines.append(f"{label}:")
            core_lines.extend(shown[cat])

    if not core_lines and not indexed:
        return ""

    out = [
        "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]",
        *core_lines,
    ]

    if indexed:
        budget, names = PROMPT_INDEX_CHARS, []
        for n in indexed:
            if budget - len(n) - 2 < 0:
                break
            names.append(n)
            budget -= len(n) + 2
        if names:
            out.append("")
            out.append(
                "[ALSO REMEMBERED — values not shown here. Call recall_memory "
                "with a keyword to read any of these before saying you do not know]"
            )
            out.append(", ".join(names)
                       + (f" (+{len(indexed) - len(names)} more)"
                          if len(indexed) > len(names) else ""))

    return "\n".join(out) + "\n"


def _score(query_words: list[str], cat: str, key: str, value: str) -> int:
    hay_key = _pretty(key).lower()
    hay_val = value.lower()
    score   = 0
    for w in query_words:
        if not w:
            continue
        if w == hay_key:
            score += 10
        elif w in hay_key:
            score += 6
        if w in hay_val:
            score += 3
        if w in cat:
            score += 1
    return score

def search_memory(query: str, limit: int = 8) -> str:
    """Recall tool — now uses new SQLite brain when user_id is available."""
    uid = get_user_id()
    if uid:
        return _search_new(query, limit, uid)
    return _search_legacy(query, limit)

def _search_new(query: str, limit: int, user_id: str) -> str:
    """Search using new FTS5 brain."""
    results = retrieval.retrieve_context(user_id, query, limit=limit)
    if not results:
        return f"Mujhe '{query}' ke baare mein kuch yaad nahi hai." if query else "Abhi kuch yaad nahi hai."

    lines = []
    for r in results:
        conf = f" [{r['confidence']}]" if r["confidence"] != "observation" else ""
        lines.append(f"• {r['content'][:120]}{conf}")

    head = f"Yaad hai '{query}':" if query else "Mujhe ye yaad hai:"
    return head + "\n" + "\n".join(lines)

def _search_legacy(query: str, limit: int) -> str:
    memory = load_memory()
    words  = [w for w in re.split(r"[^\w]+", (query or "").lower()) if len(w) > 1]
    rows: list[tuple[int, str, str, str]] = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            s = _score(words, cat, key, val) if words else 1
            if s > 0:
                rows.append((s, cat, key, val))
    if not rows:
        return (f"Nothing stored about '{query}'." if query
                else "I have not stored anything about this person yet.")
    rows.sort(key=lambda r: (-r[0], r[2]))
    lines = [f"{cat}/{_pretty(key)}: {val}" for _s, cat, key, val in rows[:max(1, limit)]]
    head  = (f"Stored facts matching '{query}':" if query
             else "Everything currently stored:")
    more  = (f"\n(+{len(rows) - len(lines)} more — search with a narrower keyword)"
             if len(rows) > len(lines) else "")
    return head + "\n" + "\n".join(lines) + more


def all_entries_for_ui() -> list[dict]:
    uid = get_user_id()
    if uid:
        return _entries_new_for_ui(uid)
    return _entries_legacy_for_ui()

def _entries_new_for_ui(user_id: str) -> list[dict]:
    memories = db.list_memories(user_id, limit=200)
    prefs = db.get_active_preferences(user_id)
    projects = db.list_projects(user_id)
    rows = []
    for m in memories:
        rows.append({
            "category": m.memory_type,
            "key": m.memory_id,
            "value": m.content[:200],
            "updated": m.updated_at,
            "importance": m.importance,
            "confidence": m.confidence,
        })
    for p in prefs:
        rows.append({
            "category": f"pref:{p.category}",
            "key": p.key,
            "value": p.value,
            "updated": p.updated_at,
        })
    for p in projects:
        rows.append({
            "category": "project",
            "key": p.name,
            "value": p.technology_stack or p.architecture_summary or "active",
            "updated": p.last_activity,
        })
    rows.sort(key=lambda r: (r.get("updated") or "0000-00-00"), reverse=True)
    return rows

def _entries_legacy_for_ui() -> list[dict]:
    memory = load_memory()
    rows = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            val = _entry_value(entry)
            if not val:
                continue
            rows.append({
                "category": cat,
                "key":      key,
                "value":    val,
                "updated":  (entry.get("updated", "") if isinstance(entry, dict) else ""),
            })
    rows.sort(key=lambda r: (r["updated"] or "0000-00-00"), reverse=True)
    return rows


def remember(key: str, value: str, category: str = "notes") -> str:
    uid = get_user_id()
    if uid:
        return _remember_new(key, value, category, uid)
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"

def _remember_new(key: str, value: str, category: str, user_id: str) -> str:
    # Check for existing preference with same key
    existing = db.find_preference(user_id, category, key)
    if existing:
        db.update_memory_fields(
            existing.preference_id, user_id,
            value=value,
            reinforcement_count=existing.reinforcement_count + 1,
            last_confirmed_at=_now_iso(),
        )
        return f"Updated: {key} = {value}"

    pref = Preference(
        user_id=user_id,
        category=category,
        key=key,
        value=value,
        confidence=Confidence.FACT.value,
        source="explicit",
    )
    db.store_preference(pref)
    return f"Remembered: {key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    uid = get_user_id()
    if uid:
        return _forget_new(key, category, uid)
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"

def _forget_new(key: str, category: str, user_id: str) -> str:
    # Try preferences first
    pref = db.find_preference(user_id, category, key)
    if pref:
        db.update_memory_fields(
            pref.preference_id, user_id,
            status=MemoryStatus.FORGOTTEN.value,
        )
        return f"Bhool gaya: {key}"

    # Try memories
    results = db.search_memories(user_id, key, limit=5)
    if results:
        for m in results:
            db.update_memory_fields(
                m.memory_id, user_id,
                status=MemoryStatus.FORGOTTEN.value,
            )
        return f"Bhool gaya: {len(results)} memories bhool gaya."

    return f"Nahi mila: {key}"


forget_memory = forget


# ── session memory (legacy JSON, preserved) ─────────────────────────

_SESSION_MAX = 3

def save_session_summary(summary: str, language: str = "") -> None:
    """Save session summary to both legacy JSON and new SQLite."""
    summary = (summary or "").strip()
    if not summary:
        return

    # Save to new SQLite brain
    uid = get_user_id()
    if uid:
        ss = SessionSummary(
            user_id=uid,
            summary=summary[:500],
            created_at=_now_iso(),
        )
        db.store_session_summary(ss)

    # Also save to legacy JSON
    memory   = load_memory()
    sessions = memory.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    entry: dict = {
        "date":    datetime.now().strftime("%Y-%m-%d"),
        "summary": summary[:280],
    }
    if language:
        entry["language"] = language
    sessions.append(entry)
    memory["sessions"] = sessions[-_SESSION_MAX:]
    with _lock:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"[Memory] 📝 Session saved ({entry['date']}): {summary[:60]}…")

def pop_last_session() -> dict | None:
    with _lock:
        if not MEMORY_PATH.exists():
            return None
        try:
            memory   = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list) or not sessions:
                return None
            entry = sessions.pop()
            memory["sessions"] = sessions
            MEMORY_PATH.write_text(
                json.dumps(memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return entry
        except Exception as e:
            print(f"[Memory] ⚠️ pop_last_session error: {e}")
            return None


# ── new brain public API ───────────────────────────────────────────

def handle_remember(text: str, session_id: str = "", project_id: str = "") -> str:
    """Handle explicit 'remember X' command."""
    uid = get_user_id()
    if not uid:
        return "Pehle login karo, phir memory save hogi."
    return extractor.handle_remember_command(text, uid, session_id, project_id)

def handle_forget(text: str) -> str:
    """Handle explicit 'forget X' command."""
    uid = get_user_id()
    if not uid:
        return "Pehle login karo."
    return extractor.handle_forget_command(text, uid)

def handle_memory_query() -> str:
    """Handle 'what do you remember' query."""
    uid = get_user_id()
    if not uid:
        return "Pehle login karo."
    return extractor.handle_query_command(uid)

def extract_from_turn(user_text: str, assistant_text: str,
                      session_id: str = "", project_id: str = "") -> int:
    """Extract memories from a conversation turn. Returns count stored."""
    uid = get_user_id()
    if not uid:
        return 0
    candidates = extractor.extract_from_turn(
        user_text, assistant_text, uid, session_id, project_id
    )
    return extractor.process_candidates(candidates, uid, session_id, project_id)

def build_prompt_context(user_message: str, project_id: str = "",
                         session_id: str = "") -> str:
    """Build memory context for the system prompt."""
    uid = get_user_id()
    if not uid:
        return format_memory_for_prompt(load_memory())
    return build_context(uid, user_message, project_id, session_id)

def consolidate_memory() -> dict:
    """Run consolidation cycle."""
    uid = get_user_id()
    if not uid:
        return {}
    return consolidation.consolidate(uid)

def get_memory_stats() -> dict:
    """Get memory stats for observability."""
    uid = get_user_id()
    if not uid:
        return {}
    return db.get_db_stats(uid)
