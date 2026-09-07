"""SONIC AI — Update Startup Hook.

Called at app startup to check for updates in the background.
Non-blocking — does not delay normal app launch.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui import SonicUI

logger = logging.getLogger("UPDATER")


def check_for_updates_on_startup(ui: "SonicUI") -> None:
    """
    Check for updates in a background thread.

    If an update is available, emit a signal to the UI to show the popup.
    Does NOT block app startup.
    """
    def _check():
        try:
            from updater import get_update_manager, UpdateState
            from updater.ui import UpdatePopup

            manager = get_update_manager()
            settings = manager.get_settings()

            if not settings.get("auto_check", True):
                return

            manifest = manager.check_for_update()
            if manifest is None:
                return

            # Schedule UI update on main thread using QTimer
            from PyQt6.QtCore import QTimer

            def _show():
                try:
                    popup = UpdatePopup(manifest, parent=ui._win)
                    popup.show()
                except Exception as e:
                    logger.warning("[UPDATER] Could not show popup: %s", e)

            QTimer.singleShot(0, _show)

        except Exception as e:
            logger.warning("[UPDATER] Startup check failed: %s", e)

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()
