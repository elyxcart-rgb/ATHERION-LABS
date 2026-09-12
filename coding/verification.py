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
        py_files = [f for f in root.rglob("*.py")
                    if "__pycache__" not in str(f)
                    and ".venv" not in str(f)]
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
        tests_ran = False
        test_patterns = ["test_", "tests/", "test/", "spec_"]
        has_tests = any(
            any(p in str(f).lower() for p in test_patterns)
            for f in root.rglob("*.py")
        )
        if has_tests:
            tests_ran = True
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
                        errors.append(f"Tests failed: {result.stdout[:300]}")
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
