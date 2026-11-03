"""SONIC AI — Capability Router.

Picks the best interaction tier for a given action, given current state.

Preference order (from spec §35):
    T1 native API   >  T2 DOM/ARIA  >  T3 UIA  >  T4 adapter  >
    T5 vision       >  T6 input fallback  >  T7 recovery

But ToolPerformanceMemory can override this order per-app if a lower tier
historically outperforms a higher one.

Public API:
    CapabilityRouter()
    .decide(action, state, app) -> CapabilityDecision
    .register_tier_driver(tier, driver)  # pluggable drivers
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

from .state import EnvironmentState, ApplicationContext, AppKind
from .actions import Action, ActionType, CapabilityTier
from .tool_memory import ToolPerformanceMemory


logger = logging.getLogger("sonic.capability_router")


# Driver callable signature:
#   driver(action, state, app) -> ActionResult
TierDriver = Callable[[Action, EnvironmentState, Optional[ApplicationContext]], "object"]


@dataclass
class CapabilityDecision:
    """What the router decided to use for this action."""

    tier: CapabilityTier = CapabilityTier.T6_INPUT_FALLBACK
    method: str = ""                       # driver name to call
    confidence: float = 1.0
    reason: str = ""
    fallback_chain: list[CapabilityTier] = field(default_factory=list)
    skip_tiers: list[CapabilityTier] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["fallback_chain"] = [t.value for t in self.fallback_chain]
        d["skip_tiers"] = [t.value for t in self.skip_tiers]
        return d


# ──────────────────────────────────────────────────────────────────────
# Default tier ladder
# ──────────────────────────────────────────────────────────────────────
DEFAULT_LADDER = [
    CapabilityTier.T1_NATIVE_API,
    CapabilityTier.T2_DOM_ARIA,
    CapabilityTier.T3_UIA,
    CapabilityTier.T4_ADAPTER,
    CapabilityTier.T5_VISION,
    CapabilityTier.T6_INPUT_FALLBACK,
    CapabilityTier.T7_RECOVERY,
]


class CapabilityRouter:
    """Chooses the right tier for each action."""

    def __init__(self, tool_memory: Optional[ToolPerformanceMemory] = None):
        self._drivers: dict[CapabilityTier, list[TierDriver]] = {
            t: [] for t in CapabilityTier
        }
        self._memory = tool_memory or ToolPerformanceMemory()
        self._method_names: dict[CapabilityTier, list[str]] = {
            t: [] for t in CapabilityTier
        }

    def register_tier_driver(self, tier: CapabilityTier,
                             driver: TierDriver, name: str = ""):
        self._drivers[tier].append(driver)
        self._method_names[tier].append(name or driver.__name__)

    # ── decision ──
    def decide(self, action: Action,
               state: EnvironmentState,
               app: Optional[ApplicationContext] = None) -> CapabilityDecision:
        app = app or (state.active_app if state else None)
        ladder = list(DEFAULT_LADDER)

        # Filter by app kind
        if app:
            ladder = self._filter_by_app(app, ladder)

        # Filter by action type
        ladder = self._filter_by_action(action, ladder)

        # ToolMemory may demote a high tier that historically fails for this app
        if app:
            ladder = self._memory.reorder_for_app(app.process_name, ladder)

        # Find first tier with a registered driver
        chosen = None
        for tier in ladder:
            if self._drivers.get(tier):
                chosen = tier
                break

        if chosen is None:
            chosen = CapabilityTier.T6_INPUT_FALLBACK  # always present (mouse/kbd)

        method_idx = 0
        if self._method_names.get(chosen):
            method_idx = min(len(self._method_names[chosen]) - 1, 0)

        fallback = [t for t in ladder if t != chosen]
        return CapabilityDecision(
            tier=chosen,
            method=self._method_names[chosen][method_idx] if self._method_names.get(chosen) else "mouse_input",
            confidence=1.0 if chosen in (CapabilityTier.T1_NATIVE_API,
                                          CapabilityTier.T2_DOM_ARIA,
                                          CapabilityTier.T3_UIA) else 0.7,
            reason=f"tier_ladder_pick({chosen.value})",
            fallback_chain=fallback,
        )

    def execute(self, decision: CapabilityDecision, action: Action,
                state: EnvironmentState,
                app: Optional[ApplicationContext] = None):
        """Run the driver for the chosen tier."""
        from .actions import ActionResult
        drivers = self._drivers.get(decision.tier, [])
        if not drivers:
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=f"no driver registered for tier {decision.tier.value}",
                error_class="execution",
                used_tier=decision.tier,
            )
        try:
            return drivers[0](action, state, app)
        except Exception as exc:  # pragma: no cover
            logger.exception("driver crashed")
            return ActionResult(
                action_id=action.action_id,
                success=False,
                error=str(exc),
                error_class="execution",
                used_tier=decision.tier,
            )

    # ── filters ──
    @staticmethod
    def _filter_by_app(app: ApplicationContext,
                       ladder: list[CapabilityTier]) -> list[CapabilityTier]:
        out = list(ladder)
        if app.kind != AppKind.BROWSER and CapabilityTier.T2_DOM_ARIA in out:
            out.remove(CapabilityTier.T2_DOM_ARIA)
        if app.kind != AppKind.WINDOWS_APP and CapabilityTier.T3_UIA in out:
            out.remove(CapabilityTier.T3_UIA)
        if not app.has_native_api and CapabilityTier.T1_NATIVE_API in out:
            out.remove(CapabilityTier.T1_NATIVE_API)
        return out

    @staticmethod
    def _filter_by_action(action: Action,
                          ladder: list[CapabilityTier]) -> list[CapabilityTier]:
        # Filesystem actions never need DOM/UIA/vision
        if action.action_type in (ActionType.FILE_OPEN, ActionType.FILE_SAVE,
                                  ActionType.FILE_MOVE, ActionType.FILE_COPY,
                                  ActionType.FILE_DELETE, ActionType.FILE_RENAME,
                                  ActionType.FILE_SEARCH, ActionType.EXECUTE_COMMAND):
            out = []
            for t in ladder:
                if t in (CapabilityTier.T1_NATIVE_API, CapabilityTier.T6_INPUT_FALLBACK,
                         CapabilityTier.T7_RECOVERY):
                    out.append(t)
            return out or [CapabilityTier.T6_INPUT_FALLBACK]
        # WAIT / OBSERVE / NOOP always just run inline
        if action.action_type in (ActionType.WAIT, ActionType.OBSERVE, ActionType.NOOP):
            return [CapabilityTier.T1_NATIVE_API]
        return ladder

    @property
    def memory(self) -> ToolPerformanceMemory:
        return self._memory
