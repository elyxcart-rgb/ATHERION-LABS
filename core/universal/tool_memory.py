"""SONIC AI — Tool Performance Memory.

Learns which interaction tier works best per (app, action_type). Reorders
the capability ladder based on historical success.

Records are in-memory and persist to JSON in the SONIC data dir.

Public API:
    ToolPerformanceMemory(data_dir=None)
    .record(app, action_type, tier, method, success, duration_ms)
    .reorder_for_app(app, ladder) -> ladder
    .best_tier(app, action_type) -> CapabilityTier
    .stats() -> dict
    .save() / .load()
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .actions import CapabilityTier, ActionType


logger = logging.getLogger("sonic.tool_memory")


@dataclass
class PerformanceRecord:
    app: str
    action_type: str
    tier: str
    method: str
    success: bool
    duration_ms: float
    ts: float = field(default_factory=time.time)


class ToolPerformanceMemory:
    """Cross-app capability performance tracker."""

    MAX_RECORDS = 5000

    def __init__(self, data_dir: Optional[Path] = None):
        self._records: list[PerformanceRecord] = []
        self._app_dir = data_dir or (Path.home() / ".sonic" / "memory")
        self._app_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._app_dir / "tool_memory.json"
        self._load()

    # ── public ──
    def record(self, app: str, action_type: ActionType,
               tier: CapabilityTier, method: str,
               success: bool, duration_ms: float):
        rec = PerformanceRecord(
            app=app or "unknown",
            action_type=action_type.value if hasattr(action_type, "value") else str(action_type),
            tier=tier.value if hasattr(tier, "value") else str(tier),
            method=method,
            success=success,
            duration_ms=duration_ms,
        )
        self._records.append(rec)
        if len(self._records) > self.MAX_RECORDS:
            self._records = self._records[-self.MAX_RECORDS:]
        self.save()

    def reorder_for_app(self, app: str,
                        ladder: list[CapabilityTier]) -> list[CapabilityTier]:
        """Move historically-best tiers to the front."""
        if not app:
            return ladder
        scores = self._score_per_tier(app)
        if not scores:
            return ladder
        # Sort ladder by (score desc, default-order asc)
        order = {t: i for i, t in enumerate(ladder)}
        return sorted(ladder,
                      key=lambda t: (-scores.get(t, 0.0), order.get(t, 99)))

    def best_tier(self, app: str, action_type: ActionType) -> Optional[CapabilityTier]:
        scores = self._score_per_tier(app, action_type)
        if not scores:
            return None
        best = max(scores.items(), key=lambda kv: kv[1])
        return best[0] if best[1] > 0 else None

    def stats(self) -> dict:
        per_app: dict[str, dict[str, dict[str, float]]] = {}
        for r in self._records:
            per_app.setdefault(r.app, {}).setdefault(r.action_type, {})
            d = per_app[r.app][r.action_type]
            d.setdefault("count", 0)
            d["count"] += 1
            d.setdefault("success", 0)
            d["success"] += 1 if r.success else 0
            d.setdefault("avg_ms", 0.0)
            d["avg_ms"] = (d["avg_ms"] + r.duration_ms) / 2
        for app, types in per_app.items():
            for action_type, d in types.items():
                d["success_rate"] = d["success"] / d["count"] if d["count"] else 0.0
        return {
            "total_records": len(self._records),
            "per_app": per_app,
        }

    # ── internal ──
    def _score_per_tier(self, app: str,
                        action_type: Optional[ActionType] = None
                        ) -> dict[CapabilityTier, float]:
        wanted_action = action_type.value if action_type and hasattr(action_type, "value") else None
        per_tier: dict[CapabilityTier, dict[str, float]] = defaultdict(
            lambda: {"success": 0, "total": 0}
        )
        for r in self._records:
            if r.app != app:
                continue
            if wanted_action and r.action_type != wanted_action:
                continue
            try:
                tier = CapabilityTier(r.tier)
            except ValueError:
                continue
            per_tier[tier]["total"] += 1
            if r.success:
                per_tier[tier]["success"] += 1
        scores: dict[CapabilityTier, float] = {}
        for tier, d in per_tier.items():
            if d["total"] == 0:
                continue
            scores[tier] = d["success"] / d["total"]
        return scores

    def save(self):
        try:
            data = [asdict(r) for r in self._records[-self.MAX_RECORDS:]]
            self._store_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            logger.exception("tool_memory.save failed")

    def _load(self):
        if not self._store_path.exists():
            return
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            self._records = [PerformanceRecord(**d) for d in data[-self.MAX_RECORDS:]]
        except Exception:
            logger.exception("tool_memory.load failed")
            self._records = []
