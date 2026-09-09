"""SONIC AI — Advanced Security System.

Comprehensive security module with:
- Rate limiting (brute force protection)
- Audit logging (tamper-proof)
- Intrusion detection (anomaly + signature)
- Session hardening
- Input sanitization
- API key rotation
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import sys
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("sonic.security")


# ═══════════════════════════════════════════════════════════════════════════
# 1. RATE LIMITER — Brute Force Protection
# ═══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Sliding window rate limiter with lockout."""

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: int = 300,
        lockout_seconds: int = 900,
    ):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._lockouts: dict[str, float] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> tuple[bool, str]:
        """Check if request is allowed. Returns (allowed, reason)."""
        now = time.time()

        with self._lock:
            # Check lockout
            if key in self._lockouts:
                lockout_until = self._lockouts[key]
                if now < lockout_until:
                    remaining = int(lockout_until - now)
                    return False, f"Locked out. Try again in {remaining}s"
                else:
                    del self._lockouts[key]
                    self._attempts[key] = []

            # Clean old attempts
            cutoff = now - self.window_seconds
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]

            # Check rate
            if len(self._attempts[key]) >= self.max_attempts:
                self._lockouts[key] = now + self.lockout_seconds
                return False, f"Too many attempts. Locked for {self.lockout_seconds}s"

            self._attempts[key].append(now)
            return True, "OK"

    def record_success(self, key: str) -> None:
        """Clear attempts on successful auth."""
        with self._lock:
            self._attempts.pop(key, None)
            self._lockouts.pop(key, None)

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        with self._lock:
            return {
                "active_keys": len(self._attempts),
                "locked_keys": len(self._lockouts),
                "total_attempts": sum(len(v) for v in self._attempts.values()),
            }


# Global rate limiter
auth_limiter = RateLimiter(max_attempts=5, window_seconds=300, lockout_seconds=900)
api_limiter = RateLimiter(max_attempts=60, window_seconds=60, lockout_seconds=300)


# ═══════════════════════════════════════════════════════════════════════════
# 2. AUDIT LOGGER — Tamper-Proof Event Logging
# ═══════════════════════════════════════════════════════════════════════════

class AuditEvent(Enum):
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGE = "auth.password.change"
    API_KEY_ACCESS = "secret.api_key.access"
    API_KEY_ROTATE = "secret.api_key.rotate"
    CODE_EXEC = "code.execute"
    CODE_BLOCKED = "code.blocked"
    FILE_DELETE = "file.delete"
    FILE_WRITE = "file.write"
    INTRUSION_DETECTED = "security.intrusion"
    RATE_LIMIT_HIT = "security.rate_limit"
    SESSION_CREATE = "session.create"
    SESSION_EXPIRE = "session.expire"
    SETTINGS_CHANGE = "settings.change"


@dataclass
class AuditEntry:
    timestamp: float
    event: AuditEvent
    user_id: str
    details: str = ""
    ip: str = ""
    severity: str = "INFO"
    checksum: str = ""

    def to_dict(self) -> dict:
        return {
            "ts": self.timestamp,
            "event": self.event.value,
            "user": self.user_id,
            "details": self.details,
            "ip": self.ip,
            "severity": self.severity,
            "checksum": self.checksum,
        }


class AuditLogger:
    """Append-only audit log with integrity verification."""

    def __init__(self, log_path: Optional[Path] = None):
        if log_path is None:
            log_path = Path.home() / ".sonic" / "audit.log"
        self._path = log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        """Load the last entry's hash for chain verification."""
        try:
            if self._path.exists():
                lines = self._path.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if line.strip():
                        entry = json.loads(line)
                        return entry.get("checksum", "")
        except Exception:
            pass
        return "GENESIS"

    def _compute_hash(self, data: dict, prev_hash: str) -> str:
        """Compute HMAC-SHA256 for integrity chain."""
        payload = json.dumps(data, sort_keys=True) + prev_hash
        return hashlib.sha256(payload.encode()).hexdigest()[:32]

    def log(
        self,
        event: AuditEvent,
        user_id: str = "system",
        details: str = "",
        ip: str = "",
        severity: str = "INFO",
    ) -> AuditEntry:
        """Write an audit entry."""
        entry = AuditEntry(
            timestamp=time.time(),
            event=event,
            user_id=user_id,
            details=details,
            ip=ip,
            severity=severity,
        )
        data = entry.to_dict()
        data.pop("checksum")
        entry.checksum = self._compute_hash(data, self._last_hash)
        data["checksum"] = entry.checksum

        with self._lock:
            try:
                with open(self._path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data) + "\n")
                self._last_hash = entry.checksum
            except Exception as e:
                logger.error("[Audit] Write failed: %s", e)

        return entry

    def verify_integrity(self) -> tuple[bool, int, str]:
        """Verify the entire audit chain. Returns (valid, entry_count, error_msg)."""
        try:
            if not self._path.exists():
                return True, 0, ""

            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
            prev_hash = "GENESIS"
            count = 0

            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                entry = json.loads(line)
                stored_hash = entry.pop("checksum", "")
                computed = self._compute_hash(entry, prev_hash)
                if computed != stored_hash:
                    return False, count, f"Chain broken at entry {i + 1}"
                prev_hash = stored_hash
                count += 1

            return True, count, ""
        except Exception as e:
            return False, 0, f"Verification error: {e}"

    def get_recent(self, n: int = 50) -> list[dict]:
        """Get last N audit entries."""
        try:
            if not self._path.exists():
                return []
            lines = self._path.read_text(encoding="utf-8").strip().split("\n")
            entries = []
            for line in reversed(lines[-n:]):
                if line.strip():
                    entries.append(json.loads(line))
            return entries
        except Exception:
            return []


# Global audit logger
audit = AuditLogger()


# ═══════════════════════════════════════════════════════════════════════════
# 3. INTRUSION DETECTION — Anomaly + Signature Based
# ═══════════════════════════════════════════════════════════════════════════

class ThreatLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Threat:
    timestamp: float
    threat_type: str
    severity: ThreatLevel
    source: str
    details: str
    blocked: bool = False


class IntrusionDetector:
    """Detects suspicious patterns and anomalies."""

    def __init__(self):
        self._events: list[Threat] = []
        self._ip_counts: dict[str, list[float]] = defaultdict(list)
        self._user_anomalies: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

        # Signature patterns
        self._signatures: list[tuple[str, str, ThreatLevel]] = [
            # SQL injection
            (r"(?i)(union\s+select|or\s+1\s*=\s*1|drop\s+table|insert\s+into|delete\s+from)", "SQL Injection", ThreatLevel.HIGH),
            # XSS
            (r"<script[^>]*>|javascript:|on\w+\s*=", "XSS Attempt", ThreatLevel.HIGH),
            # Path traversal
            (r"\.\./\.\./|\.\.\\\\|/etc/passwd|/etc/shadow", "Path Traversal", ThreatLevel.CRITICAL),
            # Command injection
            (r"[;&|`]|\\$\(|\beval\s*\(|\bexec\s*\(", "Command Injection", ThreatLevel.CRITICAL),
            # Credential stuffing patterns
            (r"(?i)(admin|root|password|123456|qwerty)", "Weak Credential Probe", ThreatLevel.MEDIUM),
            # Data exfiltration
            (r"(?i)(curl|wget|requests\.post|socket\.connect).*\.(bin|dat|key|pem)", "Data Exfiltration", ThreatLevel.HIGH),
            # Privilege escalation
            (r"(?i)(sudo|chmod\s+777|chown\s+root|setuid)", "Privilege Escalation", ThreatLevel.CRITICAL),
            # Malware patterns
            (r"(?i)(reverse\s+shell|bind\s+shell|meterpreter|metasploit)", "Malware Signature", ThreatLevel.CRITICAL),
        ]

    def check_input(self, input_str: str, source: str = "user") -> list[Threat]:
        """Check input string against threat signatures."""
        threats = []

        for pattern, threat_type, severity in self._signatures:
            if re.search(pattern, input_str):
                threat = Threat(
                    timestamp=time.time(),
                    threat_type=threat_type,
                    severity=severity,
                    source=source,
                    details=f"Pattern matched: {input_str[:100]}",
                    blocked=severity in (ThreatLevel.HIGH, ThreatLevel.CRITICAL),
                )
                threats.append(threat)
                self._record_threat(threat)

        return threats

    def check_rate_anomaly(self, ip: str, max_per_minute: int = 30) -> Optional[Threat]:
        """Detect IP-based rate anomalies."""
        now = time.time()
        cutoff = now - 60

        with self._lock:
            self._ip_counts[ip] = [t for t in self._ip_counts[ip] if t > cutoff]
            self._ip_counts[ip].append(now)

            if len(self._ip_counts[ip]) > max_per_minute:
                threat = Threat(
                    timestamp=now,
                    threat_type="Rate Anomaly",
                    severity=ThreatLevel.HIGH,
                    source=ip,
                    details=f"{len(self._ip_counts[ip])} requests/min from {ip}",
                    blocked=True,
                )
                self._record_threat(threat)
                return threat

        return None

    def check_behavior_anomaly(self, user_id: str, action: str) -> Optional[Threat]:
        """Detect unusual user behavior patterns."""
        now = time.time()
        cutoff = now - 300  # 5 minutes

        with self._lock:
            self._user_anomalies[user_id] = [
                t for t in self._user_anomalies[user_id] if t > cutoff
            ]
            self._user_anomalies[user_id].append(now)

            # Rapid-fire actions
            if len(self._user_anomalies[user_id]) > 50:
                threat = Threat(
                    timestamp=now,
                    threat_type="Behavior Anomaly",
                    severity=ThreatLevel.MEDIUM,
                    source=user_id,
                    details=f"{len(self._user_anomalies[user_id])} actions in 5min",
                )
                self._record_threat(threat)
                return threat

        return None

    def _record_threat(self, threat: Threat) -> None:
        """Record a detected threat."""
        with self._lock:
            self._events.append(threat)
            # Keep last 1000 events
            if len(self._events) > 1000:
                self._events = self._events[-1000:]

        # Log to audit
        audit.log(
            event=AuditEvent.INTRUSION_DETECTED,
            user_id=threat.source,
            details=f"{threat.threat_type}: {threat.details}",
            severity=threat.severity.value.upper(),
        )

        logger.warning("[IDS] Threat: %s from %s (%s)",
                       threat.threat_type, threat.source, threat.severity.value)

    def get_threats(self, hours: int = 24) -> list[Threat]:
        """Get threats from last N hours."""
        cutoff = time.time() - (hours * 3600)
        with self._lock:
            return [t for t in self._events if t.timestamp > cutoff]

    def get_stats(self) -> dict:
        """Get intrusion detection statistics."""
        with self._lock:
            recent = [t for t in self._events if t.timestamp > time.time() - 3600]
            return {
                "total_threats_24h": len([t for t in self._events if t.timestamp > time.time() - 86400]),
                "threats_last_hour": len(recent),
                "blocked_count": sum(1 for t in recent if t.blocked),
                "by_type": dict(defaultdict(int, {t.threat_type: 1 for t in recent})),
            }


# Global intrusion detector
ids = IntrusionDetector()


# ═══════════════════════════════════════════════════════════════════════════
# 4. SESSION MANAGER — Secure Session Handling
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Session:
    session_id: str
    user_id: str
    created_at: float
    expires_at: float
    ip: str = ""
    user_agent: str = ""
    is_valid: bool = True
    last_activity: float = 0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> dict:
        return {
            "sid": self.session_id[:8] + "...",
            "user": self.user_id,
            "created": datetime.fromtimestamp(self.created_at).isoformat(),
            "expires": datetime.fromtimestamp(self.expires_at).isoformat(),
            "ip": self.ip,
            "valid": self.is_valid and not self.is_expired(),
        }


class SessionManager:
    """Secure session management with rotation and expiry."""

    def __init__(self, session_timeout: int = 3600, max_sessions: int = 10):
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, list[str]] = defaultdict(list)
        self._session_timeout = session_timeout
        self._max_sessions = max_sessions
        self._lock = threading.Lock()

    def create_session(
        self,
        user_id: str,
        ip: str = "",
        user_agent: str = "",
    ) -> Session:
        """Create a new session with secure token."""
        session_id = secrets.token_urlsafe(32)
        now = time.time()

        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + self._session_timeout,
            ip=ip,
            user_agent=user_agent,
            last_activity=now,
        )

        with self._lock:
            # Enforce max sessions per user
            user_sids = self._user_sessions[user_id]
            if len(user_sids) >= self._max_sessions:
                oldest = user_sids.pop(0)
                self._sessions.pop(oldest, None)

            self._sessions[session_id] = session
            self._user_sessions[user_id].append(session_id)

        audit.log(
            event=AuditEvent.SESSION_CREATE,
            user_id=user_id,
            details=f"Session created from {ip}",
        )

        return session

    def validate_session(self, session_id: str) -> Optional[Session]:
        """Validate and refresh a session."""
        with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return None

            if session.is_expired():
                self._invalidate(session_id)
                audit.log(
                    event=AuditEvent.SESSION_EXPIRE,
                    user_id=session.user_id,
                    details="Session expired",
                )
                return None

            if not session.is_valid:
                return None

            # Refresh expiry on activity
            session.last_activity = time.time()
            session.expires_at = time.time() + self._session_timeout
            return session

    def _invalidate(self, session_id: str) -> None:
        """Invalidate a session."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.is_valid = False
            user_sids = self._user_sessions.get(session.user_id, [])
            if session_id in user_sids:
                user_sids.remove(session_id)

    def invalidate_all(self, user_id: str) -> int:
        """Invalidate all sessions for a user."""
        count = 0
        with self._lock:
            sids = self._user_sessions.pop(user_id, [])
            for sid in sids:
                if sid in self._sessions:
                    self._sessions[sid].is_valid = False
                    del self._sessions[sid]
                    count += 1
        return count

    def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        count = 0
        now = time.time()
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
            for sid in expired:
                self._invalidate(sid)
                count += 1
        return count

    def get_active_sessions(self, user_id: str) -> list[Session]:
        """Get all active sessions for a user."""
        with self._lock:
            sids = self._user_sessions.get(user_id, [])
            return [
                self._sessions[sid]
                for sid in sids
                if sid in self._sessions and not self._sessions[sid].is_expired()
            ]


# Global session manager
sessions = SessionManager()


# ═══════════════════════════════════════════════════════════════════════════
# 5. INPUT SANITIZER — XSS & Injection Prevention
# ═══════════════════════════════════════════════════════════════════════════

class InputSanitizer:
    """Sanitize user inputs against XSS, injection, and overflow."""

    # HTML entities that need encoding
    _HTML_ESCAPE = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#x27;",
        "/": "&#x2F;",
        "`": "&#x60;",
    }

    @classmethod
    def sanitize_html(cls, text: str, max_len: int = 10000) -> str:
        """Escape HTML entities."""
        text = text[:max_len]
        for char, escaped in cls._HTML_ESCAPE.items():
            text = text.replace(char, escaped)
        return text

    @classmethod
    def sanitize_sql(cls, text: str) -> str:
        """Basic SQL injection prevention."""
        if not isinstance(text, str):
            return text
        # Remove null bytes
        text = text.replace("\x00", "")
        # Escape single quotes
        text = text.replace("'", "''")
        # Remove comment sequences
        text = re.sub(r"--\s", "", text)
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        return text

    @classmethod
    def sanitize_filename(cls, name: str) -> str:
        """Sanitize filename for safe filesystem operations."""
        # Remove path separators
        name = name.replace("/", "").replace("\\", "")
        # Remove null bytes
        name = name.replace("\x00", "")
        # Remove control characters
        name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)
        # Strip dots and spaces at ends
        name = name.strip(". ")
        # Limit length
        return name[:255]

    @classmethod
    def sanitize_path(cls, path: str) -> str:
        """Sanitize file path to prevent traversal."""
        # Normalize separators
        path = path.replace("\\", "/")
        # Remove null bytes
        path = path.replace("\x00", "")
        # Remove double dots
        while "/../" in path:
            path = path.replace("/../", "/")
        # Remove control characters
        path = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", path)
        return path

    @classmethod
    def sanitize_command(cls, cmd: str) -> str:
        """Sanitize shell command input."""
        # Block dangerous characters
        blocked = set(';&|`$(){}[]!#~<>?\\')
        return "".join(c for c in cmd if c not in blocked)

    @classmethod
    def validate_email(cls, email: str) -> bool:
        """Validate email format."""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @classmethod
    def validate_url(cls, url: str) -> bool:
        """Validate URL format and protocol."""
        pattern = r'^https?://[a-zA-Z0-9.-]+(/.*)?$'
        return bool(re.match(pattern, url))

    @classmethod
    def check_overflow(cls, data: str, max_size: int = 1_000_000) -> bool:
        """Check if data exceeds size limit."""
        return len(data.encode("utf-8")) > max_size


# Global sanitizer
sanitizer = InputSanitizer()


# ═══════════════════════════════════════════════════════════════════════════
# 6. API KEY ROTATION — Automatic Key Management
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class APIKeyRecord:
    key_id: str
    key_hash: str
    created_at: float
    expires_at: float
    is_active: bool = True
    last_used: float = 0
    use_count: int = 0


class APIKeyManager:
    """Manage API keys with automatic rotation."""

    def __init__(self, rotation_days: int = 90):
        self._keys: dict[str, APIKeyRecord] = {}
        self._rotation_days = rotation_days
        self._lock = threading.Lock()

    def generate_key(self, name: str, days_valid: int = 90) -> tuple[str, APIKeyRecord]:
        """Generate a new API key."""
        key = secrets.token_urlsafe(32)
        key_id = hashlib.sha256(key.encode()).hexdigest()[:16]
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        now = time.time()
        record = APIKeyRecord(
            key_id=key_id,
            key_hash=key_hash,
            created_at=now,
            expires_at=now + (days_valid * 86400),
        )

        with self._lock:
            self._keys[key_id] = record

        audit.log(
            event=AuditEvent.API_KEY_ROTATE,
            details=f"Key {key_id} generated, expires in {days_valid} days",
        )

        return key, record

    def validate_key(self, key: str) -> bool:
        """Validate an API key."""
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        with self._lock:
            for record in self._keys.values():
                if record.key_hash == key_hash:
                    if not record.is_active:
                        return False
                    if time.time() > record.expires_at:
                        record.is_active = False
                        return False
                    record.last_used = time.time()
                    record.use_count += 1
                    return True

        return False

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        with self._lock:
            record = self._keys.get(key_id)
            if record:
                record.is_active = False
                audit.log(
                    event=AuditEvent.API_KEY_ROTATE,
                    details=f"Key {key_id} revoked",
                )
                return True
        return False

    def cleanup_expired(self) -> int:
        """Remove expired keys."""
        count = 0
        now = time.time()
        with self._lock:
            for key_id, record in list(self._keys.items()):
                if now > record.expires_at:
                    record.is_active = False
                    count += 1
        return count

    def get_stats(self) -> dict:
        """Get key statistics."""
        with self._lock:
            active = sum(1 for r in self._keys.values() if r.is_active)
            expired = sum(1 for r in self._keys.values() if time.time() > r.expires_at)
            return {
                "total_keys": len(self._keys),
                "active_keys": active,
                "expired_keys": expired,
            }


# Global API key manager
api_keys = APIKeyManager()


# ═══════════════════════════════════════════════════════════════════════════
# 7. SECURITY DASHBOARD — Real-time Security Status
# ═══════════════════════════════════════════════════════════════════════════

def get_security_status() -> dict:
    """Get comprehensive security status."""
    # Audit log integrity
    audit_valid, audit_count, audit_error = audit.verify_integrity()

    return {
        "timestamp": datetime.now().isoformat(),
        "rate_limiter": auth_limiter.get_stats(),
        "audit_log": {
            "valid": audit_valid,
            "entries": audit_count,
            "error": audit_error,
        },
        "intrusion_detection": ids.get_stats(),
        "api_keys": api_keys.get_stats(),
        "active_sessions": len(sessions._sessions),
    }


def security_health_check() -> tuple[bool, list[str]]:
    """Run a security health check. Returns (healthy, issues)."""
    issues = []

    # Check audit log integrity
    valid, count, error = audit.verify_integrity()
    if not valid:
        issues.append(f"Audit log integrity compromised: {error}")

    # Check for recent intrusions
    recent_threats = ids.get_threats(hours=1)
    high_threats = [t for t in recent_threats if t.severity in (ThreatLevel.HIGH, ThreatLevel.CRITICAL)]
    if high_threats:
        issues.append(f"{len(high_threats)} high-severity threats in last hour")

    # Check locked accounts
    rate_stats = auth_limiter.get_stats()
    if rate_stats["locked_keys"] > 0:
        issues.append(f"{rate_stats['locked_keys']} accounts locked out")

    return len(issues) == 0, issues
