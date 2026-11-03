"""SONIC AI — Dialog / Popup Detector.

Recognizes modal dialogs and permission prompts so the UniversalAgent
can decide whether to:
  - dismiss (e.g. cookie banners)
  - confirm (e.g. Save As overwrite)
  - pause for user (e.g. 2FA, CAPTCHA)

Public API:
    DialogDetector()
    .detect_from_window_title(title) -> DetectedDialog | None
    .detect_from_ocr_text(text) -> list[DetectedDialog]
    .is_destructive_prompt(text) -> bool
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


logger = logging.getLogger("sonic.dialog")


@dataclass
class DetectedDialog:
    kind: str = "unknown"   # "permission" / "save" / "confirm" / "auth" / "cookie" / "error"
    title: str = ""
    text: str = ""
    severity: str = "info"  # "info" / "warning" / "dangerous"
    suggested_action: str = "review"  # "dismiss" / "confirm" / "review" / "abort"
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return asdict(self)


_TITLE_PATTERNS = [
    (re.compile(r"(?i)sign[\s_-]?in|log[\s_-]?in|2fa|two[\s_-]?factor|verify.*identity"), "auth", "warning", "review", 0.85),
    (re.compile(r"(?i)permission|access|allow|grant"), "permission", "warning", "review", 0.75),
    (re.compile(r"(?i)save\s*as|overwrite|replace existing"), "save", "warning", "confirm", 0.80),
    (re.compile(r"(?i)are you sure|confirm delete|delete permanently|this action cannot be undone"),
        "confirm", "dangerous", "review", 0.90),
    (re.compile(r"(?i)cookies?|gdpr|consent"), "cookie", "info", "dismiss", 0.70),
    (re.compile(r"(?i)error|failed|crash|exception"), "error", "dangerous", "review", 0.65),
]


_OCR_PATTERNS = [
    (re.compile(r"(?i)do you want to allow"), "permission", "warning", "review", 0.75),
    (re.compile(r"(?i)send (?:a )?message to"), "confirm", "info", "confirm", 0.70),
    (re.compile(r"(?i)are you sure you want to (?:delete|remove|format)"),
        "confirm", "dangerous", "review", 0.90),
    (re.compile(r"(?i)unsaved changes"), "save", "warning", "confirm", 0.80),
    (re.compile(r"(?i)(?:purchase|payment|billing)"), "purchase", "dangerous", "review", 0.95),
]


class DialogDetector:
    def detect_from_window_title(self, title: str) -> Optional[DetectedDialog]:
        if not title:
            return None
        for pat, kind, sev, sug, conf in _TITLE_PATTERNS:
            if pat.search(title):
                return DetectedDialog(
                    kind=kind, title=title, text="",
                    severity=sev, suggested_action=sug, confidence=conf,
                )
        return None

    def detect_from_ocr_text(self, text: str) -> list[DetectedDialog]:
        out = []
        if not text:
            return out
        for pat, kind, sev, sug, conf in _OCR_PATTERNS:
            for m in pat.finditer(text):
                snippet = text[max(0, m.start() - 30): m.end() + 30]
                out.append(DetectedDialog(
                    kind=kind, title="", text=snippet,
                    severity=sev, suggested_action=sug,
                    confidence=conf,
                ))
        return out

    def is_destructive_prompt(self, text: str) -> bool:
        destructive_kw = (
            "delete permanently", "format", "remove all",
            "purchase", "payment", "send message",
            "this action cannot be undone",
        )
        low = (text or "").lower()
        return any(k in low for k in destructive_kw)
