"""SONIC AI — Code Sandbox.

Safe Python execution with output capture, timeout, and result aggregation.
JARVIS can run code on your behalf ("run python: print hello", "compute 2^100",
"sort this list").

Public API:
    CodeSandbox(timeout_seconds=10)
    .run(code: str) -> SandboxResult
    .run_file(path: str) -> SandboxResult
    .is_safe(code: str) -> (ok: bool, warnings: list[str])
    .get_stats()
"""
from __future__ import annotations

import ast
import builtins
import io
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


# ═════════════════════════════════════════════════════════════════════════════
# SandboxResult
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class SandboxResult:
    """Outcome of a sandboxed Python execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    return_value: str = ""
    duration_ms: float = 0.0
    exit_code: int = 0
    timed_out: bool = False
    killed: bool = False
    error_type: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        if self.timed_out:
            return f"[TIMEOUT after {self.duration_ms:.0f}ms]"
        if not self.success:
            err = self.error_message or self.stderr.strip()
            return f"[ERROR] {self.error_type}: {err[:200]}"
        out = self.stdout.strip()
        rv = self.return_value.strip()
        if rv and out:
            return f"{out}\n=> {rv}"
        return out or rv or "[no output]"


# ═════════════════════════════════════════════════════════════════════════════
# Whitelist / safety checks
# ═════════════════════════════════════════════════════════════════════════════

# Modules allowed in the sandbox
_ALLOWED_MODULES = {
    "math", "random", "statistics", "json", "re", "string", "datetime",
    "collections", "itertools", "functools", "operator", "typing",
    "pathlib", "io", "os", "sys", "time", "calendar",
    "decimal", "fractions", "numbers", "bisect", "heapq",
    "array", "queue", "enum", "dataclasses", "copy",
}

# Modules / callables that are explicitly DANGEROUS (we block these)
_DANGEROUS_CALLS = {
    "os.system", "os.popen", "os.remove", "os.rmdir", "os.unlink",
    "os.removedirs", "subprocess.run", "subprocess.call", "subprocess.Popen",
    "shutil.rmtree", "shutil.move",
    "open",  # when called with "w" mode in dangerous paths
    "eval", "exec", "compile",
    "__import__",
    "socket.socket", "urllib.request.urlopen",
    "requests.get", "requests.post",
}

_DANGEROUS_PATTERNS = [
    r"\bos\.system\s*\(",
    r"\bsubprocess\.",
    r"\bshutil\.rmtree\s*\(",
    r"__import__\s*\(",
    r"\bexec\s*\(",
    r"\bcompile\s*\(",
    r"\bos\.remove\s*\(",
]


# ═════════════════════════════════════════════════════════════════════════════
# In-process executor (fast, with timeout via signal/subprocess)
# ═════════════════════════════════════════════════════════════════════════════

class CodeSandbox:
    """Runs Python code safely with output capture, timeout, and reporting."""

    def __init__(self, timeout_seconds: float = 10.0,
                 allow_network: bool = False,
                 work_dir: Optional[str] = None):
        self._timeout = timeout_seconds
        self._allow_network = allow_network
        self._work_dir = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sonic_sandbox_"))
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._stats = {"runs": 0, "successes": 0, "failures": 0, "timeouts": 0}

    # ── Public ───────────────────────────────────────────────────────────────

    def run(self, code: str, stdin_input: str = "") -> SandboxResult:
        """Execute code in the sandbox, return the result."""
        t0 = time.time()
        with self._lock:
            self._stats["runs"] += 1

        # Safety check
        ok, warnings = self.is_safe(code)
        if not ok:
            with self._lock:
                self._stats["failures"] += 1
            return SandboxResult(
                success=False,
                error_type="SecurityError",
                error_message="; ".join(warnings),
                duration_ms=(time.time() - t0) * 1000,
            )

        # Write code to a tempfile
        script = self._work_dir / f"run_{int(time.time()*1000)}.py"
        try:
            script.write_text(code, encoding="utf-8")
        except Exception as e:
            return SandboxResult(
                success=False,
                error_type="IOError",
                error_message=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )

        # Run in subprocess so we can enforce timeout
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-W", "ignore", str(script)],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._work_dir),
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "HOME": os.environ.get("HOME", str(self._work_dir)),
                    "TEMP": str(self._work_dir),
                    "TMP": str(self._work_dir),
                    "SONIC_SANDBOX": "1",
                    **{k: v for k, v in os.environ.items()
                       if k.startswith("SONIC_") or k.startswith("PYTHON_")},
                },
            )
            success = proc.returncode == 0
            duration_ms = (time.time() - t0) * 1000
            with self._lock:
                if success:
                    self._stats["successes"] += 1
                else:
                    self._stats["failures"] += 1
            return SandboxResult(
                success=success,
                stdout=proc.stdout,
                stderr=proc.stderr,
                duration_ms=duration_ms,
                exit_code=proc.returncode,
            )
        except subprocess.TimeoutExpired:
            with self._lock:
                self._stats["timeouts"] += 1
            return SandboxResult(
                success=False,
                timed_out=True,
                error_type="TimeoutError",
                error_message=f"execution exceeded {self._timeout}s timeout",
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            with self._lock:
                self._stats["failures"] += 1
            return SandboxResult(
                success=False,
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=(time.time() - t0) * 1000,
            )
        finally:
            # Clean up script
            try:
                script.unlink(missing_ok=True)
            except Exception:
                pass

    def run_expression(self, expr: str) -> SandboxResult:
        """Run a single expression and return its value."""
        code = f"import sys, json\n_result = {expr}\nsys.stdout.write(json.dumps(_result, default=str))"
        return self.run(code)

    def run_file(self, path: str) -> SandboxResult:
        """Execute a Python file."""
        try:
            code = Path(path).read_text(encoding="utf-8")
            return self.run(code)
        except Exception as e:
            return SandboxResult(
                success=False,
                error_type=type(e).__name__,
                error_message=str(e),
            )

    def is_safe(self, code: str) -> tuple[bool, list[str]]:
        """Static safety check on code. Returns (ok, warnings)."""
        warnings = []
        import re

        # Pattern check for dangerous calls
        for pat in _DANGEROUS_PATTERNS:
            if re.search(pat, code):
                warnings.append(f"blocked by safety pattern: {pat}")

        # AST-based check
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, [f"SyntaxError: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn_name = self._call_name(node)
                if fn_name in _DANGEROUS_CALLS:
                    warnings.append(f"dangerous call: {fn_name}")
                # Check import
                if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                    warnings.append("dynamic import blocked")

            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                root = mod.split(".")[0] if mod else ""
                if root and root not in _ALLOWED_MODULES and root not in ("__future__",):
                    warnings.append(f"module not in whitelist: {root}")

        return len(warnings) == 0, warnings

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internal helpers ────────────────────────────────────────────────────

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        """Extract a string name from an ast.Call node (best-effort)."""
        f = node.func
        if isinstance(f, ast.Name):
            return f.id
        if isinstance(f, ast.Attribute):
            parts = []
            cur = f
            while isinstance(cur, ast.Attribute):
                parts.append(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.append(cur.id)
            return ".".join(reversed(parts))
        return ""
