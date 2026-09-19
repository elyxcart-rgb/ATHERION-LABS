"""SONIC AI — Autonomous Task Planner

Breaks complex multi-step tasks into executable plans.
The AI model calls this to plan, then executes each step via existing tools.

Usage:
    "Research laptops, compare prices, and recommend the best one"
    "Open Chrome, go to YouTube, play relaxing music, and lower volume"
    "Download this file, organize it, and create a backup"
"""
from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("TASK_PLANNER")

# ── Persistent storage ──────────────────────────────────────────────────
_TASKS_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "tasks"
_TASKS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class TaskStep:
    """A single step in a task plan."""
    step_id: int
    tool_name: str
    parameters: dict
    description: str = ""
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    depends_on: list[int] = field(default_factory=list)  # step IDs this depends on

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "description": self.description,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "depends_on": self.depends_on,
        }


@dataclass
class TaskPlan:
    """A complete task plan with multiple steps."""
    task_id: str
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    status: str = "planning"  # planning | ready | running | completed | failed | partial
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    current_step: int = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "current_step": self.current_step,
        }


class TaskPlanner:
    """Plans and tracks multi-step autonomous tasks."""

    def __init__(self):
        self._active_plans: dict[str, TaskPlan] = {}
        self._plan_history: list[dict] = []
        self._load_history()

    def _load_history(self) -> None:
        """Load past task history from disk."""
        history_file = _TASKS_DIR / "task_history.json"
        if history_file.exists():
            try:
                data = json.loads(history_file.read_text(encoding="utf-8"))
                self._plan_history = data.get("plans", [])[-50:]  # keep last 50
            except Exception:
                self._plan_history = []

    def _save_history(self) -> None:
        """Save task history to disk."""
        history_file = _TASKS_DIR / "task_history.json"
        try:
            history_file.write_text(
                json.dumps({"plans": self._plan_history[-50:]}, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save task history: {e}")

    def create_plan(self, goal: str, steps: list[dict]) -> dict:
        """
        Create a new task plan.

        Each step dict should have:
        - tool_name: str — which tool to call
        - parameters: dict — tool parameters
        - description: str — what this step does
        - depends_on: list[int] — step IDs this depends on (optional)
        """
        task_id = f"task_{int(time.time() * 1000)}"
        plan = TaskPlan(
            task_id=task_id,
            goal=goal,
            created_at=time.time(),
            status="ready",
        )

        for i, step_data in enumerate(steps):
            step = TaskStep(
                step_id=i + 1,
                tool_name=step_data.get("tool_name", ""),
                parameters=step_data.get("parameters", {}),
                description=step_data.get("description", ""),
                depends_on=step_data.get("depends_on", []),
            )
            plan.steps.append(step)

        self._active_plans[task_id] = plan

        return {
            "success": True,
            "task_id": task_id,
            "goal": goal,
            "total_steps": len(plan.steps),
            "steps": [s.to_dict() for s in plan.steps],
            "status": "ready",
        }

    def get_next_step(self, task_id: str) -> dict | None:
        """Get the next executable step (all dependencies met)."""
        plan = self._active_plans.get(task_id)
        if not plan:
            return None

        for step in plan.steps:
            if step.status != "pending":
                continue

            # Check dependencies
            deps_met = True
            for dep_id in step.depends_on:
                dep_step = next((s for s in plan.steps if s.step_id == dep_id), None)
                if dep_step and dep_step.status != "completed":
                    deps_met = False
                    break

            if deps_met:
                return step.to_dict()

        return None

    def mark_step_running(self, task_id: str, step_id: int) -> dict:
        """Mark a step as currently running."""
        plan = self._active_plans.get(task_id)
        if not plan:
            return {"error": "Plan not found"}

        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "running"
                step.started_at = time.time()
                plan.current_step = step_id
                plan.status = "running"
                return {"success": True, "step": step.to_dict()}

        return {"error": "Step not found"}

    def mark_step_complete(self, task_id: str, step_id: int, result: str = "") -> dict:
        """Mark a step as completed with its result."""
        plan = self._active_plans.get(task_id)
        if not plan:
            return {"error": "Plan not found"}

        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "completed"
                step.result = result
                step.completed_at = time.time()
                break

        # Check if plan is complete
        all_done = all(s.status in ("completed", "skipped") for s in plan.steps)
        any_failed = any(s.status == "failed" for s in plan.steps)

        if all_done:
            plan.status = "completed"
            plan.completed_at = time.time()
            self._archive_plan(plan)
        elif any_failed:
            plan.status = "partial"

        return {
            "success": True,
            "step": step.to_dict(),
            "plan_status": plan.status,
            "progress": f"{sum(1 for s in plan.steps if s.status in ('completed', 'skipped'))}/{len(plan.steps)}",
        }

    def mark_step_failed(self, task_id: str, step_id: int, error: str = "") -> dict:
        """Mark a step as failed."""
        plan = self._active_plans.get(task_id)
        if not plan:
            return {"error": "Plan not found"}

        for step in plan.steps:
            if step.step_id == step_id:
                step.status = "failed"
                step.error = error
                step.completed_at = time.time()
                break

        plan.status = "partial"
        return {"success": True, "step": step.to_dict(), "plan_status": "partial"}

    def get_plan_status(self, task_id: str) -> dict:
        """Get the current status of a plan."""
        plan = self._active_plans.get(task_id)
        if not plan:
            return {"error": "Plan not found"}

        completed = sum(1 for s in plan.steps if s.status in ("completed", "skipped"))
        failed = sum(1 for s in plan.steps if s.status == "failed")
        total = len(plan.steps)

        return {
            "task_id": task_id,
            "goal": plan.goal,
            "status": plan.status,
            "progress": f"{completed}/{total}",
            "completed": completed,
            "failed": failed,
            "total": total,
            "current_step": plan.current_step,
            "steps": [s.to_dict() for s in plan.steps],
        }

    def _archive_plan(self, plan: TaskPlan) -> None:
        """Archive completed plan to history."""
        self._plan_history.append(plan.to_dict())
        self._save_history()

    def list_active_plans(self) -> list[dict]:
        """List all active plans."""
        return [
            {
                "task_id": pid,
                "goal": p.goal,
                "status": p.status,
                "progress": f"{sum(1 for s in p.steps if s.status in ('completed', 'skipped'))}/{len(p.steps)}",
            }
            for pid, p in self._active_plans.items()
        ]

    def list_recent_history(self, limit: int = 10) -> list[dict]:
        """List recent completed plans."""
        return self._plan_history[-limit:]


# ── Singleton ───────────────────────────────────────────────────────────
_planner: TaskPlanner | None = None


def get_task_planner() -> TaskPlanner:
    global _planner
    if _planner is None:
        _planner = TaskPlanner()
    return _planner


# ── Tool Interface ──────────────────────────────────────────────────────

def task_planner(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Autonomous task planner tool.
    Creates, manages, and executes multi-step task plans.
    """
    planner = get_task_planner()
    action = parameters.get("action", "plan")

    if action == "plan":
        goal = parameters.get("goal", "")
        steps = parameters.get("steps", [])

        if not goal:
            return "Error: goal is required for planning"
        if not steps:
            return "Error: steps are required for planning"

        result = planner.create_plan(goal, steps)
        if result.get("success"):
            lines = [f"Task Plan Created: {result['task_id']}", f"Goal: {result['goal']}", f"Steps ({result['total_steps']}):"]
            for s in result["steps"]:
                lines.append(f"  {s['step_id']}. [{s['tool_name']}] {s['description']}")
            return "\n".join(lines)
        return f"Error creating plan: {result}"

    elif action == "next":
        task_id = parameters.get("task_id", "")
        if not task_id:
            # Get next step from any active plan
            for pid in planner._active_plans:
                task_id = pid
                break
        result = planner.get_next_step(task_id)
        if result:
            return json.dumps(result, indent=2)
        return "No pending steps in active plans"

    elif action == "start":
        task_id = parameters.get("task_id", "")
        step_id = parameters.get("step_id", 0)
        result = planner.mark_step_running(task_id, step_id)
        return json.dumps(result, indent=2)

    elif action == "complete":
        task_id = parameters.get("task_id", "")
        step_id = parameters.get("step_id", 0)
        result_text = parameters.get("result", "")
        result = planner.mark_step_complete(task_id, step_id, result_text)
        return json.dumps(result, indent=2)

    elif action == "fail":
        task_id = parameters.get("task_id", "")
        step_id = parameters.get("step_id", 0)
        error = parameters.get("error", "")
        result = planner.mark_step_failed(task_id, step_id, error)
        return json.dumps(result, indent=2)

    elif action == "status":
        task_id = parameters.get("task_id", "")
        if task_id:
            return json.dumps(planner.get_plan_status(task_id), indent=2)
        plans = planner.list_active_plans()
        if plans:
            return json.dumps(plans, indent=2)
        return "No active plans"

    elif action == "history":
        limit = parameters.get("limit", 10)
        history = planner.list_recent_history(limit)
        if history:
            return json.dumps(history, indent=2)
        return "No task history yet"

    return f"Unknown action: {action}. Use: plan, next, start, complete, fail, status, history"
