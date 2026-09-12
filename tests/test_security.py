"""Security module tests."""
import time
import threading
from security.advanced import (
    RateLimiter,
    AuditLogger,
    IntrusionDetector,
    SessionManager,
    InputSanitizer,
    APIKeyManager,
    AuditEvent,
    ThreatLevel,
)


class TestRateLimiter:
    def test_allows_within_limit(self):
        rl = RateLimiter(max_attempts=3, window_seconds=60)
        assert rl.is_allowed("user1")[0] is True
        assert rl.is_allowed("user1")[0] is True
        assert rl.is_allowed("user1")[0] is True

    def test_blocks_after_limit(self):
        rl = RateLimiter(max_attempts=2, window_seconds=60, lockout_seconds=10)
        rl.is_allowed("user1")
        rl.is_allowed("user1")
        allowed, reason = rl.is_allowed("user1")
        assert allowed is False
        assert "Locked" in reason or "Too many" in reason

    def test_success_clears_attempts(self):
        rl = RateLimiter(max_attempts=2, window_seconds=60)
        rl.is_allowed("user1")
        rl.is_allowed("user1")
        rl.record_success("user1")
        assert rl.is_allowed("user1")[0] is True

    def test_separate_keys(self):
        rl = RateLimiter(max_attempts=1, window_seconds=60, lockout_seconds=10)
        rl.is_allowed("user1")
        allowed, _ = rl.is_allowed("user1")
        assert allowed is False
        assert rl.is_allowed("user2")[0] is True

    def test_stats(self):
        rl = RateLimiter(max_attempts=5, window_seconds=60)
        rl.is_allowed("u1")
        rl.is_allowed("u2")
        stats = rl.get_stats()
        assert stats["active_keys"] == 2


class TestAuditLogger:
    def test_log_writes_entry(self, tmp_path):
        log = AuditLogger(tmp_path / "test.log")
        log.log(AuditEvent.LOGIN_SUCCESS, "user1", "test login")
        valid, count, _ = log.verify_integrity()
        assert valid is True
        assert count == 1

    def test_chain_integrity(self, tmp_path):
        log = AuditLogger(tmp_path / "test.log")
        for i in range(10):
            log.log(AuditEvent.LOGIN_SUCCESS, "user1", f"entry {i}")
        valid, count, error = log.verify_integrity()
        assert valid is True
        assert count == 10

    def test_get_recent(self, tmp_path):
        log = AuditLogger(tmp_path / "test.log")
        for i in range(5):
            log.log(AuditEvent.LOGIN_SUCCESS, "user1", f"entry {i}")
        recent = log.get_recent(3)
        assert len(recent) == 3


class TestIntrusionDetector:
    def test_detects_sql_injection(self):
        ids = IntrusionDetector()
        threats = ids.check_input("SELECT * FROM users WHERE 1=1 OR 1=1")
        assert len(threats) > 0
        assert any("SQL" in t.threat_type for t in threats)

    def test_detects_xss(self):
        ids = IntrusionDetector()
        threats = ids.check_input("<script>alert(1)</script>")
        assert len(threats) > 0
        assert any("XSS" in t.threat_type for t in threats)

    def test_detects_path_traversal(self):
        ids = IntrusionDetector()
        threats = ids.check_input("../../../etc/passwd")
        assert len(threats) > 0

    def test_safe_input(self):
        ids = IntrusionDetector()
        threats = ids.check_input("Hello, how are you?")
        assert len(threats) == 0

    def test_rate_anomaly(self):
        import pytest
        pytest.skip("Rate anomaly test requires timing - covered by integration tests")

    def test_threats_list(self):
        ids = IntrusionDetector()
        ids.check_input("SELECT * FROM users WHERE 1=1 OR 1=1", "test")
        threats = ids.get_threats(hours=1)
        assert len(threats) > 0


class TestSessionManager:
    def test_create_session(self):
        sm = SessionManager()
        session = sm.create_session("user1", "127.0.0.1")
        assert session.session_id
        assert session.user_id == "user1"

    def test_validate_session(self):
        sm = SessionManager()
        session = sm.create_session("user1")
        validated = sm.validate_session(session.session_id)
        assert validated is not None
        assert validated.user_id == "user1"

    def test_invalid_session(self):
        sm = SessionManager()
        assert sm.validate_session("invalid_id") is None

    def test_invalidate_all(self):
        sm = SessionManager()
        sm.create_session("user1")
        sm.create_session("user1")
        count = sm.invalidate_all("user1")
        assert count == 2

    def test_max_sessions(self):
        sm = SessionManager(max_sessions=2)
        sm.create_session("user1")
        sm.create_session("user1")
        sm.create_session("user1")
        sessions = sm.get_active_sessions("user1")
        assert len(sessions) <= 2


class TestInputSanitizer:
    def test_sanitize_html(self):
        s = InputSanitizer()
        result = s.sanitize_html("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;" in result

    def test_sanitize_filename(self):
        s = InputSanitizer()
        result = s.sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_sanitize_path(self):
        s = InputSanitizer()
        result = s.sanitize_path("C:/Users/../../Windows/System32")
        assert ".." not in result

    def test_validate_email(self):
        s = InputSanitizer()
        assert s.validate_email("test@example.com") is True
        assert s.validate_email("invalid") is False

    def test_validate_url(self):
        s = InputSanitizer()
        assert s.validate_url("https://example.com") is True
        assert s.validate_url("javascript:alert(1)") is False

    def test_check_overflow(self):
        s = InputSanitizer()
        assert s.check_overflow("x" * 100, max_size=50) is True
        assert s.check_overflow("small", max_size=50) is False


class TestAPIKeyManager:
    def test_generate_key(self):
        km = APIKeyManager()
        key, record = km.generate_key("test")
        assert key
        assert record.key_id

    def test_validate_key(self):
        km = APIKeyManager()
        key, _ = km.generate_key("test")
        assert km.validate_key(key) is True

    def test_invalid_key(self):
        km = APIKeyManager()
        assert km.validate_key("invalid_key") is False

    def test_revoke_key(self):
        km = APIKeyManager()
        key, record = km.generate_key("test")
        assert km.revoke_key(record.key_id) is True
        assert km.validate_key(key) is False

    def test_stats(self):
        km = APIKeyManager()
        km.generate_key("test1")
        km.generate_key("test2")
        stats = km.get_stats()
        assert stats["total_keys"] == 2
        assert stats["active_keys"] == 2
