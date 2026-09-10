"""SONIC AI — Single authoritative version declaration.

Every part of the application must import from here.
Never hardcode version strings elsewhere.
The updater fetches release info from GitHub API — no hardcoded update URLs here.
"""
from __future__ import annotations

# ── Semantic version (major.minor.patch) ────────────────────────────────────
APP_VERSION: str = "1.0.4"

# ── Build metadata (set by release.py) ──────────────────────────────────────
BUILD_VERSION: str = "1.0.0+build.0"
BUILD_DATE: str = "2026-09-10"

# ── Application identity ────────────────────────────────────────────────────
APP_NAME: str = "SONIC AI"
APP_ID: str = "sonic-ai"
APP_CHANNEL: str = "stable"  # stable | beta | dev

# ── Schema version for data migrations ──────────────────────────────────────
APP_SCHEMA_VERSION: int = 1

# ── GitHub release source ───────────────────────────────────────────────────
GITHUB_REPO: str = "elyxcart-rgb/ATHERION-LABS"

# ── Semantic version comparison ──────────────────────────────────────────────

def _parse_semver(v: str) -> tuple[int, int, int]:
    """Parse 'X.Y.Z' into (major, minor, patch). Strips leading '+' metadata."""
    core = v.split("+")[0].split("-")[0]
    parts = core.split(".")
    while len(parts) < 3:
        parts.append("0")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def version_tuple(v: str | None = None) -> tuple[int, int, int]:
    """Return (major, minor, patch) for given version or APP_VERSION."""
    return _parse_semver(v or APP_VERSION)


def is_newer(remote: str, local: str | None = None) -> bool:
    """Return True if *remote* version is strictly newer than *local*."""
    return _parse_semver(remote) > _parse_semver(local or APP_VERSION)


def is_compatible(remote_min: str) -> bool:
    """Return True if current APP_VERSION >= remote_min (minimum supported)."""
    return _parse_semver(APP_VERSION) >= _parse_semver(remote_min)


def format_version(v: str | None = None) -> str:
    """Pretty-print version: 'SONIC AI v1.2.3'."""
    return f"{APP_NAME} v{v or APP_VERSION}"
