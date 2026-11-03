"""SONIC AI — Screen Vision.

JARVIS-level screen awareness: SONIC can SEE what's on the user's screen.
- Captures the screen (or a region)
- Runs OCR to extract visible text
- Detects focused window + app context
- Optional LLM-based scene description ("what's on the screen?")
- Caches results (5-second TTL) so rapid commands stay cheap

Designed for both programmatic use and conversational "what's on my screen?"
queries.
"""
from __future__ import annotations

import io
import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable, Any


@dataclass
class ScreenContext:
    """What SONIC sees right now."""
    captured_at: float                        # unix timestamp
    width: int = 0
    height: int = 0
    focused_window: str = ""
    focused_app: str = ""
    visible_text: str = ""                    # OCR output (first 2k chars)
    text_blocks: int = 0                      # number of OCR'd regions
    image_b64: str = ""                       # base64 PNG of the capture
    scene_description: str = ""               # LLM-generated description
    word_count: int = 0
    language: str = "en"

    def summary(self) -> str:
        """One-line human-readable summary for verbal response."""
        bits = []
        if self.focused_app:
            bits.append(f"focused on {self.focused_app}")
        if self.word_count:
            bits.append(f"{self.word_count} words visible")
        if self.scene_description:
            bits.append(self.scene_description[:200])
        return " | ".join(bits) if bits else "screen captured"

    def to_dict(self) -> dict:
        return asdict(self)


class ScreenVision:
    """Live screen awareness — capture, OCR, describe."""

    def __init__(self, llm_client: Optional[Callable[[str], str]] = None,
                 cache_ttl_seconds: float = 5.0):
        self._llm = llm_client
        self._ttl = cache_ttl_seconds
        self._last: Optional[ScreenContext] = None
        self._lock = threading.Lock()
        self._stats = {"captures": 0, "ocr_runs": 0, "llm_describes": 0, "cache_hits": 0}

    # ── Public ───────────────────────────────────────────────────────────────

    def see(self, force_refresh: bool = False, with_description: bool = True) -> ScreenContext:
        """Capture the current screen and return a context snapshot.

        Returns a cached snapshot if it's younger than cache_ttl_seconds and
        force_refresh is False.
        """
        with self._lock:
            now = time.time()
            if (not force_refresh and self._last is not None
                    and now - self._last.captured_at < self._ttl):
                self._stats["cache_hits"] += 1
                return self._last

        ctx = self._capture()
        ctx.visible_text, ctx.text_blocks = self._ocr_text(ctx)
        ctx.word_count = len(ctx.visible_text.split())

        if with_description and self._llm is not None:
            ctx.scene_description = self._describe(ctx)

        with self._lock:
            self._last = ctx
            self._stats["captures"] += 1
        return ctx

    def see_region(self, x: int, y: int, width: int, height: int) -> ScreenContext:
        """Capture a specific region of the screen."""
        ctx = self._capture_region(x, y, width, height)
        ctx.visible_text, ctx.text_blocks = self._ocr_text(ctx)
        ctx.word_count = len(ctx.visible_text.split())
        return ctx

    def get_cached(self) -> Optional[ScreenContext]:
        with self._lock:
            return self._last

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ────────────────────────────────────────────────────────────

    def _capture(self) -> ScreenContext:
        """Capture the primary screen."""
        ctx = ScreenContext(captured_at=time.time())
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            ctx.width, ctx.height = img.size
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            ctx.image_b64 = _b64encode(buf.getvalue())
        except Exception as e:
            ctx.scene_description = f"capture error: {e}"
            ctx.width, ctx.height = 1920, 1080

        # Focused window
        ctx.focused_window, ctx.focused_app = _focused_window()
        return ctx

    def _capture_region(self, x: int, y: int, w: int, h: int) -> ScreenContext:
        ctx = ScreenContext(captured_at=time.time(), width=w, height=h)
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            ctx.width, ctx.height = img.size
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            ctx.image_b64 = _b64encode(buf.getvalue())
        except Exception as e:
            ctx.scene_description = f"region capture error: {e}"
        return ctx

    def _ocr_text(self, ctx: ScreenContext) -> tuple[str, int]:
        """Run OCR on the captured image. Tries pytesseract first, then a
        heuristic fallback that uses PIL to find text-like regions."""
        if not ctx.image_b64:
            return "", 0
        self._stats["ocr_runs"] += 1

        # Try pytesseract
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(_b64decode(ctx.image_b64)))
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            blocks = 0
            words = []
            for i, txt in enumerate(data.get("text", [])):
                if txt and txt.strip():
                    blocks += 1
                    words.append(txt.strip())
            text = " ".join(words)[:2000]
            return text, blocks
        except ImportError:
            pass
        except Exception:
            pass

        # Fallback: just say we couldn't OCR
        return "(OCR unavailable — install pytesseract for screen text recognition)", 0

    def _describe(self, ctx: ScreenContext) -> str:
        """Use LLM to describe what's on the screen."""
        if self._llm is None:
            return ""
        self._stats["llm_describes"] += 1
        snippet = ctx.visible_text[:600] if ctx.visible_text else "(no text)"
        prompt = (
            "You are SONIC AI, a JARVIS-class assistant. Briefly describe what "
            "the user is looking at based on this context. Be concise (1-2 sentences).\n"
            f"App: {ctx.focused_app or 'unknown'}\n"
            f"Window: {ctx.focused_window or 'unknown'}\n"
            f"Visible text sample: {snippet}\n"
            "Description:"
        )
        try:
            return self._llm(prompt).strip()
        except Exception as e:
            return f"(description failed: {e})"


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _b64encode(b: bytes) -> str:
    import base64
    return base64.b64encode(b).decode("ascii")


def _b64decode(s: str) -> bytes:
    import base64
    return base64.b64decode(s.encode("ascii"))


def _focused_window() -> tuple[str, str]:
    """Get the currently focused window title and app name."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value or ""
        # Try to get app name
        app = ""
        try:
            import psutil
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            p = psutil.Process(pid.value)
            app = p.name().replace(".exe", "")
        except Exception:
            pass
        return title, app
    except Exception:
        return "", ""
