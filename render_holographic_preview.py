"""Render the new holographic SONIC Apex bootstrap UI to PNG.

Does NOT call any external services — just instantiates SonicBootUI in a
non-blocking state, simulates a finished detection, and grabs a screenshot.
"""
import sys
import os
from pathlib import Path

# Force UTF-8 stdout (Windows cp1252 safety)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap

# Add project to path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from bootstrap.state import BootstrapState
from bootstrap.ui import SonicBootUI
from bootstrap.detector import DepResult, Status


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    state = BootstrapState()

    # Force-show the action button (skip detection for preview)
    ui = SonicBootUI(state)
    ui.show()
    ui._hero._title_reveal = 1.0
    ui._hero._subtitle_alpha = 1.0

    # Show everything for the screenshot
    for w in (ui._pipeline, ui._progress_label, ui._percent_label,
              ui._scifi_progress, ui._status_label, ui._glass_panel,
              ui._action_btn, ui._skip_btn):
        w.show()

    # Add some demo detection results (including the long names that
    # previously truncated!)
    demo = [
        DepResult(id="opencode", name="OPENCODE PLAYER",
                  status=Status.INSTALLED,
                  message="Found at: C:\\Users\\94\\AppData\\Roaming\\npm\\opencode.CMD"),
        DepResult(id="disk_space", name="DISK SPACE",
                  status=Status.INSTALLED, message="1125 MB free"),
        DepResult(id="playwright_chromium", name="PLAYWRIGHT CHROMIUM",
                  status=Status.INSTALLED, message="Available"),
        DepResult(id="ffmpeg", name="FFMPEG CODEC",
                  status=Status.INSTALLED, message="v6.1.1 build 2024"),
        DepResult(id="python_runtime", name="PYTHON RUNTIME",
                  status=Status.INSTALLED, message="Python 3.11.7 x64"),
    ]
    for r in demo:
        ui._glass_panel.add_item(r.name,
                                  "installed" if r.status == Status.INSTALLED else "missing",
                                  r.message)
        # Let layout settle between adds so rows don't stack on each other
        QApplication.processEvents()

    # Mark all pipeline stages done
    for key in ("system", "audio", "runtime", "tools", "verify", "ready"):
        ui._pipeline.set_stage(key, "done")

    # Set final state
    ui._hero.set_state("ready")
    ui._percent_label.setText("100%")
    ui._scifi_progress.setValue(100)
    ui._status_label.setText(">> SONIC IS READY")
    ui._action_btn.setText("ENTER SONIC  →")
    ui._action_btn.setEnabled(True)

    # Wait a moment for repaint, then screenshot
    out_dir = Path(r"D:\download\previews")
    out_dir.mkdir(parents=True, exist_ok=True)

    def grab():
        # Let backdrop animate a couple frames
        QTimer.singleShot(400, do_grab)

    def do_grab():
        pix = ui.grab()
        out = out_dir / "sonic_holographic_v1.png"
        ok = pix.save(str(out), "PNG")
        print(f"Screenshot saved: {out}  ({pix.width()}x{pix.height()})  ok={ok}")
        app.quit()

    QTimer.singleShot(800, do_grab)
    app.exec()


if __name__ == "__main__":
    main()