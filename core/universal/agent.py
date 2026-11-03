"""SONIC AI — Universal Agent (orchestrator).

The single entry point for goal-driven computer-use. Wraps:
  - UniversalRouter     — parses natural language → Route (action + args)
  - ActionBridge        — executes via existing SONIC actions
  - TargetResolver      — resolves UI targets
  - CapabilityRouter    — picks the right tier
  - VerificationEngine  — verifies postconditions
  - RecoveryEngine      — re-plans on failure
  - TaskCheckpointManager— persists progress
  - ToolPerformanceMemory— learns best tier per app

Public API:
    agent = UniversalAgent()
    result = agent.run("Open Chrome and search YouTube for OpenAI latest video")
    agent.cancel("task_id")
    agent.resume("task_id")
    agent.status()
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any

from .actions import (
    Action, ActionResult, ActionType, CapabilityTier,
    ActionValidator, VerificationSpec,
)
from .state import EnvironmentState, ApplicationContext
from .target_resolver import TargetResolver, ResolvedTarget
from .capability_router import CapabilityRouter, CapabilityDecision
from .verification import VerificationEngine, VerificationOutcome, Verdict
from .recovery import RecoveryEngine, RecoveryPlan, RecoveryStrategy
from .checkpoint import TaskCheckpointManager, Checkpoint
from .tool_memory import ToolPerformanceMemory
from .ue_goals import UnrealGoalInterpreter


logger = logging.getLogger("sonic.universal_agent")


class AgentStatus(str, Enum):
    PENDING = "pending"
    OBSERVING = "observing"
    PLANNING = "planning"
    RESOLVING = "resolving"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


@dataclass
class AgentGoal:
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    text: str = ""
    context: dict = field(default_factory=dict)
    max_actions: int = 50
    require_confirmation_for_destructive: bool = True


@dataclass
class AgentResult:
    goal_id: str = ""
    status: AgentStatus = AgentStatus.PENDING
    actions_attempted: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    recovery_attempts: int = 0
    final_message: str = ""
    steps: list[dict] = field(default_factory=list)
    started_at_ms: int = 0
    finished_at_ms: int = 0
    error: str = ""

    @property
    def duration_ms(self) -> float:
        if self.started_at_ms and self.finished_at_ms:
            return self.finished_at_ms - self.started_at_ms
        return 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ──────────────────────────────────────────────────────────────────────
# Optional SONIC bridge — only loaded if available, never blocks imports
# ──────────────────────────────────────────────────────────────────────
def _try_bridge():
    try:
        from ..action_bridge import ActionBridge
        return ActionBridge()
    except Exception:
        return None


def _try_router():
    try:
        from ..universal_router import UniversalRouter
        return UniversalRouter()
    except Exception:
        return None


def _try_screen_vision():
    try:
        from ..screen_vision import ScreenVision
        return ScreenVision()
    except Exception:
        return None


def _try_llm_chain():
    """Try to load the project's LLM provider chain (Gemini → OpenAI → Local)."""
    try:
        from ..providers import get_default_chain
        chain = get_default_chain()
        # Verify it's actually reachable (one cheap probe)
        try:
            chain.generate("ok", max_tokens=4)
            return chain
        except Exception:
            # Not reachable — return None so callers can fall back to heuristic
            return None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────
# The Agent
# ──────────────────────────────────────────────────────────────────────
class UniversalAgent:
    def __init__(self, data_dir: Optional[Any] = None,
                 bridge=None, router=None, screen_vision=None, llm=None):
        self.memory = ToolPerformanceMemory(data_dir=data_dir)
        self.capability_router = CapabilityRouter(tool_memory=self.memory)
        self.target_resolver = TargetResolver()
        self.verifier = VerificationEngine()
        self.recovery = RecoveryEngine(router=self.capability_router,
                                       verifier=self.verifier)
        self.checkpoints = TaskCheckpointManager(data_dir=data_dir)

        # SONIC integrations (graceful if missing)
        self._bridge = bridge if bridge is not None else _try_bridge()
        self._router = router if router is not None else _try_router()
        self._vision = screen_vision if screen_vision is not None else _try_screen_vision()
        self._llm = llm if llm is not None else _try_llm_chain()

        # register default fallback driver (T6 input fallback)
        self.capability_router.register_tier_driver(
            CapabilityTier.T6_INPUT_FALLBACK,
            self._exec_input_fallback,
            name="input_fallback",
        )
        self.capability_router.register_tier_driver(
            CapabilityTier.T1_NATIVE_API,
            self._exec_native_or_bridge,
            name="sonic_bridge",
        )

        # Task registry
        self._tasks: dict[str, dict] = {}
        self._cancel_flags: dict[str, bool] = {}

        # Domain-specific high-level goal interpreters
        self.ue_interpreter = UnrealGoalInterpreter()

    # ── public ──
    def run(self, goal_text: str,
            context: Optional[dict] = None) -> AgentResult:
        goal = AgentGoal(text=goal_text, context=context or {})
        return self._run_goal(goal)

    def run_unreal_op(self, op: str, **params) -> "object":
        """Execute a single Unreal editor operation directly through the adapter.

        Returns the AdapterResult dict. Useful for scripting:
            agent.run_unreal_op("import_fbx",
                                source_path="D:/models/hero.fbx",
                                destination="/Game/Meshes")
        """
        from .adapters.unreal import UnrealAdapter
        from .adapters.actions_compat import ActionType
        ad = UnrealAdapter()
        return ad.run_op(op, **params)

    def list_unreal_ops(self) -> list[str]:
        from .adapters.unreal import UnrealAdapter, UE_OPERATIONS
        return list(UE_OPERATIONS)

    def list_unreal_goals(self) -> list[str]:
        return self.ue_interpreter.catalog()

    def llm_status(self) -> dict:
        """Return LLM chain status + recent call stats."""
        if self._llm is None:
            return {"available": False,
                    "reason": "no LLM chain reachable (check API key)"}
        try:
            return {"available": True, **self._llm.stats()}
        except Exception as exc:
            return {"available": True, "stats_error": str(exc)}

    @staticmethod
    def _is_likely_unreal(text: str) -> bool:
        low = text.lower()
        return any(kw in low for kw in (
            "unreal", "blueprint", "uproject", "level", "actor",
            "static mesh", "skeletal mesh", "light", "material ",
            "texture", "niagara", "sequencer", "packag",
        ))

    def cancel(self, goal_id: str) -> bool:
        if goal_id in self._cancel_flags:
            self._cancel_flags[goal_id] = True
            return True
        return False

    def resume(self, goal_id: str) -> Optional[AgentResult]:
        cp = self.checkpoints.load(goal_id)
        if not cp or cp.status != "in_progress":
            return None
        return self._resume_checkpoint(cp)

    def status(self) -> dict:
        return {
            "active_tasks": sum(1 for t in self._tasks.values()
                                if t.get("status") not in (
                                    AgentStatus.COMPLETED.value,
                                    AgentStatus.FAILED.value,
                                    AgentStatus.CANCELLED.value)),
            "tasks": list(self._tasks.keys()),
            "tool_memory_records": len(self.memory._records),
            "pending_checkpoints": [cp.task_id for cp in self.checkpoints.list_pending()],
        }

    # ── core loop ──
    def _run_goal(self, goal: AgentGoal) -> AgentResult:
        result = AgentResult(
            goal_id=goal.goal_id,
            started_at_ms=int(time.time() * 1000),
        )
        self._tasks[goal.goal_id] = {"goal": goal, "status": AgentStatus.PLANNING.value}
        self._cancel_flags[goal.goal_id] = False

        cp = Checkpoint(task_id=goal.goal_id, goal_text=goal.text)
        try:
            # 1. Decompose goal → list of Actions via UniversalRouter
            actions = self._plan(goal, result, cp)
            if not actions:
                result.status = AgentStatus.FAILED
                result.error = "planner produced no actions"
                return result

            # 2. Execute actions in order
            for action in actions:
                if self._cancel_flags.get(goal.goal_id):
                    result.status = AgentStatus.CANCELLED
                    break
                if result.actions_attempted >= goal.max_actions:
                    result.status = AgentStatus.FAILED
                    result.error = f"max_actions={goal.max_actions} reached"
                    break

                ok = self._execute_action(action, goal, result, cp)
                if not ok and result.status == AgentStatus.PENDING:
                    # recovery escape set status already
                    pass

            if result.status in (AgentStatus.PENDING, AgentStatus.PLANNING,
                                  AgentStatus.OBSERVING, AgentStatus.EXECUTING):
                result.status = AgentStatus.COMPLETED
            result.final_message = self._compose_final_message(goal, result)
            cp.status = ("completed" if result.status == AgentStatus.COMPLETED
                         else result.status.value)

        except Exception as exc:
            logger.exception("universal_agent.run crashed")
            result.status = AgentStatus.FAILED
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            result.finished_at_ms = int(time.time() * 1000)
            cp.last_error = result.error
            self.checkpoints.save(cp)
            self._tasks[goal.goal_id]["status"] = result.status.value

        return result

    def _resume_checkpoint(self, cp: Checkpoint) -> AgentResult:
        result = AgentResult(
            goal_id=cp.task_id,
            started_at_ms=cp.created_at_ms,
        )
        self._cancel_flags[cp.task_id] = False
        # Re-queue pending actions
        for action_dict in cp.pending_actions:
            try:
                action = Action(**{
                    k: v for k, v in action_dict.items()
                    if k in Action.__dataclass_fields__
                })
            except Exception:
                continue
            self._execute_action(action,
                                 AgentGoal(goal_id=cp.task_id, text=cp.goal_text),
                                 result, cp)
        if result.status == AgentStatus.PENDING:
            result.status = AgentStatus.COMPLETED
        result.finished_at_ms = int(time.time() * 1000)
        return result

    # ── planning ──
    def _plan(self, goal: AgentGoal, result: AgentResult,
              cp: Checkpoint) -> list[Action]:
        result.status = AgentStatus.PLANNING
        self._tasks[goal.goal_id]["status"] = AgentStatus.PLANNING.value

        actions: list[Action] = []

        # 0. Unreal-specific high-level goal interpreter (most specific)
        try:
            ue_actions = self.ue_interpreter.interpret(
                goal.text, context=goal.context or {},
            )
            # Only adopt if interpreter returned real ops (not just noop)
            real = [a for a in ue_actions
                    if a.parameters.get("op")
                    and a.parameters.get("op") != "noop"]
            if real:
                actions.extend(real)
                for a in actions:
                    cp.mark_action_pending(a.to_dict())
                self.checkpoints.save(cp)
                return actions
        except Exception:
            logger.exception("ue_interpreter failed")

        # 0b. LLM-powered planning (when LLM available + goal is complex)
        if self._llm is not None:
            try:
                intent = self._llm_parse_intent(goal.text)
                if intent and not intent.get("needs_clarification"):
                    # Get available ops from the right adapter based on context
                    from .adapters.unreal import UE_OPERATIONS
                    ops = UE_OPERATIONS
                    # Detect non-UE goal (browser/file/etc.) — use universal ops
                    if self._router and not self._is_likely_unreal(goal.text):
                        from .actions import ActionType
                        ops = [a.value for a in ActionType]
                    llm_plan = self._llm_plan(goal.text, intent, ops)
                    if llm_plan:
                        llm_actions = []
                        for step in llm_plan:
                            llm_actions.append(Action(
                                action_type=ActionType.RUN_WORKFLOW,
                                target_name=step["op"],
                                parameters={"op": step["op"],
                                            **(step["params"] or {})},
                                preferred_tier=CapabilityTier.T1_NATIVE_API,
                                description=f"llm.plan→{step['op']}",
                            ))
                        if llm_actions:
                            actions.extend(llm_actions)
                            result.steps.append({
                                "phase": "llm_plan",
                                "intent": intent,
                                "actions_planned": len(llm_actions),
                            })
                            for a in actions:
                                cp.mark_action_pending(a.to_dict())
                            self.checkpoints.save(cp)
                            return actions
            except Exception:
                logger.exception("LLM planning failed")

        # 1. Try UniversalRouter for direct mapping (single-shot intent)
        if self._router is not None:
            try:
                route = self._router.route(goal.text)
                action = self._route_to_action(route)
                if action:
                    actions.append(action)
                    cp.mark_action_pending(action.to_dict())
                    self.checkpoints.save(cp)
                    return actions
            except Exception:
                logger.exception("UniversalRouter.route failed")

        # 2. Heuristic decomposition — tokenize, recognize verbs + objects
        actions.extend(self._heuristic_plan(goal.text))
        for a in actions:
            cp.mark_action_pending(a.to_dict())
        self.checkpoints.save(cp)
        return actions

    def _llm_parse_intent(self, goal_text: str) -> Optional[dict]:
        """Use the LLM to extract intent + entities from natural language.

        Returns parsed dict or None if LLM unavailable / failed.
        Output schema:
          {
            "intent": str,            # short action name
            "entities": dict,         # slot → value
            "needs_clarification": bool,
            "confidence": float,      # 0..1
          }
        """
        if self._llm is None:
            return None
        prompt = f"""You are a SONIC intent parser. Given a user goal in natural language, output ONLY a JSON object (no prose, no markdown) with fields:
  - intent: short action verb-noun (e.g. "send_message", "open_app", "search_web", "import_asset")
  - entities: dict of slot → value (e.g. {{"recipient": "Ahmed", "content_ref": "meeting_notes", "date_ref": "yesterday", "transport": "whatsapp"}})
  - needs_clarification: bool (true if the goal is ambiguous or missing critical info)
  - confidence: float 0..1 (how sure you are)

User goal: "{goal_text}"
"""
        try:
            r = self._llm.generate(prompt, max_tokens=400, temperature=0.2)
            text = (r.text or "").strip()
            # Strip code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            import json as _json
            data = _json.loads(text)
            if not isinstance(data, dict):
                return None
            data.setdefault("intent", "unknown")
            data.setdefault("entities", {})
            data.setdefault("needs_clarification", False)
            data.setdefault("confidence", 0.5)
            return data
        except Exception:
            logger.exception("LLM intent parse failed")
            return None

    def _llm_plan(self, goal_text: str, intent: dict,
                   available_ops: list[str]) -> Optional[list[dict]]:
        """Ask the LLM to produce a step-by-step plan using only listed ops.

        Returns list of {op, params} dicts, or None.
        """
        if self._llm is None:
            return None
        ops_list = "\n".join(f"  - {op}" for op in available_ops[:80])
        prompt = f"""You are the SONIC planner. Convert the user's goal into a sequence of CONCRETE editor operations.

Available Unreal-style ops (use only these):
{ops_list}

Goal: "{goal_text}"
Parsed intent: {intent}

Rules:
  - Each step is {{"op": "<one of the listed ops>", "params": {{ ... }} }}
  - Pick params that make sense (paths, names, locations, etc.)
  - Output ONLY a JSON array of steps, no prose, no markdown

Example output:
[
  {{"op": "new_level", "params": {{"level_path": "/Game/Maps/MyMap"}}}},
  {{"op": "save_current_level", "params": {{}}}}
]
"""
        try:
            r = self._llm.generate(prompt, max_tokens=800, temperature=0.2)
            text = (r.text or "").strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            import json as _json
            plan = _json.loads(text)
            if not isinstance(plan, list):
                return None
            # validate each step
            cleaned = []
            for step in plan:
                if isinstance(step, dict) and step.get("op") in available_ops:
                    cleaned.append({
                        "op": step["op"],
                        "params": step.get("params") or {},
                    })
            return cleaned or None
        except Exception:
            logger.exception("LLM plan synthesis failed")
            return None

    def _route_to_action(self, route) -> Optional[Action]:
        try:
            action_name = getattr(route, "action", None) or getattr(route, "intent", None) or ""
            params = getattr(route, "parameters", None) or getattr(route, "args", {}) or {}
            # Preserve destructive intent that the router may have flagged
            is_destructive = bool(getattr(route, "destructive", False) or
                                   action_name in {
                                       "delete", "delete_file", "remove",
                                       "send", "send_message", "send_email",
                                       "purchase", "pay", "format",
                                       "uninstall", "shutdown", "restart",
                                   })
            require_confirm = is_destructive
            action = Action(
                action_type=ActionType.RUN_WORKFLOW,
                target_name=action_name,
                parameters={"sonic_action": action_name, **(params if isinstance(params, dict) else {})},
                preferred_tier=CapabilityTier.T1_NATIVE_API,
                is_destructive=is_destructive,
                require_confirmation=require_confirm,
                description=f"router→{action_name}({params})",
            )
            return action
        except Exception:
            return None

    def _heuristic_plan(self, text: str) -> list[Action]:
        """Fallback decomposition when UniversalRouter doesn't match."""
        low = text.lower()
        actions: list[Action] = []

        # OPEN_APP patterns
        for kw in ("open chrome", "launch chrome", "start chrome"):
            if kw in low:
                actions.append(Action(
                    action_type=ActionType.OPEN_APP,
                    target_name="Google Chrome",
                    target_process="chrome",
                    preferred_tier=CapabilityTier.T1_NATIVE_API,
                    description="open Chrome",
                ))
                break
        for kw in ("open vscode", "launch vs code", "open vs code"):
            if kw in low:
                actions.append(Action(
                    action_type=ActionType.OPEN_APP,
                    target_name="Visual Studio Code",
                    target_process="Code",
                    preferred_tier=CapabilityTier.T1_NATIVE_API,
                ))
                break
        for kw in ("open settings", "windows settings"):
            if kw in low:
                actions.append(Action(
                    action_type=ActionType.OPEN_APP,
                    target_name="Settings",
                    target_process="SystemSettings",
                    preferred_tier=CapabilityTier.T1_NATIVE_API,
                ))
                break
        for kw in ("open file manager", "open explorer", "open files"):
            if kw in low:
                actions.append(Action(
                    action_type=ActionType.OPEN_APP,
                    target_name="File Explorer",
                    target_process="explorer",
                    preferred_tier=CapabilityTier.T1_NATIVE_API,
                ))
                break
        for kw in ("open whatsapp", "open whatsapp web"):
            if kw in low:
                actions.append(Action(
                    action_type=ActionType.OPEN_APP,
                    target_name="WhatsApp Web",
                    target_process="chrome",
                    preferred_tier=CapabilityTier.T1_NATIVE_API,
                ))
                break
        for kw in ("open notepad",):
            if kw in low:
                actions.append(Action(
                    action_type=ActionType.OPEN_APP,
                    target_name="Notepad",
                    target_process="notepad",
                    preferred_tier=CapabilityTier.T1_NATIVE_API,
                ))
                break

        # SEARCH in browser
        if "youtube" in low and ("search" in low or "find" in low or "play" in low):
            query = self._extract_quoted(text) or self._extract_after(text, "for")
            actions.append(Action(
                action_type=ActionType.NAVIGATE,
                target_url=f"https://www.youtube.com/results?search_query={query or ''}".replace(" ", "+"),
                preferred_tier=CapabilityTier.T2_DOM_ARIA,
                description=f"search youtube: {query}",
            ))
        elif "google" in low and ("search" in low or "find" in low):
            query = self._extract_quoted(text) or self._extract_after(text, "for")
            actions.append(Action(
                action_type=ActionType.NAVIGATE,
                target_url=f"https://www.google.com/search?q={(query or '').replace(' ', '+')}",
                preferred_tier=CapabilityTier.T2_DOM_ARIA,
            ))
        elif "search" in low:
            query = self._extract_quoted(text) or self._extract_after(text, "for")
            actions.append(Action(
                action_type=ActionType.NAVIGATE,
                target_url=f"https://www.google.com/search?q={(query or '').replace(' ', '+')}",
                preferred_tier=CapabilityTier.T2_DOM_ARIA,
            ))

        # FILE_OPS
        if "find" in low and ("file" in low or "pdf" in low or "document" in low):
            actions.append(Action(
                action_type=ActionType.FILE_SEARCH,
                target_text=text,
                preferred_tier=CapabilityTier.T1_NATIVE_API,
            ))
        if "move" in low and ("to" in low or "into" in low):
            actions.append(Action(
                action_type=ActionType.FILE_MOVE,
                target_text=text,
                preferred_tier=CapabilityTier.T1_NATIVE_API,
                is_destructive=True,
                require_confirmation=True,
            ))
        if "delete" in low or "remove" in low:
            actions.append(Action(
                action_type=ActionType.FILE_DELETE,
                target_text=text,
                preferred_tier=CapabilityTier.T1_NATIVE_API,
                is_destructive=True,
                require_confirmation=True,
            ))

        # SEND message
        if "send" in low and "message" in low:
            actions.append(Action(
                action_type=ActionType.RUN_WORKFLOW,
                target_name="send_message",
                parameters={"sonic_action": "send_message", "message": text},
                is_destructive=True,
                require_confirmation=True,
                preferred_tier=CapabilityTier.T1_NATIVE_API,
            ))

        # VOLUME / SETTINGS
        m = self._match_number_after(text, "volume")
        if m is not None:
            actions.append(Action(
                action_type=ActionType.RUN_WORKFLOW,
                target_name="set_volume",
                parameters={"sonic_action": "set_volume", "value": m},
                preferred_tier=CapabilityTier.T1_NATIVE_API,
            ))
        if "bluetooth" in low:
            actions.append(Action(
                action_type=ActionType.NAVIGATE,
                target_url="ms-settings:bluetooth",
                preferred_tier=CapabilityTier.T1_NATIVE_API,
            ))

        # If still nothing, fall back to ActionBridge as a single workflow call
        if not actions:
            actions.append(Action(
                action_type=ActionType.RUN_WORKFLOW,
                target_name="auto",
                parameters={"sonic_action": "auto", "raw_text": text},
                preferred_tier=CapabilityTier.T1_NATIVE_API,
                description=text,
            ))

        return actions

    # ── action execution with full recover loop ──
    def _execute_action(self, action: Action, goal: AgentGoal,
                        result: AgentResult, cp: Checkpoint) -> bool:
        result.actions_attempted += 1
        last_result: Optional[ActionResult] = None
        for attempt in range(3):
            # validation
            ok, err = ActionValidator.validate(action)
            if not ok:
                last_result = ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=err,
                    error_class="validation",
                    used_tier=action.preferred_tier,
                )
            else:
                # observe
                state = self._observe()
                # resolve
                if action.target_name and action.action_type not in (
                        ActionType.NAVIGATE, ActionType.OPEN_APP,
                        ActionType.FILE_OPEN, ActionType.FILE_SAVE,
                        ActionType.FILE_MOVE, ActionType.FILE_COPY,
                        ActionType.FILE_DELETE, ActionType.FILE_RENAME,
                        ActionType.FILE_SEARCH, ActionType.EXECUTE_COMMAND,
                        ActionType.RUN_WORKFLOW, ActionType.WAIT, ActionType.OBSERVE,
                        ActionType.NOOP, ActionType.SWITCH_TAB, ActionType.NEW_TAB,
                        ActionType.CLOSE_TAB, ActionType.CLOSE_APP):
                    resolved = self.target_resolver.resolve_best(
                        action.target_name, state, destructive=action.is_destructive,
                    )
                    if resolved and resolved.control:
                        action.coordinates = resolved.control.center
                        action.text = action.text or resolved.control.text
                        action.target_automation_id = resolved.control.automation_id
                        action.target_text = resolved.control.text
                        result.steps.append({
                            "phase": "resolve",
                            "method": resolved.method.value,
                            "confidence": resolved.confidence,
                            "reason": resolved.reason,
                        })
                    else:
                        last_result = ActionResult(
                            action_id=action.action_id,
                            success=False,
                            error=f"could not resolve target: {action.target_name}",
                            error_class="resolution",
                            used_tier=action.preferred_tier,
                        )

                if last_result is None or last_result.error_class != "resolution":
                    # capability decision
                    decision = self.capability_router.decide(action, state,
                                                              state.active_app if state else None)
                    # execute
                    t0 = time.time()
                    last_result = self.capability_router.execute(
                        decision, action, state, state.active_app if state else None,
                    )
                    duration_ms = (time.time() - t0) * 1000.0
                    last_result.used_tier = decision.tier
                    last_result.used_method = decision.method
                    last_result.duration_ms = duration_ms
                    last_result.action_id = action.action_id

                    # record tool memory
                    self.memory.record(
                        app=(state.active_app.process_name if state and state.active_app else ""),
                        action_type=action.action_type,
                        tier=decision.tier,
                        method=decision.method,
                        success=last_result.success,
                        duration_ms=duration_ms,
                    )

                    # verify
                    if last_result.success and action.verification:
                        v = self.verifier.verify(action.verification, state)
                        last_result.verification = v.to_dict()
                        if not v.passed:
                            last_result.success = False
                            last_result.error_class = "verification"
                            last_result.error = v.reason

            # record step
            step = {
                "phase": "execute",
                "attempt": attempt + 1,
                "action": action.to_dict(),
                "result": last_result.to_dict(),
            }
            result.steps.append(step)

            if last_result.success:
                result.actions_succeeded += 1
                cp.mark_action_done(action.to_dict(), last_result.to_dict())
                self.checkpoints.save(cp)
                # remember resolver success
                if action.target_name and state and state.active_app:
                    self.target_resolver.remember_success(
                        state.active_app.process_name,
                        action.target_name,
                        action.target_name,
                        resolved.method if 'resolved' in dir() else None,
                    )
                return True

            # failure → recovery
            result.actions_failed += 1
            result.recovery_attempts += 1
            plan = self.recovery.handle(action, last_result, state,
                                        state.active_app if state else None)
            result.steps.append({"phase": "recover", "plan": plan.to_dict()})
            if plan.strategy == RecoveryStrategy.RECOVERY_ESCAPE:
                result.status = AgentStatus.FAILED
                result.error = plan.reason
                return False
            if plan.strategy == RecoveryStrategy.USER_INTERVENTION:
                result.status = AgentStatus.AWAITING_CONFIRMATION
                result.final_message = plan.message_to_user
                return False
            if plan.wait_ms:
                time.sleep(plan.wait_ms / 1000.0)
            if plan.next_tier:
                action.preferred_tier = plan.next_tier
            last_result = None  # try again

        # out of attempts
        result.status = AgentStatus.FAILED
        result.error = f"action {action.action_id} failed after 3 attempts"
        return False

    # ── default drivers ──
    def _exec_input_fallback(self, action: Action, state: EnvironmentState,
                              app: Optional[ApplicationContext]) -> ActionResult:
        """T6 input-fallback driver — uses pyautogui if available."""
        try:
            import pyautogui  # type: ignore
        except ImportError:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error="pyautogui not installed",
                error_class="execution",
                used_tier=CapabilityTier.T6_INPUT_FALLBACK,
            )
        try:
            if action.action_type == ActionType.CLICK and action.coordinates != (0, 0):
                x, y = action.coordinates
                pyautogui.click(x, y)
            elif action.action_type == ActionType.TYPE:
                pyautogui.typewrite(action.text, interval=0.02)
            elif action.action_type == ActionType.KEYPRESS:
                pyautogui.hotkey(*action.keys)
            elif action.action_type == ActionType.MOUSE_MOVE:
                pyautogui.moveTo(*action.coordinates)
            elif action.action_type == ActionType.SCROLL:
                amt = action.scroll_amount or 3
                if action.scroll_direction in ("down", "up"):
                    pyautogui.scroll(amt if action.scroll_direction == "up" else -amt)
            elif action.action_type == ActionType.WAIT:
                time.sleep(max(0.0, float(action.parameters.get("seconds", 1.0))))
            elif action.action_type == ActionType.OBSERVE or action.action_type == ActionType.NOOP:
                pass
            else:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=f"input_fallback does not implement {action.action_type.value}",
                    error_class="execution",
                    used_tier=CapabilityTier.T6_INPUT_FALLBACK,
                )
            return ActionResult(
                action_id=action.action_id,
                success=True,
                used_tier=CapabilityTier.T6_INPUT_FALLBACK,
                used_method="pyautogui",
            )
        except Exception as exc:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=str(exc),
                error_class="execution",
                used_tier=CapabilityTier.T6_INPUT_FALLBACK,
            )

    def _exec_native_or_bridge(self, action: Action, state: EnvironmentState,
                                app: Optional[ApplicationContext]) -> ActionResult:
        """T1 native/bridge driver — delegates to ActionBridge if available."""
        t0 = time.time()
        # Try ActionBridge for RUN_WORKFLOW with sonic_action
        if action.action_type == ActionType.RUN_WORKFLOW:
            sonic_action = action.parameters.get("sonic_action")
            if sonic_action and self._bridge is not None:
                try:
                    args = {k: v for k, v in action.parameters.items()
                            if k != "sonic_action"}
                    text_result = self._bridge.execute_text(sonic_action, args)
                    return ActionResult(
                        action_id=action.action_id,
                        success=True,
                        used_tier=CapabilityTier.T1_NATIVE_API,
                        used_method=f"ActionBridge.{sonic_action}",
                        duration_ms=(time.time() - t0) * 1000.0,
                        raw_response=text_result,
                    )
                except Exception as exc:
                    return ActionResult(
                        action_id=action.action_id,
                        success=False,
                        error=str(exc),
                        error_class="execution",
                        used_tier=CapabilityTier.T1_NATIVE_API,
                    )

        # OPEN_APP via subprocess
        if action.action_type == ActionType.OPEN_APP and action.target_process:
            import subprocess
            try:
                subprocess.Popen([action.target_process + ".exe"]
                                 if not action.target_process.endswith(".exe")
                                 else [action.target_process])
                return ActionResult(
                    action_id=action.action_id,
                    success=True,
                    used_tier=CapabilityTier.T1_NATIVE_API,
                    used_method="subprocess",
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            except Exception as exc:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=str(exc),
                    error_class="execution",
                    used_tier=CapabilityTier.T1_NATIVE_API,
                )

        # NAVIGATE via webbrowser or default handler
        if action.action_type == ActionType.NAVIGATE and action.target_url:
            import webbrowser
            try:
                webbrowser.open(action.target_url)
                return ActionResult(
                    action_id=action.action_id,
                    success=True,
                    used_tier=CapabilityTier.T1_NATIVE_API,
                    used_method="webbrowser.open",
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            except Exception as exc:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=str(exc),
                    error_class="execution",
                    used_tier=CapabilityTier.T1_NATIVE_API,
                )

        # FILE_* via stdlib
        if action.action_type in (ActionType.FILE_SEARCH,):
            import subprocess
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Get-ChildItem -Path $HOME -Recurse -Filter '*{action.target_text or ''}*' -ErrorAction SilentlyContinue | Select-Object -First 5 FullName"],
                    capture_output=True, text=True, timeout=15,
                )
                return ActionResult(
                    action_id=action.action_id,
                    success=True,
                    used_tier=CapabilityTier.T1_NATIVE_API,
                    used_method="powershell_search",
                    duration_ms=(time.time() - t0) * 1000.0,
                    raw_response=out.stdout[:500],
                )
            except Exception as exc:
                return ActionResult(
                    action_id=action.action_id,
                    success=False,
                    error=str(exc),
                    error_class="execution",
                    used_tier=CapabilityTier.T1_NATIVE_API,
                )

        # Fallback: not implemented at this tier
        return ActionResult(
            action_id=action.action_id,
            success=False,
            error=f"native tier does not implement {action.action_type.value}",
            error_class="execution",
            used_tier=CapabilityTier.T1_NATIVE_API,
        )

    # ── observation ──
    def _observe(self) -> EnvironmentState:
        """Build a best-effort EnvironmentState from available SONIC signals."""
        state = EnvironmentState()
        try:
            import psutil  # type: ignore
            fg = None
            for proc in psutil.process_iter(['name', 'pid']):
                pass
            # best effort: take the active process via psutil
            try:
                fg = psutil.Process()
                state.running_processes = [
                    {"name": p.info['name'], "pid": p.info['pid']}
                    for p in psutil.process_iter(['name', 'pid'])
                ][:50]
            except Exception:
                pass
        except ImportError:
            pass
        if self._vision is not None:
            try:
                snap = self._vision.snapshot() if hasattr(self._vision, "snapshot") else None
                if snap:
                    # map snap fields to state
                    if isinstance(snap, dict):
                        if "window_title" in snap:
                            from .state import AppKind, ApplicationContext
                            ctx = ApplicationContext(
                                kind=AppKind.WINDOWS_APP,
                                name=snap.get("window_title", ""),
                                process_name=snap.get("process_name", ""),
                                window_title=snap.get("window_title", ""),
                            )
                            state.active_app = ctx
            except Exception:
                logger.exception("ScreenVision.snapshot failed")
        return state

    # ── helpers ──
    def _compose_final_message(self, goal: AgentGoal, result: AgentResult) -> str:
        if result.status == AgentStatus.COMPLETED:
            return (f"Goal '{goal.text}' completed. "
                    f"{result.actions_succeeded}/{result.actions_attempted} actions succeeded, "
                    f"{result.recovery_attempts} recovery events.")
        if result.status == AgentStatus.CANCELLED:
            return f"Goal '{goal.text}' cancelled by user."
        if result.status == AgentStatus.AWAITING_CONFIRMATION:
            return result.final_message or "Awaiting confirmation."
        return f"Goal '{goal.text}' failed: {result.error}"

    @staticmethod
    def _extract_quoted(text: str) -> str:
        import re
        m = re.search(r'"([^"]+)"', text) or re.search(r"'([^']+)'", text)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_after(text: str, keyword: str) -> str:
        idx = text.lower().find(keyword.lower())
        if idx < 0:
            return ""
        tail = text[idx + len(keyword):].strip(" :,-")
        # cut at first "and", "then", "."
        for sep in (" and ", " then ", ".", ","):
            if sep in tail.lower():
                tail = tail[:tail.lower().find(sep)]
        return tail.strip(" '\"")

    @staticmethod
    def _match_number_after(text: str, keyword: str) -> Optional[int]:
        import re
        m = re.search(rf"{keyword}\s*(?:to\s*)?(\d{{1,3}})", text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return None
        return None
