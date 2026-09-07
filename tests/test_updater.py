"""Tests for SONIC AI Update System."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is importable
import sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from version import (
    APP_VERSION, APP_NAME, APP_CHANNEL,
    _parse_semver, version_tuple, is_newer, is_compatible, format_version,
)
from updater import (
    UpdateState, UpdateManifest, UpdateProgress,
    UpdateManager, _STAGING_DIR, _BACKUP_DIR, _USER_DATA,
)


class TestVersionModule(unittest.TestCase):
    """Test semantic version comparison."""

    def test_parse_semver_basic(self):
        self.assertEqual(_parse_semver("1.0.0"), (1, 0, 0))
        self.assertEqual(_parse_semver("2.3.4"), (2, 3, 4))
        self.assertEqual(_parse_semver("0.0.1"), (0, 0, 1))

    def test_parse_semver_strips_metadata(self):
        self.assertEqual(_parse_semver("1.2.3+build.45"), (1, 2, 3))
        self.assertEqual(_parse_semver("1.0.0-beta.1"), (1, 0, 0))

    def test_parse_semver_defaults(self):
        self.assertEqual(_parse_semver("1"), (1, 0, 0))
        self.assertEqual(_parse_semver("1.2"), (1, 2, 0))

    def test_version_tuple(self):
        self.assertEqual(version_tuple("1.2.3"), (1, 2, 3))
        # Default uses APP_VERSION
        self.assertEqual(version_tuple(), _parse_semver(APP_VERSION))

    def test_is_newer(self):
        self.assertTrue(is_newer("1.0.1", "1.0.0"))
        self.assertTrue(is_newer("1.1.0", "1.0.9"))
        self.assertTrue(is_newer("2.0.0", "1.9.9"))
        self.assertFalse(is_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_newer("1.0.0", "1.0.1"))
        self.assertFalse(is_newer("1.0.9", "1.0.10"))  # numeric, not string

    def test_is_compatible(self):
        self.assertTrue(is_compatible("0.0.1"))
        self.assertTrue(is_compatible("1.0.0"))
        self.assertTrue(is_compatible(APP_VERSION))
        # Can't test future version without mocking APP_VERSION

    def test_format_version(self):
        self.assertIn(APP_NAME, format_version())
        self.assertIn(APP_VERSION, format_version())
        self.assertIn("1.2.3", format_version("1.2.3"))

    def test_app_version_is_string(self):
        self.assertIsInstance(APP_VERSION, str)
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")

    def test_app_channel_is_valid(self):
        self.assertIn(APP_CHANNEL, ("stable", "beta", "dev"))


class TestUpdateManifest(unittest.TestCase):
    """Test manifest dataclass."""

    def test_from_dict(self):
        data = {
            "version": "2.0.0",
            "channel": "stable",
            "download_url": "https://example.com/sonic.zip",
            "sha256": "abc123",
            "mandatory": True,
            "summary": "Bug fixes",
        }
        m = UpdateManifest.from_dict(data)
        self.assertEqual(m.version, "2.0.0")
        self.assertEqual(m.channel, "stable")
        self.assertTrue(m.mandatory)
        self.assertEqual(m.sha256, "abc123")

    def test_to_dict(self):
        m = UpdateManifest(version="1.0.0", download_url="https://x.com/a.zip")
        d = m.to_dict()
        self.assertEqual(d["version"], "1.0.0")
        self.assertIn("download_url", d)

    def test_defaults(self):
        m = UpdateManifest()
        self.assertEqual(m.channel, "stable")
        self.assertFalse(m.mandatory)
        self.assertEqual(m.minimum_supported_version, "0.0.0")


class TestUpdateState(unittest.TestCase):
    """Test state machine has all required states."""

    REQUIRED_STATES = [
        "idle", "checking", "available", "downloading", "verifying",
        "staging", "waiting_to_install", "installing", "verifying_install",
        "completed", "failed", "rolling_back", "rolled_back", "cancelled",
    ]

    def test_all_states_exist(self):
        actual = {s.value for s in UpdateState}
        for state in self.REQUIRED_STATES:
            self.assertIn(state, actual, f"Missing state: {state}")


class TestUpdateManager(unittest.TestCase):
    """Test UpdateManager core logic."""

    def setUp(self):
        self.manager = UpdateManager()
        # Use temp dirs to avoid touching real user data
        self._orig_staging = _STAGING_DIR
        self._orig_backup = _BACKUP_DIR
        self._tmp = tempfile.mkdtemp()
        # Patch paths
        import updater
        updater._STAGING_DIR = Path(self._tmp) / "staging"
        updater._BACKUP_DIR = Path(self._tmp) / "backup"
        updater._DOWNLOAD_DIR = Path(self._tmp) / "downloads"
        updater._MANIFEST_CACHE = Path(self._tmp) / ".cache.json"
        updater._LAST_CHECK_PATH = Path(self._tmp) / ".last_check"
        updater._USER_DATA = Path(self._tmp)
        updater._SETTINGS_PATH = Path(self._tmp) / "update_settings.json"
        self.manager._ensure_dirs()

    def tearDown(self):
        import updater
        updater._STAGING_DIR = self._orig_staging
        updater._BACKUP_DIR = self._orig_backup
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_initial_state(self):
        self.assertEqual(self.manager.state, UpdateState.IDLE)

    def test_callback_registration(self):
        cb = MagicMock()
        self.manager.register_callback(cb)
        self.manager._emit()
        cb.assert_called_once()

    def test_callback_unregister(self):
        cb = MagicMock()
        self.manager.register_callback(cb)
        self.manager.unregister_callback(cb)
        self.manager._emit()
        cb.assert_not_called()

    def test_should_check_first_time(self):
        self.assertTrue(self.manager.should_check())

    def test_should_check_rate_limit(self):
        self.manager.mark_checked()
        self.assertFalse(self.manager.should_check())

    def test_should_check_force(self):
        # Force bypasses rate limit (handled by caller)
        self.manager.mark_checked()
        # should_check still returns False, but check_for_update(force=True) bypasses it
        self.assertFalse(self.manager.should_check())

    def test_get_settings_defaults(self):
        settings = self.manager.get_settings()
        self.assertTrue(settings["auto_check"])
        self.assertEqual(settings["channel"], "stable")
        self.assertFalse(settings["auto_download"])

    def test_save_settings(self):
        self.manager.save_settings({"auto_check": False})
        settings = self.manager.get_settings()
        self.assertFalse(settings["auto_check"])

    def test_verify_integrity_pass(self):
        # Create a test zip
        staging = Path(self._tmp) / "staging"
        staging.mkdir(exist_ok=True)
        zip_path = staging / "test.zip"
        zip_path.write_bytes(b"test content")

        expected = hashlib.sha256(b"test content").hexdigest()
        self.assertTrue(self.manager.verify_integrity(zip_path, expected))

    def test_verify_integrity_fail(self):
        staging = Path(self._tmp) / "staging"
        staging.mkdir(exist_ok=True)
        zip_path = staging / "test.zip"
        zip_path.write_bytes(b"test content")

        self.assertFalse(self.manager.verify_integrity(zip_path, "wrong_hash"))

    def test_verify_integrity_no_hash(self):
        staging = Path(self._tmp) / "staging"
        staging.mkdir(exist_ok=True)
        zip_path = staging / "test.zip"
        zip_path.write_bytes(b"test")

        # No hash provided — should pass
        self.assertTrue(self.manager.verify_integrity(zip_path, ""))

    def test_create_backup(self):
        # Create a fake app dir with main.py
        import updater
        orig_app = updater._APP_DIR
        updater._APP_DIR = Path(self._tmp) / "app"
        updater._APP_DIR.mkdir(exist_ok=True)
        (updater._APP_DIR / "main.py").write_text("print('hello')")
        (updater._APP_DIR / "__pycache__").mkdir(exist_ok=True)

        try:
            backup = self.manager.create_backup()
            self.assertIsNotNone(backup)
            self.assertTrue(backup.exists())
            self.assertTrue((backup / "main.py").exists())
            # __pycache__ should not be backed up
            self.assertFalse((backup / "__pycache__").exists())
        finally:
            updater._APP_DIR = orig_app

    def test_cleanup(self):
        staging = Path(self._tmp) / "staging"
        staging.mkdir(exist_ok=True)
        (staging / "file.txt").write_text("x")
        self.manager.cleanup()
        self.assertFalse(staging.exists())


class TestUpdateProgress(unittest.TestCase):
    """Test progress data class."""

    def test_defaults(self):
        p = UpdateProgress()
        self.assertEqual(p.state, UpdateState.IDLE)
        self.assertEqual(p.percent, 0.0)

    def test_with_values(self):
        p = UpdateProgress(state=UpdateState.DOWNLOADING, percent=75.0, message="Downloading...")
        self.assertEqual(p.state, UpdateState.DOWNLOADING)
        self.assertEqual(p.percent, 75.0)


if __name__ == "__main__":
    unittest.main()
