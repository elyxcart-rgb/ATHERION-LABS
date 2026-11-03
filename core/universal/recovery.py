"""SONIC AI — Recovery Engine.

When an action fails, the RecoveryEngine:
  1. Inspects the error class
  2. Re-observes the environment
  3. Classifies failure mode
  4. Selects an alternative capability tier (or strategy)
  5. Re-plans or retries safely
  6. Records the failure pattern in ToolPerformanceMemory

Strategies (from least to most aggressive):
  - RETRY_SAME         — retry identical action once (transient blip)
  - RETRY_RESOLVED     — re-resolve target then retry (UI may have moved)
  - DOWNGRADE_TIER     — try the next lower tier in the capability ladder
  - WAIT_AND_RETRY     — wait, re-observe, retry (page still loading)
  - RECOVERY_ESCAPE    — abort current goal safely, return partial result
  - USER_INTERVENTION  — pause and ask the user

Public API:
    RecoveryEngine(router, verifier, max_attempts=3)
    .handle(action, result, state, app) -> RecoveryPlan
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .actions import Action, ActionResult, ActionType, CapabilityTier
from .state import EnvironmentState, ApplicationContext
from .capability_router import CapabilityRouter, CapabilityDecision
from .verification import VerificationEngine


logger = logging.getLogger("sonic.recovery")


class RecoveryStrategy(str, Enum):
    NONE = "none"
    RETRY_SAME = "retry_same"
    RETRY_RESOLVED = "retry_resolved"
    DOWNGRADE_TIER = "downgrade_tier"
    WAIT_AND_RETRY = "wait_and_retry"
    ROLLBACK = "rollback"
    RECOVERY_ESCAPE = "recovery_escape"
    USER_INTERVENTION = "user_intervention"


@dataclass
class RecoveryPlan:
    strategy: RecoveryStrategy = RecoveryStrategy.NONE
    reason: str = ""
    attempts: int = 0
    next_tier: Optional[CapabilityTier] = None
    next_method: str = ""
    wait_ms: int = 0
    re_observe: bool = False
    message_to_user: str = ""
    fallback_action: Optional[Action] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        d["next_tier"] = self.next_tier.value if self.next_tier else None
        return d


class RecoveryEngine:
    def __init__(self, router: Optional[CapabilityRouter] = None,
                 verifier: Optional[VerificationEngine] = None,
                 max_attempts: int = 3):
        self._router = router or CapabilityRouter()
        self._verifier = verifier or VerificationEngine()
        self._max_attempts = max_attempts
        self._attempt_counts: dict[str, int] = {}

    def handle(self, action: Action, result: ActionResult,
               state: EnvironmentState,
               app: Optional[ApplicationContext] = None) -> RecoveryPlan:
        # bound attempts per action
        attempts = self._attempt_counts.get(action.action_id, 0) + 1
        self._attempt_counts[action.action_id] = attempts

        if attempts > self._max_attempts:
            return RecoveryPlan(
                strategy=RecoveryStrategy.RECOVERY_ESCAPE,
                reason=f"max_attempts({self._max_attempts}) exceeded",
                attempts=attempts,
                message_to_user="SONIC couldn't complete this step after multiple retries.",
            )

        err = (result.error or "").lower()
        err_class = (result.error_class or "").lower()

        # verification failure → retry resolved target
        if err_class == "verification":
            return RecoveryPlan(
                strategy=RecoveryStrategy.RETRY_RESOLVED,
                reason="postcondition failed; re-resolving target",
                attempts=attempts,
                re_observe=True,
            )

        # resolution failure → downgrade tier + wait
        if err_class == "resolution":
            decision = self._router.decide(action, state, app)
            lower = self._next_lower_tier(decision.tier)
            return RecoveryPlan(
                strategy=RecoveryStrategy.DOWNGRADE_TIER,
                reason=f"target not resolvable at {decision.tier.value}; downgrade to {lower.value if lower else 'NONE'}",
                attempts=attempts,
                next_tier=lower,
                re_observe=True,
                wait_ms=500,
            )

        # execution failure → check if transient
        if err_class == "execution":
            if any(k in err for k in ("timeout", "timed out", "loading", "busy")):
                return RecoveryPlan(
                    strategy=RecoveryStrategy.WAIT_AND_RETRY,
                    reason="transient: page/app busy",
                    attempts=attempts,
                    re_observe=True,
                    wait_ms=1500,
                )
            # element moved / stale → re-resolve
            if any(k in err for k in ("stale", "not visible", "not enabled", "intercepted",
                                       "not attached", "moved", "expired")):
                return RecoveryPlan(
                    strategy=RecoveryStrategy.RETRY_RESOLVED,
                    reason="element stale or moved",
                    attempts=attempts,
                    re_observe=True,
                )
            # unknown execution error → downgrade tier
            decision = self._router.decide(action, state, app)
            lower = self._next_lower_tier(decision.tier)
            if lower:
                return RecoveryPlan(
                    strategy=RecoveryStrategy.DOWNGRADE_TIER,
                    reason=f"execution failed; downgrading {decision.tier.value} → {lower.value}",
                    attempts=attempts,
                    next_tier=lower,
                    re_observe=True,
                )
            return RecoveryPlan(
                strategy=RecoveryStrategy.RECOVERY_ESCAPE,
                reason=f"execution failed with no lower tier: {result.error}",
                attempts=attempts,
            )

        # destructive confirmation refused
        if err_class == "confirmation":
            return RecoveryPlan(
                strategy=RecoveryStrategy.USER_INTERVENTION,
                reason="destructive action requires confirmation",
                attempts=attempts,
                message_to_user="SONIC wants to perform a destructive action. Confirm?",
            )

        # unknown
        return RecoveryPlan(
            strategy=RecoveryStrategy.RETRY_SAME,
            reason=f"unknown error; retrying once: {result.error}",
            attempts=attempts,
            re_observe=True,
            wait_ms=300,
        )

    def reset(self, action_id: str = ""):
        if action_id:
            self._attempt_counts.pop(action_id, None)
        else:
            self._attempt_counts.clear()

    @staticmethod
    def _next_lower_tier(tier: CapabilityTier) -> Optional[CapabilityTier]:
        ladder = [
            CapabilityTier.T1_NATIVE_API,
            CapabilityTier.T2_DOM_ARIA,
            CapabilityTier.T3_UIA,
            CapabilityTier.T4_ADAPTER,
            CapabilityTier.T5_VISION,
            CapabilityTier.T6_INPUT_FALLBACK,
            CapabilityTier.T7_RECOVERY,
        ]
        try:
            idx = ladder.index(tier)
        except ValueError:
            return None
        if idx + 1 < len(ladder):
            return ladder[idx + 1]
        return None
