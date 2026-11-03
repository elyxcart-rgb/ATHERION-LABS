"""SONIC AI — Office Adapter (Excel / Word / PowerPoint).

Uses win32com (pywin32) if installed, else falls back to subprocess opening
the file with the default Office app. Office automation is rich when
COM is available — Excel sheets, Word docs, PPT slides can all be
manipulated programmatically.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.office")


class OfficeAdapter(AppAdapter):
    name = "office"
    processes = ["excel", "winword", "powerpnt", "outlook"]
    capabilities = [
        AdapterCapability.CLICK, AdapterCapability.TYPE,
        AdapterCapability.CUSTOM, AdapterCapability.EXTRACT_TEXT,
    ]

    def __init__(self):
        self._win32 = None
        self._tried = False

    def _ensure_win32(self):
        if self._tried:
            return self._win32
        self._tried = True
        try:
            import win32com.client  # type: ignore
            self._win32 = win32com_client
        except ImportError:
            pass
        return self._win32

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        win32 = self._ensure_win32()
        if win32 is None:
            # graceful fallback — just open the file
            return self._fallback_open(action, t0)

        prog_map = {
            "excel": "Excel.Application",
            "winword": "Word.Application",
            "powerpnt": "PowerPoint.Application",
            "outlook": "Outlook.Application",
        }
        prog = None
        for proc, app_prog in prog_map.items():
            if proc in (action.target_process or "").lower():
                prog = app_prog
                break

        if not prog:
            return self._fallback_open(action, t0)

        try:
            app = win32.Dispatch(prog)
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="office.dispatch_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

        try:
            if action.action_type in (ActionType.OPEN_APP, ActionType.FILE_OPEN):
                path = action.target_path or action.parameters.get("path")
                if path:
                    if prog == "Excel.Application":
                        wb = app.Workbooks.Open(path)
                    elif prog == "Word.Application":
                        doc = app.Documents.Open(path)
                    elif prog == "PowerPoint.Application":
                        pres = app.Presentations.Open(path, WithWindow=True)
                    else:
                        pass
                    app.Visible = True
                    return AdapterResult(
                        success=True, method=f"office.open({prog})",
                        duration_ms=(time.time() - t0) * 1000.0,
                    )
                app.Visible = True
                return AdapterResult(
                    success=True, method=f"office.visible({prog})",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            if action.action_type == ActionType.FILE_SAVE:
                app.ActiveDocument.Save() if hasattr(app, "ActiveDocument") else app.ActiveWorkbook.Save()
                return AdapterResult(
                    success=True, method="office.save",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            if action.action_type == ActionType.EXTRACT_TEXT:
                text = ""
                if prog == "Word.Application":
                    text = app.ActiveDocument.Content.Text
                elif prog == "Excel.Application":
                    sheet = app.ActiveSheet
                    text = "; ".join(str(c.Value) for row in sheet.UsedRange for c in row
                                     if c.Value is not None)[:5000]
                elif prog == "PowerPoint.Application":
                    text = " ".join(s.NotesPage.Shapes.Placeholders[2].TextFrame.TextRange.Text
                                    for s in app.ActivePresentation.Slides if s.HasNotesPage)
                return AdapterResult(
                    success=True, method="office.extract_text",
                    data={"text": text},
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.EXTRACT_TEXT],
                )

            return AdapterResult(
                success=False,
                error=f"office adapter does not implement {action.action_type.value}",
                method="office.unsupported",
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="office.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def _fallback_open(self, action, t0) -> AdapterResult:
        try:
            target = action.target_path or action.parameters.get("path")
            if target and Path(target).exists():
                subprocess.Popen(["start", "", target], shell=True)
            else:
                # Just launch the app
                prog_map = {"excel": "excel", "winword": "winword",
                            "powerpnt": "powerpnt", "outlook": "outlook"}
                p = (action.target_process or "").lower()
                exe = prog_map.get(p)
                if exe:
                    subprocess.Popen([exe])
                else:
                    return AdapterResult(
                        success=False, error="no target path or process",
                        method="office.fallback_nopath",
                    )
            return AdapterResult(
                success=True, method="office.fallback_open",
                duration_ms=(time.time() - t0) * 1000.0,
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="office.fallback_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        win32 = self._ensure_win32()
        if win32 is None:
            return {"error": "win32com not installed"}
        try:
            return {
                "running": [
                    p for p in ("excel", "winword", "powerpnt", "outlook")
                    if self._is_running(p)
                ]
            }
        except Exception:
            return {}

    def _is_running(self, name: str) -> bool:
        try:
            import psutil  # type: ignore
            return any(proc.info['name'] and name in proc.info['name'].lower()
                       for proc in psutil.process_iter(['name']))
        except ImportError:
            return False
