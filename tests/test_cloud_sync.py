"""Tests for SONIC AI Cloud Sync — Firestore ↔ local SQLite bridge."""
import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from unittest.mock import patch, MagicMock
from memory import db
from memory.models import Memory, Preference, Project, Task
from memory.memory_manager import set_user_id, get_user_id
import tempfile


# ── TEST 1: pull_from_cloud returns empty when no Firestore ────────

def test_pull_no_firestore():
    from memory.cloud_sync import pull_from_cloud
    result = pull_from_cloud("test_uid")
    assert isinstance(result, dict)
    assert result == {}
    print("✅ test_pull_no_firestore passed")


# ── TEST 2: push_to_cloud returns empty when no Firestore ──────────

def test_push_no_firestore():
    from memory.cloud_sync import push_to_cloud
    result = push_to_cloud("test_uid")
    assert isinstance(result, dict)
    assert result == {}
    print("✅ test_push_no_firestore passed")


# ── TEST 3: sync_cloud with no uid returns empty ───────────────────

def test_sync_no_uid():
    from memory.cloud_sync import sync_cloud
    result = sync_cloud("")
    assert result == {}
    print("✅ test_sync_no_uid passed")


# ── TEST 4: on_login hook with empty uid ───────────────────────────

def test_on_login_empty_uid():
    from memory.cloud_sync import on_login
    result = on_login("")
    assert result == {}
    print("✅ test_on_login_empty_uid passed")


# ── TEST 5: on_logout hook with empty uid ──────────────────────────

def test_on_logout_empty_uid():
    from memory.cloud_sync import on_logout
    result = on_logout("")
    assert result == {}
    print("✅ test_on_logout_empty_uid passed")


# ── TEST 6: start/stop background sync ─────────────────────────────

def test_background_sync_lifecycle():
    from memory.cloud_sync import start_background_sync, stop_background_sync, _sync_timer

    start_background_sync("test_user")
    import time
    time.sleep(0.1)
    stop_background_sync()

    from memory.cloud_sync import _sync_timer as timer
    # Timer should be stopped (None or cancelled)
    print("✅ test_background_sync_lifecycle passed")


# ── TEST 7: get_sync_status returns valid structure ────────────────

def test_sync_status():
    from memory.cloud_sync import get_sync_status
    status = get_sync_status()
    assert isinstance(status, dict)
    assert "firestore_available" in status
    assert "last_sync" in status
    assert "background_active" in status
    assert "sync_interval" in status
    print("✅ test_sync_status passed")


# ── TEST 8: on_memory_changed with empty uid ───────────────────────

def test_on_memory_changed_empty():
    from memory.cloud_sync import on_memory_changed
    # Should not raise
    on_memory_changed("")
    print("✅ test_on_memory_changed_empty passed")


# ── TEST 9: pull from mock Firestore merges into local DB ──────────

def test_pull_merges_to_local():
    from memory.cloud_sync import pull_from_cloud
    from auth.firestore_sync import FirestoreIsolation

    # Setup test DB
    test_db = Path(tempfile.mkdtemp()) / "test_pull_merge.db"
    db._DB_PATH = test_db
    db.init_db()
    uid = "pull_merge_user"

    # Mock Firestore to return data
    mock_cloud_data = [
        {
            "memory_id": "cloud_mem_001",
            "user_id": uid,
            "memory_type": "episodic",
            "content": "Cloud memory: favorite IDE is VS Code",
            "importance": "medium",
            "confidence": "observation",
            "status": "active",
            "tags": "",
            "project_id": "",
            "task_id": "",
            "session_id": "",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-06-01T00:00:00",
        }
    ]

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'load_memories', return_value=mock_cloud_data), \
         patch.object(FirestoreIsolation, 'load_preferences', return_value={}), \
         patch.object(FirestoreIsolation, 'load_projects', return_value=[]), \
         patch.object(FirestoreIsolation, 'load_tasks', return_value=[]):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = True
        result = pull_from_cloud(uid)

    # Verify memory was pulled
    assert result.get("memories", 0) == 1
    local = db.get_memory("cloud_mem_001", uid)
    assert local is not None
    assert local.content == "Cloud memory: favorite IDE is VS Code"

    # Cleanup
    test_db.unlink(missing_ok=True)
    print("✅ test_pull_merges_to_local passed")


# ── TEST 10: pull skips existing local data ────────────────────────

def test_pull_skips_existing():
    from memory.cloud_sync import pull_from_cloud
    from auth.firestore_sync import FirestoreIsolation

    test_db = Path(tempfile.mkdtemp()) / "test_pull_skip.db"
    db._DB_PATH = test_db
    db.init_db()
    uid = "pull_skip_user"

    # Store local memory first
    db.store_memory(Memory(
        memory_id="existing_mem",
        user_id=uid,
        content="Local version",
        updated_at="2026-09-01T00:00:00",
    ))

    # Cloud has same memory but older
    mock_cloud = [{
        "memory_id": "existing_mem",
        "user_id": uid,
        "memory_type": "episodic",
        "content": "Cloud version (older)",
        "importance": "medium",
        "confidence": "observation",
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-06-01T00:00:00",
    }]

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'load_memories', return_value=mock_cloud), \
         patch.object(FirestoreIsolation, 'load_preferences', return_value={}), \
         patch.object(FirestoreIsolation, 'load_projects', return_value=[]), \
         patch.object(FirestoreIsolation, 'load_tasks', return_value=[]):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = True
        result = pull_from_cloud(uid)

    # Should have been skipped (pulled 0 new memories)
    local = db.get_memory("existing_mem", uid)
    assert local.content == "Local version"

    test_db.unlink(missing_ok=True)
    print("✅ test_pull_skips_existing passed")


# ── TEST 11: push uploads local memories to Firestore ──────────────

def test_push_uploads_memories():
    from memory.cloud_sync import push_to_cloud
    from auth.firestore_sync import FirestoreIsolation

    test_db = Path(tempfile.mkdtemp()) / "test_push_mem.db"
    db._DB_PATH = test_db
    db.init_db()
    uid = "push_mem_user"

    db.store_memory(Memory(user_id=uid, content="Test memory for push"))
    db.store_memory(Memory(user_id=uid, content="Another test memory"))

    saved_data = []
    def mock_save(uid_arg, memories):
        saved_data.extend(memories)
        return True

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'save_memories', side_effect=mock_save), \
         patch.object(FirestoreIsolation, 'save_preferences', return_value=True), \
         patch.object(FirestoreIsolation, 'save_project', return_value=True), \
         patch.object(FirestoreIsolation, 'save_task', return_value=True):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = True
        result = push_to_cloud(uid)

    assert result.get("memories", 0) == 2
    assert len(saved_data) == 2

    test_db.unlink(missing_ok=True)
    print("✅ test_push_uploads_memories passed")


# ── TEST 12: full sync is bidirectional ────────────────────────────

def test_full_sync_bidirectional():
    from memory.cloud_sync import sync_cloud, pull_from_cloud, push_to_cloud

    with patch('memory.cloud_sync.pull_from_cloud', return_value={"memories": 1}) as mock_pull, \
         patch('memory.cloud_sync.push_to_cloud', return_value={"memories": 2}) as mock_push:
        result = sync_cloud("test_uid")

    assert "pull" in result
    assert "push" in result
    mock_pull.assert_called_once_with("test_uid")
    mock_push.assert_called_once_with("test_uid")
    print("✅ test_full_sync_bidirectional passed")


# ── TEST 13: on_login triggers pull + starts bg sync ───────────────

def test_on_login_triggers_pull():
    from memory.cloud_sync import on_login, stop_background_sync

    with patch('memory.cloud_sync.pull_from_cloud', return_value={"memories": 3}) as mock_pull, \
         patch('memory.cloud_sync.start_background_sync') as mock_bg:
        result = on_login("login_user")

    assert result == {"memories": 3}
    mock_pull.assert_called_once_with("login_user")
    mock_bg.assert_called_once_with("login_user")
    stop_background_sync()
    print("✅ test_on_login_triggers_pull passed")


# ── TEST 14: on_logout triggers push + stops bg sync ───────────────

def test_on_logout_triggers_push():
    from memory.cloud_sync import on_logout

    with patch('memory.cloud_sync.push_to_cloud', return_value={"memories": 5}) as mock_push, \
         patch('memory.cloud_sync.stop_background_sync') as mock_stop:
        result = on_logout("logout_user")

    assert result == {"memories": 5}
    mock_push.assert_called_once_with("logout_user")
    mock_stop.assert_called_once()
    print("✅ test_on_logout_triggers_push passed")


# ── TEST 15: cloud sync respects user isolation ────────────────────

def test_cloud_sync_user_isolation():
    from memory.cloud_sync import pull_from_cloud
    from auth.firestore_sync import FirestoreIsolation

    test_db = Path(tempfile.mkdtemp()) / "test_cloud_isolation.db"
    db._DB_PATH = test_db
    db.init_db()

    user_a = "cloud_user_a"
    user_b = "cloud_user_b"

    # Cloud returns data only for user_a
    mock_cloud_a = [{
        "memory_id": "cloud_a_mem",
        "user_id": user_a,
        "memory_type": "episodic",
        "content": "User A's cloud memory",
        "importance": "medium",
        "confidence": "observation",
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-06-01T00:00:00",
    }]

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'load_memories', return_value=mock_cloud_a), \
         patch.object(FirestoreIsolation, 'load_preferences', return_value={}), \
         patch.object(FirestoreIsolation, 'load_projects', return_value=[]), \
         patch.object(FirestoreIsolation, 'load_tasks', return_value=[]):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = True
        pull_from_cloud(user_a)

    # User A has memory
    mems_a = db.list_memories(user_a)
    assert any("cloud_a_mem" in m.memory_id for m in mems_a)

    # User B has nothing
    mems_b = db.list_memories(user_b)
    assert len(mems_b) == 0

    test_db.unlink(missing_ok=True)
    print("✅ test_cloud_sync_user_isolation passed")


# ── TEST 16: push handles empty local data gracefully ──────────────

def test_push_empty_data():
    from memory.cloud_sync import push_to_cloud
    from auth.firestore_sync import FirestoreIsolation

    test_db = Path(tempfile.mkdtemp()) / "test_push_empty.db"
    db._DB_PATH = test_db
    db.init_db()

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'save_memories', return_value=True), \
         patch.object(FirestoreIsolation, 'save_preferences', return_value=True), \
         patch.object(FirestoreIsolation, 'save_project', return_value=True), \
         patch.object(FirestoreIsolation, 'save_task', return_value=True):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = True
        result = push_to_cloud("empty_user")

    assert result.get("memories", 0) == 0
    assert result.get("preferences", 0) == 0
    assert result.get("projects", 0) == 0
    assert result.get("tasks", 0) == 0

    test_db.unlink(missing_ok=True)
    print("✅ test_push_empty_data passed")


# ── TEST 17: sync handles Firestore init failure ───────────────────

def test_sync_handles_init_failure():
    from memory.cloud_sync import push_to_cloud
    from auth.firestore_sync import FirestoreIsolation

    with patch.object(FirestoreIsolation, 'initialize', return_value=False):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = False
        result = push_to_cloud("fail_user")

    assert result == {}
    print("✅ test_sync_handles_init_failure passed")


# ── TEST 18: sync_cloud handles exceptions gracefully ──────────────

def test_sync_handles_exception():
    from memory.cloud_sync import sync_cloud

    with patch('memory.cloud_sync.pull_from_cloud', side_effect=Exception("network error")):
        result = sync_cloud("exception_user")

    # Should not crash, returns empty or partial
    assert isinstance(result, dict)
    print("✅ test_sync_handles_exception passed")


# ── TEST 19: _to_dict converts dataclass properly ─────────────────

def test_to_dict_conversion():
    from memory.cloud_sync import _to_dict
    from memory.models import Memory

    mem = Memory(user_id="u1", content="test content")
    d = _to_dict(mem)
    assert isinstance(d, dict)
    assert d["content"] == "test content"
    assert d["user_id"] == "u1"
    print("✅ test_to_dict_conversion passed")


# ── TEST 20: full round-trip: store → push → pull into new DB ──────

def test_full_round_trip():
    from memory.cloud_sync import push_to_cloud, pull_from_cloud
    from auth.firestore_sync import FirestoreIsolation

    test_db = Path(tempfile.mkdtemp()) / "test_roundtrip.db"
    db._DB_PATH = test_db
    db.init_db()
    uid = "roundtrip_user"

    # Store 2 memories locally
    db.store_memory(Memory(user_id=uid, content="Round trip memory 1", importance="high"))
    db.store_memory(Memory(user_id=uid, content="Round trip memory 2", importance="low"))

    # Capture what gets pushed
    pushed_memories = []
    def capture_push(uid_arg, memories):
        pushed_memories.extend(memories)
        return True

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'save_memories', side_effect=capture_push), \
         patch.object(FirestoreIsolation, 'save_preferences', return_value=True), \
         patch.object(FirestoreIsolation, 'save_project', return_value=True), \
         patch.object(FirestoreIsolation, 'save_task', return_value=True):
        from memory.cloud_sync import get_firestore
        fs = get_firestore()
        fs._initialized = True
        push_to_cloud(uid)

    assert len(pushed_memories) == 2

    # Now simulate pulling into a fresh DB
    test_db2 = Path(tempfile.mkdtemp()) / "test_roundtrip2.db"
    db._DB_PATH = test_db2
    db.init_db()

    with patch.object(FirestoreIsolation, 'initialize', return_value=True), \
         patch.object(FirestoreIsolation, 'load_memories', return_value=pushed_memories), \
         patch.object(FirestoreIsolation, 'load_preferences', return_value={}), \
         patch.object(FirestoreIsolation, 'load_projects', return_value=[]), \
         patch.object(FirestoreIsolation, 'load_tasks', return_value=[]):
        result = pull_from_cloud(uid)

    assert result.get("memories") == 2
    local = db.list_memories(uid)
    assert len(local) == 2
    contents = {m.content for m in local}
    assert "Round trip memory 1" in contents
    assert "Round trip memory 2" in contents

    test_db.unlink(missing_ok=True)
    test_db2.unlink(missing_ok=True)
    print("✅ test_full_round_trip passed")


# ── RUN ALL TESTS ──────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_pull_no_firestore,
        test_push_no_firestore,
        test_sync_no_uid,
        test_on_login_empty_uid,
        test_on_logout_empty_uid,
        test_background_sync_lifecycle,
        test_sync_status,
        test_on_memory_changed_empty,
        test_pull_merges_to_local,
        test_pull_skips_existing,
        test_push_uploads_memories,
        test_full_sync_bidirectional,
        test_on_login_triggers_pull,
        test_on_logout_triggers_push,
        test_cloud_sync_user_isolation,
        test_push_empty_data,
        test_sync_handles_init_failure,
        test_sync_handles_exception,
        test_to_dict_conversion,
        test_full_round_trip,
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

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*50}")

    sys.exit(0 if failed == 0 else 1)
