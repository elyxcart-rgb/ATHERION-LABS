"""SONIC AI — Generic Windows Adapter (fallback).

Used when no specific adapter is registered for an app. Tries:
  1. pywinauto (if installed) — UIA-based control access
  2. pygetwindow (if installed) — window positioning
  3. ctypes SendInput / win32api — keyboard + mouse fallback

This is the last-tier adapter before the UniversalAgent falls through to
T5 vision / T6 input fallback.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .base import AppAdapter, AdapterResult, AdapterCapability


logger = logging.getLogger("sonic.adapter.generic")


class GenericWindowsAdapter(AppAdapter):
    name = "generic_windows"
    processes = []  # matches anything not claimed by a more specific adapter
    capabilities = [
        AdapterCapability.CLICK, AdapterCapability.TYPE,
        AdapterCapability.KEYPRESS, AdapterCapability.LIST_CONTROLS,
        AdapterCapability.EXTRACT_TEXT,
    ]

    def __init__(self):
        self._pywinauto = None
        self._tried_import = False

    def _ensure_pywinauto(self):
        if self._tried_import:
            return self._pywinauto
        self._tried_import = True
        try:
            import pywinauto  # type: ignore
            self._pywinauto = pywinauto
        except ImportError:
            pass
        return self._pywinauto

    def handles_processes(self) -> list[str]:
        # Empty list means "fallback for unknown processes"
        return []

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        pw = self._ensure_pywinauto()
        if pw is None:
            return AdapterResult(
                success=False,
                error="pywinauto not available; generic adapter cannot operate",
                method="generic.no_pywinauto",
                duration_ms=(time.time() - t0) * 1000.0,
            )

        # Best effort: find window for the target process / name
        try:
            from pywinauto import Application  # type: ignore
        except ImportError:
            return AdapterResult(
                success=False,
                error="pywinauto.Application import failed",
                method="generic.import_fail",
            )

        # The UniversalAgent passes target_process / target_name on the action.
        target_process = (action.target_process or "").lower()
        target_name = (action.target_name or "").lower()

        app = None
        try:
            if target_process:
                app = Application(backend="uia").connect(process=target_process, timeout=2)
            elif target_name:
                app = Application(backend="uia").connect(title_re=f".*{target_name}.*", timeout=2)
            else:
                # connect to foreground
                app = Application(backend="uia").connect(active_only=True, timeout=2)
        except Exception as exc:
            return AdapterResult(
                success=False,
                error=f"could not attach to window: {exc}",
                method="generic.connect_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

        try:
            win = app.window(active_only=True)
            from .actions_compat import ActionType
            if action.action_type == ActionType.CLICK:
                ctrl = win.child_window(title_re=f".*{action.target_text or action.target_name}.*",
                                        control_type="Button", timeout=2)
                ctrl.invoke()
                return AdapterResult(
                    success=True, method="generic.uia_invoke",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.CLICK],
                )
            elif action.action_type == ActionType.TYPE:
                edit = win.child_window(control_type="Edit", timeout=2)
                edit.set_edit_text(action.text or "")
                return AdapterResult(
                    success=True, method="generic.set_edit_text",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.TYPE],
                )
            elif action.action_type == ActionType.KEYPRESS:
                win.type_keys("+".join(action.keys), with_spaces=True)
                return AdapterResult(
                    success=True, method="generic.type_keys",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.KEYPRESS],
                )
            else:
                return AdapterResult(
                    success=False,
                    error=f"generic adapter does not implement {action.action_type.value}",
                    method="generic.unsupported",
                )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="generic.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        pw = self._ensure_pywinauto()
        if pw is None:
            return {"error": "pywinauto not installed"}
        try:
            from pywinauto import Application  # type: ignore
            app = Application(backend="uia").connect(active_only=True, timeout=2)
            win = app.window(active_only=True)
            return {
                "title": win.window_text(),
                "class_name": win.class_name(),
                "control_count": len(win.children()),
            }
        except Exception as exc:
            return {"error": str(exc)}
