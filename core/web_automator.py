"""SONIC AI — Web Automator.

Browser-driven automation using Playwright. Lets SONIC actually **open**
a real browser, navigate to any URL, interact with the page (click,
type, fill forms, scroll), download files via the browser's own
download manager, scrape content, take screenshots, and run JavaScript.

Why this is the missing piece:
    - The previous ``core.navigator.open_url`` only calls
      ``webbrowser.open`` — that hands the URL to the OS and SONIC loses
      all control.
    - WebAutomator keeps the browser under SONIC's control so it can
      wait for elements, click buttons, fill forms, and capture the
      results.

Public surface (stable, opt-in):
    - ``WebAutomator()``                 — manager (owns the browser)
    - ``with web.open_page(url) as page`` — context-managed page session
    - ``web.click(page, selector)``
    - ``web.type_text(page, selector, text)``
    - ``web.fill_form(page, fields)``
    - ``web.download_url(page, url, dest)``
    - ``web.scrape(page, selector)``
    - ``web.screenshot(page, path)``
    - ``web.run_script(page, script)``
    - ``web.youtube_search(query, max_videos)``      — convenience
    - ``web.github_latest_release(user, repo)``     — convenience

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("WEB_AUTOMATOR")


# ═════════════════════════════════════════════════════════════════════════════
# Async helpers — Playwright is async-native
# ═════════════════════════════════════════════════════════════════════════════

def _run_async(coro):
    """Run an async coroutine from sync code.

    Uses a fresh event loop per call so this module is safe to use from
    threads and from inside other event loops.
    """
    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except RuntimeError as e:
        logger.warning(f"async run failed: {e}")
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DownloadResult:
    url: str
    path: str = ""
    ok: bool = False
    bytes_downloaded: int = 0
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScrapeResult:
    url: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    links: list = field(default_factory=list)
    images: list = field(default_factory=list)
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Manager
# ═════════════════════════════════════════════════════════════════════════════

class WebAutomator:
    """Real browser automation via Playwright.

    Lazily launches Chromium on first use; reuses it across calls.
    """

    def __init__(self, *, headless: bool = True,
                 browser: str = "chromium",
                 download_dir: Optional[Path] = None):
        self.headless = headless
        self.browser_name = browser
        self.download_dir = Path(download_dir) if download_dir else (
            Path.home() / "Downloads" / "SONIC"
        )
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._pw = None
        self._browser = None
        self._playwright = None

    def _ensure_browser(self):
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && "
                "playwright install chromium"
            ) from e
        self._pw = sync_playwright().start()
        launcher = getattr(self._pw, self.browser_name, None)
        if launcher is None:
            raise RuntimeError(f"Unknown browser: {self.browser_name}")
        self._browser = launcher.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

    def close(self):
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._browser = None
        self._pw = None

    # ── Page context manager ─────────────────────────────────────────────
    @contextmanager
    def open_page(self, url: str, *, wait_for: Optional[str] = None,
                 timeout_ms: int = 30_000):
        """Open a URL in a new page, return the page, clean up after."""
        self._ensure_browser()
        context = self._browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()
        try:
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_for:
                page.wait_for_selector(wait_for, timeout=timeout_ms)
            yield page
        finally:
            try:
                context.close()
            except Exception:
                pass

    # ── Interactions ─────────────────────────────────────────────────────
    @staticmethod
    def click(page, selector: str, *, timeout_ms: int = 10_000):
        page.click(selector, timeout=timeout_ms)

    @staticmethod
    def type_text(page, selector: str, text: str, *, delay_ms: int = 20):
        page.fill(selector, text)  # fill clears first
        # Add a tiny per-char delay for human-like behaviour if desired
        # (omitted in fill; call type() if you need character-by-character)

    @staticmethod
    def fill_form(page, fields: dict, *, submit_selector: Optional[str] = None):
        """Fill a form from ``{selector: value}`` and optionally submit.

        Args:
            page:           Playwright page.
            fields:         ``{selector: value}`` pairs.
            submit_selector: If provided, click this after filling.
        """
        for sel, val in fields.items():
            page.fill(sel, str(val))
        if submit_selector:
            page.click(submit_selector)

    @staticmethod
    def wait_for(page, selector: str, *, timeout_ms: int = 15_000,
                 state: str = "visible"):
        page.wait_for_selector(selector, state=state, timeout=timeout_ms)

    @staticmethod
    def scroll(page, *, to_bottom: bool = False, pixels: int = 0):
        if to_bottom:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif pixels:
            page.evaluate(f"window.scrollBy(0, {pixels})")

    # ── Downloads ────────────────────────────────────────────────────────
    def download_url(self, page, url: str, *, dest: Optional[Path] = None,
                    wait_ms: int = 5_000) -> DownloadResult:
        """Navigate to ``url`` and capture the browser's download.

        Works for: direct file links, attachments, ``Content-Disposition``,
        and download buttons that trigger a download dialog.
        """
        if dest is None:
            dest = self.download_dir / Path(url.split("?")[0]).name
        dest = Path(dest)
        try:
            with page.expect_download(timeout=wait_ms) as info:
                # Trigger the download via direct navigation
                page.goto(url)
            dl = info.value
            dl.save_as(str(dest))
            return DownloadResult(url=url, path=str(dest), ok=True,
                                 bytes_downloaded=dest.stat().st_size)
        except Exception as e:
            return DownloadResult(url=url, ok=False, error=str(e))

    def download_via_click(self, page, selector: str, *,
                            dest: Optional[Path] = None,
                            wait_ms: int = 10_000) -> DownloadResult:
        """Click ``selector`` and capture the resulting download."""
        if dest is None:
            dest = self.download_dir / "download.bin"
        dest = Path(dest)
        try:
            with page.expect_download(timeout=wait_ms) as info:
                page.click(selector)
            dl = info.value
            suggested = dl.suggested_filename
            final = dest if dest.name != "download.bin" else (dest.parent / suggested)
            dl.save_as(str(final))
            return DownloadResult(url=selector, path=str(final), ok=True,
                                 bytes_downloaded=final.stat().st_size,
                                 metadata={"suggested_filename": suggested})
        except Exception as e:
            return DownloadResult(url=selector, ok=False, error=str(e))

    # ── Scraping ─────────────────────────────────────────────────────────
    def scrape(self, page, *, selector: Optional[str] = None,
              include_html: bool = False,
              include_links: bool = True,
              include_images: bool = True) -> ScrapeResult:
        """Extract text + metadata from the current page."""
        result = ScrapeResult(url=page.url)
        try:
            result.title = page.title()
            if selector:
                result.text = page.locator(selector).inner_text()
            else:
                result.text = page.inner_text("body")
            if include_html:
                result.html = page.content()
            if include_links:
                result.links = page.evaluate(
                    "() => Array.from(document.querySelectorAll('a[href]'))"
                    ".map(a => ({text: a.innerText, href: a.href}))"
                    ".filter(a => a.href)"
                )
            if include_images:
                result.images = page.evaluate(
                    "() => Array.from(document.querySelectorAll('img[src]'))"
                    ".map(i => ({alt: i.alt, src: i.src}))"
                )
        except Exception as e:
            result.error = str(e)
        return result

    # ── Screenshot ──────────────────────────────────────────────────────
    @staticmethod
    def screenshot(page, path: str, *, full_page: bool = False) -> str:
        page.screenshot(path=path, full_page=full_page)
        return path

    # ── Run JavaScript ──────────────────────────────────────────────────
    @staticmethod
    def run_script(page, script: str) -> Any:
        return page.evaluate(script)

    # ── Convenience helpers ─────────────────────────────────────────────
    def youtube_search(self, query: str, *, max_videos: int = 5) -> list[dict]:
        """Open YouTube and return the top video results."""
        results: list[dict] = []
        try:
            with self.open_page(
                f"https://www.youtube.com/results?search_query={query}"
            ) as page:
                page.wait_for_selector("ytd-video-renderer", timeout=15_000)
                raw = page.evaluate(
                    """() => Array.from(document.querySelectorAll('ytd-video-renderer'))
                        .slice(0, __MAX__)
                        .map(v => ({
                            title:    v.querySelector('#video-title')?.innerText || '',
                            channel:  v.querySelector('#channel-info a')?.innerText || '',
                            url:      v.querySelector('#video-title')?.href || '',
                            duration: v.querySelector('#time-status')?.innerText || '',
                        }))""".replace("__MAX__", str(max_videos))
                )
                results = raw
        except Exception as e:
            logger.warning(f"youtube_search failed: {e}")
        return results

    def github_latest_release(self, user: str, repo: str) -> dict:
        """Fetch the latest release page from GitHub and extract download URLs."""
        url = f"https://github.com/{user}/{repo}/releases/latest"
        try:
            with self.open_page(url) as page:
                # The "Latest" button href gives the redirect target
                page.wait_for_selector("a[href*='releases/tag']", timeout=15_000)
                assets = page.evaluate(
                    """() => Array.from(document.querySelectorAll(
                        'a[href*="' + window.location.pathname + '"]'))
                        .filter(a => a.href.includes(window.location.pathname))
                        .filter(a => a.href.match(/\\.(zip|tar|gz|exe|dmg|pkg|deb|rpm|msi)$/i))
                        .map(a => ({name: a.innerText.trim(), url: a.href}))"""
                )
                return {
                    "ok": True,
                    "url": page.url,
                    "tag": page.url.rstrip("/").rsplit("/", 1)[-1],
                    "assets": assets,
                }
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[WebAutomator] = None


def web() -> WebAutomator:
    """Return the process-wide WebAutomator instance."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = WebAutomator(headless=True)
    return _INSTANCE


__all__ = [
    "WebAutomator", "DownloadResult", "ScrapeResult",
    "web",
]
