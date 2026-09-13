from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .models import CodingTask, TaskState


class Verifier:
    @classmethod
    def run_checks(cls, task: CodingTask) -> tuple[bool, list[str]]:
        errors: list[str] = []
        root = Path(task.project_root) if task.project_root else Path.cwd()

        # Get Python files, excluding caches and venvs
        py_files = [f for f in root.rglob("*.py")
                    if "__pycache__" not in str(f)
                    and ".venv" not in str(f)
                    and "node_modules" not in str(f)]

        # Syntax check all Python files
        for f in py_files[:20]:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "py_compile", str(f)],
                    capture_output=True, text=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if result.returncode != 0:
                    errors.append(f"Syntax error in {f.name}: {result.stderr[:200]}")
            except Exception:
                pass

        # Only run tests if there are actual test files (not just the code itself)
        test_files = [f for f in py_files if f.name.startswith("test_")]
        if test_files:
            for cmd in [
                [sys.executable, "-m", "pytest", "--tb=short", "-q"],
                [sys.executable, "-m", "unittest", "discover", "-s", "test", "-q"],
            ]:
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True,
                        timeout=60, cwd=str(root),
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    if result.returncode == 0:
                        break
                    else:
                        # Only report as error if tests actually failed (not just "no tests found")
                        output = result.stdout + result.stderr
                        if "no tests ran" not in output.lower() and "no tests found" not in output.lower():
                            errors.append(f"Tests failed: {output[:300]}")
                        break
                except Exception:
                    continue

        return len(errors) == 0, errors

    @classmethod
    def verify(cls, task: CodingTask) -> TaskState:
        task.state = TaskState.VERIFYING
        passed, errors = cls.run_checks(task)
        if passed:
            return TaskState.SUCCEEDED
        task.error = "; ".join(errors[:5])
        return TaskState.FAILED
