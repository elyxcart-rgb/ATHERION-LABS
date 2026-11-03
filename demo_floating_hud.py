"""SONIC AI — Floating HUD demo.

Launches the floating HUD as a standalone always-on-top window.
Demonstrates the unique SONIC design (not iPhone/Android/Windows).
"""
from __future__ import annotations

import sys
from pathlib import Path

try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.floating_hud import FloatingHUD


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    hud = FloatingHUD()
    hud.show_at("top_right")
    print(f"HUD shown at top-right corner")
    print(f"HUD stats: {hud.get_stats()}")

    OUT = Path(r"D:\download\previews")
    OUT.mkdir(parents=True, exist_ok=True)

    states = ["idle", "listening", "thinking", "speaking", "ready", "error"]
    audio_levels = [0.05, 0.6, 0.3, 0.8, 0.1, 0.0]

    captures = []

    def cycle_state(i: int):
        if i >= len(states):
            QTimer.singleShot(300, finish)
            return
        state = states[i]
        audio = audio_levels[i]
        hud.set_state(state)
        hud.set_audio_level(audio)
        print(f"  → State: {state:<10} Audio: {audio}")
        QTimer.singleShot(200, lambda: do_grab(state, i))

    def do_grab(state: str, i: int):
        pix = hud.grab()
        out = OUT / f"sonic_hud_{state}.png"
        pix.save(str(out), "PNG")
        captures.append((state, out))
        QTimer.singleShot(50, lambda: cycle_state(i + 1))

    def finish():
        print("\nAll HUD screenshots saved:")
        for state, path in captures:
            print(f"  ✓ {path.name}  ({path.stat().st_size // 1024}KB)")
        print()
        print("HUD also stayed always-on-top in the live demo.")
        print("Try opening any other app and the HUD floats above it.")
        app.quit()

    QTimer.singleShot(800, lambda: cycle_state(0))
    app.exec()


if __name__ == "__main__":
    main()
