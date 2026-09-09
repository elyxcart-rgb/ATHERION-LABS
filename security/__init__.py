"""SONIC AI Security Module.

Provides comprehensive security infrastructure:
- Rate limiting (brute force protection)
- Audit logging (tamper-proof chain)
- Intrusion detection (signature + anomaly)
- Session management (rotation, expiry)
- Input sanitization (XSS, SQL, path traversal)
- API key rotation (automatic expiry)
"""
from .advanced import (
    auth_limiter,
    api_limiter,
    audit,
    ids,
    sessions,
    sanitizer,
    api_keys,
    get_security_status,
    security_health_check,
    AuditEvent,
    ThreatLevel,
)

__all__ = [
    "auth_limiter",
    "api_limiter",
    "audit",
    "ids",
    "sessions",
    "sanitizer",
    "api_keys",
    "get_security_status",
    "security_health_check",
    "AuditEvent",
    "ThreatLevel",
]
