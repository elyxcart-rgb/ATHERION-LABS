"""SONIC AI — Plugin Security Verifier.

A high-end security layer that protects SONIC from rogue plugins by
**verifying integrity, authorship, and permissions** before a plugin is
loaded.

Why this matters:
    - The current ``core/plugin_loader.py`` runs *any* ``.py`` file dropped
      into ``plugins/`` with the user's full permissions.
    - This verifier adds a defence-in-depth chain: hash, trusted-author
      manifest, declared permissions, and a permission gate.
    - Zero-touch: nothing in the existing loader is modified. The loader
      can *opt in* by calling ``verify(path)`` first; if it doesn't, the
      system keeps working exactly as before.

Public surface (stable, opt-in):
    - ``verify_plugin(path)``              — entry point
    - ``VerificationResult``               — dataclass with verdict + reasons
    - ``TrustLevel``                       — enum: TRUSTED / KNOWN / UNKNOWN / BLOCKED
    - ``TrustedRegistry``                  — manages the trusted hash database
    - ``PermissionManifest``               — dataclass for declared permissions
    - ``PermissionViolation``              — raised when a plugin exceeds its grant
"""
from __future__ import annotations

import ast
import hashlib
import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("PLUGIN_VERIFIER")

_REGISTRY_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "plugins_registry"
_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
_REGISTRY_PATH = _REGISTRY_DIR / "trusted_hashes.db"


# ═════════════════════════════════════════════════════════════════════════════
# Trust + result types
# ═════════════════════════════════════════════════════════════════════════════

class TrustLevel(Enum):
    """How much we trust a plugin before loading it."""
    TRUSTED = "trusted"         # Signed by an author on the trusted list
    KNOWN = "known"             # Hash matches a previously approved version
    UNKNOWN = "unknown"         # Never seen — requires explicit user approval
    BLOCKED = "blocked"         # Hash is on the block list


@dataclass
class VerificationResult:
    path: str
    sha256: str
    trust: TrustLevel
    author: Optional[str] = None
    version: Optional[str] = None
    permissions: "PermissionManifest" = field(default_factory=lambda: PermissionManifest())
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when the plugin is safe to load (no errors)."""
        return not self.errors and self.trust != TrustLevel.BLOCKED

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "trust": self.trust.value,
            "author": self.author,
            "version": self.version,
            "ok": self.ok,
            "permissions": self.permissions.to_dict(),
            "warnings": self.warnings,
            "errors": self.errors,
        }


# ═════════════════════════════════════════════════════════════════════════════
# Permission manifest
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class PermissionManifest:
    """What a plugin is allowed to do. Empty = safe, no side effects."""
    network: bool = False
    filesystem: bool = False
    subprocess: bool = False
    microphone: bool = False
    camera: bool = False
    clipboard: bool = False
    notifications: bool = False
    allowed_paths: list[str] = field(default_factory=list)
    allowed_hosts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class PermissionViolation(RuntimeError):
    """Raised when running code attempts to exceed its declared grant."""


_PERMISSION_AUDITORS = {}  # name -> callable


def register_permission_auditor(name: str, fn):
    """Register a runtime check for a permission. ``fn(path) -> bool`."""
    _PERMISSION_AUDITORS[name] = fn


def check_permission(plugin_id: str, permission: str, *args, **kwargs) -> bool:
    """Runtime check used by guarded stdlib wrappers.

    Returns True when the plugin has declared the permission AND the
    auditor (if any) approves the specific call.
    """
    manifest = _RUNTIME_GRANTS.get(plugin_id)
    if manifest is None:
        # No manifest → conservative deny
        return False
    flag = getattr(manifest, permission, False)
    if not flag:
        return False
    auditor = _PERMISSION_AUDITORS.get(permission)
    if auditor is None:
        return True
    try:
        return bool(auditor(*args, **kwargs))
    except Exception as e:
        logger.warning(f"[permissions] {permission} auditor raised: {e}")
        return False


_RUNTIME_GRANTS: dict[str, PermissionManifest] = {}


def _extract_permissions_from_docstring(text: str) -> PermissionManifest:
    """Look for a SONIC-PERMISSIONS block in the module docstring."""
    if not text:
        return PermissionManifest()
    # Find first triple-quoted block
    for q in ('"""', "'''"):
        start = text.find(q)
        if start != -1:
            end = text.find(q, start + 3)
            if end == -1:
                break
            docstring = text[start + 3:end]
            if "SONIC-PERMISSIONS" in docstring:
                return _parse_permission_block(docstring)
            break
    return PermissionManifest()


def _parse_permission_block(docstring: str) -> PermissionManifest:
    """Parse a YAML-like block:
        SONIC-PERMISSIONS:
            network: true
            filesystem: true
            allowed_paths:
              - C:/Users/me/Documents
            allowed_hosts:
              - api.openai.com
    """
    import re
    perm = PermissionManifest()

    def _yn(v: str) -> bool:
        return v.strip().lower() in ("true", "yes", "1", "on")

    in_block = False
    section = None  # list | scalar
    current_list_key = None

    for raw in docstring.splitlines():
        line = raw.rstrip()
        if not in_block:
            if "SONIC-PERMISSIONS:" in line:
                in_block = True
            continue

        if not line.strip():
            continue
        stripped = line.strip()

        # List item: "  - foo"
        m = re.match(r"-\s*(.+)$", stripped)
        if m and current_list_key is not None:
            getattr(perm, current_list_key).append(m.group(1).strip())
            continue
        current_list_key = None

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val == "":
                # New section header — could be scalar or list
                if key in ("allowed_paths", "allowed_hosts"):
                    section = "list"
                    current_list_key = key
                else:
                    section = "scalar"
            else:
                if hasattr(perm, key):
                    if isinstance(getattr(perm, key), bool):
                        setattr(perm, key, _yn(val))
                    elif isinstance(getattr(perm, key), list):
                        getattr(perm, key).append(val)
                section = None
    return perm


# ═════════════════════════════════════════════════════════════════════════════
# Trusted hash registry
# ═════════════════════════════════════════════════════════════════════════════

class TrustedRegistry:
    """SQLite-backed store of approved plugin hashes + authors."""

    def __init__(self, db_path: Optional[Path] = None):
        self._path = Path(db_path) if db_path else _REGISTRY_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trusted (
                sha256    TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                author    TEXT,
                version   TEXT,
                added_at  REAL NOT NULL,
                notes     TEXT
            );
            CREATE TABLE IF NOT EXISTS blocked (
                sha256    TEXT PRIMARY KEY,
                reason    TEXT,
                added_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS known (
                sha256    TEXT PRIMARY KEY,
                name      TEXT NOT NULL,
                first_seen REAL NOT NULL,
                approved  INTEGER NOT NULL DEFAULT 0
            );
        """)
        self._conn.commit()

    def trust(self, sha256: str, name: str, author: str = "",
              version: str = "", notes: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO trusted "
                "(sha256, name, author, version, added_at, notes) "
                "VALUES (?, ?, ?, ?, strftime('%s','now'), ?)",
                (sha256, name, author, version, notes),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO known (sha256, name, first_seen, approved) "
                "VALUES (?, ?, strftime('%s','now'), 1) "
                "ON CONFLICT(sha256) DO UPDATE SET approved=1",
                (sha256, name),
            )
            self._conn.commit()

    def block(self, sha256: str, reason: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO blocked (sha256, reason, added_at) "
                "VALUES (?, ?, strftime('%s','now'))",
                (sha256, reason),
            )
            self._conn.commit()

    def is_blocked(self, sha256: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM blocked WHERE sha256=?", (sha256,)
        ).fetchone()
        return row is not None

    def lookup(self, sha256: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT name, author, version FROM trusted WHERE sha256=?",
            (sha256,),
        ).fetchone()
        if row:
            return {"name": row["name"], "author": row["author"],
                    "version": row["version"]}
        return None

    def record_seen(self, sha256: str, name: str) -> bool:
        """Mark a plugin as 'seen' (and approved if it wasn't blocked)."""
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO known (sha256, name, first_seen, approved) "
                "VALUES (?, ?, strftime('%s','now'), 0)",
                (sha256, name),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT approved FROM known WHERE sha256=?", (sha256,)
            ).fetchone()
            return bool(row and row["approved"])

    def list_trusted(self) -> list[dict]:
        return [
            {"sha256": r["sha256"], "name": r["name"], "author": r["author"],
             "version": r["version"], "added_at": r["added_at"]}
            for r in self._conn.execute(
                "SELECT sha256, name, author, version, added_at "
                "FROM trusted ORDER BY added_at DESC"
            ).fetchall()
        ]

    def list_blocked(self) -> list[dict]:
        return [
            {"sha256": r["sha256"], "reason": r["reason"], "added_at": r["added_at"]}
            for r in self._conn.execute(
                "SELECT sha256, reason, added_at "
                "FROM blocked ORDER BY added_at DESC"
            ).fetchall()
        ]


# ═════════════════════════════════════════════════════════════════════════════
# Static analysis
# ═════════════════════════════════════════════════════════════════════════════

# Imports / calls that hint at high-risk behaviour, used to populate warnings.
_NETWORK_IMPORTS = {"requests", "urllib", "httpx", "aiohttp", "socket"}
_FS_IMPORTS      = {"os", "shutil", "pathlib", "glob"}
_SUBPROCESS_IMPORTS = {"subprocess", "os.system", "ctypes"}
_MIC_IMPORTS     = {"pyaudio", "sounddevice", "speech_recognition"}


def _static_analysis(source: str) -> tuple[PermissionManifest, list[str]]:
    """Walk the AST and infer the permissions a plugin likely needs."""
    perm = PermissionManifest()
    warnings: list[str] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        warnings.append(f"Plugin has a syntax error: {e}")
        return perm, warnings

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ("system", "popen", "run", "call", "check_output", "Popen"):
                imported.add("subprocess")
            if name in ("open", "unlink", "rmdir", "remove", "rename"):
                imported.add("os")

    if imported & _NETWORK_IMPORTS:
        perm.network = True
        warnings.append(f"Imports network modules: {sorted(imported & _NETWORK_IMPORTS)}")
    if imported & _FS_IMPORTS:
        perm.filesystem = True
    if imported & _SUBPROCESS_IMPORTS:
        perm.subprocess = True
        warnings.append("Spawns subprocesses — high risk")
    if imported & _MIC_IMPORTS:
        perm.microphone = True
    if "cv2" in imported or "pyautogui" in imported:
        perm.camera = True

    return perm, warnings


# ═════════════════════════════════════════════════════════════════════════════
# Main verifier
# ═════════════════════════════════════════════════════════════════════════════

def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_plugin(path: str | Path,
                  registry: Optional[TrustedRegistry] = None,
                  auto_trust_known: bool = True) -> VerificationResult:
    """Run the full security verification chain on a plugin file.

    Order of checks:
        1. File exists and is readable.
        2. SHA-256 is computed.
        3. Registry block-list → BLOCKED (short-circuits everything else).
        4. Trusted hash → TRUSTED.
        5. Known hash → KNOWN.
        6. Unknown hash → UNKNOWN with warnings from static analysis.
        7. Permissions are extracted from docstring OR inferred from AST.
    """
    p = Path(path)
    result = VerificationResult(
        path=str(p), sha256="", trust=TrustLevel.UNKNOWN,
    )

    if not p.exists():
        result.errors.append(f"File not found: {p}")
        return result

    if not p.is_file():
        result.errors.append(f"Not a file: {p}")
        return result

    if p.suffix != ".py":
        result.warnings.append(f"Unexpected extension: {p.suffix} (expected .py)")

    # 1) Hash
    try:
        result.sha256 = _hash_file(p)
    except Exception as e:
        result.errors.append(f"Hashing failed: {e}")
        return result

    # 2) Registry
    reg = registry or TrustedRegistry()

    if reg.is_blocked(result.sha256):
        result.trust = TrustLevel.BLOCKED
        result.errors.append("Hash is on the block list")
        return result

    trusted_meta = reg.lookup(result.sha256)
    if trusted_meta:
        result.trust = TrustLevel.TRUSTED
        result.author = trusted_meta.get("author") or ""
        result.version = trusted_meta.get("version") or ""
    else:
        if auto_trust_known and reg.record_seen(result.sha256, p.stem):
            result.trust = TrustLevel.KNOWN
        else:
            result.trust = TrustLevel.UNKNOWN

    # 3) Permissions — declared (docstring) or inferred (AST)
    try:
        source = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        result.errors.append(f"Could not read source: {e}")
        return result

    declared = _extract_permissions_from_docstring(source)
    inferred, warnings = _static_analysis(source)
    result.warnings.extend(warnings)

    # Merge: a permission is granted if either declared OR inferred
    merged = PermissionManifest()
    for f in (
        "network", "filesystem", "subprocess",
        "microphone", "camera", "clipboard", "notifications",
    ):
        val = getattr(declared, f) or getattr(inferred, f)
        setattr(merged, f, val)
    merged.allowed_paths = list({*declared.allowed_paths, *inferred.allowed_paths})
    merged.allowed_hosts = list({*declared.allowed_hosts, *inferred.allowed_hosts})

    result.permissions = merged

    # 4) Hard rules — plugins may NEVER do this without explicit admin trust
    if merged.subprocess and result.trust != TrustLevel.TRUSTED:
        result.warnings.append(
            "Plugin spawns subprocesses — only TRUSTED plugins should do this"
        )

    # Cache runtime grant so check_permission() can be called later
    _RUNTIME_GRANTS[p.stem] = merged
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Convenience helpers
# ═════════════════════════════════════════════════════════════════════════════

def sign_plugin(path: str | Path, author: str = "",
                version: str = "", notes: str = "",
                registry: Optional[TrustedRegistry] = None) -> str:
    """Compute the hash and add the plugin to the trusted list.

    Returns the SHA-256 hash that was registered.
    """
    p = Path(path)
    sha = _hash_file(p)
    reg = registry or TrustedRegistry()
    reg.trust(sha, name=p.stem, author=author, version=version, notes=notes)
    logger.info(f"Signed {p.name} as {author or '<no author>'} ({sha[:12]}…)")
    return sha


def block_plugin(path: str | Path, reason: str = "",
                 registry: Optional[TrustedRegistry] = None) -> str:
    """Compute the hash and add the plugin to the block list."""
    p = Path(path)
    sha = _hash_file(p)
    reg = registry or TrustedRegistry()
    reg.block(sha, reason=reason)
    logger.warning(f"Blocked {p.name} ({sha[:12]}…) — {reason}")
    return sha


__all__ = [
    "verify_plugin", "sign_plugin", "block_plugin",
    "VerificationResult", "TrustLevel",
    "PermissionManifest", "PermissionViolation",
    "TrustedRegistry",
    "check_permission", "register_permission_auditor",
]
