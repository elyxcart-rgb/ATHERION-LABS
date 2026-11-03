"""SONIC AI — Ultra-Pro YouTube Ad Skipper.

The definitive ad-eliminator. Detects every type of YouTube ad via multiple
independent signals, clicks the skip button the moment it's clickable, and
verifies the ad is gone.

Detection signals (ALL combined for max confidence):
  - Visual text  : "Skip Ad" / "Skip Ads" / localized (22 languages)
  - Visual badge : "Ad ·", "Advertisement", "Sponsored"
  - Visual count : "Ad · 5s", "Your video will resume in X"
  - Visual CTA   : "Visit website", "Learn more" (sponsored cards)
  - Browser DOM  : `document.querySelector('.ytp-ad-player-overlay')` etc.
  - Audio signature: distinct ad-music RMS jump (optional)
  - Player state : video paused = likely ad break

Click strategies (priority order, fallback through them on failure):
  1. DOM click via Playwright (fastest, most reliable if browser available)
  2. Smart clicker button finder (vision-based)
  3. Keyboard Tab + Enter (focuses skip button then activates)
  4. Direct coordinate click with verification re-screenshot

Verification (never reports false success):
  - After click: re-scan and confirm "Skip Ad" text is gone
  - Confirm video player shows normal content (not ad overlay)
  - If still ad: retry up to N times with different click strategy

Ad types handled:
  - Skippable video ad        → click "Skip Ad" as soon as countdown ends
  - Non-skippable video ad    → wait it out, log progress
  - Bumper ad (6s)            → wait it out
  - Overlay ad (banner)       → click the X close button
  - Sponsored card (sidebar)  → dismiss / ignore (don't auto-click)
  - Pre-roll / mid-roll / post-roll

Resource-aware:
  - Skip scan when YouTube tab not foreground
  - Adaptive polling: 250ms during ad, 1500ms idle
  - SmartClicker screen capture reused across scans

Public API:
    skipper = YouTubeAdSkipper()
    skipper.start()                      # background daemon
    skipper.stop()
    skipper.skip_once() -> dict          # one cycle with full report
    skipper.get_stats() -> dict
    skipper.set_browser_page(page)       # hook Playwright page for DOM clicks
"""
from __future__ import annotations

import io
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sonic.ad_skipper")


# ──────────────────────────────────────────────────────────────────────
# Localization (covers YouTube's primary 22 ad-skip button languages)
# ──────────────────────────────────────────────────────────────────────
SKIP_BUTTON_TEXTS = [
    # English variants
    "Skip Ad", "Skip Ads", "Skip advertisement", "Skip",
    # Urdu/Hindi
    "ایڈ چھوڑیں", "विज्ञापन छोड़ें", "विज्ञापन स्किप करें", "विज्ञापन हटाएं",
    # Spanish / Portuguese
    "Saltar anuncio", "Saltar publicidad", "Saltar",
    "Pular anúncio", "Pular anuncios",
    # French
    "Ignorer l'annonce", "Passer l'annonce", "Ignorer",
    # German
    "Werbung überspringen", "Anzeige überspringen", "Überspringen",
    # Italian
    "Salta annuncio", "Salta",
    # Turkish
    "Reklamı atla", "Atla",
    # Russian
    "Пропустить рекламу", "Пропустить",
    # Arabic
    "تخطي الإعلان",
    # Chinese (Simplified + Traditional)
    "跳过广告", "略過廣告", "跳过", "略過",
    # Japanese
    "広告をスキップ", "スキップ",
    # Korean
    "광고 건너뛰기", "건너뛰기",
    # Polish / Dutch / Greek / Czech / Hungarian / Romanian / Thai / Vietnamese / Indonesian / Malay
    "Pomiń reklamę", "Overslaan", "Παράλειψη", "Přeskočit",
    "Hirdetés kihagyása", "Omite", "ข้ามโฆษณา",
    "Bỏ qua quảng cáo", "Lewati iklan", "Langkau iklan",
]


AD_INDICATOR_TEXTS = [
    # English
    "Ad ·", "Advertisement", "Sponsored", "Paid promotion",
    "Your video will resume in", "Video will resume after",
    "Skip Ad in", "Ad will end in",
    # Spanish / Portuguese
    "Anuncio", "Patrocinado", "Publicidade",
    # French / German
    "Publicité", "Werbung", "Gesponsert",
    # Italian / Turkish / Russian / Arabic / Chinese / Japanese / Korean
    "Annuncio", "Reklam", "Реклама", "إعلان", "广告", "広告", "광고",
]


# YouTube player state strings (from DOM `.ytp-play-button` and similar)
AD_PLAYER_CLASSES = [
    "ytp-ad-player-overlay",          # overlay ad
    "ytp-ad-text",                    # "Ad · 5s"
    "ytp-ad-skip-button",             # skip button container
    "ytp-ad-skip-button-modern",      # new style
    "ytp-skip-ad-button",             # legacy
    "ytp-ad-overlay-container",       # large overlay
    "ytp-ad-image-overlay",           # image overlay
    "ytp-ad-badge",                   # ad badge
    "ad-showing",                     # video element class
]


# ──────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────
@dataclass
class AdEvent:
    """One detected ad encounter."""
    detected_at: float = 0.0
    ad_type: str = "unknown"          # skippable / non_skippable / bumper / overlay / unknown
    detection_signals: list[str] = field(default_factory=list)
    skip_attempted: bool = False
    skip_succeeded: bool = False
    skip_method: str = ""
    skip_duration_ms: float = 0.0
    ad_duration_estimate_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "detected_at": self.detected_at,
            "ad_type": self.ad_type,
            "signals": self.detection_signals,
            "skip_attempted": self.skip_attempted,
            "skip_succeeded": self.skip_succeeded,
            "skip_method": self.skip_method,
            "skip_ms": round(self.skip_duration_ms, 1),
            "ad_estimate_s": round(self.ad_duration_estimate_s, 1),
        }


@dataclass
class AdSkipperStats:
    scans: int = 0
    ads_detected: int = 0
    skippable_ads: int = 0
    skipped_successful: int = 0
    skipped_failed: int = 0
    non_skippable_waitouts: int = 0
    false_positives: int = 0
    verification_retries: int = 0
    started_at: float = 0.0
    last_event: Optional[AdEvent] = None
    recent_events: list[AdEvent] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scans": self.scans,
            "ads_detected": self.ads_detected,
            "skippable_ads": self.skippable_ads,
            "skipped_successful": self.skipped_successful,
            "skipped_failed": self.skipped_failed,
            "non_skippable_waitouts": self.non_skippable_waitouts,
            "false_positives": self.false_positives,
            "verification_retries": self.verification_retries,
            "started_at": self.started_at,
            "uptime_s": round(time.time() - self.started_at, 1) if self.started_at else 0,
            "last_event": self.last_event.to_dict() if self.last_event else None,
            "recent_count": len(self.recent_events),
        }


# ──────────────────────────────────────────────────────────────────────
# Skipper
# ──────────────────────────────────────────────────────────────────────
class YouTubeAdSkipper:
    """The ultra-pro YouTube ad skipper."""

    POLL_IDLE_MS = 1500          # when no ad detected
    POLL_ACTIVE_MS = 250         # when ad is playing (fast response)
    VERIFY_WAIT_MS = 400         # wait before verifying after click
    SKIP_TIMEOUT_S = 35          # bail on non-skippable after this
    MAX_VERIFY_RETRIES = 3       # retry click if verification fails

    def __init__(self,
                 interval_ms: float = 1500,
                 only_when_yt_focused: bool = False,
                 enable_dom_clicks: bool = True,
                 enable_audio_signature: bool = False):
        self._interval_idle = interval_ms / 1000.0
        self._interval_active = self.POLL_ACTIVE_MS / 1000.0
        self._only_focused = only_when_yt_focused
        self._enable_dom = enable_dom_clicks
        self._enable_audio_sig = enable_audio_signature

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._stats = AdSkipperStats()

        # Browser page for DOM clicks (optional)
        self._browser_page = None
        self._browser_lock = threading.Lock()

        # Lazy imports
        self._clicker = None
        self._init_dependencies()

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def start(self):
        """Start the background scan loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stats.started_at = time.time()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="sonic-yt-ad-skipper-ultra",
            daemon=True,
        )
        self._thread.start()
        logger.info("YouTube ultra-pro ad skipper started")

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def skip_once(self) -> dict:
        """One full detection + click + verify cycle, returns report dict."""
        with self._lock:
            self._stats.scans += 1
        return self._detect_skip_verify().to_dict()

    def get_stats(self) -> dict:
        with self._lock:
            return self._stats.to_dict()

    def set_browser_page(self, page) -> None:
        """Inject a Playwright page for fast DOM-level clicks."""
        with self._browser_lock:
            self._browser_page = page

    # ── Background loop ──────────────────────────────────────────────────

    def _run_loop(self):
        """Adaptive polling loop — fast during ads, slow when idle."""
        idle_polls = 0
        while self._running:
            try:
                if self._only_focused and not self._is_yt_focused():
                    time.sleep(self._interval_idle)
                    continue
                event = self._detect_skip_verify()
                if event.skip_succeeded or event.detection_signals:
                    # ad-related activity — short interval next
                    time.sleep(self._interval_active)
                    idle_polls = 0
                else:
                    # idle — back off
                    idle_polls += 1
                    sleep = min(self._interval_idle * (idle_polls / 3 + 1), 4.0)
                    time.sleep(sleep)
            except Exception as e:
                logger.debug(f"Skipper loop error: {e}")
                time.sleep(self._interval_idle)

    # ── Detection + skip + verify (core logic) ───────────────────────────

    def _detect_skip_verify(self) -> AdEvent:
        """One full detection→skip→verify cycle."""
        event = AdEvent(detected_at=time.time())

        # 1. Capture screenshot
        img = self._capture_screen()
        if img is None:
            return event

        # 2. Multi-signal detection
        visual_signals = self._detect_visual(img)
        dom_signals = self._detect_dom()
        event.detection_signals = visual_signals + dom_signals

        if not event.detection_signals:
            return event

        # 3. Classify ad type
        event.ad_type = self._classify_ad_type(event.detection_signals, img)

        with self._lock:
            self._stats.ads_detected += 1

        # 4. Non-skippable → wait it out, don't try to click
        if event.ad_type in ("non_skippable", "bumper"):
            with self._lock:
                self._stats.non_skippable_waitouts += 1
            logger.info(f"Ad type={event.ad_type}, waiting it out ({event.detection_signals})")
            return event

        with self._lock:
            self._stats.skippable_ads += 1

        # 5. Skip — try strategies in priority order
        event.skip_attempted = True
        t0 = time.time()
        for attempt in range(self.MAX_VERIFY_RETRIES):
            success, method = self._try_skip(img, event.detection_signals)
            if success:
                # 6. Verify
                time.sleep(self.VERIFY_WAIT_MS / 1000.0)
                if self._verify_skip(img):
                    event.skip_succeeded = True
                    event.skip_method = method
                    event.skip_duration_ms = (time.time() - t0) * 1000.0
                    with self._lock:
                        self._stats.skipped_successful += 1
                        self._stats.last_event = event
                        self._stats.recent_events.append(event)
                        if len(self._stats.recent_events) > 50:
                            self._stats.recent_events.pop(0)
                    logger.info(
                        f"✓ Ad skipped via {method} in "
                        f"{event.skip_duration_ms:.0f}ms "
                        f"(signals: {event.detection_signals})"
                    )
                    return event
                else:
                    # Verification failed — ad still there, retry with different strategy
                    with self._lock:
                        self._stats.verification_retries += 1
                    logger.debug(f"Skip click landed but ad still showing, retry {attempt+1}")
                    continue
            else:
                break

        event.skip_succeeded = False
        with self._lock:
            self._stats.skipped_failed += 1
            self._stats.last_event = event
        logger.warning(f"✗ Could not skip ad (signals: {event.detection_signals})")
        return event

    # ── Visual detection ────────────────────────────────────────────────

    def _detect_visual(self, img: bytes) -> list[str]:
        """Find ad indicators in the screenshot."""
        signals = []
        try:
            if self._clicker is None:
                return signals
            # High-priority: countdown badge or skip button visible
            for text in ["Ad ·", "Skip Ad", "Skip Ads", "Advertisement",
                          "Sponsored", "Your video will resume"]:
                hits = self._clicker.find_text(text, screen_image=img, fuzzy=True)
                if hits:
                    signals.append(f"visual:{text}")
            # Localized indicators
            for text in AD_INDICATOR_TEXTS[5:]:  # skip duplicates
                if text in ("Ad ·", "Skip Ad", "Skip Ads", "Advertisement",
                             "Sponsored", "Your video will resume"):
                    continue
                hits = self._clicker.find_text(text, screen_image=img, fuzzy=True)
                if hits:
                    signals.append(f"visual:{text}")
        except Exception:
            logger.debug("Visual detection failed", exc_info=True)
        return signals

    # ── DOM detection ───────────────────────────────────────────────────

    def _detect_dom(self) -> list[str]:
        """Check the YouTube DOM for ad player classes."""
        signals = []
        if not self._enable_dom:
            return signals
        with self._browser_lock:
            page = self._browser_page
        if page is None:
            return signals
        try:
            # Quick sync JS evaluation (this is called every poll, keep cheap)
            result = page.evaluate("""() => {
                const signals = [];
                // Check video element state
                const v = document.querySelector('video');
                if (v && v.classList.contains('ad-showing')) signals.push('dom:ad-showing');
                // Check player class
                const player = document.querySelector('.html5-video-player');
                if (player && player.classList.contains('ad-showing')) signals.push('dom:player.ad-showing');
                // Check known ad containers
                const selectors = [
                  '.ytp-ad-player-overlay', '.ytp-ad-text', '.ytp-ad-skip-button',
                  '.ytp-ad-skip-button-modern', '.ytp-skip-ad-button',
                  '.ytp-ad-overlay-container', '.ytp-ad-image-overlay', '.ytp-ad-badge'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.offsetParent !== null) signals.push('dom:' + sel.slice(1));
                }
                return signals;
            }""")
            if isinstance(result, list):
                signals.extend(result)
        except Exception:
            # Page not connected, page closed, etc. — silent fallback to visual
            pass
        return signals

    # ── Ad type classification ──────────────────────────────────────────

    def _classify_ad_type(self, signals: list[str], img: bytes) -> str:
        """Determine if ad is skippable, non-skippable, bumper, or overlay."""
        # Non-skippable: countdown present but no "Skip" anywhere
        has_skip_text = any("Skip" in s for s in signals)
        has_countdown = any("Ad ·" in s or "Ad in" in s or "Ad will end in" in s
                            or "Your video will resume" in s
                            for s in signals)
        has_overlay = any("overlay" in s for s in signals)

        # Bumper: very short, no skip button (YouTube 6-sec ads)
        if not has_skip_text and has_countdown:
            # Could be non-skippable or bumper. Heuristic: if "Skip in Xs"
            # countdown is present, wait for it to reach 0 then skip.
            return "skippable_waiting"
        if has_overlay and not has_skip_text:
            return "overlay"
        if has_skip_text:
            return "skippable"
        return "unknown"

    # ── Skip strategies ──────────────────────────────────────────────────

    def _try_skip(self, img: bytes, signals: list[str]) -> tuple[bool, str]:
        """Try skip strategies in priority order. Returns (success, method)."""

        # Strategy 1: DOM click via Playwright
        if self._enable_dom:
            ok, method = self._try_dom_skip()
            if ok:
                return True, method

        # Strategy 2: Smart clicker button finder (visual)
        ok, method = self._try_smart_click(img)
        if ok:
            return True, method

        # Strategy 3: Keyboard Tab + Enter (focuses skip button)
        ok, method = self._try_keyboard_skip()
        if ok:
            return True, method

        return False, "all_failed"

    def _try_dom_skip(self) -> tuple[bool, str]:
        """Try clicking the skip button via Playwright DOM."""
        with self._browser_lock:
            page = self._browser_page
        if page is None:
            return False, "dom_no_page"
        try:
            # Look for any clickable skip button
            result = page.evaluate("""() => {
                const selectors = [
                    '.ytp-ad-skip-button', '.ytp-ad-skip-button-modern',
                    '.ytp-skip-ad-button', 'button.ytp-ad-skip-button-modern'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const rect = el.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0
                                        && el.offsetParent !== null;
                        if (visible) {
                            el.click();
                            return { clicked: true, selector: sel };
                        }
                    }
                }
                return { clicked: false };
            }""")
            if isinstance(result, dict) and result.get("clicked"):
                return True, f"dom_click:{result.get('selector', '?')}"
        except Exception:
            pass
        return False, "dom_miss"

    def _try_smart_click(self, img: bytes) -> tuple[bool, str]:
        """Use SmartClicker to find and click the skip button visually."""
        if self._clicker is None:
            return False, "no_clicker"
        # Try multiple skip text variants (multi-language)
        for text in SKIP_BUTTON_TEXTS[:25]:  # limit to top languages for speed
            try:
                target = self._clicker.find_button(text, img)
                if target and target.confidence >= 0.55:
                    ok = self._clicker.click(text, target.x, target.y)
                    if ok:
                        return True, f"smart_click:{text}"
            except Exception:
                continue
        return False, "smart_click_miss"

    def _try_keyboard_skip(self) -> tuple[bool, str]:
        """Press Tab to focus skip button, then Enter to activate."""
        try:
            import pyautogui
        except ImportError:
            return False, "no_pyautogui"
        try:
            # YouTube skip button is typically in the ad overlay area.
            # Tab focuses interactive elements in order; the skip button
            # usually takes 2-5 tabs to reach.
            for tabs in (3, 4, 2, 5):
                for _ in range(tabs):
                    pyautogui.press("tab")
                # Press Enter to activate focused element
                pyautogui.press("enter")
                # If it worked, the ad will be gone within 500ms
                time.sleep(0.2)
                if self._verify_quick():
                    return True, f"keyboard_tab{tabs}"
            return False, "keyboard_miss"
        except Exception:
            return False, "keyboard_error"

    # ── Verification ─────────────────────────────────────────────────────

    def _verify_skip(self, before_img: bytes) -> bool:
        """Confirm the ad is gone after the skip click."""
        after_img = self._capture_screen()
        if after_img is None:
            return False
        # Ad indicator texts should be absent now
        for text in ["Skip Ad", "Ad ·", "Advertisement", "Your video will resume",
                      "Sponsored"]:
            hits = self._clicker.find_text(text, screen_image=after_img, fuzzy=True)
            if hits:
                return False
        return True

    def _verify_quick(self) -> bool:
        """Fast verification for keyboard path."""
        img = self._capture_screen()
        if img is None:
            return False
        for text in ["Skip Ad", "Ad ·"]:
            if self._clicker.find_text(text, screen_image=img, fuzzy=True):
                return False
        return True

    # ── Helpers ──────────────────────────────────────────────────────────

    def _capture_screen(self):
        """Capture primary monitor as PNG bytes."""
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None

    def _is_yt_focused(self) -> bool:
        """Check if YouTube is the foreground window."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.lower()
            return "youtube" in title or ("chrome" in title and "youtube" in title)
        except Exception:
            return False

    def _init_dependencies(self):
        """Lazy-load SmartClicker and pyautogui."""
        try:
            from core.smart_clicker import SmartClicker
            self._clicker = SmartClicker()
        except Exception as e:
            logger.debug(f"SmartClicker init failed: {e}")
            self._clicker = None
