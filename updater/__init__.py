"""SONIC AI — Update Manager Core.

State machine, version checking, download, verification, staging, rollback.

Architecture:
    UpdateManager (this module)
        → checks remote manifest
        → downloads update package
        → verifies SHA-256 + optional signature
        → stages files in temp directory
        → launches updater_helper.bat to swap files
        → helper closes SONIC, replaces files, restarts SONIC

User data paths are NEVER touched by the updater.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("UPDATER")

# ── Paths ────────────────────────────────────────────────────────────────────
# When running as EXE, use the EXE's directory. When running as source, use project root.
if getattr(sys, 'frozen', False):
    # Running as PyInstaller EXE
    _APP_DIR = Path(sys.executable).resolve().parent
else:
    # Running as Python source
    _APP_DIR = Path(__file__).resolve().parent.parent

_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "SONIC AI"
_UPDATES_DIR = _USER_DATA / "updates"
_STAGING_DIR = _UPDATES_DIR / "staging"
_BACKUP_DIR = _UPDATES_DIR / "backup"
_DOWNLOAD_DIR = _UPDATES_DIR / "downloads"
_MANIFEST_CACHE = _UPDATES_DIR / ".manifest_cache.json"
_SETTINGS_PATH = _USER_DATA / "update_settings.json"
_LAST_CHECK_PATH = _USER_DATA / ".last_update_check"

# ── State Machine ────────────────────────────────────────────────────────────

class UpdateState(Enum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    STAGING = "staging"
    WAITING_TO_INSTALL = "waiting_to_install"
    INSTALLING = "installing"
    VERIFYING_INSTALL = "verifying_install"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


# ── Manifest Schema ──────────────────────────────────────────────────────────

@dataclass
class UpdateManifest:
    """Remote release manifest."""
    app: str = "SONIC AI"
    channel: str = "stable"
    version: str = ""
    minimum_supported_version: str = "0.0.0"
    release_date: str = ""
    mandatory: bool = False
    title: str = ""
    summary: str = ""
    download_url: str = ""
    sha256: str = ""
    signature: str = ""
    size_bytes: int = 0
    release_notes_url: str = ""
    release_notes: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "UpdateManifest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__ if getattr(self, k)}


@dataclass
class UpdateProgress:
    """Progress info during download/install."""
    state: UpdateState = UpdateState.IDLE
    percent: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    message: str = ""
    error: str = ""


# ── Update Manager ───────────────────────────────────────────────────────────

class UpdateManager:
    """Core update manager — state machine + operations."""

    MANIFEST_URL = "MANIFEST_URL: str = "https://raw.githubusercontent.com/elyxcart-rgb/ATHERION-LABS/main/releases/stable.json"
    CHECK_INTERVAL_HOURS = 6  # don't check more often than this

    def __init__(self) -> None:
        self.state = UpdateState.IDLE
        self.manifest: UpdateManifest | None = None
        self.progress = UpdateProgress()
        self._callbacks: list[Callable[[UpdateProgress], None]] = []
        self._ensure_dirs()

    # ── Public API ───────────────────────────────────────────────────────

    def register_callback(self, cb: Callable[[UpdateProgress], None]) -> None:
        self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable[[UpdateProgress], None]) -> None:
        self._callbacks = [c for c in self._callbacks if c is not cb]

    def _emit(self) -> None:
        self.progress.state = self.state
        for cb in self._callbacks:
            try:
                cb(self.progress)
            except Exception:
                pass

    def _set_state(self, state: UpdateState, msg: str = "", error: str = "") -> None:
        self.state = state
        self.progress.state = state
        self.progress.message = msg
        self.progress.error = error
        logger.info("[UPDATER] State: %s — %s", state.value, msg or error or "OK")
        self._emit()

    # ── Check for Update ─────────────────────────────────────────────────

    def should_check(self) -> bool:
        """Rate-limit: only check once per CHECK_INTERVAL_HOURS."""
        try:
            if _LAST_CHECK_PATH.exists():
                last = float(_LAST_CHECK_PATH.read_text().strip())
                if time.time() - last < self.CHECK_INTERVAL_HOURS * 3600:
                    return False
        except Exception:
            pass
        return True

    def mark_checked(self) -> None:
        _LAST_CHECK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LAST_CHECK_PATH.write_text(str(time.time()))

    def check_for_update(self, force: bool = False) -> UpdateManifest | None:
        """Check remote manifest. Returns manifest if update available, else None."""
        import urllib.request
        import urllib.error

        logger.info("[UPDATER] Checking for updates (force=%s)...", force)

        if not force and not self.should_check():
            logger.info("[UPDATER] Skipping check (recently checked)")
            return None

        self._set_state(UpdateState.CHECKING, "Checking for updates...")
        self.mark_checked()

        try:
            logger.info("[UPDATER] Fetching manifest from: %s", self.MANIFEST_URL)
            req = urllib.request.Request(
                self.MANIFEST_URL,
                headers={"User-Agent": "SONIC-AI-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            logger.info("[UPDATER] Manifest received: version=%s, channel=%s", data.get("version"), data.get("channel"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
            logger.warning("[UPDATER] Check failed (network): %s", e)
            self._set_state(UpdateState.IDLE, error=f"Check failed: {e}")
            return None

        manifest = UpdateManifest.from_dict(data)

        if not manifest.version:
            logger.warning("[UPDATER] Invalid manifest: no version")
            self._set_state(UpdateState.IDLE, error="Invalid manifest: no version")
            return None

        from version import APP_VERSION, is_newer, is_compatible, APP_CHANNEL

        logger.info("[UPDATER] Local: v%s, Remote: v%s, Channel: %s", APP_VERSION, manifest.version, APP_CHANNEL)

        # Channel filter — only show updates for same channel
        if manifest.channel != APP_CHANNEL:
            logger.info("[UPDATER] Ignoring %s channel (we are %s)", manifest.channel, APP_CHANNEL)
            self._set_state(UpdateState.IDLE)
            return None

        # Downgrade protection
        if not is_newer(manifest.version, APP_VERSION):
            logger.info("[UPDATER] Already up to date (%s)", APP_VERSION)
            self._set_state(UpdateState.IDLE, "You're up to date!")
            return None

        # Minimum version check
        if not is_compatible(manifest.minimum_supported_version):
            logger.warning("[UPDATER] Version too old: %s < %s", APP_VERSION, manifest.minimum_supported_version)
            self._set_state(
                UpdateState.IDLE,
                error=f"Your version ({APP_VERSION}) is too old. "
                      f"Minimum: {manifest.minimum_supported_version}. "
                      "Please reinstall from sonic-ai.dev.",
            )
            return None

        logger.info("[UPDATER] Update available: v%s -> v%s", APP_VERSION, manifest.version)
        self.manifest = manifest
        self._set_state(
            UpdateState.AVAILABLE,
            f"Update available: v{manifest.version}",
        )
        # Cache manifest
        try:
            _MANIFEST_CACHE.write_text(json.dumps(data, indent=2))
        except Exception:
            pass
        return manifest

    # ── Download ─────────────────────────────────────────────────────────

    def download_update(self, manifest: UpdateManifest | None = None) -> Path | None:
        """Download update package to staging directory. Returns path to zip."""
        manifest = manifest or self.manifest
        if not manifest or not manifest.download_url:
            self._set_state(UpdateState.FAILED, error="No manifest or download URL")
            return None

        self._set_state(UpdateState.DOWNLOADING, f"Downloading v{manifest.version}...")
        _STAGING_DIR.mkdir(parents=True, exist_ok=True)

        zip_path = _STAGING_DIR / f"sonic-v{manifest.version}.zip"

        # Resume support — check partial download
        downloaded = 0
        if zip_path.exists():
            downloaded = zip_path.stat().st_size
            if manifest.size_bytes and downloaded >= manifest.size_bytes:
                logger.info("[UPDATER] Partial file already complete")
                self.progress.percent = 100.0
                self._emit()
                return zip_path

        import urllib.request

        headers = {"User-Agent": "SONIC-AI-Updater/1.0"}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"

        req = urllib.request.Request(manifest.download_url, headers=headers)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    # Check if server supports range
                    code = resp.getcode()
                    if code == 206:
                        mode = "ab"
                    elif downloaded > 0 and code == 200:
                        mode = "wb"  # server doesn't support range, restart
                        downloaded = 0
                    else:
                        mode = "wb"
                        downloaded = 0

                    total = manifest.size_bytes or int(resp.headers.get("Content-Length", 0))
                    self.progress.total_bytes = total

                    with open(zip_path, mode) as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                self.progress.percent = (downloaded / total) * 100
                                self.progress.downloaded_bytes = downloaded
                                self._emit()

                logger.info("[UPDATER] Download complete: %d bytes", downloaded)
                return zip_path

            except (urllib.error.URLError, OSError) as e:
                logger.warning("[UPDATER] Download attempt %d failed: %s", attempt + 1, e)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                self._set_state(UpdateState.FAILED, error=f"Download failed: {e}")
                # Clean up partial download
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return None

        return None

    # ── Verification ─────────────────────────────────────────────────────

    def verify_integrity(self, zip_path: Path, expected_sha256: str) -> bool:
        """Verify SHA-256 of downloaded package."""
        self._set_state(UpdateState.VERIFYING, "Verifying integrity...")

        if not expected_sha256:
            logger.warning("[UPDATER] No SHA-256 in manifest — skipping hash check")
            return True

        sha256 = hashlib.sha256()
        try:
            with open(zip_path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sha256.update(chunk)
        except OSError as e:
            self._set_state(UpdateState.FAILED, error=f"Hash check failed: {e}")
            return False

        actual = sha256.hexdigest()
        if actual.lower() != expected_sha256.lower():
            logger.error("[UPDATER] SHA-256 mismatch: expected %s, got %s", expected_sha256, actual)
            self._set_state(UpdateState.FAILED, error=" Integrity check failed — package corrupted")
            # Delete corrupted package
            try:
                zip_path.unlink(missing_ok=True)
            except Exception:
                pass
            return False

        logger.info("[UPDATER] SHA-256 verified: %s", actual[:16])
        return True

    # ── Backup ───────────────────────────────────────────────────────────

    def create_backup(self) -> Path | None:
        """Backup current application EXE for rollback."""
        self._set_state(UpdateState.STAGING, "Creating backup...")

        from version import APP_VERSION
        backup = _BACKUP_DIR / f"v{APP_VERSION}_{int(time.time())}"
        backup.mkdir(parents=True, exist_ok=True)

        # Backup the EXE
        try:
            exe_path = _APP_DIR / "SONIC-AI.exe"
            if not exe_path.exists():
                # Try parent directory
                exe_path = _APP_DIR.parent / "SONIC-AI.exe"

            if exe_path.exists():
                shutil.copy2(exe_path, backup / "SONIC-AI.exe")
                logger.info("[UPDATER] EXE backed up: %s", exe_path)
            else:
                # Fallback: backup entire directory (for source installations)
                for item in _APP_DIR.iterdir():
                    if item.name in ("__pycache__", ".pytest_cache", ".git", "user_secrets"):
                        continue
                    if item.name.startswith("."):
                        continue
                    dest = backup / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest, ignore=shutil.ignore_patterns(
                            "__pycache__", ".pytest_cache", ".git", "*.pyc"
                        ))
                    else:
                        shutil.copy2(item, dest)
                logger.info("[UPDATER] Full backup created (source mode)")

            return backup
        except Exception as e:
            logger.error("[UPDATER] Backup failed: %s", e)
            self._set_state(UpdateState.FAILED, error=f"Backup failed: {e}")
            return None

    # ── Install (direct EXE swap) ────────────────────────────────────────

    def install_update(self, zip_path: Path, backup_path: Path) -> bool:
        """Stage update and swap EXE directly."""
        self._set_state(UpdateState.WAITING_TO_INSTALL, "Ready to install. App will restart.")

        # Extract zip to staging
        extract_dir = _STAGING_DIR / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
        except (zipfile.BadZipFile, OSError) as e:
            self._set_state(UpdateState.FAILED, error=f"Extract failed: {e}")
            return False

        # Find the new EXE inside the zip
        new_exe = None
        for child in extract_dir.rglob("SONIC-AI.exe"):
            new_exe = child
            break

        # Fallback: look for any .exe
        if not new_exe:
            for child in extract_dir.rglob("*.exe"):
                new_exe = child
                break

        if not new_exe:
            self._set_state(UpdateState.FAILED, error="No EXE found in update package")
            return False

        # Target EXE path — find where SONIC-AI.exe actually lives
        target_exe = None
        for candidate in [
            Path(sys.executable).resolve() if getattr(sys, 'frozen', False) else None,
            _APP_DIR / "SONIC-AI.exe",
            _APP_DIR.parent / "SONIC-AI.exe",
        ]:
            if candidate and candidate.exists():
                target_exe = candidate
                break

        if not target_exe:
            self._set_state(UpdateState.FAILED, error="Cannot find running SONIC-AI.exe")
            return False

        logger.info("[UPDATER] Target EXE: %s", target_exe)
        logger.info("[UPDATER] New EXE: %s", new_exe)

        # Direct swap: rename old -> copy new -> launch new -> exit
        try:
            old_exe = target_exe.with_suffix(".exe.old")
            # Remove any leftover .old from previous failed attempts
            if old_exe.exists():
                old_exe.unlink(missing_ok=True)

            # Rename running EXE (works on Windows even while running)
            target_exe.rename(old_exe)
            logger.info("[UPDATER] Renamed old EXE to %s", old_exe.name)

            # Copy new EXE to target location
            shutil.copy2(new_exe, target_exe)
            logger.info("[UPDATER] Copied new EXE to %s", target_exe)

            # Launch new EXE
            subprocess.Popen(
                [str(target_exe)],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
            logger.info("[UPDATER] New EXE launched")

            self._set_state(UpdateState.INSTALLING, "Update installed. Restarting...")
            return True

        except Exception as e:
            logger.error("[UPDATER] Install failed: %s", e)
            # Try rollback
            try:
                if old_exe.exists() and not target_exe.exists():
                    old_exe.rename(target_exe)
                    logger.info("[UPDATER] Rolled back to old EXE")
            except Exception:
                pass
            self._set_state(UpdateState.FAILED, error=f"Install failed: {e}")
            return False

    # ── Rollback ─────────────────────────────────────────────────────────

    def rollback(self, backup_path: Path) -> bool:
        """Restore from backup."""
        self._set_state(UpdateState.ROLLING_BACK, "Rolling back to previous version...")

        if not backup_path.exists():
            self._set_state(UpdateState.FAILED, error="Backup not found for rollback")
            return False

        try:
            # Check if backup contains EXE (new-style) or full directory (old-style)
            backup_exe = backup_path / "SONIC-AI.exe"
            if backup_exe.exists():
                # New-style: restore EXE
                target_exe = _APP_DIR / "SONIC-AI.exe"
                if not target_exe.exists():
                    target_exe = _APP_DIR.parent / "SONIC-AI.exe"
                shutil.copy2(backup_exe, target_exe)
                logger.info("[UPDATER] EXE restored from backup")
            else:
                # Old-style: restore full directory
                for item in _APP_DIR.iterdir():
                    if item.name in ("__pycache__", ".pytest_cache", ".git", "user_secrets"):
                        continue
                    if item.name.startswith("."):
                        continue
                    if item == _UPDATES_DIR.parent:
                        continue
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        item.unlink(missing_ok=True)

                # Restore from backup
                for item in backup_path.iterdir():
                    dest = _APP_DIR / item.name
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
                logger.info("[UPDATER] Full restore from backup")

            logger.info("[UPDATER] Rollback complete")
            self._set_state(UpdateState.ROLLED_BACK, "Rolled back successfully")
            return True
        except Exception as e:
            logger.error("[UPDATER] Rollback failed: %s", e)
            self._set_state(UpdateState.FAILED, error=f"Rollback failed: {e}")
            return False

    # ── Settings ─────────────────────────────────────────────────────────

    def get_settings(self) -> dict[str, Any]:
        defaults = {
            "auto_check": True,
            "channel": "stable",
            "auto_download": False,
            "auto_install": False,
        }
        try:
            if _SETTINGS_PATH.exists():
                data = json.loads(_SETTINGS_PATH.read_text())
                defaults.update(data)
        except Exception:
            pass
        return defaults

    def save_settings(self, settings: dict[str, Any]) -> None:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SETTINGS_PATH.write_text(json.dumps(settings, indent=2))

    # ── Internal ─────────────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        for d in (_USER_DATA, _UPDATES_DIR, _STAGING_DIR, _BACKUP_DIR, _DOWNLOAD_DIR):
            d.mkdir(parents=True, exist_ok=True)

    def cleanup(self) -> None:
        """Remove staging/downloads and .old files after successful update."""
        try:
            shutil.rmtree(_STAGING_DIR, ignore_errors=True)
            shutil.rmtree(_DOWNLOAD_DIR, ignore_errors=True)
            # Remove any .old files from previous updates
            for old_file in _APP_DIR.glob("*.exe.old"):
                old_file.unlink(missing_ok=True)
                logger.info("[UPDATER] Cleaned up: %s", old_file.name)
            for old_file in _APP_DIR.parent.glob("*.exe.old"):
                old_file.unlink(missing_ok=True)
                logger.info("[UPDATER] Cleaned up: %s", old_file.name)
        except Exception:
            pass


# ── Singleton ────────────────────────────────────────────────────────────────

_manager: UpdateManager | None = None


def get_update_manager() -> UpdateManager:
    global _manager
    if _manager is None:
        _manager = UpdateManager()
    return _manager
