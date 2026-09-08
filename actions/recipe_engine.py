"""
Recipe Engine — Automated Multi-Step Workflows
Let users create, save, and execute multi-step automation recipes.
"""
import json
import time
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from datetime import datetime


@dataclass
class RecipeStep:
    step_id: int
    tool_name: str
    parameters: dict
    description: str = ""
    delay_after: float = 0.0
    condition: str = ""

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "description": self.description,
            "delay_after": self.delay_after,
            "condition": self.condition,
        }


@dataclass
class Recipe:
    name: str
    description: str
    steps: list[RecipeStep] = field(default_factory=list)
    created_at: str = ""
    last_run: str = ""
    run_count: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        steps = [RecipeStep(**s) for s in data.get("steps", [])]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            created_at=data.get("created_at", ""),
            last_run=data.get("last_run", ""),
            run_count=data.get("run_count", 0),
            tags=data.get("tags", []),
        )


class RecipeEngine:
    """Manages recipe storage, execution, and scheduling."""

    def __init__(self, storage_path: Path = None):
        self._storage_path = storage_path or Path.home() / ".sonic" / "recipes.json"
        self._recipes: dict[str, Recipe] = {}
        self._tool_executor: Callable = None
        self._load()

    def _load(self):
        try:
            if self._storage_path.exists():
                data = json.loads(self._storage_path.read_text(encoding="utf-8"))
                for name, recipe_data in data.items():
                    self._recipes[name] = Recipe.from_dict(recipe_data)
        except Exception:
            pass

    def _save(self):
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {name: r.to_dict() for name, r in self._recipes.items()}
            self._storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def set_tool_executor(self, executor: Callable):
        self._tool_executor = executor

    def create_recipe(
        self,
        name: str,
        description: str,
        steps: list[dict],
        tags: list[str] = None,
    ) -> Recipe:
        """Create a new recipe."""
        recipe_steps = []
        for i, step in enumerate(steps, 1):
            recipe_steps.append(RecipeStep(
                step_id=i,
                tool_name=step.get("tool_name", ""),
                parameters=step.get("parameters", {}),
                description=step.get("description", f"Step {i}"),
                delay_after=step.get("delay_after", 0.0),
                condition=step.get("condition", ""),
            ))

        recipe = Recipe(
            name=name,
            description=description,
            steps=recipe_steps,
            created_at=datetime.now().isoformat(),
            tags=tags or [],
        )
        self._recipes[name] = recipe
        self._save()
        return recipe

    def delete_recipe(self, name: str) -> bool:
        if name in self._recipes:
            del self._recipes[name]
            self._save()
            return True
        return False

    def get_recipe(self, name: str) -> Recipe | None:
        return self._recipes.get(name)

    def list_recipes(self) -> list[dict]:
        return [
            {
                "name": r.name,
                "description": r.description,
                "steps": len(r.steps),
                "run_count": r.run_count,
                "tags": r.tags,
            }
            for r in self._recipes.values()
        ]

    async def execute_recipe(
        self,
        name: str,
        variables: dict = None,
        callback: Callable = None,
    ) -> str:
        """Execute a recipe step by step."""
        recipe = self._recipes.get(name)
        if not recipe:
            return f"Recipe '{name}' not found."

        if not self._tool_executor:
            return "Tool executor not available."

        results = []
        variables = variables or {}

        for step in recipe.steps:
            if callback:
                await callback(f"Step {step.step_id}/{len(recipe.steps)}: {step.description}")

            if step.condition:
                if not self._evaluate_condition(step.condition, variables):
                    results.append(f"Step {step.step_id}: Skipped (condition not met)")
                    continue

            params = self._resolve_variables(step.parameters, variables)

            try:
                if asyncio.iscoroutinefunction(self._tool_executor):
                    result = await self._tool_executor(step.tool_name, params)
                else:
                    result = await asyncio.to_thread(
                        self._tool_executor, step.tool_name, params
                    )
                results.append(f"Step {step.step_id}: {result}")
                variables[f"step_{step.step_id}_result"] = result
            except Exception as e:
                results.append(f"Step {step.step_id}: Failed — {e}")

            if step.delay_after > 0:
                await asyncio.sleep(step.delay_after)

        recipe.last_run = datetime.now().isoformat()
        recipe.run_count += 1
        self._save()

        return "\n".join(results)

    def _evaluate_condition(self, condition: str, variables: dict) -> bool:
        """Simple condition evaluation."""
        try:
            for key, value in variables.items():
                condition = condition.replace(f"{{{key}}}", str(value))
            return bool(eval(condition, {"__builtins__": {}}, {}))
        except Exception:
            return True

    def _resolve_variables(self, params: dict, variables: dict) -> dict:
        """Resolve variable references in parameters."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                var_name = value[1:-1]
                resolved[key] = variables.get(var_name, value)
            else:
                resolved[key] = value
        return resolved


_engine: RecipeEngine | None = None


def get_recipe_engine() -> RecipeEngine:
    global _engine
    if _engine is None:
        _engine = RecipeEngine()
    return _engine


async def recipe_engine(parameters: dict, **kwargs) -> str:
    """Tool handler for recipe_engine."""
    action = parameters.get("action", "list")
    engine = get_recipe_engine()

    if "tool_executor" in kwargs:
        engine.set_tool_executor(kwargs["tool_executor"])

    if action == "create":
        name = parameters.get("name", "")
        desc = parameters.get("description", "")
        steps = parameters.get("steps", [])
        tags = parameters.get("tags", [])
        if not name or not steps:
            return "Provide name and steps to create a recipe."
        recipe = engine.create_recipe(name, desc, steps, tags)
        return f"Recipe '{name}' created with {len(recipe.steps)} steps."

    elif action == "delete":
        name = parameters.get("name", "")
        if engine.delete_recipe(name):
            return f"Recipe '{name}' deleted."
        return f"Recipe '{name}' not found."

    elif action == "run":
        name = parameters.get("name", "")
        variables = parameters.get("variables", {})
        result = await engine.execute_recipe(name, variables)
        return result

    elif action == "list":
        recipes = engine.list_recipes()
        if not recipes:
            return "No recipes saved. Create one first!"
        lines = ["Saved Recipes:"]
        for r in recipes:
            lines.append(f"  - {r['name']}: {r['description']} ({r['steps']} steps, run {r['run_count']}x)")
        return "\n".join(lines)

    elif action == "get":
        name = parameters.get("name", "")
        recipe = engine.get_recipe(name)
        if not recipe:
            return f"Recipe '{name}' not found."
        return json.dumps(recipe.to_dict(), indent=2)

    return f"Unknown recipe action: {action}. Use: create, delete, run, list, get"
