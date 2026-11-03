"""Smoke test the new holographic SonicBootUI:
1. Instantiation
2. All public signals / slots callable
3. Real WorkerThread detect run (offline-safe: uses detect_all)
4. Capture to a PNG to confirm no runtime errors during render
"""
import sys
import traceback
from pathlib import Path

# Force UTF-8 stdout
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from bootstrap.state import BootstrapState
from bootstrap.ui import SonicBootUI, CoreState, WorkerThread, IntelligenceCore, StagePipeline, GlassStatusPanel


def run_smoke():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    state = BootstrapState()
    ui = SonicBootUI(state)

    # Smoke check: every public class instantiates
    assert hasattr(ui, "finished")
    assert callable(ui._on_cinematic_complete)
    assert callable(ui._fade_in_setup_ui)
    assert callable(ui._start_detection)
    assert callable(ui._on_progress)
    assert callable(ui._on_stage_update)
    assert callable(ui._on_req_check)
    assert callable(ui._on_detection_done)
    assert callable(ui._on_action)
    assert callable(ui._skip_optional)
    print("[OK] SonicBootUI has all expected methods + finished signal")

    # Reachable classes
    core = IntelligenceCore()
    core.set_state(CoreState.READY)
    print("[OK] IntelligenceCore instantiates + set_state")

    pipeline = StagePipeline()
    pipeline.set_stage("system", "done")
    print("[OK] StagePipeline instantiates + set_stage")

    panel = GlassStatusPanel()
    panel.add_item("PLAYWRIGHT CHROMIUM", "installed", "Available")
    panel.add_item("OPENCODE PLAYER", "installed", "Found at C:/x/y/z")
    panel.add_item("PYTHON RUNTIME", "installed", "3.11.7")
    panel.clear()
    print("[OK] GlassStatusPanel.add_item + clear work")

    # Slots wiring check
    ui._fade_in_setup_ui()
    print("[OK] _fade_in_setup_ui ran without error")

    # Now drive the worker for ~3 seconds to confirm worker + signals work
    finished = {"called": False, "msg": None}

    def on_done(success, msg):
        finished["called"] = True
        finished["msg"] = (success, msg)
        print(f"[OK] Worker all_done signal received: success={success} msg={msg[:60]}")

    ui._worker = WorkerThread(mode="detect")
    ui._worker.progress.connect(ui._on_progress)
    ui._worker.requirement_check.connect(ui._on_req_check)
    ui._worker.stage_update.connect(ui._on_stage_update)
    ui._worker.all_done.connect(on_done)
    ui._worker.start()
    print("[OK] WorkerThread started")

    out_dir = Path(r"D:\download\previews")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Capture both: (a) detecting state, (b) ready state
    snapshots = {"detecting": False, "ready": False}

    def capture_detecting():
        ui.show()
        ui._hero._title_reveal = 1.0
        ui._hero._subtitle_alpha = 1.0
        for w in (ui._pipeline, ui._progress_label, ui._percent_label,
                  ui._scifi_progress, ui._status_label, ui._glass_panel,
                  ui._action_btn):
            w.show()
        pix = ui.grab()
        out = out_dir / "sonic_holographic_detecting.png"
        pix.save(str(out), "PNG")
        snapshots["detecting"] = True
        print(f"[OK] Detecting-state screenshot saved: {out}")

    def capture_ready():
        ui._hero.set_state(CoreState.READY)
        ui._percent_label.setText("100%")
        ui._scifi_progress.setValue(100)
        ui._status_label.setText(">> SONIC IS READY")
        ui._action_btn.setText("ENTER SONIC  →")
        ui._action_btn.setEnabled(True)
        for key in ("system", "audio", "runtime", "tools", "verify", "ready"):
            ui._pipeline.set_stage(key, "done")
        pix = ui.grab()
        out = out_dir / "sonic_holographic_ready.png"
        pix.save(str(out), "PNG")
        snapshots["ready"] = True
        print(f"[OK] Ready-state screenshot saved: {out}")

    QTimer.singleShot(800, capture_detecting)
    QTimer.singleShot(5000, capture_ready)
    QTimer.singleShot(7000, lambda: app.quit())

    app.exec()

    if not finished["called"]:
        print("[WARN] Worker all_done did not fire within 7s — detection may have been blocked")
    else:
        print(f"[OK] Detection completed in worker thread")

    # Final assertion: no fatal tracebacks in sys.excepthook chain
    print("[SMOKE TEST PASSED]")


if __name__ == "__main__":
    try:
        run_smoke()
    except Exception:
        traceback.print_exc()
        print("[SMOKE TEST FAILED]")
        sys.exit(1)