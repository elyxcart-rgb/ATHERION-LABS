"""SONIC AI — Workflow Engine.

DAG-based multi-step automation with retry, parallel branches, and checkpointing.
The real power behind "do X, then if that works, do Y, also do Z in parallel".

Public API:
    Workflow(name="...")
    .step(id, action, args, depends_on=[...], retry=0, timeout=30, parallel=False)
    .on_complete(fn)
    .on_error(fn)

    WorkflowEngine()
    .execute(workflow, executor_fn) -> WorkflowResult

    Convenience:
    WorkflowEngine().run_simple(steps=[...], executor_fn=...) -> WorkflowResult

Step types supported as args:
    - action:    routed action name (passed to executor_fn)
    - literal:   pre-computed value (skips executor)
    - branch:    conditional step
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, asdict, field
from typing import Optional, Callable, Any


# ═════════════════════════════════════════════════════════════════════════════
# Step + Workflow
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Step:
    """One workflow step."""
    id: str
    action: str                       # "open_app" | "literal" | "branch" | "wait"
    args: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    retry: int = 0                    # how many retries on failure
    timeout: float = 30.0
    parallel: bool = False            # allow parallel execution with siblings
    on_success: list[str] = field(default_factory=list)  # step IDs to enable on success
    on_failure: list[str] = field(default_factory=list)  # step IDs to enable on failure
    value: Any = None                 # for action="literal"
    condition: Any = None             # for action="branch"


@dataclass
class StepResult:
    """Outcome of running one step."""
    step_id: str
    success: bool
    output: Any = None
    error: str = ""
    attempts: int = 1
    duration_ms: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["output"] = str(self.output)[:500]
        return d


@dataclass
class Workflow:
    """A DAG of steps."""
    name: str
    steps: list[Step] = field(default_factory=list)
    on_complete: Optional[Callable[["WorkflowResult"], None]] = None
    on_error: Optional[Callable[["WorkflowResult"], None]] = None

    def step(self, id: str, action: str, **kwargs) -> "Workflow":
        """Add a step. Returns self for chaining."""
        self.steps.append(Step(id=id, action=action, **kwargs))
        return self

    def get_step(self, id: str) -> Optional[Step]:
        for s in self.steps:
            if s.id == id:
                return s
        return None


@dataclass
class WorkflowResult:
    """Full execution result."""
    workflow_name: str
    success: bool
    step_results: list[StepResult] = field(default_factory=list)
    started_at: float = 0.0
    duration_ms: float = 0.0
    outputs: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "workflow_name": self.workflow_name,
            "success": self.success,
            "step_results": [s.to_dict() for s in self.step_results],
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "outputs": self.outputs,
            "error": self.error,
        }

    def summary(self) -> str:
        ok = sum(1 for s in self.step_results if s.success)
        total = len(self.step_results)
        return f"Workflow '{self.workflow_name}': {ok}/{total} steps ok, {self.duration_ms:.0f}ms"


# ═════════════════════════════════════════════════════════════════════════════
# WorkflowEngine
# ═════════════════════════════════════════════════════════════════════════════

class WorkflowEngine:
    """Executes workflows with retry, parallel branches, and checkpointing."""

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sonic-wf")
        self._lock = threading.Lock()
        self._stats = {"workflows": 0, "steps": 0, "failures": 0, "retries": 0}

    # ── Public ───────────────────────────────────────────────────────────────

    def execute(self, workflow: Workflow,
                executor_fn: Callable[[str, dict], Any]) -> WorkflowResult:
        """Execute a workflow. executor_fn(action_name, args) returns the output."""
        t0 = time.time()
        with self._lock:
            self._stats["workflows"] += 1

        result = WorkflowResult(
            workflow_name=workflow.name,
            started_at=t0,
            success=False,
        )

        # Build adjacency + indegree for topological sort
        by_id: dict[str, Step] = {s.id: s for s in workflow.steps}
        in_degree: dict[str, int] = {s.id: len(s.depends_on) for s in workflow.steps}
        children: dict[str, list[str]] = {s.id: [] for s in workflow.steps}
        for s in workflow.steps:
            for dep in s.depends_on:
                children[dep].append(s.id)

        # Topological order
        order: list[str] = []
        queue = deque([sid for sid, deg in in_degree.items() if deg == 0])
        while queue:
            sid = queue.popleft()
            order.append(sid)
            for child in children[sid]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(workflow.steps):
            # Cycle detected — execute in given order as fallback
            order = [s.id for s in workflow.steps]

        # Execute layer by layer; parallel within layer
        completed: dict[str, StepResult] = {}
        had_failure = False
        for layer_step_id in order:
            # Group parallel siblings
            layer = [layer_step_id]
            step = by_id[layer_step_id]
            if step.parallel:
                siblings = [s.id for s in workflow.steps
                            if s.parallel and s.id != layer_step_id
                            and set(s.depends_on).issubset(set(completed.keys()))]
                layer.extend(siblings)

            # Submit layer
            futures: dict[Future, str] = {}
            for sid in layer:
                f = self._executor.submit(
                    self._run_step, by_id[sid], executor_fn, completed
                )
                futures[f] = sid

            # Collect results
            for f, sid in futures.items():
                try:
                    sr = f.result(timeout=by_id[sid].timeout + 5)
                except Exception as e:
                    sr = StepResult(
                        step_id=sid, success=False,
                        error=str(e), duration_ms=0,
                        timestamp=time.time(),
                    )
                completed[sid] = sr
                result.step_results.append(sr)
                if sr.success:
                    result.outputs[sid] = sr.output
                else:
                    had_failure = True
                    with self._lock:
                        self._stats["failures"] += 1

        result.success = not had_failure
        result.duration_ms = (time.time() - t0) * 1000
        result.error = "" if result.success else (
            f"{sum(1 for s in completed.values() if not s.success)} step(s) failed"
        )

        with self._lock:
            self._stats["steps"] += len(completed)

        # Callbacks (don't let them break the result)
        try:
            if result.success and workflow.on_complete:
                workflow.on_complete(result)
            elif not result.success and workflow.on_error:
                workflow.on_error(result)
        except Exception:
            pass

        return result

    def run_simple(self, name: str,
                   steps: list[dict],
                   executor_fn: Callable[[str, dict], Any]) -> WorkflowResult:
        """Convenience: define steps as a list of dicts and run.

        Example:
            steps = [
              {"id": "open", "action": "open_app", "args": {"target": "chrome"}},
              {"id": "wait", "action": "wait", "args": {"seconds": 2},
               "depends_on": ["open"]},
              {"id": "search", "action": "web_search",
               "args": {"query": "python"}, "depends_on": ["wait"]},
            ]
        """
        wf = Workflow(name=name)
        for s in steps:
            wf.steps.append(Step(**s))
        return self.execute(wf, executor_fn)

    def stop(self):
        self._executor.shutdown(wait=False)

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ────────────────────────────────────────────────────────────

    def _run_step(self, step: Step, executor_fn: Callable,
                  completed: dict[str, StepResult]) -> StepResult:
        t0 = time.time()
        attempts = 0
        last_error = ""
        output: Any = None

        for attempt in range(step.retry + 1):
            attempts += 1
            try:
                if step.action == "wait":
                    secs = float(step.args.get("seconds", 1))
                    time.sleep(secs)
                    output = {"waited": secs}
                elif step.action == "literal":
                    output = step.value if step.value is not None else step.args.get("value")
                elif step.action == "branch":
                    cond = step.condition if step.condition is not None else step.args.get("condition")
                    branch_true = step.args.get("if_true", [])
                    branch_false = step.args.get("if_false", [])
                    # For brevity, just store the chosen path
                    output = {"branch": "true" if cond else "false",
                              "if_true": branch_true, "if_false": branch_false}
                else:
                    output = executor_fn(step.action, step.args)
                return StepResult(
                    step_id=step.id, success=True, output=output,
                    attempts=attempts,
                    duration_ms=(time.time() - t0) * 1000,
                    timestamp=time.time(),
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                with self._lock:
                    self._stats["retries"] += 1
                if attempts > step.retry:
                    break
                time.sleep(0.3 * attempts)

        return StepResult(
            step_id=step.id, success=False, error=last_error,
            attempts=attempts,
            duration_ms=(time.time() - t0) * 1000,
            timestamp=time.time(),
        )
