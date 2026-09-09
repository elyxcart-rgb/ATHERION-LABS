"""SONIC AI — Code Execution Sandbox.

Scans LLM-generated code for dangerous patterns before execution.
Blocks destructive commands, filesystem escapes, and network exfiltration.
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("sonic.sandbox")


class ThreatLevel(Enum):
    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    BLOCKED = "blocked"


@dataclass
class ScanResult:
    level: ThreatLevel = ThreatLevel.SAFE
    threats: list[str] = field(default_factory=list)
    blocked_patterns: list[str] = field(default_factory=list)

    @property
    def is_safe(self) -> bool:
        return self.level == ThreatLevel.SAFE

    @property
    def summary(self) -> str:
        if self.is_safe:
            return "Code passed security scan."
        severity = "BLOCKED" if self.level == ThreatLevel.BLOCKED else "WARNING"
        lines = [f"[{severity}] {len(self.threats)} threat(s) detected:"]
        for t in self.threats:
            lines.append(f"  - {t}")
        return "\n".join(lines)


# ── Dangerous patterns ─────────────────────────────────────────────────

_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    # System destruction
    (r"os\.system\s*\(\s*['\"].*rm\s+-rf", "Destructive: rm -rf"),
    (r"os\.system\s*\(\s*['\"].*del\s+/[sfq]", "Destructive: Windows del"),
    (r"subprocess\..*['\"].*rm\s+-rf", "Destructive: rm -rf via subprocess"),
    (r"shutil\.rmtree\s*\(", "Recursive directory deletion"),
    (r"os\.remove\s*\(\s*['\"]\/", "Absolute path deletion"),

    # Network exfiltration
    (r"requests\.post\s*\(.*(?:password|token|secret|key|credential)", "Possible credential exfiltration"),
    (r"urllib\.request\.urlopen\s*\(.*(?:password|token|secret)", "Possible credential exfiltration"),
    (r"socket\.connect\s*\(", "Raw socket connection"),
    (r"subprocess\..*['\"].*curl.*-X\s*POST", "Data exfiltration via curl"),

    # Privilege escalation
    (r"os\.system\s*\(\s*['\"].*sudo", "Privilege escalation: sudo"),
    (r"subprocess\..*['\"].*sudo", "Privilege escalation: sudo"),
    (r"os\.system\s*\(\s*['\"].*chmod\s+777", "Dangerous permission change: chmod 777"),
    (r"ctypes\.windll.*ShellExecute", "Windows ShellExecute (privilege escalation)"),

    # Code injection
    (r"exec\s*\(\s*(?!.*#.*sandbox)", "Dynamic code execution: exec()"),
    (r"eval\s*\(\s*(?!.*#.*sandbox)", "Dynamic code evaluation: eval()"),
    (r"__import__\s*\(", "Dynamic module import"),

    # System info leakage
    (r"os\.environ\s*\[.*(?:PASSWORD|SECRET|TOKEN|KEY|CRED)", "Reading system secrets from env"),
    (r"open\s*\(.*(?:\/etc\/passwd|\/etc\/shadow)", "Reading system auth files"),

    # Process manipulation
    (r"os\.kill\s*\(", "Process termination"),
    (r"subprocess\..*['\"].*taskkill", "Windows process kill"),
    (r"subprocess\..*['\"].*kill", "Process kill via subprocess"),

    # Disk manipulation
    (r"subprocess\..*['\"].*format\s+[a-zA-Z]:", "Disk format attempt"),
    (r"subprocess\..*['\"].*diskpart", "Disk partition manipulation"),
]

_SUSPICIOUS_PATTERNS: list[tuple[str, str]] = [
    # Broad file operations
    (r"os\.system\s*\(", "OS command execution (review needed)"),
    (r"subprocess\.call\s*\(.*shell\s*=\s*True", "Shell=True subprocess call"),
    (r"subprocess\.Popen\s*\(.*shell\s*=\s*True", "Shell=True Popen call"),

    # Network access
    (r"requests\.(get|post|put|delete)\s*\(", "HTTP request (review destination)"),
    (r"urllib\.request\.", "URL library usage"),

    # File system
    (r"open\s*\(.*['\"]w", "File write operation"),
    (r"os\.makedirs\s*\(", "Directory creation"),
    (r"shutil\.copy", "File copy operation"),

    # Environment
    (r"os\.environ", "Environment variable access"),
    (r"os\.getenv\s*\(", "Environment variable read"),
]


def scan_code(code: str) -> ScanResult:
    """Scan code for dangerous patterns."""
    result = ScanResult()
    lines = code.split("\n")

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # Check blocked patterns
        for pattern, desc in _BLOCKED_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                result.level = ThreatLevel.BLOCKED
                result.threats.append(f"L{line_no}: {desc}")
                result.blocked_patterns.append(pattern)

        # Check suspicious patterns
        for pattern, desc in _SUSPICIOUS_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                if result.level != ThreatLevel.BLOCKED:
                    result.level = ThreatLevel.SUSPICIOUS
                result.threats.append(f"L{line_no}: {desc}")

    if result.threats:
        logger.warning("[Sandbox] %d threat(s) found: %s",
                       len(result.threats), result.level.value)

    return result


def sanitize_for_execution(code: str) -> tuple[str, ScanResult]:
    """Scan code and return cleaned version or rejection.

    Returns (cleaned_code_or_empty, scan_result).
    If scan_result.is_safe is False, cleaned_code is empty and should not run.
    """
    result = scan_code(code)

    if result.level == ThreatLevel.BLOCKED:
        logger.error("[Sandbox] Code BLOCKED: %s", result.threats)
        return "", result

    if result.level == ThreatLevel.SUSPICIOUS:
        logger.warning("[Sandbox] Code SUSPICIOUS but allowed: %s", result.threats)

    return code, result


def validate_package_name(name: str) -> bool:
    """Validate pip package name to prevent injection."""
    if not name or not name.strip():
        return False
    # Only allow valid pip package characters
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9._-]*[a-zA-Z0-9])?$', name.strip()))


def sanitize_filename(name: str) -> str:
    """Sanitize a filename to prevent path traversal."""
    # Remove path separators
    name = name.replace("/", "").replace("\\", "")
    # Remove null bytes
    name = name.replace("\x00", "")
    # Strip dots and spaces
    name = name.strip(". ")
    return name
