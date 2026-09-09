"""SONIC AI — Update Startup Hook

Non-blocking background check on app launch.
If update available → show popup (non-modal).
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

if TYPE_CHECKING:
    from ui import SonicUI

logger = logging.getLogger("UPDATER")


def check_for_updates_on_startup(ui: "SonicUI") -> None:
    """Check for updates in background thread. Show popup on main thread."""

    def _check():
        try:
            from updater import get_update_manager
            manager = get_update_manager()
            manifest = manager.check_for_update()
            if manifest is not None:
                QTimer.singleShot(0, lambda: _show(manifest, ui))
        except Exception as e:
            logger.warning("[UPDATER] Startup check failed: %s", e)

    def _show(manifest, ui_ref):
        try:
            from updater.ui import UpdatePopup
            popup = UpdatePopup(manifest, parent=ui_ref._win)
            popup.show()
        except Exception as e:
            logger.warning("[UPDATER] Could not show popup: %s", e)

    QTimer.singleShot(2000, lambda: threading.Thread(target=_check, daemon=True).start())
