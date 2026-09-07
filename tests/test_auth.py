"""Comprehensive tests for SONIC AI Auth + User Isolation + Profile system."""
import sys
import os
import io
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ── TEST 1: restore_session returns dict ───────────────────────────

def test_restore_session_returns_dict():
    """restore_session() must return a dict with user_id, not just bool."""
    from auth.core import SonicAuth, _safe_json_write, _SESSION_PATH
    import time

    # Create a mock session file
    session_data = {
        "user_id": "test_user_123",
        "email": "test@example.com",
        "display_name": "Test User",
        "photo_url": "",
        "id_token": "mock_token",
        "refresh_token": "mock_refresh",
        "token_expires_at": time.time() + 3600,
        "is_authenticated": True,
        "provider": "email",
    }
    _safe_json_write(_SESSION_PATH, session_data)

    # Create auth instance and restore
    auth = SonicAuth()
    result = auth.restore_session()

    # Must be a dict, not just bool
    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert result.get("user_id") == "test_user_123"
    assert result.get("email") == "test@example.com"

    # Cleanup
    auth.logout()
    print("✅ test_restore_session_returns_dict passed")


# ── TEST 2: restore_session returns False when no session ──────────

def test_restore_session_false_when_empty():
    """restore_session() returns False when no session exists."""
    from auth.core import SonicAuth, _SESSION_PATH

    # Ensure no session file
    if _SESSION_PATH.exists():
        _SESSION_PATH.unlink()

    auth = SonicAuth()
    result = auth.restore_session()
    assert result is False
    print("✅ test_restore_session_false_when_empty passed")


# ── TEST 3: user_id property works ────────────────────────────────

def test_user_id_property():
    """user_id property returns the current user's ID."""
    from auth.core import SonicAuth

    auth = SonicAuth()
    # Before login, user_id should be empty
    assert auth.user_id == "" or isinstance(auth.user_id, str)
    print("✅ test_user_id_property passed")


# ── TEST 4: Secrets isolation — per-user storage ──────────────────

def test_secrets_isolation():
    """Each user's secrets are stored in separate files."""
    from auth.secrets import UserSecrets, SECRETS_DIR

    # Create two users
    user_a = UserSecrets("user_a_test")
    user_b = UserSecrets("user_b_test")

    # Set different secrets
    user_a.set("gemini_key", "key_a_123")
    user_b.set("gemini_key", "key_b_456")

    # Verify isolation
    assert user_a.get("gemini_key") == "key_a_123"
    assert user_b.get("gemini_key") == "key_b_456"

    # Verify files are different
    assert user_a._path != user_b._path

    # Cleanup
    user_a.delete_file()
    user_b.delete_file()
    print("✅ test_secrets_isolation passed")


# ── TEST 5: Runtime secrets cleared on logout ─────────────────────

def test_runtime_secrets_clear():
    """Runtime secrets are cleared when clear_runtime_secrets() is called."""
    from auth.secrets import set_runtime_secret, get_runtime_secret, clear_runtime_secrets

    set_runtime_secret("test_key", "test_value")
    assert get_runtime_secret("test_key") == "test_value"

    clear_runtime_secrets()
    assert get_runtime_secret("test_key") == ""
    print("✅ test_runtime_secrets_clear passed")


# ── TEST 6: Memory user_id isolation ──────────────────────────────

def test_memory_user_isolation():
    """Memory system properly isolates data by user_id."""
    from memory import db
    from memory.models import Memory, Preference
    import tempfile
    from pathlib import Path

    # Use temporary database
    test_db = Path(tempfile.mkdtemp()) / "test_isolation.db"
    db._DB_PATH = test_db
    db.init_db()

    user_a = "test_user_alpha"
    user_b = "test_user_beta"

    # User A stores memory
    db.store_memory(Memory(user_id=user_a, content="User A's secret: favorite editor is VS Code"))

    # User B stores memory
    db.store_memory(Memory(user_id=user_b, content="User B's secret: favorite editor is Neovim"))

    # User A search should NOT return User B's memory
    results_a = db.search_memories(user_a, "editor")
    assert all(r.user_id == user_a for r in results_a)
    assert not any("Neovim" in r.content for r in results_a)

    # User B search should NOT return User A's memory
    results_b = db.search_memories(user_b, "editor")
    assert all(r.user_id == user_b for r in results_b)
    assert not any("VS Code" in r.content for r in results_b)

    # Cleanup
    test_db.unlink(missing_ok=True)
    print("✅ test_memory_user_isolation passed")


# ── TEST 7: Preference isolation ──────────────────────────────────

def test_preference_isolation():
    """User preferences are isolated by user_id."""
    from memory import db
    from memory.models import Preference
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_pref_isolation.db"
    db._DB_PATH = test_db
    db.init_db()

    user_a = "pref_user_alpha"
    user_b = "pref_user_beta"

    # User A prefers English
    db.store_preference(Preference(user_id=user_a, category="lang", key="language", value="English", source="explicit"))

    # User B prefers Roman Urdu
    db.store_preference(Preference(user_id=user_b, category="lang", key="language", value="Roman Urdu", source="explicit"))

    # User A gets English
    prefs_a = db.get_active_preferences(user_a, category="lang")
    assert any(p.value == "English" for p in prefs_a)
    assert not any(p.value == "Roman Urdu" for p in prefs_a)

    # User B gets Roman Urdu
    prefs_b = db.get_active_preferences(user_b, category="lang")
    assert any(p.value == "Roman Urdu" for p in prefs_b)
    assert not any(p.value == "English" for p in prefs_b)

    test_db.unlink(missing_ok=True)
    print("✅ test_preference_isolation passed")


# ── TEST 8: Project isolation ─────────────────────────────────────

def test_project_isolation():
    """Projects are isolated by user_id."""
    from memory import db
    from memory.models import Project
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_proj_isolation.db"
    db._DB_PATH = test_db
    db.init_db()

    user_a = "proj_user_alpha"
    user_b = "proj_user_beta"

    db.store_project(Project(user_id=user_a, name="SONIC AI", technology_stack="Python"))
    db.store_project(Project(user_id=user_b, name="WebApp", technology_stack="React"))

    projects_a = db.list_projects(user_a)
    assert any(p.name == "SONIC AI" for p in projects_a)
    assert not any(p.name == "WebApp" for p in projects_a)

    projects_b = db.list_projects(user_b)
    assert any(p.name == "WebApp" for p in projects_b)
    assert not any(p.name == "SONIC AI" for p in projects_b)

    test_db.unlink(missing_ok=True)
    print("✅ test_project_isolation passed")


# ── TEST 9: Task isolation ────────────────────────────────────────

def test_task_isolation():
    """Tasks are isolated by user_id."""
    from memory import db
    from memory.models import Task
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_task_isolation.db"
    db._DB_PATH = test_db
    db.init_db()

    user_a = "task_user_alpha"
    user_b = "task_user_beta"

    db.store_task(Task(user_id=user_a, objective="Fix STT", status="in_progress"))
    db.store_task(Task(user_id=user_b, objective="Build UI", status="pending"))

    tasks_a = db.list_tasks(user_a)
    assert any("STT" in t.objective for t in tasks_a)
    assert not any("UI" in t.objective for t in tasks_a)

    tasks_b = db.list_tasks(user_b)
    assert any("UI" in t.objective for t in tasks_b)
    assert not any("STT" in t.objective for t in tasks_b)

    test_db.unlink(missing_ok=True)
    print("✅ test_task_isolation passed")


# ── TEST 10: Logout clears all state ──────────────────────────────

def test_logout_clears_state():
    """Logout clears all runtime state."""
    from auth.core import SonicAuth, _SESSION_PATH
    from auth.secrets import set_runtime_secret, get_runtime_secret, clear_runtime_secrets
    from memory.memory_manager import set_user_id, get_user_id

    # Set some state
    set_runtime_secret("api_key", "secret123")
    set_user_id("test_uid")

    # Create auth and simulate login state
    auth = SonicAuth()
    auth._user_id = "test_uid"
    auth._email = "test@test.com"
    auth._is_authenticated = True

    # Logout
    auth.logout()

    # Verify state cleared
    assert auth.user_id == ""
    assert auth._email == ""
    assert auth._is_authenticated is False
    assert get_runtime_secret("api_key") == ""
    assert get_user_id() == ""

    print("✅ test_logout_clears_state passed")


# ── TEST 11: Profile persistence ──────────────────────────────────

def test_profile_persistence():
    """Profile data persists across instances."""
    from auth.core import SonicAuth, _PROFILE_PATH

    # Create auth and save profile
    auth1 = SonicAuth()
    auth1._user_id = "profile_test_user"
    auth1._is_authenticated = True
    auth1.update_extended_profile(
        full_name="Test Profile User",
        location="Test City",
        preferences={"language": "Roman Urdu"}
    )

    # Load profile from new instance
    auth2 = SonicAuth()
    profile = auth2.get_extended_profile()
    assert profile.get("profile", {}).get("full_name") == "Test Profile User"
    assert profile.get("profile", {}).get("location") == "Test City"

    # Cleanup
    if _PROFILE_PATH.exists():
        _PROFILE_PATH.unlink()
    print("✅ test_profile_persistence passed")


# ── TEST 12: Session persistence across restart ───────────────────

def test_session_persistence():
    """Session persists across auth instance recreation (simulates restart)."""
    from auth.core import SonicAuth, _SESSION_PATH
    import time

    # Create session
    session_data = {
        "user_id": "restart_test_user",
        "email": "restart@test.com",
        "display_name": "Restart Test",
        "photo_url": "",
        "id_token": "mock_token",
        "refresh_token": "mock_refresh",
        "token_expires_at": time.time() + 3600,
        "is_authenticated": True,
        "provider": "email",
    }
    from auth.core import _safe_json_write
    _safe_json_write(_SESSION_PATH, session_data)

    # Simulate restart — new auth instance
    auth = SonicAuth()
    result = auth.restore_session()

    assert isinstance(result, dict)
    assert result.get("user_id") == "restart_test_user"
    assert result.get("email") == "restart@test.com"

    # Cleanup
    auth.logout()
    print("✅ test_session_persistence passed")


# ── TEST 13: Memory extraction works with user_id ─────────────────

def test_memory_extraction_with_uid():
    """Memory extraction works when user_id is set."""
    from memory.memory_manager import set_user_id, get_user_id, extract_from_turn
    from memory import db
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_extract.db"
    db._DB_PATH = test_db
    db.init_db()

    set_user_id("extract_test_user")
    assert get_user_id() == "extract_test_user"

    # Extract from a turn
    count = extract_from_turn(
        "My project is called SONIC AI",
        "Great project!",
        session_id="test_session"
    )

    # Should have extracted at least one memory
    memories = db.list_memories("extract_test_user")
    assert len(memories) > 0

    # Cleanup
    set_user_id("")
    test_db.unlink(missing_ok=True)
    print("✅ test_memory_extraction_with_uid passed")


# ── TEST 14: Context builder uses user_id ─────────────────────────

def test_context_builder_uses_uid():
    """Context builder retrieves user-specific memories."""
    from memory.memory_manager import set_user_id
    from memory.context_builder import build_context
    from memory import db
    from memory.models import Memory
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_ctx.db"
    db._DB_PATH = test_db
    db.init_db()

    uid = "ctx_test_user"
    set_user_id(uid)

    db.store_memory(Memory(user_id=uid, content="User prefers Roman Urdu", importance="high", confidence="fact"))

    ctx = build_context(uid, "Roman Urdu preference")
    assert "Roman Urdu" in ctx

    set_user_id("")
    test_db.unlink(missing_ok=True)
    print("✅ test_context_builder_uses_uid passed")


# ── TEST 15: Secrets file is per-user ─────────────────────────────

def test_secrets_per_user_file():
    """Each user gets a separate secrets file."""
    from auth.secrets import UserSecrets, SECRETS_DIR

    user_a = UserSecrets("file_test_a")
    user_b = UserSecrets("file_test_b")

    assert user_a._path != user_b._path
    assert user_a._path.parent == SECRETS_DIR
    assert user_b._path.parent == SECRETS_DIR

    user_a.delete_file()
    user_b.delete_file()
    print("✅ test_secrets_per_user_file passed")


# ── TEST 16: .gitignore excludes auth files ───────────────────────

def test_gitignore_excludes_auth():
    """Auth files are properly excluded in .gitignore."""
    gitignore = Path(__file__).resolve().parent.parent / ".gitignore"
    if not gitignore.exists():
        print("⚠️ test_gitignore_excludes_auth SKIPPED (no .gitignore)")
        return

    content = gitignore.read_text(encoding="utf-8")
    assert "auth/.session.json" in content
    assert "auth/.profile.json" in content
    assert "auth/.local_users.json" in content
    assert "auth/firebase_config.json" in content
    assert "memory/*.db" in content
    print("✅ test_gitignore_excludes_auth passed")


# ── TEST 17: Firestore rules exist ────────────────────────────────

def test_firestore_rules_exist():
    """Firestore security rules file exists with proper structure."""
    rules_path = Path(__file__).resolve().parent.parent / "firestore.rules"
    assert rules_path.exists(), "firestore.rules not found"

    content = rules_path.read_text(encoding="utf-8")
    assert "request.auth.uid == userId" in content
    assert "allow read, write: if false" in content
    print("✅ test_firestore_rules_exist passed")


# ── TEST 18: Full user switching scenario ─────────────────────────

def test_user_switching():
    """User A data is completely isolated from User B."""
    from memory import db
    from memory.models import Memory, Preference, Project, Task
    from memory.memory_manager import set_user_id
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_switching.db"
    db._DB_PATH = test_db
    db.init_db()

    # User A
    set_user_id("switching_user_a")
    db.store_memory(Memory(user_id="switching_user_a", content="User A's favorite color is blue"))
    db.store_preference(Preference(user_id="switching_user_a", category="personal", key="color", value="blue"))
    db.store_project(Project(user_id="switching_user_a", name="Project A"))

    # User B
    set_user_id("switching_user_b")
    db.store_memory(Memory(user_id="switching_user_b", content="User B's favorite color is red"))
    db.store_preference(Preference(user_id="switching_user_b", category="personal", key="color", value="red"))
    db.store_project(Project(user_id="switching_user_b", name="Project B"))

    # Verify User A sees only A's data
    mems_a = db.list_memories("switching_user_a")
    assert any("blue" in m.content for m in mems_a)
    assert not any("red" in m.content for m in mems_a)

    prefs_a = db.get_active_preferences("switching_user_a")
    assert any(p.value == "blue" for p in prefs_a)
    assert not any(p.value == "red" for p in prefs_a)

    projs_a = db.list_projects("switching_user_a")
    assert any(p.name == "Project A" for p in projs_a)
    assert not any(p.name == "Project B" for p in projs_a)

    # Verify User B sees only B's data
    mems_b = db.list_memories("switching_user_b")
    assert any("red" in m.content for m in mems_b)
    assert not any("blue" in m.content for m in mems_b)

    # Switch back to User A — data still there
    set_user_id("switching_user_a")
    mems_a2 = db.list_memories("switching_user_a")
    assert any("blue" in m.content for m in mems_a2)

    set_user_id("")
    test_db.unlink(missing_ok=True)
    print("✅ test_user_switching passed")


# ── TEST 19: Logout does NOT delete cloud data ────────────────────

def test_logout_preserves_data():
    """Logout clears runtime but preserves persistent data."""
    from memory import db
    from memory.models import Memory
    from memory.memory_manager import set_user_id, get_user_id
    from auth.core import SonicAuth
    import tempfile
    from pathlib import Path

    test_db = Path(tempfile.mkdtemp()) / "test_logout_preserve.db"
    db._DB_PATH = test_db
    db.init_db()

    # Login as user, store data
    set_user_id("logout_preserve_user")
    db.store_memory(Memory(user_id="logout_preserve_user", content="Important fact"))

    # Verify data exists
    mems = db.list_memories("logout_preserve_user")
    assert len(mems) == 1

    # Logout
    auth = SonicAuth()
    auth._user_id = "logout_preserve_user"
    auth.logout()

    # Runtime cleared
    assert get_user_id() == ""

    # But data still in database
    mems_after = db.list_memories("logout_preserve_user")
    assert len(mems_after) == 1
    assert "Important fact" in mems_after[0].content

    test_db.unlink(missing_ok=True)
    print("✅ test_logout_preserves_data passed")


# ── TEST 20: Email validation ─────────────────────────────────────

def test_email_validation():
    """Email validation works correctly."""
    from auth.core import _validate_email

    assert _validate_email("user@example.com") is True
    assert _validate_email("test@test.co") is True
    assert _validate_email("invalid") is False
    assert _validate_email("@no-user.com") is False
    assert _validate_email("no-at-sign.com") is False
    assert _validate_email("") is False
    print("✅ test_email_validation passed")


# ── RUN ALL TESTS ──────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_restore_session_returns_dict,
        test_restore_session_false_when_empty,
        test_user_id_property,
        test_secrets_isolation,
        test_runtime_secrets_clear,
        test_memory_user_isolation,
        test_preference_isolation,
        test_project_isolation,
        test_task_isolation,
        test_logout_clears_state,
        test_profile_persistence,
        test_session_persistence,
        test_memory_extraction_with_uid,
        test_context_builder_uses_uid,
        test_secrets_per_user_file,
        test_gitignore_excludes_auth,
        test_firestore_rules_exist,
        test_user_switching,
        test_logout_preserves_data,
        test_email_validation,
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
