"""SONIC AI — Task Checkpoint Manager.

Persists the progress of long-running universal tasks so SONIC can:
  - resume after interruption (close/crash/restart)
  - cancel mid-way safely (user says "cancel that")
  - avoid duplicating completed steps on retry

Stored as JSON in the SONIC data dir. Each checkpoint contains:
  - task_id, goal_text
  - completed_actions
  - pending_actions
  - last_verified_state (serialized EnvironmentState)
  - last_error

Public API:
    TaskCheckpointManager(data_dir=None)
    .save(task_id, plan_state)
    .load(task_id) -> Checkpoint | None
    .delete(task_id)
    .list_pending() -> list[str]
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


logger = logging.getLogger("sonic.checkpoint")


@dataclass
class Checkpoint:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    goal_text: str = ""
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    updated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    status: str = "in_progress"   # in_progress / completed / failed / cancelled
    completed_actions: list[dict] = field(default_factory=list)
    pending_actions: list[dict] = field(default_factory=list)
    last_verified_state: dict = field(default_factory=dict)
    last_error: str = ""
    attempts_per_action: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        return cls(**d)

    def mark_action_done(self, action_dict: dict, result: dict):
        self.completed_actions.append({
            "action": action_dict,
            "result": result,
            "ts": int(time.time() * 1000),
        })
        # remove from pending
        aid = action_dict.get("action_id")
        self.pending_actions = [a for a in self.pending_actions if a.get("action_id") != aid]
        self.updated_at_ms = int(time.time() * 1000)

    def mark_action_pending(self, action_dict: dict):
        if not any(a.get("action_id") == action_dict.get("action_id")
                   for a in self.pending_actions):
            self.pending_actions.append(action_dict)
        self.updated_at_ms = int(time.time() * 1000)


class TaskCheckpointManager:
    def __init__(self, data_dir: Optional[Path] = None):
        self._dir = data_dir or (Path.home() / ".sonic" / "memory" / "checkpoints")
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: Checkpoint):
        try:
            path = self._dir / f"{checkpoint.task_id}.json"
            checkpoint.updated_at_ms = int(time.time() * 1000)
            path.write_text(json.dumps(checkpoint.to_dict(), indent=2),
                            encoding="utf-8")
        except Exception:
            logger.exception("checkpoint.save failed")

    def load(self, task_id: str) -> Optional[Checkpoint]:
        path = self._dir / f"{task_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Checkpoint.from_dict(data)
        except Exception:
            logger.exception("checkpoint.load failed")
            return None

    def delete(self, task_id: str):
        path = self._dir / f"{task_id}.json"
        try:
            if path.exists():
                path.unlink()
        except Exception:
            logger.exception("checkpoint.delete failed")

    def list_pending(self) -> list[Checkpoint]:
        out: list[Checkpoint] = []
        for p in self._dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                cp = Checkpoint.from_dict(data)
                if cp.status == "in_progress":
                    out.append(cp)
            except Exception:
                continue
        return out

    def list_all(self) -> list[Checkpoint]:
        out: list[Checkpoint] = []
        for p in self._dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                out.append(Checkpoint.from_dict(data))
            except Exception:
                continue
        return out
