"""SONIC AI — Universal Computer-Use Engine.

Additive layer on top of SONIC's existing core/. Provides:

  UniversalAgent       — orchestrator (the single entry point for goal-driven tasks)
  Planner              — multi-step task planning with verification gates
  EnvironmentModel     — live state of active app, window, browser, controls
  TargetResolver       — resolves natural-language targets into ranked candidates
  CapabilityRouter     — picks the best capability tier per task
  VerificationEngine   — verifies postconditions, blocks false-success
  RecoveryEngine       — re-observes and replans when actions fail
  TaskCheckpointManager— persists progress so interrupted tasks can resume
  ToolPerformanceMemory— learns which capability works best per app

Integrates with existing SONIC modules WITHOUT duplicating them:
  - action_bridge     → ActionBridge.execute()
  - smart_clicker     → SmartClicker.find_button()
  - screen_vision     → ScreenVision.snapshot()
  - app_automator     → AppAutomator.run()
  - web_automator     → WebAutomator.run()
  - file_controller   → from actions/
  - browser_control   → from actions/
  - universal_router  → UniversalRouter.route() (intent parsing)
  - jarvis_brain      → JarvisBrain.think() (for ambient context)

Public API:
    from core.universal import UniversalAgent, AgentGoal, AgentResult
    agent = UniversalAgent()
    result = agent.run("Open Chrome and search YouTube for OpenAI latest video")
"""
from __future__ import annotations

from .state import (
    EnvironmentState,
    ApplicationContext,
    AppKind,
    BrowserContext,
    BrowserTab,
    ControlSnapshot,
    ControlRole,
    DisplayInfo,
)
from .actions import (
    Action,
    ActionResult,
    ActionType,
    CapabilityTier,
    VerificationSpec,
)
from .target_resolver import (
    TargetResolver,
    ResolvedTarget,
    ResolutionMethod,
)
from .capability_router import (
    CapabilityRouter,
    CapabilityDecision,
)
from .verification import VerificationEngine, VerificationOutcome
from .recovery import RecoveryEngine, RecoveryPlan, RecoveryStrategy
from .checkpoint import TaskCheckpointManager, Checkpoint
from .tool_memory import ToolPerformanceMemory, PerformanceRecord
from .ue_goals import UnrealGoalInterpreter, GOAL_CATALOG
from .agent import UniversalAgent, AgentGoal, AgentResult, AgentStatus

__all__ = [
    # state
    "EnvironmentState", "ApplicationContext", "AppKind",
    "BrowserContext", "BrowserTab", "ControlSnapshot",
    "ControlRole", "DisplayInfo",
    # actions
    "Action", "ActionResult", "ActionType", "CapabilityTier", "VerificationSpec",
    # target resolver
    "TargetResolver", "ResolvedTarget", "ResolutionMethod",
    # capability router
    "CapabilityRouter", "CapabilityDecision",
    # verification
    "VerificationEngine", "VerificationOutcome",
    # recovery
    "RecoveryEngine", "RecoveryPlan", "RecoveryStrategy",
    # checkpoint
    "TaskCheckpointManager", "Checkpoint",
    # tool memory
    "ToolPerformanceMemory", "PerformanceRecord",
    # Unreal-specific
    "UnrealGoalInterpreter", "GOAL_CATALOG",
    # main agent
    "UniversalAgent", "AgentGoal", "AgentResult", "AgentStatus",
]
