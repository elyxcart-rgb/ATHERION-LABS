"""SONIC AI — YouTube Player.

Control YouTube playback at JARVIS level:
  - Play a single video by URL or query
  - Play a queue/list of videos (auto-advances)
  - Playlist autopilot (continuously play next)
  - All keyboard shortcuts: play/pause/next/prev/mute/seek/fullscreen/etc.
  - Like / dislike / subscribe
  - Close ads (delegates to YouTubeAdSkipper)
  - Now-playing info (title, channel, current time)

Uses Playwright for reliable control (instead of fragile key presses).

Public API:
    YouTubePlayer(ad_skipper=None, headless=False)
    .play(url_or_query)
    .play_list([url1, url2, ...])
    .autopilot(playlist_url, max_videos=10)
    .pause() / .resume() / .toggle_pause()
    .next() / .previous()
    .seek(seconds) / .seek_percent(0-100)
    .set_volume(0-100) / .mute() / .unmute()
    .fullscreen()
    .like() / .dislike() / .subscribe()
    .get_now_playing()
    .stop()
    .get_stats()
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("sonic.youtube")


@dataclass
class VideoInfo:
    """Currently playing video."""
    url: str = ""
    title: str = ""
    channel: str = ""
    duration_s: float = 0.0
    position_s: float = 0.0
    is_playing: bool = False
    is_ad: bool = False
    volume: int = 100

    def to_dict(self) -> dict:
        return asdict(self)


class YouTubePlayer:
    """Control YouTube playback via Playwright + keyboard shortcuts."""

    YOUTUBE_DOMAIN = "youtube.com"
    YOUTUBE_SHORT_DOMAIN = "youtu.be"

    # YouTube keyboard shortcuts (these are baked into the player)
    SHORTCUTS = {
        "play_pause":   "k",
        "mute":         "m",
        "fullscreen":   "f",
        "next":         "Shift+n",
        "previous":     "Shift+p",
        "seek_forward": "l",          # 5 sec
        "seek_forward_10": "j",      # 10 sec (older)
        "seek_back":    "j",          # 5 sec (newer)
        "seek_back_10": "l",          # 10 sec
        "volume_up":    "ArrowUp",
        "volume_down":  "ArrowDown",
        "subtitles":    "c",
        "theater":      "t",
        "miniplayer":   "i",
        "fullscreen_exit": "Escape",
        "like":         "",
        "dislike":      "",
    }

    def __init__(self, ad_skipper=None, headless: bool = False):
        """Args:
            ad_skipper:  YouTubeAdSkipper instance (auto-cleans ads).
            headless:    Browser visibility (False = visible).
        """
        self._skipper = ad_skipper
        self._headless = headless

        self._pw = None
        self._browser = None
        self._ctx = None
        self._page = None

        self._lock = threading.RLock()
        self._current = VideoInfo()
        self._queue: list[str] = []
        self._autopilot_active = False
        self._autopilot_thread: Optional[threading.Thread] = None

        self._stats = {
            "videos_played": 0,
            "ads_skipped": 0,
            "controls_executed": 0,
            "errors": 0,
        }

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _ensure_browser(self):
        """Lazy-init Playwright browser."""
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=self._headless,
                args=["--autoplay-policy=no-user-gesture-required"],
            )
            self._ctx = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
            )
            self._page = self._ctx.new_page()
        except Exception as e:
            logger.warning(f"Browser init failed: {e}")
            self._page = None

    def close(self):
        """Close the browser."""
        try:
            if self._autopilot_active:
                self.stop_autopilot()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pw = self._browser = self._ctx = self._page = None

    # ── Playback controls ────────────────────────────────────────────────────

    def play(self, url_or_query: str) -> bool:
        """Play a single video by URL or search query.

        url_or_query: "https://youtu.be/..." OR "search query string"
        """
        if not url_or_query:
            return False
        self._ensure_browser()
        if self._page is None:
            return False

        with self._lock:
            self._stats["videos_played"] += 1

        url = self._resolve_url(url_or_query)
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
            # Wait for player to be ready
            time.sleep(2)
            # Try to skip ad if present
            self._try_skip_ad()
            self._current = VideoInfo(
                url=url,
                is_playing=True,
                title=self._extract_title(),
                channel=self._extract_channel(),
            )
            return True
        except Exception as e:
            self._stats["errors"] += 1
            logger.warning(f"Play failed: {e}")
            return False

    def play_list(self, urls: list[str], stop_after: Optional[int] = None
                   ) -> bool:
        """Play a list of videos in sequence.

        Each URL is played one after another (waits for video to end before
        playing next). If stop_after set, stops after that many videos.
        """
        if not urls:
            return False
        with self._lock:
            self._queue = list(urls)
        count = 0
        for url in urls:
            if stop_after and count >= stop_after:
                break
            ok = self.play(url)
            if not ok:
                continue
            # Wait for video to end (or 10 min max)
            self._wait_for_video_end(max_wait_s=600)
            count += 1
        return True

    def autopilot(self, playlist_url: str, max_videos: int = 10) -> bool:
        """Start background autopilot: continuously play next in playlist.

        Returns True if started.
        """
        if self._autopilot_active:
            return False
        self._ensure_browser()
        if self._page is None:
            return False
        try:
            self._page.goto(playlist_url, wait_until="domcontentloaded",
                              timeout=15000)
            self._try_skip_ad()
        except Exception as e:
            logger.warning(f"Autopilot start failed: {e}")
            return False

        with self._lock:
            self._autopilot_active = True

        def _loop():
            videos_played = 0
            while self._autopilot_active and videos_played < max_videos:
                if not self._wait_for_video_end(max_wait_s=900):
                    break
                self._try_skip_ad()
                # Click next video via "Up next" or next button
                if not self._click_next_video():
                    break
                videos_played += 1
            with self._lock:
                self._autopilot_active = False

        self._autopilot_thread = threading.Thread(
            target=_loop, name="sonic-yt-autopilot", daemon=True
        )
        self._autopilot_thread.start()
        return True

    def stop_autopilot(self):
        with self._lock:
            self._autopilot_active = False
        if self._autopilot_thread and self._autopilot_thread.is_alive():
            self._autopilot_thread.join(timeout=2.0)

    def pause(self) -> bool:
        """Pause playback."""
        return self._send_key("k", action="pause")

    def resume(self) -> bool:
        """Resume playback."""
        return self._send_key("k", action="resume")

    def toggle_pause(self) -> bool:
        """Toggle play/pause."""
        return self._send_key("k", action="toggle_pause")

    def next(self) -> bool:
        """Play next video."""
        # YouTube playlist keyboard: Shift+N (newer) or N key
        if self._page is None:
            return False
        try:
            self._send_key("Shift+n", action="next_video")
            return True
        except Exception:
            return self._click_next_video()

    def previous(self) -> bool:
        """Play previous video."""
        return self._send_key("Shift+p", action="previous_video")

    def seek(self, seconds: int) -> bool:
        """Seek N seconds forward (negative for back)."""
        if seconds >= 0:
            # YouTube: pressing 'l' seeks 5s, holding for 10s etc
            return self._send_key("l", action=f"seek_forward_{seconds}s",
                                   count=abs(seconds) // 5)
        else:
            return self._send_key("j", action=f"seek_back_{-seconds}s",
                                   count=abs(seconds) // 5)

    def seek_percent(self, percent: float) -> bool:
        """Seek to N% of video (0.0 - 1.0)."""
        if self._page is None:
            return False
        try:
            # Use YouTube's seek API via JS
            video_duration = self._page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    return v ? v.duration : 0;
                }
            """)
            if video_duration:
                target_s = (percent / 100.0) * video_duration
                self._page.evaluate(f"""
                    () => {{
                        const v = document.querySelector('video');
                        if (v) {{ v.currentTime = {target_s}; }}
                    }}
                """)
                return True
        except Exception:
            pass
        return False

    def set_volume(self, level: int) -> bool:
        """Set volume 0-100."""
        if not (0 <= level <= 100):
            return False
        if self._page is None:
            return False
        try:
            self._page.evaluate(f"""
                () => {{
                    const v = document.querySelector('video');
                    if (v) {{ v.volume = {level / 100.0}; v.muted = false; }}
                }}
            """)
            with self._lock:
                self._current.volume = level
            return True
        except Exception:
            return False

    def mute(self) -> bool:
        return self._send_key("m", action="mute")

    def unmute(self) -> bool:
        return self._send_key("m", action="unmute")

    def fullscreen(self) -> bool:
        return self._send_key("f", action="fullscreen")

    def like(self) -> bool:
        """Click the Like button. Disabled if already liked."""
        if self._page is None:
            return False
        try:
            # Button has aria-label like "Like this video" or "Unlike"
            self._page.evaluate("""
                () => {
                    const btns = document.querySelectorAll(
                        'button[aria-label*="ike this"], button[aria-label*="Unlike"]'
                    );
                    if (btns.length) btns[0].click();
                }
            """)
            return True
        except Exception:
            return False

    def subscribe(self) -> bool:
        """Click Subscribe on the channel page."""
        if self._page is None:
            return False
        try:
            self._page.evaluate("""
                () => {
                    const btns = document.querySelectorAll(
                        'button[aria-label*="Subscribe"], tp-yt-paper-button'
                    );
                    for (const b of btns) {
                        if (b.innerText.includes('Subscribe') && !b.innerText.includes('Subscribed')) {
                            b.click();
                            break;
                        }
                    }
                }
            """)
            return True
        except Exception:
            return False

    def stop(self) -> bool:
        """Stop playback."""
        return self.pause()

    def get_now_playing(self) -> VideoInfo:
        """Return current video info (refreshes from page)."""
        if self._page is not None:
            with self._lock:
                try:
                    self._current.title = self._extract_title()
                    self._current.channel = self._extract_channel()
                    self._current.position_s = self._page.evaluate("""
                        () => {
                            const v = document.querySelector('video');
                            return v ? v.currentTime : 0;
                        }
                    """) or 0
                    self._current.duration_s = self._page.evaluate("""
                        () => {
                            const v = document.querySelector('video');
                            return v ? v.duration : 0;
                        }
                    """) or 0
                    paused = self._page.evaluate("""
                        () => {
                            const v = document.querySelector('video');
                            return v ? v.paused : true;
                        }
                    """)
                    self._current.is_playing = not paused
                    self._current.is_ad = self._is_ad_playing()
                except Exception:
                    pass
        return self._current

    def get_stats(self) -> dict:
        with self._lock:
            stats = dict(self._stats)
            stats["autopilot_active"] = self._autopilot_active
            stats["queue_size"] = len(self._queue)
            return stats

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _resolve_url(self, url_or_query: str) -> str:
        """Convert query string to YouTube search URL; pass through URLs."""
        # If it looks like URL, pass through
        parsed = urlparse(url_or_query)
        if parsed.netloc in (self.YOUTUBE_DOMAIN, self.YOUTUBE_SHORT_DOMAIN,
                              "www.youtube.com", "m.youtube.com"):
            return url_or_query
        if parsed.netloc:  # any other URL
            return url_or_query
        # Otherwise treat as search query
        from urllib.parse import quote_plus
        return f"https://www.youtube.com/results?search_query={quote_plus(url_or_query)}"

    def _send_key(self, key: str, action: str = "key",
                   count: int = 1) -> bool:
        """Send a key press to the YouTube player."""
        if self._page is None:
            return False
        try:
            for _ in range(count):
                self._page.keyboard.press(key)
            with self._lock:
                self._stats["controls_executed"] += 1
            return True
        except Exception as e:
            logger.debug(f"Key {key} ({action}) failed: {e}")
            return False

    def _click_next_video(self) -> bool:
        """Click the 'Next' button on screen."""
        if self._page is None:
            return False
        try:
            self._page.evaluate("""
                () => {
                    // Click next button (playlist "Next" video)
                    const btns = document.querySelectorAll(
                        '.ytp-next-button, button[aria-label*="Next"]'
                    );
                    for (const b of btns) {
                        if (b.offsetParent !== null) { b.click(); return true; }
                    }
                    return false;
                }
            """)
            return True
        except Exception:
            return False

    def _try_skip_ad(self) -> bool:
        """Try to skip current ad. Returns True if an ad was skipped."""
        if self._skipper is None:
            from core.youtube_ad_skipper import YouTubeAdSkipper
            self._skipper = YouTubeAdSkipper()
        ok = self._skipper.skip_once()
        if ok:
            with self._lock:
                self._stats["ads_skipped"] += 1
        return ok

    def _is_ad_playing(self) -> bool:
        """Check current state for ad indicators."""
        if self._page is None:
            return False
        try:
            return self._page.evaluate("""
                () => {
                    return !!(
                        document.querySelector('.ytp-ad-player-overlay') ||
                        document.querySelector('.video-ads') ||
                        document.querySelector('.ytp-ad-text')
                    );
                }
            """)
        except Exception:
            return False

    def _wait_for_video_end(self, max_wait_s: int = 600) -> bool:
        """Wait for current video to finish (or timeout)."""
        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            if self._page is None:
                return False
            try:
                ended = self._page.evaluate("""
                    () => {
                        const v = document.querySelector('video');
                        if (!v) return true;
                        return v.ended || (v.duration > 0 && v.currentTime >= v.duration - 1);
                    }
                """)
                if ended:
                    return True
                # Check for ad in between
                if self._is_ad_playing():
                    self._try_skip_ad()
            except Exception:
                pass
            time.sleep(2)
        return False

    def _extract_title(self) -> str:
        if self._page is None:
            return ""
        try:
            return self._page.evaluate("""
                () => document.title.replace(' - YouTube', '')
            """) or ""
        except Exception:
            return ""

    def _extract_channel(self) -> str:
        if self._page is None:
            return ""
        try:
            return self._page.evaluate("""
                () => {
                    const el = document.querySelector(
                        'ytd-channel-name a, .ytd-video-owner-renderer a'
                    );
                    return el ? el.textContent.trim() : '';
                }
            """) or ""
        except Exception:
            return ""
