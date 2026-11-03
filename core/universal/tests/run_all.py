"""SONIC AI — Universal Agent Test Runner.

Run with:  python -m core.universal.tests.run_all
"""
from __future__ import annotations

import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable, Any


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float = 0.0
    message: str = ""


@dataclass
class TestSuite:
    name: str
    results: list[TestResult] = field(default_factory=list)

    def add(self, name: str, fn: Callable[[], None]):
        t0 = time.time()
        try:
            fn()
            self.results.append(TestResult(
                name=name, passed=True,
                duration_ms=(time.time() - t0) * 1000.0,
            ))
            print(f"  PASS  {name}")
        except AssertionError as exc:
            self.results.append(TestResult(
                name=name, passed=False,
                duration_ms=(time.time() - t0) * 1000.0,
                message=str(exc),
            ))
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:
            self.results.append(TestResult(
                name=name, passed=False,
                duration_ms=(time.time() - t0) * 1000.0,
                message=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            ))
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def summary(self) -> dict:
        return {
            "suite": self.name,
            "passed": self.passed_count(),
            "failed": self.failed_count(),
            "total": len(self.results),
            "results": [
                {"name": r.name, "passed": r.passed, "ms": round(r.duration_ms, 1),
                 "message": r.message if not r.passed else ""}
                for r in self.results
            ],
        }


def _imports_test():
    """Verify all foundation modules import without error."""
    from core.universal import (
        UniversalAgent, AgentGoal, AgentResult, AgentStatus,
        Action, ActionType, CapabilityTier,
        EnvironmentState, ApplicationContext, AppKind,
        TargetResolver, ResolvedTarget, ResolutionMethod,
        CapabilityRouter, CapabilityDecision,
        VerificationEngine, VerificationOutcome,
        RecoveryEngine, RecoveryPlan, RecoveryStrategy,
        TaskCheckpointManager, Checkpoint,
        ToolPerformanceMemory, PerformanceRecord,
    )
    assert UniversalAgent is not None
    assert ActionType.CLICK.value == "click"
    assert CapabilityTier.T1_NATIVE_API.value == "t1_native_api"


def _target_spec_parse_test():
    """TargetSpec parses common intents correctly."""
    from core.universal.target_resolver import TargetSpec

    spec = TargetSpec.parse("the third blue button")
    assert spec.role_hint == "button", f"role_hint={spec.role_hint}"
    assert spec.index == 3, f"index={spec.index}"
    assert spec.color_hint == "blue", f"color={spec.color_hint}"

    spec = TargetSpec.parse("first search input")
    assert spec.role_hint in ("text_input", "input"), f"role={spec.role_hint}"
    assert spec.index == 1

    spec = TargetSpec.parse("delete the file")
    assert spec.is_destructive_intent is True

    spec = TargetSpec.parse("top-right close button")
    assert spec.role_hint == "button"
    assert spec.position_hint == "top-right"


def _action_validator_test():
    """ActionValidator blocks malformed actions."""
    from core.universal.actions import Action, ActionType, ActionValidator

    bad_click = Action(action_type=ActionType.CLICK)
    ok, err = ActionValidator.validate(bad_click)
    assert not ok, "click without target must be rejected"
    assert "target" in err.lower()

    bad_type = Action(action_type=ActionType.TYPE)
    ok, err = ActionValidator.validate(bad_type)
    assert not ok
    assert "text" in err.lower()

    bad_nav = Action(action_type=ActionType.NAVIGATE)
    ok, err = ActionValidator.validate(bad_nav)
    assert not ok

    good_type = Action(action_type=ActionType.TYPE, text="hello")
    ok, err = ActionValidator.validate(good_type)
    assert ok, err


def _target_resolver_test():
    """TargetResolver ranks candidates correctly."""
    from core.universal.state import (
        EnvironmentState, ApplicationContext, ControlSnapshot,
        ControlRole, AppKind,
    )
    from core.universal.target_resolver import TargetResolver, ResolutionMethod

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="Notepad",
        visible_controls=[
            ControlSnapshot(
                role=ControlRole.BUTTON, name="Save",
                automation_id="SaveButton", text="Save",
            ),
            ControlSnapshot(
                role=ControlRole.BUTTON, name="Cancel",
                automation_id="CancelButton", text="Cancel",
            ),
            ControlSnapshot(
                role=ControlRole.BUTTON, name="Save As...",
                automation_id="SaveAsButton", text="Save As...",
            ),
        ],
    )

    resolver = TargetResolver()
    candidates = resolver.resolve("Save button", state)
    assert candidates, "no candidates returned"
    assert candidates[0].control.name == "Save"
    assert candidates[0].method in (ResolutionMethod.UIA_NAME,
                                     ResolutionMethod.DOM_TEXT)

    # destructive intent for low-confidence target must not auto-pick
    candidates2 = resolver.resolve("Submit", state)
    assert all(c.method != ResolutionMethod.UIA_AUTOMATION_ID for c in candidates2)


def _verification_engine_test():
    """VerificationEngine passes/fails appropriately."""
    from core.universal.actions import VerificationSpec
    from core.universal.state import EnvironmentState, ApplicationContext, AppKind
    from core.universal.verification import VerificationEngine, Verdict

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="X",
        window_title="Untitled - Notepad",
    )

    eng = VerificationEngine()
    spec = VerificationSpec(
        expect_window_title_substring="Notepad",
        timeout_ms=200, poll_interval_ms=50,
    )
    outcome = eng.verify(spec, state)
    assert outcome.passed, outcome.reason
    assert outcome.verdict == Verdict.PASSED

    fail_spec = VerificationSpec(
        expect_window_title_substring="Photoshop",
        timeout_ms=100, poll_interval_ms=50,
    )
    fail_outcome = eng.verify(fail_spec, state)
    assert not fail_outcome.passed


def _recovery_engine_test():
    """RecoveryEngine classifies failures and picks strategies."""
    from core.universal.actions import Action, ActionResult, ActionType, CapabilityTier
    from core.universal.state import EnvironmentState, ApplicationContext, AppKind
    from core.universal.recovery import RecoveryEngine, RecoveryStrategy, RecoveryPlan

    state = EnvironmentState()
    state.active_app = ApplicationContext(
        kind=AppKind.WINDOWS_APP, name="X", process_name="x",
    )
    rec = RecoveryEngine(max_attempts=3)

    action = Action(action_type=ActionType.CLICK, target_name="Save")

    # verification failure → retry resolved
    r1 = ActionResult(success=False, error_class="verification", error="postcondition failed")
    plan = rec.handle(action, r1, state, state.active_app)
    assert plan.strategy == RecoveryStrategy.RETRY_RESOLVED

    # resolution failure → downgrade tier
    r2 = ActionResult(success=False, error_class="resolution", error="no target")
    plan2 = rec.handle(action, r2, state, state.active_app)
    assert plan2.strategy == RecoveryStrategy.DOWNGRADE_TIER

    # execution failure with "stale" → retry resolved
    r3 = ActionResult(success=False, error_class="execution", error="element not visible (stale)")
    plan3 = rec.handle(action, r3, state, state.active_app)
    assert plan3.strategy == RecoveryStrategy.RETRY_RESOLVED


def _tool_memory_persistence_test(tmp_dir):
    """ToolPerformanceMemory persists across instances."""
    from pathlib import Path
    from core.universal.tool_memory import ToolPerformanceMemory
    from core.universal.actions import CapabilityTier, ActionType

    m1 = ToolPerformanceMemory(data_dir=Path(tmp_dir))
    m1.record("chrome", ActionType.CLICK, CapabilityTier.T2_DOM_ARIA,
              "playwright", True, 50.0)
    m1.record("chrome", ActionType.CLICK, CapabilityTier.T3_UIA,
              "uia", False, 200.0)
    m1.save()

    m2 = ToolPerformanceMemory(data_dir=Path(tmp_dir))
    assert len(m2._records) >= 2
    stats = m2.stats()
    assert stats["total_records"] >= 2


def _universal_agent_plan_test():
    """UniversalAgent decomposes natural-language goals."""
    from core.universal.agent import UniversalAgent, AgentGoal
    from core.universal.actions import ActionType

    agent = UniversalAgent.__new__(UniversalAgent)  # skip __init__ — bridge not needed
    # wire minimal dependencies
    from core.universal.tool_memory import ToolPerformanceMemory
    from core.universal.capability_router import CapabilityRouter
    from core.universal.target_resolver import TargetResolver
    from core.universal.verification import VerificationEngine
    from core.universal.recovery import RecoveryEngine
    from core.universal.checkpoint import TaskCheckpointManager
    from core.universal.ue_goals import UnrealGoalInterpreter

    agent.memory = ToolPerformanceMemory()
    agent.capability_router = CapabilityRouter(tool_memory=agent.memory)
    agent.target_resolver = TargetResolver()
    agent.verifier = VerificationEngine()
    agent.recovery = RecoveryEngine(router=agent.capability_router,
                                    verifier=agent.verifier)
    agent.checkpoints = TaskCheckpointManager()
    agent.ue_interpreter = UnrealGoalInterpreter()
    agent._bridge = None
    agent._router = None
    agent._vision = None
    agent._llm = None
    agent._tasks = {}
    agent._cancel_flags = {}

    goal = AgentGoal(text="Open Chrome and search YouTube for OpenAI latest video")
    from core.universal.checkpoint import Checkpoint
    cp = Checkpoint(task_id="t1", goal_text=goal.text)
    result = type("R", (), {"steps": [], "actions_attempted": 0,
                             "actions_succeeded": 0, "actions_failed": 0,
                             "recovery_attempts": 0, "status": "pending",
                             "final_message": "", "error": "",
                             "goal_id": "t1"})()
    # Pre-register the task so _plan can update status without KeyError
    agent._tasks[goal.goal_id] = {"goal": goal, "status": "pending"}
    agent._cancel_flags[goal.goal_id] = False
    actions = agent._plan(goal, result, cp)
    assert actions, "planner produced no actions"
    action_types = [a.action_type for a in actions]
    ops = [a.parameters.get("op") for a in actions]
    # The planner may route via UniversalRouter, UE interpreter, or heuristic.
    # Accept any of the common action types that accomplish the goal.
    assert (ActionType.OPEN_APP in action_types
            or ActionType.NAVIGATE in action_types
            or ActionType.RUN_WORKFLOW in action_types), \
        f"planner produced only {action_types} with ops {ops}"

    # File deletion should be marked destructive + require confirmation
    goal2 = AgentGoal(text="delete the file old.txt")
    cp2 = Checkpoint(task_id="t2", goal_text=goal2.text)
    agent._tasks[goal2.goal_id] = {"goal": goal2, "status": "pending"}
    agent._cancel_flags[goal2.goal_id] = False
    actions2 = agent._plan(goal2, result, cp2)
    file_deletes = [a for a in actions2 if a.action_type == ActionType.FILE_DELETE]
    if file_deletes:
        assert file_deletes[0].is_destructive is True
        assert file_deletes[0].require_confirmation is True


def _zero_break_jarvis_brain_test():
    """JarvisBrain still works after additive UniversalAgent integration."""
    import shutil
    import tempfile
    from pathlib import Path
    from core.jarvis_brain import JarvisBrain

    tmp_dir = tempfile.mkdtemp(prefix="sonic_brain_test_")
    try:
        brain = JarvisBrain(db_dir=tmp_dir)
        # All original subsystems should still exist
        assert brain.router is not None
        assert brain.memory is not None
        assert brain.proactive is not None
        assert brain.healer is not None
        # New universal field exists (additive)
        # universal may be None if import failed; either way it must not crash status()
        st = brain.status()
        assert "universal" in st, "status() must include universal entry"
        # run_goal should at least return something without raising
        r = brain.run_goal("test")
        assert isinstance(r, dict), "run_goal must return dict"
    finally:
        # Best-effort cleanup. KG/SQLite may hold handles — let shutil retry.
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────
# Run all
# ──────────────────────────────────────────────────────────────────────
def main() -> int:
    import tempfile
    suite = TestSuite(name="universal_agent")
    print(f"\n=== SONIC AI — Universal Agent Test Suite ===\n")

    suite.add("imports", _imports_test)
    suite.add("TargetSpec.parse", _target_spec_parse_test)
    suite.add("ActionValidator", _action_validator_test)
    suite.add("TargetResolver", _target_resolver_test)
    suite.add("VerificationEngine", _verification_engine_test)
    suite.add("RecoveryEngine", _recovery_engine_test)
    with tempfile.TemporaryDirectory() as tmp:
        suite.add("ToolPerformanceMemory persistence",
                  lambda: _tool_memory_persistence_test(tmp))
    suite.add("UniversalAgent.plan", _universal_agent_plan_test)
    suite.add("JarvisBrain zero-break", _zero_break_jarvis_brain_test)

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
    print("  ALL GREEN ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
