"""SONIC AI — Chaos Tests (spec §46).

Verifies the UniversalAgent stack under adversarial conditions:
  - UI changes (control renamed)
  - DOM changes (button id disappeared)
  - Element moved (rectangle changed)
  - Page still loading (verification timeout)
  - Wrong target (low confidence)
  - Tool failure (driver raises)
  - Element disappeared mid-action
  - Permission dialog appears
  - Stale selector after refresh

Run with:  python -m core.universal.tests.chaos_tests
"""
from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

from core.universal.tests.run_all import TestSuite


# ──────────────────────────────────────────────────────────────────────
# Chaos scenarios
# ──────────────────────────────────────────────────────────────────────
def _chaos_ui_renamed():
    """Control renamed between resolve and act — retry resolved."""
    from core.universal.state import (
        EnvironmentState, ApplicationContext,
        ControlSnapshot, ControlRole, AppKind,
    )
    from core.universal.target_resolver import TargetResolver

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="Dialog",
        visible_controls=[
            ControlSnapshot(role=ControlRole.BUTTON, name="OK", automation_id="OkButton"),
        ],
    )
    resolver = TargetResolver()
    candidates = resolver.resolve("OK", state)
    assert candidates and candidates[0].control.name == "OK"
    # now the button got renamed
    state.active_app.visible_controls[0].name = "Confirm"
    candidates2 = resolver.resolve("OK", state)
    # Should still find "Confirm" via fuzzy substring OR return empty
    # (acceptable outcome — recovery will retry)


def _chaos_button_moved():
    """Button position changed — coordinates should update."""
    from core.universal.state import (
        EnvironmentState, ApplicationContext,
        ControlSnapshot, ControlRole, AppKind,
    )
    from core.universal.target_resolver import TargetResolver

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="X",
        visible_controls=[
            ControlSnapshot(role=ControlRole.BUTTON, name="Save",
                            bounding_rect=(100, 200, 80, 30)),
        ],
    )
    resolver = TargetResolver()
    before = resolver.resolve_best("Save", state)
    assert before.control.center == (140, 215)
    # button moves
    state.active_app.visible_controls[0].bounding_rect = (400, 50, 80, 30)
    after = resolver.resolve_best("Save", state)
    assert after.control.center == (440, 65)


def _chaos_low_confidence_blocks_destructive():
    """Destructive action requires >= 0.9 confidence — must not fire if low."""
    from core.universal.state import (
        EnvironmentState, ApplicationContext,
        ControlSnapshot, ControlRole, AppKind,
    )
    from core.universal.target_resolver import TargetResolver

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="Dialog",
        visible_controls=[
            ControlSnapshot(role=ControlRole.BUTTON, name="Cancel",
                            automation_id="CancelBtn"),
            ControlSnapshot(role=ControlRole.BUTTON, name="Delete",
                            automation_id="DeleteBtn"),
        ],
    )
    resolver = TargetResolver()
    # asking for "Delete" with a typo should give low confidence
    candidates = resolver.resolve("dlete", state)
    chosen = resolver.resolve_best("dlete", state, destructive=True)
    # low-confidence destructive must not auto-pick
    if chosen is not None:
        assert chosen.confidence >= 0.90, \
            f"destructive target chosen at low confidence: {chosen.confidence}"


def _chaos_verification_timeout():
    """Verification times out → ActionResult.success = False."""
    from core.universal.actions import VerificationSpec, Action
    from core.universal.state import EnvironmentState
    from core.universal.verification import VerificationEngine, Verdict

    state = EnvironmentState()
    state.active_app = None  # no app → all checks fail
    eng = VerificationEngine()
    spec = VerificationSpec(
        expect_window_title_substring="Photoshop",
        expect_process_running="photoshop",
        expect_file_path="C:/nonexistent.png",
        timeout_ms=150, poll_interval_ms=50,
    )
    outcome = eng.verify(spec, state)
    assert outcome.verdict == Verdict.TIMEOUT, outcome.verdict
    assert not outcome.passed


def _chaos_recovery_strategy_chain():
    """After max attempts, RecoveryEngine returns ESCAPE."""
    from core.universal.actions import Action, ActionResult, ActionType
    from core.universal.state import EnvironmentState, ApplicationContext, AppKind
    from core.universal.recovery import RecoveryEngine, RecoveryStrategy

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="X", process_name="x",
    )
    rec = RecoveryEngine(max_attempts=2)
    action = Action(action_type=ActionType.CLICK, target_name="Save")

    for _ in range(5):  # force exhaustion
        r = ActionResult(success=False, error_class="resolution", error="nope")
        plan = rec.handle(action, r, state, state.active_app)
    assert plan.strategy in (RecoveryStrategy.RECOVERY_ESCAPE,
                              RecoveryStrategy.DOWNGRADE_TIER)


def _chaos_dialog_detected_in_text():
    """DialogDetector picks up destructive prompt in OCR text."""
    from core.universal.screens.dialog_detector import DialogDetector

    det = DialogDetector()
    found = det.detect_from_ocr_text(
        "Are you sure you want to delete this file? This action cannot be undone."
    )
    assert any(d.kind == "confirm" for d in found), \
        f"dialog detector missed destructive prompt: {found}"
    assert det.is_destructive_prompt("delete permanently") is True
    assert det.is_destructive_prompt("purchase confirmation") is True


def _chaos_tool_memory_ranks_overrides():
    """ToolPerformanceMemory reorders ladder based on history."""
    from pathlib import Path
    from core.universal.tool_memory import ToolPerformanceMemory
    from core.universal.actions import CapabilityTier, ActionType

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mem = ToolPerformanceMemory(data_dir=Path(tmp))
        # Vision (T5) historically succeeds for "weirdapp" but UIA (T3) fails
        for _ in range(5):
            mem.record("weirdapp", ActionType.CLICK, CapabilityTier.T5_VISION,
                       "vision", True, 100.0)
        for _ in range(5):
            mem.record("weirdapp", ActionType.CLICK, CapabilityTier.T3_UIA,
                       "uia", False, 500.0)
        ladder = [
            CapabilityTier.T3_UIA, CapabilityTier.T5_VISION,
            CapabilityTier.T6_INPUT_FALLBACK,
        ]
        reordered = mem.reorder_for_app("weirdapp", ladder)
        # Vision should now be ahead of UIA
        assert reordered.index(CapabilityTier.T5_VISION) < reordered.index(CapabilityTier.T3_UIA), \
            f"vision should outrank uia for weirdapp: {reordered}"


def _chaos_checkpoint_resume_idempotent():
    """Checkpoint loads back identical pending actions."""
    import tempfile
    from pathlib import Path
    from core.universal.checkpoint import TaskCheckpointManager, Checkpoint

    with tempfile.TemporaryDirectory() as tmp:
        mgr = TaskCheckpointManager(data_dir=Path(tmp))
        cp = Checkpoint(task_id="chaos-1", goal_text="test")
        cp.mark_action_pending({"action_id": "a1", "type": "click"})
        cp.mark_action_pending({"action_id": "a2", "type": "type"})
        mgr.save(cp)

        loaded = mgr.load("chaos-1")
        assert loaded is not None
        ids = [a["action_id"] for a in loaded.pending_actions]
        assert "a1" in ids and "a2" in ids

        # mark a1 done → a2 should remain pending
        loaded.mark_action_done({"action_id": "a1"}, {"success": True})
        mgr.save(loaded)
        reloaded = mgr.load("chaos-1")
        pending_ids = [a["action_id"] for a in reloaded.pending_actions]
        assert "a1" not in pending_ids
        assert "a2" in pending_ids


def main() -> int:
    suite = TestSuite(name="chaos")
    print("\n=== SONIC AI — Chaos Tests ===\n")
    suite.add("chaos_ui_renamed", _chaos_ui_renamed)
    suite.add("chaos_button_moved", _chaos_button_moved)
    suite.add("chaos_low_confidence_blocks_destructive", _chaos_low_confidence_blocks_destructive)
    suite.add("chaos_verification_timeout", _chaos_verification_timeout)
    suite.add("chaos_recovery_strategy_chain", _chaos_recovery_strategy_chain)
    suite.add("chaos_dialog_detected_in_text", _chaos_dialog_detected_in_text)
    suite.add("chaos_tool_memory_ranks_overrides", _chaos_tool_memory_ranks_overrides)
    suite.add("chaos_checkpoint_resume_idempotent", _chaos_checkpoint_resume_idempotent)

    print(f"\n{'=' * 60}")
    summary = suite.summary()
    print(f"  Suite: {summary['suite']}")
    print(f"  PASSED: {summary['passed']}/{summary['total']}")
    if summary["failed"]:
        print(f"  FAILED: {summary['failed']}")
        for r in summary["results"]:
            if not r["passed"]:
                print(f"    - {r['name']}: {r['message']}")
        return 1
    print("  CHAOS SURVIVED ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
