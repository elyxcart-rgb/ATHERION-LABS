"""SONIC AI — Verification Engine.

Verifies the postcondition of every executed action. Blocks false-success
reports. If postcondition fails, marks ActionResult.success=False so the
RecoveryEngine can take over.

Checks supported:
  - expect_url_substring        — current browser URL contains substring
  - expect_window_title_substring — foreground window title contains substring
  - expect_control_name         — a control with this name is visible+enabled
  - expect_text_present         — OCR/DOM shows this text
  - expect_file_path            — file exists at this path
  - expect_process_running      — process with this name is in running list
  - expect_volume               — system volume equals this value (0-100)
  - custom_check                — name of a registered check function

Public API:
    VerificationEngine()
    .register_check(name, fn)
    .verify(spec, state) -> VerificationOutcome
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from .actions import VerificationSpec
from .state import EnvironmentState


logger = logging.getLogger("sonic.verification")


class Verdict(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class VerificationOutcome:
    verdict: Verdict = Verdict.SKIPPED
    checked_spec: Optional[VerificationSpec] = None
    actual: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    reason: str = ""
    duration_ms: float = 0.0
    attempts: int = 0

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.PASSED

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


class VerificationEngine:
    """Postcondition checker."""

    def __init__(self):
        self._custom: dict[str, Callable[[VerificationSpec, EnvironmentState], tuple[bool, str]]] = {}
        self._register_defaults()

    def register_check(self, name: str,
                       fn: Callable[[VerificationSpec, EnvironmentState], tuple[bool, str]]):
        self._custom[name] = fn

    def verify(self, spec: Optional[VerificationSpec],
               state: EnvironmentState) -> VerificationOutcome:
        if spec is None:
            return VerificationOutcome(verdict=Verdict.SKIPPED, reason="no_spec")

        deadline = time.time() + (spec.timeout_ms / 1000.0)
        attempts = 0
        last_reason = ""
        while time.time() < deadline:
            attempts += 1
            outcome = self._check_once(spec, state)
            if outcome.passed:
                outcome.attempts = attempts
                return outcome
            last_reason = outcome.reason
            time.sleep(max(0.05, spec.poll_interval_ms / 1000.0))
        return VerificationOutcome(
            verdict=Verdict.TIMEOUT,
            checked_spec=spec,
            reason=f"timeout after {attempts} attempts: {last_reason}",
            attempts=attempts,
            duration_ms=spec.timeout_ms,
        )

    # ── internal ──
    def _check_once(self, spec: VerificationSpec,
                    state: EnvironmentState) -> VerificationOutcome:
        checks = []

        if spec.expect_url_substring:
            url = (state.browser.page_url if state.browser else "").lower()
            ok = spec.expect_url_substring.lower() in url
            checks.append((ok, "url", spec.expect_url_substring, url))

        if spec.expect_window_title_substring:
            title = (state.active_app.window_title if state.active_app else "").lower()
            ok = spec.expect_window_title_substring.lower() in title
            checks.append((ok, "window_title", spec.expect_window_title_substring, title))

        if spec.expect_control_name:
            ctrl = state.find_control_by_name(spec.expect_control_name) if state else None
            ok = ctrl is not None and ctrl.is_enabled and ctrl.is_visible
            actual = ctrl.to_dict() if ctrl else None
            checks.append((ok, "control_name", spec.expect_control_name,
                          actual.get("name") if actual else ""))

        if spec.expect_text_present:
            text = ""
            if state and state.visible_text_regions:
                text = " ".join(r.get("text", "") for r in state.visible_text_regions).lower()
            ok = spec.expect_text_present.lower() in text
            checks.append((ok, "text_present", spec.expect_text_present, text[:80]))

        if spec.expect_file_path:
            ok = Path(spec.expect_file_path).exists()
            checks.append((ok, "file_path", spec.expect_file_path, str(Path(spec.expect_file_path).exists())))

        if spec.expect_process_running:
            name = spec.expect_process_running.lower()
            ok = any(p.get("name", "").lower() == name
                     for p in state.running_processes) if state else False
            checks.append((ok, "process_running", spec.expect_process_running,
                          [p.get("name") for p in state.running_processes][:5]))

        if spec.expect_volume is not None:
            # Defer to system volume query — caller may pre-populate
            actual = state.active_app.attributes.get("volume") if state and state.active_app else None
            ok = actual == spec.expect_volume
            checks.append((ok, "volume", spec.expect_volume, actual))

        if spec.custom_check:
            fn = self._custom.get(spec.custom_check)
            if not fn:
                return VerificationOutcome(
                    verdict=Verdict.ERROR,
                    checked_spec=spec,
                    reason=f"unknown custom_check: {spec.custom_check}",
                )
            try:
                ok, reason = fn(spec, state)
            except Exception as exc:
                return VerificationOutcome(
                    verdict=Verdict.ERROR,
                    checked_spec=spec,
                    reason=f"custom_check raised: {exc}",
                )
            checks.append((ok, spec.custom_check, "", reason))

        if not checks:
            return VerificationOutcome(verdict=Verdict.SKIPPED, reason="empty_spec")

        failed = [c for c in checks if not c[0]]
        if not failed:
            return VerificationOutcome(
                verdict=Verdict.PASSED,
                checked_spec=spec,
                expected={c[1]: c[2] for c in checks},
                actual={c[1]: c[3] for c in checks},
                reason="all_checks_passed",
            )
        return VerificationOutcome(
            verdict=Verdict.FAILED,
            checked_spec=spec,
            expected={c[1]: c[2] for c in checks},
            actual={c[1]: c[3] for c in checks},
            reason=f"failed: {failed[0][1]}",
        )

    def _register_defaults(self):
        # placeholder — real checks use state already
        pass
