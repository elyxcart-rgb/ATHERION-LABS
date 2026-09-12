"""SONIC AI Bootstrapper - Main Module.

Entry point for the bootstrap system.
Determines whether to show first-run UI or skip to app.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .state import BootstrapState
from .detector import detect_required, get_system_info, Status


class Bootstrapper:
    def __init__(self, state_dir: Optional[str] = None):
        self._state = BootstrapState(state_dir)
        self._ui = None

    @property
    def state(self) -> BootstrapState:
        return self._state

    def needs_bootstrap(self) -> bool:
        return self._state.needs_check(max_age_hours=24)

    def run_lightweight_check(self) -> bool:
        required = detect_required()
        all_ok = all(r.status == Status.INSTALLED for r in required)
        return all_ok

    def show_setup_ui(self, app: Optional[object] = None) -> bool:
        from .ui import SonicBootUI

        if app is None:
            app = QApplication.instance()
        if app is None:
            from PyQt6.QtWidgets import QApplication
            app = QApplication(sys.argv)

        self._ui = SonicBootUI(self._state)
        self._ui.finished.connect(lambda: app.quit())
        self._ui.show()
        app.exec()

        return self._state.completed

    def is_first_run(self) -> bool:
        return not self._state.completed

    def get_status_summary(self) -> dict:
        info = get_system_info()
        return {
            "first_run": self.is_first_run(),
            "bootstrap_completed": self._state.completed,
            "system": {
                "os": info.os_name,
                "build": info.os_build,
                "arch": info.architecture,
                "python": info.python_version,
                "ram_gb": info.total_ram_gb,
                "disk_free_mb": info.free_disk_mb,
                "is_64bit": info.is_64bit,
            },
            "installed_count": len(self._state._data.get("installed_requirements", [])),
            "failed_count": len(self._state._data.get("failed_requirements", [])),
        }


def should_show_bootstrap(state_dir: Optional[str] = None) -> bool:
    state = BootstrapState(state_dir)
    return state.needs_check(max_age_hours=24)


def run_bootstrap_check() -> dict:
    state = BootstrapState()
    required = detect_required()
    info = get_system_info()

    results = {}
    for r in required:
        results[r.id] = {
            "name": r.name,
            "status": r.status.value,
            "message": r.message,
        }

    return {
        "system": {
            "os": info.os_name,
            "build": info.os_build,
            "arch": info.architecture,
            "python": info.python_version,
        },
        "requirements": results,
        "all_required_ok": all(r.status == Status.INSTALLED for r in required),
    }
