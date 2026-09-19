"""SONIC AI — Tool Chaining Engine

Chains multiple tool calls together in a single flow.
Result of Tool A becomes input of Tool B automatically.

Usage:
    "Search for Python tutorials, download the first one, and save it to Documents"
    "Open Chrome, go to YouTube, play music, and lower volume"
    "Find my largest files, delete the old ones, and organize the rest"
"""
from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("TOOL_CHAIN")


@dataclass
class ChainStep:
    """A single step in a tool chain."""
    step_id: int
    tool_name: str
    parameters: dict
    description: str = ""
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: str = ""
    error: str = ""
    output_key: str = ""  # key to reference this step's output in next steps
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "description": self.description,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "output_key": self.output_key,
        }


@dataclass
class ToolChain:
    """A chain of tool calls that execute sequentially."""
    chain_id: str
    description: str
    steps: list[ChainStep] = field(default_factory=list)
    status: str = "ready"  # ready | running | completed | failed | partial
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    current_step: int = 0
    context: dict = field(default_factory=dict)  # shared context between steps

    def to_dict(self) -> dict:
        return {
            "chain_id": self.chain_id,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status,
            "current_step": self.current_step,
            "context": self.context,
        }


class ToolChainEngine:
    """Executes chains of tool calls with automatic result passing."""

    def __init__(self):
        self._active_chains: dict[str, ToolChain] = {}
        self._chain_history: list[dict] = []
        self._tool_executor: Callable | None = None

    def set_tool_executor(self, executor: Callable) -> None:
        """Set the function that executes tool calls."""
        self._tool_executor = executor

    def create_chain(self, description: str, steps: list[dict]) -> dict:
        """
        Create a new tool chain.

        Each step dict:
        - tool_name: str — tool to call
        - parameters: dict — tool parameters (can reference previous outputs with $step_id.output_key)
        - description: str — what this step does
        - output_key: str — key to store this step's output (optional)
        """
        chain_id = f"chain_{int(time.time() * 1000)}"
        chain = ToolChain(
            chain_id=chain_id,
            description=description,
            created_at=time.time(),
            status="ready",
        )

        for i, step_data in enumerate(steps):
            step = ChainStep(
                step_id=i + 1,
                tool_name=step_data.get("tool_name", ""),
                parameters=step_data.get("parameters", {}),
                description=step_data.get("description", ""),
                output_key=step_data.get("output_key", f"step_{i + 1}"),
            )
            chain.steps.append(step)

        self._active_chains[chain_id] = chain

        return {
            "success": True,
            "chain_id": chain_id,
            "description": description,
            "total_steps": len(chain.steps),
            "steps": [s.to_dict() for s in chain.steps],
        }

    def _resolve_parameters(self, step: ChainStep, chain: ToolChain) -> dict:
        """Resolve parameter references to previous step outputs."""
        resolved = {}
        for key, value in step.parameters.items():
            if isinstance(value, str) and value.startswith("$"):
                # Reference to previous step output: $step_1.result
                ref = value[1:]  # remove $
                parts = ref.split(".", 1)
                if len(parts) == 2:
                    ref_step_id = int(parts[0].replace("step_", ""))
                    ref_key = parts[1]
                    # Find the referenced step
                    for s in chain.steps:
                        if s.step_id == ref_step_id and s.status == "completed":
                            if ref_key == "result":
                                resolved[key] = s.result
                            else:
                                resolved[key] = s.result
                            break
                    else:
                        resolved[key] = value  # keep original if reference not found
                else:
                    resolved[key] = value
            else:
                resolved[key] = value
        return resolved

    async def execute_chain(self, chain_id: str) -> dict:
        """Execute all steps in a chain sequentially."""
        chain = self._active_chains.get(chain_id)
        if not chain:
            return {"error": "Chain not found"}

        if not self._tool_executor:
            return {"error": "Tool executor not set"}

        chain.status = "running"
        chain.started_at = time.time()
        results = []

        for step in chain.steps:
            if step.status in ("completed", "skipped"):
                continue

            step.status = "running"
            step.started_at = time.time()
            chain.current_step = step.step_id

            try:
                # Resolve parameter references
                resolved_params = self._resolve_parameters(step, chain)

                # Execute the tool
                logger.info(f"[Chain] Executing step {step.step_id}: {step.tool_name}")
                result = self._tool_executor(step.tool_name, resolved_params)

                step.status = "completed"
                step.result = str(result) if result else ""
                step.completed_at = time.time()

                # Store in chain context
                chain.context[step.output_key] = step.result

                results.append({
                    "step_id": step.step_id,
                    "tool": step.tool_name,
                    "status": "completed",
                    "result": step.result[:200] + "..." if len(step.result) > 200 else step.result,
                })

                logger.info(f"[Chain] Step {step.step_id} completed")

            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                step.completed_at = time.time()
                chain.status = "failed"

                results.append({
                    "step_id": step.step_id,
                    "tool": step.tool_name,
                    "status": "failed",
                    "error": str(e),
                })

                logger.error(f"[Chain] Step {step.step_id} failed: {e}")
                break  # Stop chain on failure

        # Determine final status
        all_done = all(s.status in ("completed", "skipped") for s in chain.steps)
        any_failed = any(s.status == "failed" for s in chain.steps)

        if all_done:
            chain.status = "completed"
        elif any_failed:
            chain.status = "failed"

        chain.completed_at = time.time()

        return {
            "chain_id": chain_id,
            "description": chain.description,
            "status": chain.status,
            "results": results,
            "duration": round(chain.completed_at - chain.started_at, 2),
        }

    def get_chain_status(self, chain_id: str) -> dict:
        """Get current status of a chain."""
        chain = self._active_chains.get(chain_id)
        if not chain:
            return {"error": "Chain not found"}

        completed = sum(1 for s in chain.steps if s.status in ("completed", "skipped"))
        failed = sum(1 for s in chain.steps if s.status == "failed")
        total = len(chain.steps)

        return {
            "chain_id": chain_id,
            "description": chain.description,
            "status": chain.status,
            "progress": f"{completed}/{total}",
            "completed": completed,
            "failed": failed,
            "total": total,
            "current_step": chain.current_step,
            "steps": [s.to_dict() for s in chain.steps],
        }

    def list_active_chains(self) -> list[dict]:
        """List all active chains."""
        return [
            {
                "chain_id": cid,
                "description": c.description,
                "status": c.status,
                "progress": f"{sum(1 for s in c.steps if s.status in ('completed', 'skipped'))}/{len(c.steps)}",
            }
            for cid, c in self._active_chains.items()
        ]


# ── Singleton ───────────────────────────────────────────────────────────
_engine: ToolChainEngine | None = None


def get_tool_chain_engine() -> ToolChainEngine:
    global _engine
    if _engine is None:
        _engine = ToolChainEngine()
    return _engine


# ── Tool Interface ──────────────────────────────────────────────────────

def tool_chain(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Tool chaining engine.
    Create and execute chains of tool calls.
    """
    engine = get_tool_chain_engine()
    action = parameters.get("action", "create")

    if action == "create":
        description = parameters.get("description", "")
        steps = parameters.get("steps", [])

        if not description:
            return "Error: description is required"
        if not steps:
            return "Error: steps are required"

        result = engine.create_chain(description, steps)
        if result.get("success"):
            lines = [
                f"Tool Chain Created: {result['chain_id']}",
                f"Description: {result['description']}",
                f"Steps ({result['total_steps']}):",
            ]
            for s in result["steps"]:
                lines.append(f"  {s['step_id']}. [{s['tool_name']}] {s['description']}")
            return "\n".join(lines)
        return f"Error creating chain: {result}"

    elif action == "execute":
        chain_id = parameters.get("chain_id", "")
        if not chain_id:
            # Get first active chain
            for cid in engine._active_chains:
                chain_id = cid
                break
        if not chain_id:
            return "No active chains to execute"

        # Note: actual execution requires async context
        # This returns the chain info for the caller to execute
        status = engine.get_chain_status(chain_id)
        return json.dumps(status, indent=2)

    elif action == "status":
        chain_id = parameters.get("chain_id", "")
        if chain_id:
            return json.dumps(engine.get_chain_status(chain_id), indent=2)
        chains = engine.list_active_chains()
        if chains:
            return json.dumps(chains, indent=2)
        return "No active chains"

    elif action == "list":
        chains = engine.list_active_chains()
        if chains:
            return json.dumps(chains, indent=2)
        return "No active chains"

    return f"Unknown action: {action}. Use: create, execute, status, list"
