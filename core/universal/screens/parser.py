"""SONIC AI — Screen Understanding.

Builds a structured SceneSnapshot from a screenshot + optional OCR
output. The parser does NOT re-do OCR — it consumes an existing OCR
list of {text, bbox, confidence} regions and labels each region by
likely role (button, input, heading, link) using simple heuristics.

This is intentionally lightweight (no model call) so the UniversalAgent
can call it on every observe().

Public API:
    ScreenUnderstanding()
    .parse(screenshot_path, ocr_regions=None) -> SceneSnapshot
    .parse_image(PIL.Image, ocr_regions=None) -> SceneSnapshot
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .dpi import MultiMonitor, DPIBridge
from .dialog_detector import DialogDetector, DetectedDialog


logger = logging.getLogger("sonic.screens")


@dataclass
class SceneElement:
    text: str = ""
    role_hint: str = ""        # "button" / "input" / "heading" / "link" / "text"
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    confidence: float = 0.0
    ocr_confidence: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SceneSnapshot:
    captured_at_ms: int = 0
    width_px: int = 0
    height_px: int = 0
    scale_factor: float = 1.0
    elements: list[SceneElement] = field(default_factory=list)
    text_regions: list[dict] = field(default_factory=list)
    detected_dialogs: list[DetectedDialog] = field(default_factory=list)
    screenshot_path: str = ""
    screenshot_signature: str = ""

    def to_dict(self) -> dict:
        return {
            "captured_at_ms": self.captured_at_ms,
            "width_px": self.width_px,
            "height_px": self.height_px,
            "scale_factor": self.scale_factor,
            "elements": [e.to_dict() for e in self.elements],
            "detected_dialogs": [d.to_dict() for d in self.detected_dialogs],
            "screenshot_path": self.screenshot_path,
            "screenshot_signature": self.screenshot_signature,
        }

    def find_text(self, needle: str, fuzzy: bool = True) -> list[SceneElement]:
        out = []
        needle_l = needle.lower()
        for e in self.elements:
            if not fuzzy and needle_l == e.text.lower():
                out.append(e)
            elif fuzzy and needle_l in e.text.lower():
                out.append(e)
        return out


class ScreenUnderstanding:
    BUTTON_KEYWORDS = {
        "ok", "cancel", "apply", "save", "open", "close", "submit",
        "yes", "no", "next", "back", "continue", "finish", "accept",
        "decline", "allow", "block", "install", "download", "update",
        "delete", "remove", "send", "reply", "forward", "share",
        "search", "browse", "upload", "login", "logout", "sign in",
        "sign up", "register", "subscribe", "buy", "purchase",
    }
    LINK_PATTERNS = ("http://", "https://", "www.")
    HEADING_HINTS = (":", "—", "?", "!")

    def __init__(self):
        self._dialog = DialogDetector()

    def parse(self, screenshot_path: str,
              ocr_regions: Optional[list[dict]] = None) -> SceneSnapshot:
        path = Path(screenshot_path)
        if not path.exists():
            return SceneSnapshot(screenshot_path=str(path))
        try:
            from PIL import Image  # type: ignore
            img = Image.open(path)
            return self.parse_image(img, ocr_regions=ocr_regions,
                                     screenshot_path=str(path))
        except ImportError:
            logger.warning("PIL not installed; cannot parse screenshot")
            return SceneSnapshot(screenshot_path=str(path))

    def parse_image(self, img, ocr_regions: Optional[list[dict]] = None,
                     screenshot_path: str = "") -> SceneSnapshot:
        scale = DPIBridge.get_scale_factor()
        snap = SceneSnapshot(
            captured_at_ms=int(time.time() * 1000),
            width_px=img.width,
            height_px=img.height,
            scale_factor=scale,
            screenshot_path=screenshot_path,
            screenshot_signature=self._perceptual_hash(img),
        )
        if ocr_regions:
            snap.text_regions = ocr_regions
            snap.elements = [self._classify_region(r) for r in ocr_regions]
            # detect dialogs from concatenated text
            joined = " ".join(r.get("text", "") for r in ocr_regions)
            snap.detected_dialogs = self._dialog.detect_from_ocr_text(joined)
        return snap

    @classmethod
    def _classify_region(cls, region: dict) -> SceneElement:
        text = (region.get("text") or "").strip()
        bbox = region.get("bbox") or region.get("rect") or (0, 0, 0, 0)
        if isinstance(bbox, dict):
            bbox = (bbox.get("x", 0), bbox.get("y", 0),
                    bbox.get("w", 0), bbox.get("h", 0))
        bbox = tuple(bbox or (0, 0, 0, 0))
        conf = float(region.get("confidence", 0.0) or 0.0)
        role = "text"
        low = text.lower().strip(" .,!?:;")

        if not text:
            role = "unknown"
        elif low in cls.BUTTON_KEYWORDS or (len(text) <= 20 and low in cls.BUTTON_KEYWORDS):
            role = "button"
        elif any(text.startswith(p) for p in cls.LINK_PATTERNS):
            role = "link"
        elif region.get("is_input") or region.get("role") == "text_input":
            role = "input"
        elif region.get("role") == "heading" or (len(text) < 60 and text.endswith(cls.HEADING_HINTS)):
            role = "heading"
        elif region.get("role") == "link":
            role = "link"
        elif len(text) <= 3:
            role = "icon"
        return SceneElement(
            text=text, role_hint=role,
            bbox=bbox,  # type: ignore
            confidence=conf, ocr_confidence=conf,
        )

    @staticmethod
    def _perceptual_hash(img, size: int = 16) -> str:
        try:
            from PIL import Image  # type: ignore
            small = img.convert("L").resize((size, size))
            data = list(small.getdata())
            avg = sum(data) / len(data)
            bits = "".join("1" if px >= avg else "0" for px in data)
            return f"{int(bits, 2):0>{size * size // 4}x}"
        except Exception:
            return ""
