"1.0.1"

# ── Build metadata (set by CI / build script) ───────────────────────────────
BUILD_VERSION: str = "1.0.1+build.1788866837"
BUILD_DATE: str = "2026-09-08"

# ── Application identity ─────────────────────────────────────────────────────
APP_NAME: str = "SONIC AI"
APP_ID: str = "sonic-ai"
APP_CHANNEL: str = "stable"  # stable | beta | dev

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
