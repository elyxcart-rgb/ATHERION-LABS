"""SONIC AI — File Manager Adapter (Windows Explorer).

Uses pywinauto when available to attach to Explorer windows and interact
with files / folders. Falls back to PowerShell commands for headless ops.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.file_manager")


class FileManagerAdapter(AppAdapter):
    name = "file_manager"
    processes = ["explorer"]
    capabilities = [
        AdapterCapability.CLICK, AdapterCapability.TYPE,
        AdapterCapability.LIST_CONTROLS, AdapterCapability.EXTRACT_TEXT,
    ]

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        try:
            if action.action_type == ActionType.FILE_OPEN and action.target_path:
                subprocess.Popen(["explorer", action.target_path])
                return AdapterResult(
                    success=True, method="file_manager.explorer_open",
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            if action.action_type == ActionType.FILE_SEARCH:
                query = action.target_text or action.parameters.get("query", "*")
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     f"Get-ChildItem -Path $HOME -Recurse -Filter '*{query}*' -ErrorAction SilentlyContinue | Select-Object -First 10 FullName"],
                    capture_output=True, text=True, timeout=20,
                )
                return AdapterResult(
                    success=True, method="file_manager.search",
                    data={"results": out.stdout.strip().splitlines()},
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            if action.action_type in (ActionType.FILE_MOVE, ActionType.FILE_COPY,
                                       ActionType.FILE_DELETE, ActionType.FILE_RENAME):
                if action.is_destructive and action.require_confirmation:
                    return AdapterResult(
                        success=False,
                        error="destructive action needs confirmation",
                        method="file_manager.needs_confirm",
                    )
                return self._filesystem_op(action, t0)
            if action.action_type == ActionType.OPEN_APP and action.target_process == "explorer":
                subprocess.Popen(["explorer"])
                return AdapterResult(
                    success=True, method="file_manager.open_explorer",
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            return AdapterResult(
                success=False,
                error=f"file_manager adapter does not implement {action.action_type.value}",
                method="file_manager.unsupported",
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="file_manager.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def _filesystem_op(self, action, t0) -> AdapterResult:
        src = action.parameters.get("src") or action.parameters.get("source") or ""
        dst = action.parameters.get("dst") or action.parameters.get("destination") or ""
        try:
            if action.action_type == ActionType.FILE_MOVE and src and dst:
                Path(src).rename(dst)
            elif action.action_type == ActionType.FILE_COPY and src and dst:
                import shutil
                shutil.copy2(src, dst)
            elif action.action_type == ActionType.FILE_DELETE and src:
                Path(src).unlink()
            elif action.action_type == ActionType.FILE_RENAME and src:
                new_name = action.parameters.get("new_name") or ""
                if new_name:
                    Path(src).rename(Path(src).parent / new_name)
            else:
                return AdapterResult(
                    success=False,
                    error="missing src/dst parameters",
                    method="file_manager.bad_params",
                )
            return AdapterResult(
                success=True,
                method=f"file_manager.{action.action_type.value}",
                duration_ms=(time.time() - t0) * 1000.0,
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="file_manager.fs_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        return {"cwd": str(Path.cwd())}
