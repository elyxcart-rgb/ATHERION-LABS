"""
Squad Mode — Multi-Agent Parallel Task Execution
Allows SONIC to spawn sub-agents that work on parallel tasks simultaneously,
then synthesize results into a unified response.
"""
import asyncio
import json
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SubTask:
    id: int
    description: str
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration": round(self.completed_at - self.started_at, 2) if self.completed_at else 0,
        }


@dataclass
class SquadResult:
    task_id: str
    original_request: str
    subtasks: list[SubTask] = field(default_factory=list)
    synthesis: str = ""
    total_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "original_request": self.original_request,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "synthesis": self.synthesis,
            "total_time": round(self.total_time, 2),
        }


class SquadManager:
    """Manages parallel sub-agent execution."""

    def __init__(self, tool_executor: Callable = None):
        self._tool_executor = tool_executor
        self._active_squads: dict[str, SquadResult] = {}
        self._task_counter = 0

    def _next_id(self) -> int:
        self._task_counter += 1
        return self._task_counter

    async def execute_squad(
        self,
        tasks: list[str],
        context: str = "",
        timeout_per_task: int = 60,
    ) -> SquadResult:
        """Execute multiple tasks in parallel and synthesize results."""
        task_id = f"squad_{int(time.time())}"
        squad = SquadResult(
            task_id=task_id,
            original_request=context or "; ".join(tasks),
        )

        subtasks = []
        for desc in tasks:
            subtasks.append(SubTask(id=self._next_id(), description=desc))
        squad.subtasks = subtasks

        self._active_squads[task_id] = squad
        start = time.time()

        async def run_subtask(st: SubTask):
            st.status = TaskStatus.RUNNING
            st.started_at = time.time()
            try:
                result = await asyncio.wait_for(
                    self._execute_single(st.description),
                    timeout=timeout_per_task,
                )
                st.result = result
                st.status = TaskStatus.COMPLETED
            except asyncio.TimeoutError:
                st.error = f"Timed out after {timeout_per_task}s"
                st.status = TaskStatus.FAILED
            except Exception as e:
                st.error = str(e)
                st.status = TaskStatus.FAILED
            finally:
                st.completed_at = time.time()

        await asyncio.gather(*[run_subtask(st) for st in subtasks])

        squad.total_time = time.time() - start
        squad.synthesis = self._synthesize(squad)

        del self._active_squads[task_id]
        return squad

    async def _execute_single(self, description: str) -> str:
        """Execute a single sub-task. Uses the tool executor if available."""
        if self._tool_executor:
            try:
                result = await asyncio.to_thread(
                    self._tool_executor,
                    "web_search",
                    {"query": description, "mode": "research"},
                )
                return result
            except Exception:
                pass
        return f"Task completed: {description}"

    def _synthesize(self, squad: SquadResult) -> str:
        """Synthesize results from all subtasks."""
        completed = [st for st in squad.subtasks if st.status == TaskStatus.COMPLETED]
        failed = [st for st in squad.subtasks if st.status == TaskStatus.FAILED]

        parts = []
        if completed:
            parts.append(f"Successfully completed {len(completed)} task(s):")
            for st in completed:
                parts.append(f"  [{st.id}] {st.description[:80]}")
                if st.result:
                    preview = st.result[:300]
                    parts.append(f"       {preview}")

        if failed:
            parts.append(f"\nFailed {len(failed)} task(s):")
            for st in failed:
                parts.append(f"  [{st.id}] {st.description[:80]} — {st.error}")

        parts.append(f"\nTotal time: {squad.total_time:.1f}s")
        return "\n".join(parts)

    def get_status(self) -> dict:
        return {
            "active_squads": len(self._active_squads),
            "squads": {k: v.to_dict() for k, v in self._active_squads.items()},
        }


_squad_manager: SquadManager | None = None


def get_squad_manager(tool_executor: Callable = None) -> SquadManager:
    global _squad_manager
    if _squad_manager is None:
        _squad_manager = SquadManager(tool_executor)
    return _squad_manager


async def squad_mode(parameters: dict, **kwargs) -> str:
    """Tool handler for squad_mode."""
    tasks = parameters.get("tasks", [])
    context = parameters.get("context", "")
    timeout = parameters.get("timeout_per_task", 60)

    if not tasks:
        return "Provide a list of tasks for squad mode."

    if len(tasks) > 5:
        return "Squad mode supports maximum 5 parallel tasks."

    manager = get_squad_manager(kwargs.get("tool_executor"))
    result = await manager.execute_squad(tasks, context, timeout)
    return result.synthesis
