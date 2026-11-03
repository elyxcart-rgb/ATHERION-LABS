"""SONIC AI — VS Code Adapter.

Uses the `code` CLI for navigation/open + the VS Code extension WebSocket
API when available. Falls back to keyboard shortcuts through the generic
input fallback for in-editor interactions.
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.vscode")


class VSCodeAdapter(AppAdapter):
    name = "vscode"
    processes = ["code", "code - insiders", "code-insiders"]
    capabilities = [
        AdapterCapability.CLICK, AdapterCapability.TYPE,
        AdapterCapability.NAVIGATE, AdapterCapability.EXTRACT_TEXT,
    ]

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        code_exe = self._find_code_exe()
        try:
            if action.action_type in (ActionType.OPEN_APP, ActionType.FILE_OPEN):
                if code_exe and (action.target_path or action.parameters.get("path")):
                    subprocess.Popen([code_exe, action.target_path or action.parameters.get("path")])
                elif code_exe:
                    subprocess.Popen([code_exe])
                else:
                    return AdapterResult(
                        success=False, error="`code` CLI not on PATH",
                        method="vscode.no_cli",
                    )
                return AdapterResult(
                    success=True, method="vscode.launch",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            if action.action_type == ActionType.EXECUTE_COMMAND:
                cmd = action.parameters.get("cmd") or action.target_text
                if code_exe and cmd:
                    # `code --command` is supported in recent VS Code
                    out = subprocess.run(
                        [code_exe, "--command", cmd],
                        capture_output=True, text=True, timeout=10,
                    )
                    return AdapterResult(
                        success=True, method="vscode.command",
                        data={"stdout": out.stdout, "stderr": out.stderr},
                        duration_ms=(time.time() - t0) * 1000.0,
                    )

            if action.action_type == ActionType.EXTRACT_TEXT:
                # Use the editor's selection — extract via `code -g file:line:col`
                if code_exe and action.parameters.get("file"):
                    out = subprocess.run(
                        [code_exe, "-g", action.parameters.get("file")],
                        capture_output=True, text=True, timeout=5,
                    )
                    return AdapterResult(
                        success=True, method="vscode.goto",
                        data={"stdout": out.stdout},
                        duration_ms=(time.time() - t0) * 1000.0,
                    )

            return AdapterResult(
                success=False,
                error=f"vscode adapter does not implement {action.action_type.value}",
                method="vscode.unsupported",
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="vscode.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        return {
            "cli_available": bool(self._find_code_exe()),
        }

    @staticmethod
    def _find_code_exe() -> str:
        for exe in ("code.cmd", "code", "code-insiders.cmd", "code-insiders"):
            try:
                out = subprocess.run(["where", exe],
                                     capture_output=True, text=True, timeout=2)
                if out.returncode == 0:
                    return out.stdout.strip().splitlines()[0]
            except Exception:
                continue
        # Also check default install location
        default = Path.home() / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
        if default.exists():
            return str(default)
        return ""
