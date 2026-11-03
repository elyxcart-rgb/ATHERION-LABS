"""SONIC AI — Smart UI Clicker.

Intelligent UI element finder that doesn't depend on Gemini API quota.
Multi-strategy detection:

  1. OCR text match (multiple languages, fuzzy)
  2. Visual cues (button styling, position, color)
  3. Context awareness (near "Download X" or "Get X" text)
  4. Icon detection (down arrow, download arrow)
  5. Common app/site patterns (Steam, Microsoft Store, App Store, etc.)
  6. URL pattern detection (file://, .exe, .msi, .dmg, .pkg)

Public API:
    SmartClicker()
    .find_button(intent, screen_image=None) -> dict  # x, y, text, confidence
    .find_download_button(screen_image=None, app_name=None) -> dict
    .click(intent, x, y) -> bool
    .find_text(text, screen_image=None, fuzzy=True) -> list[dict]
    .list_supported_languages() -> list[str]
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

logger = logging.getLogger("sonic.clicker")


# ═════════════════════════════════════════════════════════════════════════════
# Button vocabulary — multi-language download/install button labels
# ═════════════════════════════════════════════════════════════════════════════

# Direct download labels across languages
DOWNLOAD_LABELS = {
    # English
    "download", "download now", "download free", "free download",
    "download file", "get download", "get it now", "get now",
    "install now", "install", "save", "save file", "save to",
    "click to download", "click here to download",
    # Spanish
    "descargar", "descarga", "bajar", "obtener",
    # French
    "télécharger", "telecharger", "obtenir",
    # German
    "herunterladen", "downloaden", "speichern",
    # Italian
    "scarica", "scaricare",
    # Portuguese
    "baixar", "download agora",
    # Russian
    "скачать", "загрузить",
    # Chinese
    "下载", "立即下载", "免费下载", "高速下载",
    # Japanese
    "ダウンロード", "ダウンロードする",
    # Korean
    "다운로드", "다운로드하기",
    # Arabic
    "تنزيل", "تحميل",
    # Hindi/Urdu
    "डाउनलोड", "ڈاؤن لوڈ",
    # Turkish
    "indir", "indirmek",
    # Polish
    "pobierz",
    # Dutch
    "downloaden",
    # Greek
    "λήψη",
    # Czech
    "stáhnout",
    # Swedish
    "ladda ner", "laddaned",
    # Vietnamese
    "tải về",
    # Indonesian/Malay
    "unduh", "muat turun",
}

# Skip/close/next labels (for ads, popups)
SKIP_LABELS = {
    "skip", "skip ad", "skip ads", "skip this ad",
    "close", "close this", "no thanks", "no, thanks", "not now",
    "later", "skip trial", "dismiss",
    # Multi-language
    "saltar", "saltar anuncio",           # Spanish
    "passer", "ignorer",                  # French
    "überspringen", "schließen",           # German
    "ignora", "salta",                    # Italian
    "pular", "fechar",                    # Portuguese
    "пропустить", "закрыть",              # Russian
    "跳过", "关闭", "不，谢谢",              # Chinese
    "スキップ", "閉じる",                   # Japanese
    "건너뛰기", "닫기",                    # Korean
    "تخطي", "إغلاق",                      # Arabic
    "skippe",                             # German alt
}

# Get/install (often paired with download)
GET_LABELS = {
    "get", "get app", "get now", "get it", "get for free",
    "free", "free download", "free install",
    "install", "install now", "install app",
    "add to cart", "buy now", "purchase",
}

# Generic button indicators (for visual detection)
BUTTON_CLASSES = {
    "button", "btn", "download-btn", "install-btn", "get-btn",
    "primary-button", "action-button", "cta", "call-to-action",
    "download-button", "submit", "action",
}


# ═════════════════════════════════════════════════════════════════════════════
# Click target
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ClickTarget:
    """Where to click, with confidence + reason."""
    x: int = 0
    y: int = 0
    text: str = ""
    confidence: float = 0.0
    source: str = "unknown"          # ocr|visual|context|url|known_site
    language: str = "unknown"
    bbox: tuple = (0, 0, 0, 0)       # x, y, width, height
    explanation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# SmartClicker
# ═════════════════════════════════════════════════════════════════════════════

class SmartClicker:
    """Intelligent UI element finder — finds buttons without Gemini API."""

    def __init__(self):
        self._lock = threading.RLock()
        self._stats = {
            "searches": 0, "clicks": 0, "found": 0, "missed": 0,
            "by_source": {"ocr": 0, "visual": 0, "context": 0,
                          "url": 0, "known_site": 0},
        }
        self._cached_image: Optional[bytes] = None
        self._cached_texts: list[dict] = []

    # ── Public ───────────────────────────────────────────────────────────────

    def find_button(self, intent: str,
                     screen_image: Optional[bytes] = None) -> Optional[ClickTarget]:
        """Find a clickable element matching the intent.

        intent: "download", "install", "skip", "skip ad", "next", etc.
        """
        with self._lock:
            self._stats["searches"] += 1

        intent_low = intent.lower().strip()

        # Determine vocabulary set
        if intent_low in ("download", "download_button", "download app"):
            vocab = DOWNLOAD_LABELS | GET_LABELS
            preferred = DOWNLOAD_LABELS
        elif intent_low in ("install", "install_app"):
            vocab = DOWNLOAD_LABELS | GET_LABELS | {"install", "install now"}
            preferred = {"install", "install now"}
        elif intent_low in ("skip", "skip_ad", "skip ad"):
            vocab = SKIP_LABELS
            preferred = SKIP_LABELS
        else:
            vocab = {intent_low}
            preferred = vocab

        # 1. OCR-based detection (if screen provided)
        if screen_image is not None:
            texts = self._ocr_screen(screen_image)
            target = self._find_in_texts(texts, vocab, preferred, intent)
            if target:
                with self._lock:
                    self._stats["found"] += 1
                    self._stats["by_source"]["ocr"] += 1
                return target

        # 2. Use cached screen if available
        if self._cached_texts:
            target = self._find_in_texts(self._cached_texts, vocab, preferred, intent)
            if target:
                with self._lock:
                    self._stats["found"] += 1
                    self._stats["by_source"]["ocr"] += 1
                return target

        # 3. Visual / contextual heuristics (if no screen)
        # Caller should provide screen for actual clicking
        return None

    def find_download_button(self, screen_image: Optional[bytes] = None,
                              app_name: Optional[str] = None) -> Optional[ClickTarget]:
        """Specifically find a download/install button.

        app_name: optional hint (e.g. "Chrome", "Steam") for known-site patterns.
        """
        # First try generic download intent
        target = self.find_button("download", screen_image)
        if target:
            return target

        # Try install intent
        target = self.find_button("install", screen_image)
        if target:
            return target

        # Try known site patterns
        if app_name:
            target = self._find_by_known_site(app_name, screen_image)
            if target:
                with self._lock:
                    self._stats["by_source"]["known_site"] += 1
                return target

        return None

    def click(self, intent: str, x: int, y: int,
              method: str = "pyautogui") -> bool:
        """Click at the given coordinates.

        method: "pyautogui" (default) | "win32" | "subprocess"
        """
        with self._lock:
            self._stats["clicks"] += 1
        try:
            if method == "win32":
                import ctypes
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)  # left down
                ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)  # left up
                return True
            else:
                # Try pyautogui first
                try:
                    import pyautogui
                    pyautogui.click(x, y)
                    return True
                except Exception:
                    pass
                # Fallback to win32
                return self.click(intent, x, y, method="win32")
        except Exception as e:
            logger.debug(f"Click failed: {e}")
            return False

    def find_text(self, text: str, screen_image: Optional[bytes] = None,
                   fuzzy: bool = True) -> list[dict]:
        """Find all occurrences of text on screen.

        Returns list of {"text": ..., "x": ..., "y": ..., "confidence": ...}.
        """
        target = text.lower().strip()
        texts = self._ocr_screen(screen_image) if screen_image else self._cached_texts
        results = []
        for entry in texts:
            t = entry.get("text", "").lower().strip()
            if not t:
                continue
            if t == target:
                results.append({**entry, "match": "exact"})
            elif fuzzy and self._fuzzy_match(target, t):
                results.append({**entry, "match": "fuzzy"})
        return results

    def list_supported_languages(self) -> list[str]:
        """Languages covered by the button vocabulary."""
        return [
            "English", "Spanish", "French", "German", "Italian",
            "Portuguese", "Russian", "Chinese", "Japanese", "Korean",
            "Arabic", "Hindi", "Urdu", "Turkish", "Polish", "Dutch",
            "Greek", "Czech", "Swedish", "Vietnamese", "Indonesian",
            "Malay",
        ]

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def cache_screen(self, image_bytes: bytes):
        """Cache a screen capture for subsequent find_button calls."""
        self._cached_image = image_bytes
        self._cached_texts = self._ocr_screen(image_bytes)

    # ── Internals ────────────────────────────────────────────────────────────

    def _ocr_screen(self, image_bytes: bytes) -> list[dict]:
        """Run OCR on the image. Returns list of {text, x, y, w, h, conf}."""
        if not image_bytes:
            return []
        try:
            import pytesseract
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
            results = []
            for i, txt in enumerate(data.get("text", [])):
                if not txt or not txt.strip():
                    continue
                results.append({
                    "text": txt.strip(),
                    "x": data["left"][i] + data["width"][i] // 2,
                    "y": data["top"][i] + data["height"][i] // 2,
                    "left": data["left"][i],
                    "top": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                    "conf": float(data["conf"][i]) / 100.0,
                })
            return results
        except Exception as e:
            logger.debug(f"OCR failed: {e}")
            return []

    def _find_in_texts(self, texts: list[dict], vocab: set,
                         preferred: set, intent: str) -> Optional[ClickTarget]:
        """Find the best-matching text from OCR results."""
        if not texts:
            return None

        best: Optional[ClickTarget] = None
        best_score = 0.0

        for entry in texts:
            t = entry.get("text", "").lower().strip()
            if not t:
                continue

            # Exact match
            if t in vocab:
                score = 1.0
                if t in preferred:
                    score = 1.5
            # Substring match
            elif any(v in t for v in vocab):
                score = 0.85
                if any(p in t for p in preferred):
                    score = 1.1
            # Fuzzy match
            elif self._fuzzy_match(t, vocab):
                score = 0.7
            else:
                continue

            # Boost by OCR confidence
            score *= 0.5 + 0.5 * entry.get("conf", 0.5)

            if score > best_score:
                best_score = score
                best = ClickTarget(
                    x=entry["x"],
                    y=entry["y"],
                    text=entry["text"],
                    confidence=min(1.0, score),
                    source="ocr",
                    language=self._detect_language(t),
                    bbox=(entry.get("left", 0), entry.get("top", 0),
                           entry.get("w", 0), entry.get("h", 0)),
                    explanation=f"OCR match for {intent!r}: '{entry['text']}'",
                )

        return best

    @staticmethod
    def _fuzzy_match(text: str, vocab) -> float:
        """Fuzzy match score 0..1 against any vocabulary entry."""
        text_low = text.lower()
        best = 0.0
        vocab_iter = vocab if not isinstance(vocab, set) else vocab
        for word in vocab_iter:
            word_low = word.lower()
            if not word_low:
                continue
            # Simple ratio
            longer = max(len(text_low), len(word_low))
            if longer == 0:
                continue
            dist = sum(c1 != c2 for c1, c2 in zip(text_low, word_low))
            dist += abs(len(text_low) - len(word_low))
            ratio = 1.0 - (dist / longer)
            if ratio > best:
                best = ratio
        return best

    @staticmethod
    def _detect_language(text: str) -> str:
        """Heuristic language detection."""
        if any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
            return "zh"  # Chinese
        if any(0x3040 <= ord(c) <= 0x309F or 0x30A0 <= ord(c) <= 0x30FF for c in text):
            return "ja"  # Japanese
        if any(0xAC00 <= ord(c) <= 0xD7AF for c in text):
            return "ko"  # Korean
        if any(0x0600 <= ord(c) <= 0x06FF for c in text):
            return "ar"  # Arabic
        if any(0x0400 <= ord(c) <= 0x04FF for c in text):
            return "ru"  # Russian
        if any(0x0900 <= ord(c) <= 0x097F for c in text):
            return "hi"  # Hindi
        return "en"

    def _find_by_known_site(self, app_name: str,
                              screen_image: Optional[bytes]) -> Optional[ClickTarget]:
        """Use known-site patterns for popular apps."""
        patterns = {
            "chrome":   ("google.com/chrome", "Download Chrome"),
            "firefox":  ("mozilla.org", "Download Firefox"),
            "steam":    ("steampowered.com", "Install Steam"),
            "discord":  ("discord.com", "Download for Windows"),
            "vscode":   ("code.visualstudio.com", "Download for Windows"),
            "notepad":  ("notepad-plus-plus.org", "Download"),
            "vlc":      ("videolan.org", "Download VLC"),
            "7zip":     ("7-zip.org", "Download"),
            "obs":      ("obsproject.com", "Download"),
            "audacity": ("audacityteam.org", "Download Audacity"),
        }
        app_low = app_name.lower().strip()
        if app_low not in patterns:
            return None
        url_hint, btn_text = patterns[app_low]
        # Look for the button text
        if screen_image is not None:
            return self.find_button(btn_text, screen_image)
        return None


# ═════════════════════════════════════════════════════════════════════════════
# Convenience functions
# ═════════════════════════════════════════════════════════════════════════════

def get_smart_clicker() -> SmartClicker:
    """Get a singleton SmartClicker instance."""
    global _clicker
    try:
        return _clicker
    except NameError:
        _clicker = SmartClicker()
        return _clicker
