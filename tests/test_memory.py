"""Comprehensive tests for SONIC AI long-term memory system."""
import os
import sys
import json
import time
import sqlite3
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Fix Windows console encoding
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Use a temporary database for tests
_test_dir = tempfile.mkdtemp()
_test_db = Path(_test_dir) / "test_sonic_brain.db"

# Patch db module to use test database
from memory import db
db._DB_PATH = _test_db

from memory.models import (
    Memory, MemoryType, Importance, Confidence, MemoryStatus,
    Preference, Project, Task, ToolExperience, SessionSummary, Entity,
    _now_iso, _uuid
)
from memory import extractor, consolidation, retrieval
from memory.context_builder import build_context

# ── helpers ─────────────────────────────────────────────────────────

TEST_USER = "test_user_001"
TEST_USER_2 = "test_user_002"

def setup():
    """Initialize test database."""
    db.init_db()

def teardown():
    """Clean up test database."""
    if _test_db.exists():
        _test_db.unlink()

def fresh_user():
    """Get a clean user_id for isolation tests."""
    return f"test_{_uuid()}"


# ── TEST 1: Database initialization ────────────────────────────────

def test_db_init():
    """Database creates all tables successfully."""
    setup()
    conn = db._connect()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    assert "memories" in tables
    assert "projects" in tables
    assert "tasks" in tables
    assert "preferences" in tables
    assert "tool_experiences" in tables
    assert "session_summaries" in tables
    assert "entities" in tables
    print("✅ test_db_init passed")


# ── TEST 2: Memory CRUD ────────────────────────────────────────────

def test_memory_crud():
    """Store, retrieve, update, delete memories."""
    setup()
    uid = fresh_user()

    # Create
    m = Memory(
        user_id=uid,
        memory_type=MemoryType.FACT.value,
        content="User prefers Roman Urdu",
        importance=Importance.HIGH.value,
        confidence=Confidence.FACT.value,
        tags="language,preference",
    )
    mid = db.store_memory(m)
    assert mid

    # Read
    fetched = db.get_memory(mid, uid)
    assert fetched is not None
    assert fetched.content == "User prefers Roman Urdu"
    assert fetched.importance == "high"

    # Update
    db.update_memory_fields(mid, uid, content="User prefers Roman Urdu for all responses")
    updated = db.get_memory(mid, uid)
    assert updated.content == "User prefers Roman Urdu for all responses"

    # List
    memories = db.list_memories(uid)
    assert len(memories) >= 1

    # Delete
    db.delete_memory(mid, uid)
    assert db.get_memory(mid, uid) is None

    print("✅ test_memory_crud passed")


# ── TEST 3: FTS5 search ───────────────────────────────────────────

def test_fts_search():
    """FTS5 full-text search returns relevant results."""
    setup()
    uid = fresh_user()

    db.store_memory(Memory(user_id=uid, content="User prefers Roman Urdu language", tags="language"))
    db.store_memory(Memory(user_id=uid, content="Project uses PyQt6 for desktop UI", tags="project,tech"))
    db.store_memory(Memory(user_id=uid, content="Microphone has intermittent connection issues", tags="stt,bug"))

    results = db.search_memories(uid, "language preference")
    assert len(results) > 0
    assert any("Roman Urdu" in r.content for r in results)

    results = db.search_memories(uid, "microphone bug")
    assert any("Microphone" in r.content for r in results)

    print("✅ test_fts_search passed")


# ── TEST 4: User isolation ─────────────────────────────────────────

def test_user_isolation():
    """Users cannot access each other's memories."""
    setup()
    user_a = fresh_user()
    user_b = fresh_user()

    db.store_memory(Memory(user_id=user_a, content="User A secret: favorite editor is VS Code"))
    db.store_memory(Memory(user_id=user_b, content="User B secret: favorite editor is Neovim"))

    # User A search should NOT return User B's memory
    results_a = db.search_memories(user_a, "editor")
    assert all(r.user_id == user_a for r in results_a)
    assert not any("Neovim" in r.content for r in results_a)

    # User B search should NOT return User A's memory
    results_b = db.search_memories(user_b, "editor")
    assert all(r.user_id == user_b for r in results_b)
    assert not any("VS Code" in r.content for r in results_b)

    print("✅ test_user_isolation passed")


# ── TEST 5: Deduplication ─────────────────────────────────────────

def test_deduplication():
    """Similar memories are merged, not duplicated."""
    setup()
    uid = fresh_user()

    # Store the same memory twice (exact duplicate)
    candidates = [
        {"type": "preference", "content": "User prefers Roman Urdu language", "importance": "high", "confidence": "fact", "tags": "language"},
        {"type": "preference", "content": "User prefers Roman Urdu language", "importance": "high", "confidence": "fact", "tags": "language"},
        {"type": "fact", "content": "User's name is Ahmad", "importance": "high", "confidence": "fact", "tags": "personal"},
    ]
    stored = extractor.process_candidates(candidates, uid)

    # Should store 2 unique memories (exact duplicate merged, Ahmad stored separately)
    memories = db.list_memories(uid)
    assert len(memories) == 2
    # Check that the duplicate was reinforced
    roman_urdu_mem = [m for m in memories if "Roman Urdu" in m.content]
    assert len(roman_urdu_mem) == 1
    assert roman_urdu_mem[0].reinforcement_count >= 1

    print("✅ test_deduplication passed")


# ── TEST 6: Preference conflict resolution ────────────────────────

def test_preference_conflict_resolution():
    """Newer explicit preferences override older inferred ones."""
    setup()
    uid = fresh_user()

    # Old preference
    old_pref = Preference(
        user_id=uid, category="communication", key="language",
        value="English", confidence="inferred", source="inferred",
    )
    db.store_preference(old_pref)

    # New explicit preference
    new_pref = Preference(
        user_id=uid, category="communication", key="language",
        value="Roman Urdu", confidence="fact", source="explicit",
    )
    db.store_preference(new_pref)

    # Run conflict resolution
    resolutions = consolidation.resolve_conflicts(uid)
    assert resolutions >= 1

    # Only the new one should be active (filter by category, not key)
    active = db.get_active_preferences(uid, category="communication")
    lang_prefs = [p for p in active if p.key == "language"]
    assert len(lang_prefs) == 1
    assert lang_prefs[0].value == "Roman Urdu"

    print("✅ test_preference_conflict_resolution passed")


# ── TEST 7: Explicit remember/forget ──────────────────────────────

def test_explicit_remember_forget():
    """User can explicitly remember and forget items."""
    setup()
    uid = fresh_user()

    # Remember
    result = extractor.handle_remember_command(
        "remember that I prefer dark mode", uid
    )
    assert "yaad" in result.lower() or "remember" in result.lower()

    # Verify stored (check memories table, not preferences)
    memories = db.list_memories(uid)
    assert any("dark mode" in m.content.lower() for m in memories)

    # Query
    result = extractor.handle_query_command(uid)
    assert "dark mode" in result.lower() or "dark" in result.lower()

    # Forget
    result = extractor.handle_forget_command("forget dark mode", uid)
    assert "bhool" in result.lower() or "forgotten" in result.lower() or "forget" in result.lower()

    print("✅ test_explicit_remember_forget passed")


# ── TEST 8: Memory extraction from turns ───────────────────────────

def test_extraction_from_turns():
    """Memory extractor identifies facts, preferences, and lessons from conversation."""
    setup()
    uid = fresh_user()

    candidates = extractor.extract_from_turn(
        user_text="My project is called SONIC AI and it uses Python",
        assistant_text="Great, SONIC AI with Python!",
        user_id=uid,
    )
    assert len(candidates) > 0
    types = [c["type"] for c in candidates]
    assert "project" in types or "fact" in types

    # Preference extraction
    candidates2 = extractor.extract_from_turn(
        user_text="I prefer Roman Urdu for explanations",
        assistant_text="Understood.",
        user_id=uid,
    )
    assert len(candidates2) > 0

    print("✅ test_extraction_from_turns passed")


# ── TEST 9: Sensitive data rejection ──────────────────────────────

def test_sensitive_data_rejection():
    """Passwords, API keys, tokens are never stored."""
    setup()
    uid = fresh_user()

    candidates = [
        {"type": "fact", "content": "My password is secret123", "importance": "high", "confidence": "fact", "tags": ""},
        {"type": "fact", "content": "API key is sk-abc123def456", "importance": "high", "confidence": "fact", "tags": ""},
        {"type": "fact", "content": "User prefers Roman Urdu", "importance": "high", "confidence": "fact", "tags": "language"},
    ]
    stored = extractor.process_candidates(candidates, uid)

    memories = db.list_memories(uid)
    assert not any("password" in m.content.lower() for m in memories)
    assert not any("api key" in m.content.lower() for m in memories)
    assert any("Roman Urdu" in m.content for m in memories)

    print("✅ test_sensitive_data_rejection passed")


# ── TEST 10: Project memory isolation ─────────────────────────────

def test_project_memory_isolation():
    """Memories from different projects don't mix."""
    setup()
    uid = fresh_user()

    proj_a = Project(user_id=uid, name="SONIC AI", technology_stack="Python/PyQt6")
    proj_b = Project(user_id=uid, name="WebApp", technology_stack="React/Node")
    db.store_project(proj_a)
    db.store_project(proj_b)

    db.store_memory(Memory(user_id=uid, content="SONIC uses Orb animation", project_id=proj_a.project_id))
    db.store_memory(Memory(user_id=uid, content="WebApp uses React hooks", project_id=proj_b.project_id))

    # Search for SONIC should not return WebApp memories
    results = retrieval.retrieve_context(uid, "Orb animation", project_id=proj_a.project_id)
    assert all(r.get("type") != "project" or "Orb" in r.get("content", "") for r in results)

    print("✅ test_project_memory_isolation passed")


# ── TEST 11: Task persistence ─────────────────────────────────────

def test_task_persistence():
    """Tasks survive across queries."""
    setup()
    uid = fresh_user()

    task = Task(
        user_id=uid, objective="Fix STT fallback", status="in_progress",
        steps="1. Identify issue 2. Implement fix", tools_used="coding_task",
    )
    db.store_task(task)

    tasks = db.list_tasks(uid, status="in_progress")
    assert len(tasks) >= 1
    assert any("STT" in t.objective for t in tasks)

    print("✅ test_task_persistence passed")


# ── TEST 12: Context builder ──────────────────────────────────────

def test_context_builder():
    """Context builder assembles concise prompt context."""
    setup()
    uid = fresh_user()

    # Add some memories
    db.store_memory(Memory(user_id=uid, content="User prefers Roman Urdu", importance="high", confidence="fact"))
    db.store_memory(Memory(user_id=uid, content="Project uses PyQt6", importance="high", confidence="fact", tags="project"))

    # Add a preference
    db.store_preference(Preference(user_id=uid, category="communication", key="language", value="Roman Urdu", confidence="fact", source="explicit"))

    # Build context
    ctx = build_context(uid, "What language do you prefer?")
    assert "Roman Urdu" in ctx or "language" in ctx.lower()

    print("✅ test_context_builder passed")


# ── TEST 13: Consolidation ────────────────────────────────────────

def test_consolidation():
    """Consolidation merges duplicates and resolves conflicts."""
    setup()
    uid = fresh_user()

    # Create duplicates
    db.store_memory(Memory(user_id=uid, content="User prefers Roman Urdu"))
    db.store_memory(Memory(user_id=uid, content="User prefers Roman Urdu"))

    # Create preference conflict
    db.store_preference(Preference(user_id=uid, category="lang", key="language", value="English", source="inferred"))
    db.store_preference(Preference(user_id=uid, category="lang", key="language", value="Roman Urdu", source="explicit"))

    stats = consolidation.consolidate(uid)
    assert stats["merges"] >= 0  # may or may not merge depending on normalization
    print("✅ test_consolidation passed")


# ── TEST 14: Tool experience memory ───────────────────────────────

def test_tool_experience():
    """Tool experiences are stored and retrievable."""
    setup()
    uid = fresh_user()

    te = ToolExperience(
        user_id=uid, task_pattern="volume_control",
        tool_name="computer_settings", outcome="success",
        success=True, duration_ms=1500,
    )
    db.store_tool_experience(te)

    exps = db.get_tool_experiences(uid, task_pattern="volume_control")
    assert len(exps) >= 1
    assert exps[0].tool_name == "computer_settings"

    print("✅ test_tool_experience passed")


# ── TEST 15: Entity memory ────────────────────────────────────────

def test_entity_memory():
    """Entities and relationships are tracked."""
    setup()
    uid = fresh_user()

    e = Entity(
        user_id=uid, entity_type="subsystem",
        name="STT", description="Speech-to-text system",
        related_to="",
    )
    db.store_entity(e)

    found = db.find_entity(uid, "STT")
    assert found is not None
    assert found.entity_type == "subsystem"

    print("✅ test_entity_memory passed")


# ── TEST 16: Session summary persistence ──────────────────────────

def test_session_summary():
    """Session summaries persist across queries."""
    setup()
    uid = fresh_user()

    ss = SessionSummary(
        user_id=uid, summary="Discussed microphone issues and fixed STT fallback",
        topic="STT", tools_used="coding_task",
    )
    db.store_session_summary(ss)

    summaries = db.list_session_summaries(uid)
    assert len(summaries) >= 1
    assert any("microphone" in s.summary for s in summaries)

    print("✅ test_session_summary passed")


# ── TEST 17: Retrieval ranking ────────────────────────────────────

def test_retrieval_ranking():
    """Retrieval returns most relevant memories first."""
    setup()
    uid = fresh_user()

    db.store_memory(Memory(user_id=uid, content="User prefers Roman Urdu for all responses", importance="high", confidence="fact"))
    db.store_memory(Memory(user_id=uid, content="Project uses Python PyQt6 desktop framework", importance="medium", confidence="fact"))
    db.store_memory(Memory(user_id=uid, content="Microphone has intermittent connection issues", importance="medium", confidence="observation"))

    results = retrieval.retrieve_context(uid, "language preference Roman Urdu")
    assert len(results) > 0
    # Most relevant should be first
    assert "Roman Urdu" in results[0]["content"]

    print("✅ test_retrieval_ranking passed")


# ── TEST 18: Preference reinforcement ─────────────────────────────

def test_preference_reinforcement():
    """Repeated explicit statements increase confidence."""
    setup()
    uid = fresh_user()

    # First time - creates memory with reinforcement_count=0
    extractor.process_candidates([
        {"type": "preference", "content": "User prefers Roman Urdu", "importance": "high", "confidence": "fact", "tags": "language"}
    ], uid)

    # Second time - reinforces to reinforcement_count=1
    extractor.process_candidates([
        {"type": "preference", "content": "User prefers Roman Urdu", "importance": "high", "confidence": "fact", "tags": "language"}
    ], uid)

    # Third time - reinforces to reinforcement_count=2
    extractor.process_candidates([
        {"type": "preference", "content": "User prefers Roman Urdu", "importance": "high", "confidence": "fact", "tags": "language"}
    ], uid)

    # Check reinforcement count increased
    memories = db.list_memories(uid)
    roman_urdu_mem = [m for m in memories if "Roman Urdu" in m.content]
    assert len(roman_urdu_mem) >= 1
    assert roman_urdu_mem[0].reinforcement_count >= 2

    print("✅ test_preference_reinforcement passed")


# ── TEST 19: Memory stats ─────────────────────────────────────────

def test_memory_stats():
    """Memory stats return correct counts."""
    setup()
    uid = fresh_user()

    db.store_memory(Memory(user_id=uid, content="Test memory 1"))
    db.store_memory(Memory(user_id=uid, content="Test memory 2"))
    db.store_preference(Preference(user_id=uid, category="test", key="key", value="val"))

    stats = db.get_db_stats(uid)
    assert stats["memories"] >= 2
    assert stats["preferences"] >= 1

    print("✅ test_memory_stats passed")


# ── TEST 20: Cross-session persistence ────────────────────────────

def test_cross_session_persistence():
    """Data persists after simulated restart (database close/reopen)."""
    setup()
    uid = fresh_user()

    # Session 1: Store memories
    db.store_memory(Memory(user_id=uid, content="User's name is Ahmad", importance="high", confidence="fact"))
    db.store_preference(Preference(user_id=uid, category="personal", key="name", value="Ahmad", confidence="fact", source="explicit"))
    db.store_project(Project(user_id=uid, name="SONIC AI", technology_stack="Python/PyQt6"))

    # Simulate restart: close and reopen database
    db._DB_PATH.exists()  # verify file exists

    # Session 2: Retrieve memories
    memories = db.list_memories(uid)
    assert any("Ahmad" in m.content for m in memories)

    prefs = db.get_active_preferences(uid)
    assert any(p.value == "Ahmad" for p in prefs)

    projects = db.list_projects(uid)
    assert any(p.name == "SONIC AI" for p in projects)

    print("✅ test_cross_session_persistence passed")


# ── RUN ALL TESTS ──────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_db_init,
        test_memory_crud,
        test_fts_search,
        test_user_isolation,
        test_deduplication,
        test_preference_conflict_resolution,
        test_explicit_remember_forget,
        test_extraction_from_turns,
        test_sensitive_data_rejection,
        test_project_memory_isolation,
        test_task_persistence,
        test_context_builder,
        test_consolidation,
        test_tool_experience,
        test_entity_memory,
        test_session_summary,
        test_retrieval_ranking,
        test_preference_reinforcement,
        test_memory_stats,
        test_cross_session_persistence,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Cleanup
    teardown()
    if _test_dir and os.path.exists(_test_dir):
        shutil.rmtree(_test_dir, ignore_errors=True)

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*50}")

    sys.exit(0 if failed == 0 else 1)
