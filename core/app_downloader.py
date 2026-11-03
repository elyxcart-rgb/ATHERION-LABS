"""SONIC AI — Smart App Downloader.

Downloads apps intelligently:
  1. Navigate to app's download page
  2. Smart-click real download button (skip ads, tracker buttons)
  3. Handle consent dialogs ("Accept cookies")
  4. Wait for the download to start
  5. Verify file in ~/Downloads
  6. Optionally launch installer

This is the high-level orchestrator that wraps SmartClicker + browser
automation. Uses Playwright (already installed) for navigation and
SmartClicker for the button detection (no Gemini API needed).

Public API:
    AppDownloader()
    .download(app_name, url=None) -> DownloadResult
    .get_stats()
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sonic.downloader")


@dataclass
class DownloadResult:
    app_name: str
    success: bool
    file_path: str = ""
    file_size_mb: float = 0.0
    duration_s: float = 0.0
    steps: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        if self.success:
            return f"Downloaded {self.app_name} → {self.file_path} ({self.file_size_mb:.1f}MB)"
        return f"Failed to download {self.app_name}: {self.error}"


class AppDownloader:
    """Smart app downloader with ad-skipping + consent handling."""

    # Common "sponsored"/"ad" indicators to skip when finding real download
    SPONSORED_INDICATORS = [
        "sponsored", "advertisement", "promoted", "ad ·",
        "your video will resume", "install now (recommended)",
    ]

    # Common consent dialog buttons
    CONSENT_BUTTONS = [
        "accept", "accept all", "i agree", "agree", "ok",
        "got it", "allow", "allow all", "i accept",
        "aceptar", "akzeptieren", "accepter", "同意",
    ]

    # Sites that have known direct-download patterns
    KNOWN_SITES = {
        "chrome":   "https://www.google.com/chrome/",
        "firefox":  "https://www.mozilla.org/en-US/firefox/new/",
        "vscode":   "https://code.visualstudio.com/Download",
        "notepad":  "https://notepad-plus-plus.org/downloads/",
        "vlc":      "https://www.videolan.org/vlc/",
        "7zip":     "https://www.7-zip.org/download.html",
        "obs":      "https://obsproject.com/download",
        "audacity": "https://www.audacityteam.org/download/",
        "discord":  "https://discord.com/download",
        "steam":    "https://store.steampowered.com/about/",
    }

    def __init__(self, downloads_dir: Optional[str] = None):
        self._downloads_dir = Path(downloads_dir) if downloads_dir else (
            Path.home() / "Downloads"
        )
        self._downloads_dir.mkdir(parents=True, exist_ok=True)

        from core.smart_clicker import SmartClicker
        self._clicker = SmartClicker()

        self._lock = threading.RLock()
        self._stats = {"downloads": 0, "successes": 0, "failures": 0}

    # ── Public ───────────────────────────────────────────────────────────────

    def download(self, app_name: str, url: Optional[str] = None,
                  timeout_s: float = 120.0) -> DownloadResult:
        """Download an app intelligently.

        Args:
            app_name: "chrome", "vscode", "firefox", etc.
            url:      Optional override URL (else use known site map).
            timeout_s: How long to wait for the download to start.
        """
        t0 = time.time()
        with self._lock:
            self._stats["downloads"] += 1

        result = DownloadResult(app_name=app_name, success=False)
        target_url = url or self.KNOWN_SITES.get(app_name.lower(), "")
        if not target_url:
            result.error = f"No URL known for {app_name}"
            result.duration_s = time.time() - t0
            self._record_failure()
            return result
        result.steps.append(f"Target URL: {target_url}")

        # Step 1: Open URL in browser (real action via Playwright)
        page = self._open_browser(target_url, result)
        if not page:
            result.duration_s = time.time() - t0
            self._record_failure()
            return result
        result.steps.append("Browser opened")

        # Step 2: Handle consent dialogs first
        self._handle_consent(page, result)

        # Step 3: Take screenshot, find the real download button
        #        (not sponsored/ads)
        screen = self._screenshot_page(page)
        if screen is None:
            result.error = "Could not capture screen"
            result.duration_s = time.time() - t0
            self._record_failure()
            return result

        target = self._find_real_download_button(screen, app_name, result)
        if not target:
            result.error = "Real download button not found"
            result.duration_s = time.time() - t0
            self._record_failure()
            return result

        result.steps.append(
            f"Real download button found at ({target.x},{target.y}) — "
            f"'{target.text}' confidence={target.confidence:.2f}"
        )

        # Step 4: Click the button
        ok = self._clicker.click("download", target.x, target.y)
        result.steps.append(f"Click executed: {ok}")
        if not ok:
            result.error = "Click failed"
            result.duration_s = time.time() - t0
            self._record_failure()
            return result

        # Step 5: Wait for the file to appear in Downloads
        file_path = self._wait_for_download(timeout_s - (time.time() - t0),
                                             app_name, result)
        if not file_path:
            result.error = "Download did not start or timeout"
            result.duration_s = time.time() - t0
            self._record_failure()
            return result

        result.file_path = str(file_path)
        result.file_size_mb = file_path.stat().st_size / (1024 * 1024)
        result.success = True
        result.duration_s = time.time() - t0
        result.steps.append(f"File saved: {file_path.name} ({result.file_size_mb:.1f}MB)")

        with self._lock:
            self._stats["successes"] += 1
        return result

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ────────────────────────────────────────────────────────────

    def _open_browser(self, url: str, result: DownloadResult):
        """Open URL in headless/visible browser, return page object."""
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=False)
            self._ctx = self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                accept_downloads=True,
            )
            self._page = self._ctx.new_page()
            self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
            return self._page
        except Exception as e:
            result.steps.append(f"Browser open failed: {e}")
            return None

    def _screenshot_page(self, page) -> Optional[bytes]:
        """Take a screenshot of the current page."""
        try:
            return page.screenshot(type="png")
        except Exception:
            return None

    def _handle_consent(self, page, result: DownloadResult):
        """Click consent / cookie banner if present."""
        try:
            for label in self.CONSENT_BUTTONS:
                target = self._clicker.find_button(label)
                if target and target.confidence > 0.5:
                    self._clicker.click(label, target.x, target.y)
                    result.steps.append(f"Consent handled: clicked '{label}'")
                    time.sleep(0.5)
                    return True
        except Exception:
            pass
        return False

    def _find_real_download_button(self, screen: bytes, app_name: str,
                                     result: DownloadResult):
        """Find the REAL download button, ignoring ads/sponsored."""
        candidates = []

        # Get all download-like buttons
        target = self._clicker.find_download_button(screen, app_name)
        if not target:
            return None

        # Filter out sponsored/ads
        text_low = target.text.lower()
        if any(sp in text_low for sp in self.SPONSORED_INDICATORS):
            # Try generic install intent
            target = self._clicker.find_button("install", screen)
        if not target:
            return None

        # Check context — the button should be near the app name
        # If app_name visible on screen and the download button is within
        # ~300px, it's likely the real button
        text_hits = self._clicker.find_text(app_name, screen_image=screen)
        if text_hits:
            for hit in text_hits:
                dist = abs(hit["x"] - target.x) + abs(hit["y"] - target.y)
                if dist < 400:
                    target.confidence = min(1.0, target.confidence + 0.15)
                    target.explanation += f" (near app name, dist={dist})"
                    break
        return target

    def _wait_for_download(self, timeout_s: float, app_name: str,
                            result: DownloadResult) -> Optional[Path]:
        """Wait for the download file to appear in ~/Downloads."""
        if timeout_s <= 0:
            timeout_s = 5.0

        deadline = time.time() + timeout_s
        before = set(p.name for p in self._downloads_dir.iterdir() if p.is_file())
        result.steps.append(f"Watching {self._downloads_dir} for new file")

        # Check every 500ms for a new file
        while time.time() < deadline:
            try:
                now = set(p.name for p in self._downloads_dir.iterdir() if p.is_file())
                new_files = now - before
                # Filter out .crdownload / .part (still in progress)
                for fn in new_files:
                    if fn.endswith(".crdownload") or fn.endswith(".part"):
                        continue
                    fp = self._downloads_dir / fn
                    # Sanity: looks like installer?
                    if self._looks_like_installer(fn, app_name):
                        return fp
                # Also check in-progress downloads (Chrome .crdownload)
                for fn in new_files:
                    if fn.endswith(".crdownload"):
                        # Wait a bit for it to complete
                        base_name = fn.replace(".crdownload", "")
                        if not (self._downloads_dir / base_name).exists():
                            time.sleep(1.0)
                            return self._downloads_dir / base_name
            except Exception as e:
                result.steps.append(f"Poll error: {e}")
            time.sleep(0.5)

        # One last check: maybe a download was already in progress before
        for p in self._downloads_dir.iterdir():
            if self._looks_like_installer(p.name, app_name):
                age_min = (time.time() - p.stat().st_mtime) / 60
                if age_min < 5:
                    return p
        return None

    @staticmethod
    def _looks_like_installer(filename: str, app_name: str) -> bool:
        """Heuristic: is this file likely the installer we want?"""
        fn_low = filename.lower()
        # Common installer extensions
        installer_exts = (".exe", ".msi", ".dmg", ".pkg", ".deb",
                           ".rpm", ".appimage", ".zip", ".tar.gz")
        if not fn_low.endswith(installer_exts):
            return False
        # Filename contains app name?
        if app_name.lower() in fn_low:
            return True
        # Generic installers (Setup, Installer)
        if any(kw in fn_low for kw in ("setup", "installer", "install")):
            return True
        return False

    def _record_failure(self):
        with self._lock:
            self._stats["failures"] += 1
