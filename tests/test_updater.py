"""Tests for SONIC AI Update System — Permanent Infrastructure."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from version import (
    APP_VERSION, APP_NAME, APP_CHANNEL,
    _parse_semver, version_tuple, is_newer, is_compatible, format_version,
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
    """Test manifest parsing from GitHub API response."""

    def _make_release(self, **overrides):
        """Create a mock GitHub API release response."""
        data = {
            "tag_name": "v1.1.0",
            "draft": False,
            "prerelease": False,
            "body": "Bug fixes and improvements",
            "published_at": "2026-09-09T12:00:00Z",
            "id": 123456,
            "html_url": "https://github.com/test/repo/releases/tag/v1.1.0",
            "assets": [
                {
                    "name": "SONIC-AI-Setup-1.1.0.exe",
                    "browser_download_url": "https://github.com/test/repo/releases/download/v1.1.0/SONIC-AI-Setup-1.1.0.exe",
                    "size": 270000000,
                }
            ],
        }
        data.update(overrides)
        return data

    def test_from_github_release_valid(self):
        from updater import UpdateManifest
        m = UpdateManifest.from_github_release(self._make_release())
        self.assertIsNotNone(m)
        self.assertEqual(m.version, "1.1.0")
        self.assertEqual(m.channel, "stable")
        self.assertIn("SONIC-AI-Setup", m.asset_name)
        self.assertEqual(m.asset_size, 270000000)

    def test_from_github_release_draft(self):
        from updater import UpdateManifest
        m = UpdateManifest.from_github_release(self._make_release(draft=True))
        self.assertIsNone(m)

    def test_from_github_release_prerelease(self):
        from updater import UpdateManifest
        m = UpdateManifest.from_github_release(self._make_release(prerelease=True))
        self.assertIsNone(m)

    def test_from_github_release_no_assets(self):
        from updater import UpdateManifest
        m = UpdateManifest.from_github_release(self._make_release(assets=[]))
        self.assertIsNone(m)

    def test_from_github_release_wrong_asset(self):
        from updater import UpdateManifest
        m = UpdateManifest.from_github_release(self._make_release(assets=[
            {"name": "some-other-file.zip", "browser_download_url": "https://x.com/a.zip", "size": 100}
        ]))
        self.assertIsNone(m)

    def test_from_github_release_empty_tag(self):
        from updater import UpdateManifest
        m = UpdateManifest.from_github_release(self._make_release(tag_name=""))
        self.assertIsNone(m)

    def test_to_dict(self):
        from updater import UpdateManifest
        m = UpdateManifest(version="1.0.0", download_url="https://x.com/a.exe")
        d = m.to_dict()
        self.assertEqual(d["version"], "1.0.0")
        self.assertIn("download_url", d)

    def test_from_dict(self):
        from updater import UpdateManifest
        data = {"version": "2.0.0", "channel": "beta", "download_url": "https://x.com/a.exe"}
        m = UpdateManifest.from_dict(data)
        self.assertEqual(m.version, "2.0.0")
        self.assertEqual(m.channel, "beta")


class TestUpdateManager(unittest.TestCase):
    """Test UpdateManager core logic."""

    def setUp(self):
        from updater import UpdateManager, _UPDATER_DIR, _DOWNLOAD_DIR, _BACKUP_DIR
        self._orig_dirs = (_UPDATER_DIR, _DOWNLOAD_DIR, _BACKUP_DIR)
        self._tmp = tempfile.mkdtemp()

        import updater
        updater._UPDATER_DIR = Path(self._tmp)
        updater._DOWNLOAD_DIR = Path(self._tmp) / "downloads"
        updater._BACKUP_DIR = Path(self._tmp) / "backup"
        updater._SETTINGS_PATH = Path(self._tmp) / "settings.json"
        updater._LAST_CHECK_PATH = Path(self._tmp) / ".last_check"
        updater._JOURNAL_DIR = Path(self._tmp) / "updates"
        updater._JOURNAL_PATH = Path(self._tmp) / "updates" / "journal.jsonl"

        self.manager = UpdateManager()

    def tearDown(self):
        import updater
        updater._UPDATER_DIR = self._orig_dirs[0]
        updater._DOWNLOAD_DIR = self._orig_dirs[1]
        updater._BACKUP_DIR = self._orig_dirs[2]
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_initial_state(self):
        self.assertIsNotNone(self.manager)

    def test_callback_registration(self):
        cb = MagicMock()
        self.manager.register_callback(cb)
        self.manager._emit("test", {"key": "value"})
        cb.assert_called_once_with("test", {"key": "value"})

    def test_callback_unregister(self):
        cb = MagicMock()
        self.manager.register_callback(cb)
        self.manager.unregister_callback(cb)
        self.manager._emit("test", {})
        cb.assert_not_called()

    def test_should_check_first_time(self):
        self.assertTrue(self.manager.should_check())

    def test_should_check_rate_limit(self):
        self.manager.mark_checked()
        self.assertFalse(self.manager.should_check())

    def test_get_settings_defaults(self):
        settings = self.manager.get_settings()
        self.assertTrue(settings["auto_check"])
        self.assertEqual(settings["channel"], "stable")

    def test_save_settings(self):
        self.manager.save_settings({"auto_check": False})
        settings = self.manager.get_settings()
        self.assertFalse(settings["auto_check"])

    def test_calculate_sha256(self):
        tmp = Path(self._tmp) / "test_file.bin"
        tmp.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        self.assertEqual(self.manager.calculate_sha256(tmp), expected)

    def test_verify_artifact_pass(self):
        tmp = Path(self._tmp) / "test.bin"
        tmp.write_bytes(b"test data")
        sha = hashlib.sha256(b"test data").hexdigest()
        self.assertTrue(self.manager.verify_artifact(tmp, sha))

    def test_verify_artifact_fail(self):
        tmp = Path(self._tmp) / "test.bin"
        tmp.write_bytes(b"test data")
        self.assertFalse(self.manager.verify_artifact(tmp, "wrong_hash"))

    def test_verify_artifact_no_hash(self):
        tmp = Path(self._tmp) / "test.bin"
        tmp.write_bytes(b"test data")
        self.assertTrue(self.manager.verify_artifact(tmp, ""))

    def test_verify_artifact_missing_file(self):
        fake = Path(self._tmp) / "nonexistent.bin"
        self.assertFalse(self.manager.verify_artifact(fake, "abc"))

    def test_journal(self):
        self.manager._journal("test_stage", key="value")
        # Journal file should exist
        from updater import _JOURNAL_PATH
        self.assertTrue(_JOURNAL_PATH.exists())
        lines = _JOURNAL_PATH.read_text().strip().split("\n")
        self.assertTrue(len(lines) >= 1)
        entry = json.loads(lines[-1])
        self.assertEqual(entry["stage"], "test_stage")
        self.assertEqual(entry["key"], "value")

    def test_diagnostics(self):
        diag = self.manager.get_diagnostics()
        self.assertIn("current_version", diag)
        self.assertIn("channel", diag)
        self.assertIn("last_check", diag)

    def test_find_backup_empty(self):
        self.assertIsNone(self.manager.find_backup())

    def test_find_backup_with_data(self):
        backup_dir = Path(self._tmp) / "backup" / "v1.0.0"
        backup_dir.mkdir(parents=True)
        (backup_dir / "SONIC-AI.exe").write_bytes(b"fake exe")
        result = self.manager.find_backup()
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
