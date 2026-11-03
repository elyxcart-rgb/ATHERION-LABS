"""SONIC AI — Target Resolver.

Given a natural-language target ("the Save button", "the third row in the table",
"the blue download button"), produce a ranked list of candidate
ControlSnapshot objects across all available signals:

  1. UIA / accessibility tree  — semantic, highest confidence
  2. DOM / ARIA (browser)       — semantic
  3. App adapter registry       — app-specific semantics
  4. Screen vision + OCR        — visual fallback
  5. Historical success         — same target, same app, learned

Low-confidence destructive targets are NEVER auto-selected.

Public API:
    TargetResolver()
    .resolve(target_spec, state, app) -> list[ResolvedTarget]
    .resolve_best(target_spec, state, app) -> ResolvedTarget | None
    .find_text(text, state, fuzzy=True) -> list[ResolvedTarget]
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .state import EnvironmentState, ControlSnapshot, ControlRole, ApplicationContext


logger = logging.getLogger("sonic.target_resolver")


class ResolutionMethod(str, Enum):
    UIA_AUTOMATION_ID = "uia_automation_id"
    UIA_NAME = "uia_name"
    DOM_TEST_ID = "dom_test_id"
    DOM_ARIA_LABEL = "dom_aria_label"
    DOM_TEXT = "dom_text"
    DOM_ROLE = "dom_role"
    ADAPTER_DOMAIN = "adapter_domain"
    OCR_TEXT = "ocr_text"
    OCR_VISUAL = "ocr_visual"
    HISTORICAL = "historical"
    HEURISTIC = "heuristic"


@dataclass
class ResolvedTarget:
    """One candidate for what the user meant by their target."""

    control: Optional[ControlSnapshot] = None
    method: ResolutionMethod = ResolutionMethod.HEURISTIC
    confidence: float = 0.0
    reason: str = ""
    alternatives: list[str] = field(default_factory=list)

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.75

    @property
    def is_destructive_safe(self) -> bool:
        """Destructive actions require >= 0.9 confidence before auto-fire."""
        return self.confidence >= 0.90

    def to_dict(self) -> dict:
        d = asdict(self)
        d["method"] = self.method.value
        if self.control:
            d["control"] = self.control.to_dict()
        return d


# ──────────────────────────────────────────────────────────────────────
# TargetSpec — parsed natural-language target
# ──────────────────────────────────────────────────────────────────────
@dataclass
class TargetSpec:
    """Parsed natural-language target."""

    raw: str = ""
    text: str = ""                # literal text to find
    role_hint: str = ""           # "button" / "input" / "link"
    attribute_hint: str = ""      # "test-id" / "automation-id"
    index: Optional[int] = None   # "third", ordinal
    color_hint: str = ""          # "blue", "red", "green"
    position_hint: str = ""       # "top", "bottom-right", "modal"
    near_text: str = ""           # "next to the price"
    is_destructive_intent: bool = False

    @classmethod
    def parse(cls, raw: str) -> "TargetSpec":
        s = raw.strip()
        spec = cls(raw=s)

        # index: "first/second/third/Nth"
        ordinals = {"first": 1, "second": 2, "third": 3, "fourth": 4,
                    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8}
        for word, num in ordinals.items():
            if re.search(rf"\b{word}\b", s, re.IGNORECASE):
                spec.index = num
                break
        m = re.search(r"\b(\d+)(?:st|nd|rd|th)?\b", s)
        if m and spec.index is None:
            try:
                spec.index = int(m.group(1))
            except ValueError:
                pass

        # role
        role_map = {
            "button": "button", "btn": "button",
            "input": "text_input", "field": "text_input", "textbox": "text_input",
            "link": "link", "anchor": "link",
            "checkbox": "checkbox", "check": "checkbox",
            "radio": "radio",
            "dropdown": "select", "select": "select", "combobox": "select",
            "tab": "tab",
            "menu": "menu_item", "menu item": "menu_item",
            "icon": "icon", "image": "image", "img": "image",
            "row": "list_item", "list item": "list_item",
            "heading": "heading", "title": "heading",
            "dialog": "dialog", "modal": "dialog", "popup": "dialog",
            "video": "video", "player": "video",
            "iframe": "iframe",
        }
        low = s.lower()
        for kw, role in role_map.items():
            if kw in low:
                spec.role_hint = role
                break

        # color hint
        for color in ("blue", "red", "green", "yellow", "orange",
                      "purple", "pink", "cyan", "white", "black", "gray", "grey"):
            if color in low:
                spec.color_hint = color
                break

        # position
        for pos in ("top-right", "bottom-right", "top-left", "bottom-left",
                    "top", "bottom", "right", "left", "center", "middle"):
            if pos in low:
                spec.position_hint = pos
                break

        # destructive intent
        destructive_words = ("delete", "remove", "drop", "uninstall",
                             "send", "submit", "purchase", "pay",
                             "transfer", "format", "reset")
        spec.is_destructive_intent = any(w in low for w in destructive_words)

        # strip the role hint and ordinal words from raw text to get the actual text
        text = s
        for w in list(role_map.keys()) + list(ordinals.keys()):
            text = re.sub(rf"\b{w}\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+(?:st|nd|rd|th)?\b", "", text)
        text = re.sub(r"\b(the|a|an)\b", "", text, flags=re.IGNORECASE)
        text = text.strip(" \t\n'\",.?!")
        spec.text = text or s
        return spec


# ──────────────────────────────────────────────────────────────────────
# Resolver
# ──────────────────────────────────────────────────────────────────────
class TargetResolver:
    """Produces ranked candidates for a target."""

    def __init__(self):
        self._history: list[dict] = []  # past resolutions per (app, target_text)

    def resolve(self, target: str,
                state: EnvironmentState,
                app: Optional[ApplicationContext] = None) -> list[ResolvedTarget]:
        """Return ranked candidates (highest confidence first)."""
        spec = TargetSpec.parse(target)
        app = app or (state.active_app if state else None)

        candidates: list[ResolvedTarget] = []

        # 1. UIA / DOM candidates
        if app and app.visible_controls:
            for ctrl in app.visible_controls:
                conf, method, reason = self._score_control(spec, ctrl)
                if conf > 0.30:
                    candidates.append(ResolvedTarget(
                        control=ctrl,
                        method=method,
                        confidence=conf,
                        reason=reason,
                    ))

        # 2. OCR / visual regions (already present in visible_text_regions)
        if state and state.visible_text_regions:
            for region in state.visible_text_regions:
                conf, reason = self._score_ocr_region(spec, region)
                if conf > 0.40:
                    # synthesize a ControlSnapshot from OCR box
                    rect = region.get("bbox", (0, 0, 0, 0))
                    if isinstance(rect, dict):
                        rect = (rect.get("x", 0), rect.get("y", 0),
                                rect.get("w", 0), rect.get("h", 0))
                    if len(rect) == 4 and rect[2] > 0 and rect[3] > 0:
                        ctrl = ControlSnapshot(
                            role=ControlRole.BUTTON,
                            name=region.get("text", ""),
                            text=region.get("text", ""),
                            bounding_rect=tuple(rect),
                            confidence=conf,
                            source="ocr",
                        )
                        candidates.append(ResolvedTarget(
                            control=ctrl,
                            method=ResolutionMethod.OCR_TEXT,
                            confidence=conf * 0.85,  # downweight vs semantic
                            reason=reason,
                        ))

        # 3. Historical boost — same (app, target_text) before
        if app and app.process_name:
            for entry in self._history[-50:]:
                if (entry.get("app") == app.process_name
                        and entry.get("target_text", "").lower() == spec.text.lower()
                        and entry.get("success")):
                    for c in candidates:
                        if c.control and c.control.name == entry.get("control_name"):
                            c.confidence = min(1.0, c.confidence + 0.10)
                            c.reason += "; historical_match"
                            c.method = ResolutionMethod.HISTORICAL

        # 4. Apply ordinal index
        if spec.index is not None and spec.index > 0:
            # Filter to candidates with the same role hint, then pick the Nth
            role_matches = [c for c in candidates
                            if not spec.role_hint
                            or (c.control and c.control.role.value == spec.role_hint)]
            role_matches.sort(key=lambda c: (
                c.control.bounding_rect[1] if c.control else 0,
                c.control.bounding_rect[0] if c.control else 0,
            ))
            if 0 < spec.index <= len(role_matches):
                chosen = role_matches[spec.index - 1]
                # boost chosen; penalize others
                chosen.confidence = min(1.0, chosen.confidence + 0.20)
                chosen.reason += f"; ordinal_index={spec.index}"
                candidates = [chosen] + [c for c in candidates if c is not chosen]

        # Sort
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def resolve_best(self, target: str,
                     state: EnvironmentState,
                     app: Optional[ApplicationContext] = None,
                     destructive: bool = False) -> Optional[ResolvedTarget]:
        candidates = self.resolve(target, state, app)
        if not candidates:
            return None
        best = candidates[0]
        if destructive and not best.is_destructive_safe:
            logger.warning(
                "destructive target %r confidence=%.2f below safe threshold",
                target, best.confidence,
            )
            return None
        return best

    def find_text(self, text: str, state: EnvironmentState,
                  fuzzy: bool = True) -> list[ResolvedTarget]:
        spec = TargetSpec(text=text, raw=text, role_hint="")
        app = state.active_app if state else None
        results = []
        if app:
            for ctrl in app.visible_controls:
                haystack = (ctrl.name + " " + ctrl.text).lower()
                needle = text.lower()
                if (needle == haystack) or (fuzzy and needle in haystack):
                    results.append(ResolvedTarget(
                        control=ctrl,
                        method=ResolutionMethod.UIA_NAME,
                        confidence=0.92 if needle == haystack else 0.78,
                        reason=f"text_match({needle})",
                    ))
        results.sort(key=lambda r: r.confidence, reverse=True)
        return results

    def remember_success(self, app_name: str, target_text: str,
                          control_name: str, used_method: ResolutionMethod):
        self._history.append({
            "ts": time.time(),
            "app": app_name,
            "target_text": target_text,
            "control_name": control_name,
            "method": used_method.value,
            "success": True,
        })

    # ── internal scoring ──
    @staticmethod
    def _score_control(spec: TargetSpec,
                       ctrl: ControlSnapshot) -> tuple[float, ResolutionMethod, str]:
        score = 0.0
        method = ResolutionMethod.HEURISTIC
        reasons = []

        # automation_id exact match — strongest signal
        if spec.text and ctrl.automation_id and spec.text.lower() == ctrl.automation_id.lower():
            score = 0.98
            method = ResolutionMethod.UIA_AUTOMATION_ID
            reasons.append(f"automation_id_exact({ctrl.automation_id})")
        # name exact
        elif spec.text and ctrl.name and spec.text.lower() == ctrl.name.lower():
            score = 0.95
            method = ResolutionMethod.UIA_NAME
            reasons.append(f"name_exact({ctrl.name})")
        # text exact
        elif spec.text and ctrl.text and spec.text.lower() == ctrl.text.lower():
            score = 0.93
            method = ResolutionMethod.DOM_TEXT
            reasons.append(f"text_exact({ctrl.text})")
        # name substring
        elif spec.text and ctrl.name and spec.text.lower() in ctrl.name.lower():
            score = 0.80
            method = ResolutionMethod.UIA_NAME
            reasons.append(f"name_substring")
        # text substring
        elif spec.text and ctrl.text and spec.text.lower() in ctrl.text.lower():
            score = 0.75
            method = ResolutionMethod.DOM_TEXT
            reasons.append(f"text_substring")
        # role match (text irrelevant but role matches)
        elif spec.role_hint and ctrl.role.value == spec.role_hint:
            score = 0.40
            method = ResolutionMethod.DOM_ROLE
            reasons.append(f"role_only({ctrl.role.value})")

        # role bonus / penalty
        if spec.role_hint:
            if ctrl.role.value == spec.role_hint:
                score += 0.05
                reasons.append("role_bonus")
            elif ctrl.role.value != ControlRole.UNKNOWN.value:
                score -= 0.05
                reasons.append("role_mismatch")

        # placeholder for inputs
        if (ctrl.role == ControlRole.TEXT_INPUT
                and spec.text
                and spec.text.lower() in (ctrl.placeholder or "").lower()):
            score = max(score, 0.70)
            reasons.append("placeholder_match")

        return min(1.0, max(0.0, score)), method, ";".join(reasons)

    @staticmethod
    def _score_ocr_region(spec: TargetSpec, region: dict) -> tuple[float, str]:
        text = (region.get("text") or "").lower()
        if not spec.text:
            return 0.0, "no_spec_text"
        needle = spec.text.lower()
        if needle == text:
            return 0.85, "ocr_exact"
        if needle in text or text in needle:
            return 0.65, "ocr_partial"
        return 0.0, "ocr_no_match"
