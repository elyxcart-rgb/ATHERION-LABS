"""SONIC AI — Permanent Update Infrastructure

GitHub Releases-based auto-update system.
Designed once, works across all future versions.

Architecture:
  GitHub API → discover release → download installer → SHA-256 verify
  → launch SONIC-Updater.exe → exit SONIC → helper installs → restart

Developer workflow:
  python release.py X.Y.Z → test → build → hash → GitHub Release → done
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable

logger = logging.getLogger("UPDATER")

# ── Paths ────────────────────────────────────────────────────────────────────
_APP_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "SONIC AI"
_UPDATER_DIR = _APP_DATA / "Updater"
_DOWNLOAD_DIR = _APP_DATA / "Updater" / "downloads"
_BACKUP_DIR = _APP_DATA / "Updater" / "backup"
_SETTINGS_PATH = _APP_DATA / "update_settings.json"
_LAST_CHECK_PATH = _APP_DATA / ".last_update_check"
_JOURNAL_DIR = _APP_DATA / "updates"
_JOURNAL_PATH = _JOURNAL_DIR / "update_journal.jsonl"

# ── Constants ────────────────────────────────────────────────────────────────
_CHECK_COOLDOWN_SECONDS = 6 * 60 * 60  # 6 hours
_DOWNLOAD_TIMEOUT = 300  # 5 minutes per chunk
_MAX_RETRIES = 3
_RETRY_DELAY = 2  # seconds, doubles each retry
_USER_AGENT = "SONIC-AI-Updater/1.0"


# ═════════════════════════════════════════════════════════════════════════════
# Data Models
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class UpdateManifest:
    """Release metadata from GitHub API."""
    version: str = ""
    channel: str = "stable"
    download_url: str = ""
    sha256: str = ""
    mandatory: bool = False
    release_notes: str = ""
    minimum_supported_version: str = "1.0.0"
    published_at: str = ""
    asset_name: str = ""
    asset_size: int = 0
    release_id: str = ""
    release_page_url: str = ""

    @classmethod
    def from_github_release(cls, release_data: dict, channel: str = "stable") -> UpdateManifest | None:
        """Parse GitHub API release response. Returns None if invalid."""
        try:
            # Skip drafts and prereleases
            if release_data.get("draft", False):
                return None
            if release_data.get("prerelease", False):
                return None

            tag = release_data.get("tag_name", "")
            if not tag:
                return None

            # Extract version from tag (v1.1.0 → 1.1.0)
            version = tag.lstrip("v").strip()
            if not version:
                return None

            # Find installer asset (SONIC-AI-Setup-*.exe)
            assets = release_data.get("assets", [])
            installer_asset = None
            for asset in assets:
                name = asset.get("name", "")
                if name.startswith("SONIC-AI-Setup") and name.endswith(".exe"):
                    installer_asset = asset
                    break

            if not installer_asset:
                logger.warning("[UPDATER] No installer asset found in release %s", tag)
                return None

            download_url = installer_asset.get("browser_download_url", "")
            if not download_url:
                return None

            body = release_data.get("body", "")
            published = release_data.get("published_at", "")
            release_id = str(release_data.get("id", ""))

            return cls(
                version=version,
                channel=channel,
                download_url=download_url,
                sha256="",  # Will be verified after download if manifest provides it
                mandatory=False,
                release_notes=body,
                minimum_supported_version="1.0.0",
                published_at=published,
                asset_name=installer_asset.get("name", ""),
                asset_size=installer_asset.get("size", 0),
                release_id=release_id,
                release_page_url=release_data.get("html_url", ""),
            )
        except Exception as e:
            logger.warning("[UPDATER] Failed to parse release: %s", e)
            return None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> UpdateManifest:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ═════════════════════════════════════════════════════════════════════════════
# Update Manager
# ═════════════════════════════════════════════════════════════════════════════

class UpdateManager:
    """Singleton update manager — GitHub Releases based."""

    GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"

    def __init__(self) -> None:
        self._callbacks: list[Callable] = []
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in (_UPDATER_DIR, _DOWNLOAD_DIR, _BACKUP_DIR, _JOURNAL_DIR):
            d.mkdir(parents=True, exist_ok=True)

    # ── Callbacks ────────────────────────────────────────────────────────

    def register_callback(self, cb: Callable) -> None:
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable) -> None:
        self._callbacks = [c for c in self._callbacks if c is not cb]

    def _emit(self, event: str, data: dict | None = None) -> None:
        for cb in self._callbacks:
            try:
                cb(event, data or {})
            except Exception:
                pass

    # ── Settings ─────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        defaults = {"auto_check": True, "channel": "stable", "auto_download": False}
        try:
            if _SETTINGS_PATH.exists():
                return {**defaults, **json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))}
        except Exception:
            pass
        return defaults

    def save_settings(self, updates: dict) -> None:
        settings = self.get_settings()
        settings.update(updates)
        _SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    # ── Rate Limiting ────────────────────────────────────────────────────

    def should_check(self) -> bool:
        """Return True if enough time has passed since last check."""
        try:
            if _LAST_CHECK_PATH.exists():
                last = float(_LAST_CHECK_PATH.read_text(encoding="utf-8").strip())
                if time.time() - last < _CHECK_COOLDOWN_SECONDS:
                    return False
        except Exception:
            pass
        return True

    def mark_checked(self) -> None:
        _LAST_CHECK_PATH.write_text(str(time.time()), encoding="utf-8")

    # ── Journal ──────────────────────────────────────────────────────────

    def _journal(self, stage: str, **kw) -> None:
        entry = {"ts": time.time(), "stage": stage, **kw}
        try:
            with open(_JOURNAL_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    # ── GitHub API Discovery ─────────────────────────────────────────────

    def _fetch_github_latest(self) -> dict | None:
        """Fetch latest release from GitHub API."""
        from version import GITHUB_REPO
        url = self.GITHUB_API_URL.format(repo=GITHUB_REPO)

        req = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": _USER_AGENT,
        })

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.info("[UPDATER] No releases found")
            else:
                logger.warning("[UPDATER] GitHub API error %d", e.code)
            return None
        except Exception as e:
            logger.warning("[UPDATER] GitHub API request failed: %s", e)
            return None

    def check_for_update(self, force: bool = False) -> UpdateManifest | None:
        """Check GitHub for latest stable release. Returns manifest or None."""
        from version import APP_VERSION, is_newer, APP_CHANNEL

        if not force and not self.should_check():
            return None

        self.mark_checked()
        self._journal("checking")

        release_data = self._fetch_github_latest()
        if release_data is None:
            self._journal("check_failed", reason="github_unavailable")
            return None

        manifest = UpdateManifest.from_github_release(release_data, channel=APP_CHANNEL)
        if manifest is None:
            self._journal("check_failed", reason="invalid_release")
            return None

        # Downgrade protection
        if not is_newer(manifest.version, APP_VERSION):
            self._journal("no_update", remote=manifest.version, local=APP_VERSION)
            return None

        # Minimum supported version check
        from version import is_compatible
        if not is_compatible(manifest.minimum_supported_version):
            self._journal("incompatible", remote=manifest.version)
            return None

        self._journal("update_available", remote=manifest.version)
        self._emit("update_available", manifest.to_dict())
        return manifest

    # ── Download ─────────────────────────────────────────────────────────

    def calculate_sha256(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha256.update(chunk)
        return sha256.hexdigest()

    def download_update(
        self,
        manifest: UpdateManifest,
        progress_cb: Callable[[float, str], None] | None = None,
    ) -> Path | None:
        """Download installer to staging dir. Returns path or None."""
        dest = _DOWNLOAD_DIR / manifest.asset_name

        self._journal("download_started", url=manifest.download_url, dest=str(dest))
        self._emit("download_started", {"url": manifest.download_url})

        for attempt in range(_MAX_RETRIES):
            try:
                if progress_cb:
                    progress_cb(0, f"Downloading... (attempt {attempt + 1}/{_MAX_RETRIES})")

                req = urllib.request.Request(manifest.download_url, headers={
                    "User-Agent": _USER_AGENT,
                })

                with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0
                    sha256 = hashlib.sha256()

                    with open(dest, "wb") as f:
                        while True:
                            chunk = resp.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                            sha256.update(chunk)
                            downloaded += len(chunk)

                            if total > 0 and progress_cb:
                                pct = (downloaded / total) * 100
                                mb_done = downloaded / (1024 * 1024)
                                mb_total = total / (1024 * 1024)
                                progress_cb(pct, f"{mb_done:.1f}/{mb_total:.1f} MB")

                # Verify hash if manifest provides one
                actual_hash = sha256.hexdigest()
                if manifest.sha256 and manifest.sha256 != actual_hash:
                    self._journal("hash_mismatch", expected=manifest.sha256, actual=actual_hash)
                    dest.unlink(missing_ok=True)
                    if progress_cb:
                        progress_cb(0, "Hash mismatch — retrying...")
                    time.sleep(_RETRY_DELAY * (attempt + 1))
                    continue

                self._journal("download_completed", path=str(dest), size=dest.stat().st_size)
                self._emit("download_completed", {"path": str(dest)})
                if progress_cb:
                    progress_cb(100, "Download complete")
                return dest

            except Exception as e:
                logger.warning("[UPDATER] Download attempt %d failed: %s", attempt + 1, e)
                self._journal("download_error", attempt=attempt + 1, error=str(e))
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY * (attempt + 1))

        self._journal("download_failed", reason="all_retries_exhausted")
        dest.unlink(missing_ok=True)
        return None

    # ── Verify ───────────────────────────────────────────────────────────

    def verify_artifact(self, path: Path, expected_sha256: str) -> bool:
        """Verify SHA-256 hash of downloaded artifact."""
        if not path.exists():
            return False
        if not expected_sha256:
            return True  # No hash to verify against
        actual = self.calculate_sha256(path)
        return actual == expected_sha256

    # ── Install ──────────────────────────────────────────────────────────

    def find_updater_helper(self) -> Path | None:
        """Find SONIC-Updater.exe."""
        # Check alongside current EXE
        import sys
        if getattr(sys, "frozen", False):
            app_dir = Path(sys.executable).parent
            helper = app_dir / "SONIC-Updater.exe"
            if helper.exists():
                return helper

        # Check in project root (development)
        project_dir = Path(__file__).resolve().parent.parent
        for candidate in [
            project_dir / "dist" / "SONIC-Updater.exe",
            project_dir / "SONIC-Updater.exe",
        ]:
            if candidate.exists():
                return candidate

        return None

    def install_update(self, artifact_path: Path, manifest: UpdateManifest) -> bool:
        """Launch updater helper and exit SONIC. Returns True if helper launched."""
        import subprocess
        import sys

        helper = self.find_updater_helper()
        if not helper:
            self._journal("install_failed", reason="updater_helper_not_found")
            logger.error("[UPDATER] SONIC-Updater.exe not found")
            return False

        if getattr(sys, "frozen", False):
            target_exe = Path(sys.executable)
        else:
            target_exe = Path(__file__).resolve().parent.parent / "dist" / "SONIC-AI.exe"

        backup_dir = _BACKUP_DIR / f"v{manifest.version}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        self._journal("install_started", helper=str(helper), target=str(target_exe))
        self._emit("install_started", {})

        try:
            subprocess.Popen(
                [str(helper), str(artifact_path), str(target_exe), str(backup_dir)],
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                close_fds=True,
            )
            # Give helper a moment to start, then exit SONIC
            time.sleep(1)
            self._journal("sonic_exiting")
            os._exit(0)
        except Exception as e:
            self._journal("install_failed", reason=str(e))
            logger.error("[UPDATER] Failed to launch helper: %s", e)
            return False

    # ── Rollback ─────────────────────────────────────────────────────────

    def find_backup(self) -> Path | None:
        """Find most recent backup."""
        if not _BACKUP_DIR.exists():
            return None
        backups = sorted(_BACKUP_DIR.iterdir(), reverse=True)
        for b in backups:
            exe = b / "SONIC-AI.exe"
            if exe.exists():
                return b
        return None

    def rollback(self) -> bool:
        """Restore from most recent backup."""
        backup = self.find_backup()
        if not backup:
            self._journal("rollback_failed", reason="no_backup")
            return False

        import sys
        if getattr(sys, "frozen", False):
            target = Path(sys.executable)
        else:
            return False

        backup_exe = backup / "SONIC-AI.exe"
        try:
            target.unlink(missing_ok=True)
            import shutil
            shutil.copy2(backup_exe, target)
            self._journal("rollback_completed", backup=str(backup))
            return True
        except Exception as e:
            self._journal("rollback_failed", reason=str(e))
            return False

    # ── Diagnostics ──────────────────────────────────────────────────────

    def get_diagnostics(self) -> dict:
        """Return diagnostic info for settings panel."""
        from version import APP_VERSION, APP_CHANNEL
        settings = self.get_settings()
        last_check = "never"
        try:
            if _LAST_CHECK_PATH.exists():
                ts = float(_LAST_CHECK_PATH.read_text(encoding="utf-8").strip())
                last_check = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        except Exception:
            pass

        return {
            "current_version": APP_VERSION,
            "channel": APP_CHANNEL,
            "auto_check": settings.get("auto_check", True),
            "last_check": last_check,
            "updater_dir": str(_UPDATER_DIR),
            "journal": str(_JOURNAL_PATH),
        }


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_manager: UpdateManager | None = None


def get_update_manager() -> UpdateManager:
    global _manager
    if _manager is None:
        _manager = UpdateManager()
    return _manager
