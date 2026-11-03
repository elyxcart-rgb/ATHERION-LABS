"""SONIC AI — Floating HUD launcher.

Starts the SONIC floating HUD as a persistent always-on-top overlay
with a system tray icon for control. Stays running until user quits.

Usage:
    python launch_floating_hud.py

Features:
  - Always-on-top overlay above every app/browser
  - System tray icon (left-click: toggle corner, right-click: menu)
  - Live state updates from JarvisBrain (if available)
  - Draggable, double-click to expand, right-click to cycle corners
  - Survives until explicitly quit via tray menu or Ctrl+Q
"""
from __future__ import annotations

import sys
import signal
from pathlib import Path

try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMessageBox,
)

from ui.floating_hud import FloatingHUD
from ui.mini_holo_orb import MiniHoloOrb


# ═════════════════════════════════════════════════════════════════════════════
# Tray icon (procedurally generated — no external file needed)
# ═════════════════════════════════════════════════════════════════════════════

def _make_tray_icon() -> QIcon:
    """Generate a small cyan orb icon for the tray."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # Outer glow
    from PyQt6.QtGui import QRadialGradient
    glow = QRadialGradient(32, 32, 30)
    glow.setColorAt(0.0, QColor(0, 220, 255, 220))
    glow.setColorAt(0.5, QColor(0, 200, 255, 120))
    glow.setColorAt(1.0, QColor(0, 200, 255, 0))
    p.setBrush(glow)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 60, 60)
    # Inner orb
    p.setBrush(QColor(255, 255, 255, 240))
    p.drawEllipse(24, 24, 16, 16)
    # Highlight
    p.setBrush(QColor(0, 220, 255, 200))
    p.drawEllipse(20, 20, 24, 24)
    p.end()
    return QIcon(pix)


# ═════════════════════════════════════════════════════════════════════════════
# HUDLauncher — the persistent floating-HUD application
# ═════════════════════════════════════════════════════════════════════════════

class HUDLauncher:
    """Persistent always-on-top SONIC floating HUD with tray control."""

    CORNERS = ["top_right", "top_left", "bottom_right", "bottom_left"]

    def __init__(self):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._app.setQuitOnLastWindowClosed(False)  # Keep running with tray

        # The HUD
        self._hud = FloatingHUD()
        self._hud.show_at("top_right")
        self._current_corner_idx = 0

        # System tray
        self._tray = QSystemTrayIcon(_make_tray_icon())
        self._tray.setToolTip("SONIC AI — Floating HUD")
        self._build_tray_menu()
        self._tray.show()

        # State cycle (for demo: when no brain, cycles through states
        # but COLOR STAYS CYAN — only label text changes)
        self._demo_timer = QTimer()
        self._demo_timer.timeout.connect(self._cycle_demo_state)
        self._demo_states = ["idle", "listening", "thinking",
                              "speaking", "ready"]
        self._demo_idx = 0

        # Brain integration (if available)
        self._brain = None
        try:
            from core.jarvis_brain import JarvisBrain
            self._brain = JarvisBrain(db_dir="~/.sonic_hud_brain")
            self._hud.set_state("ready")
            self._feed_event("SONIC HUD online · Brain connected")

            # Update label text (not color) based on real brain activity
            self._brain_timer = QTimer()
            self._brain_timer.timeout.connect(self._update_from_brain)
            self._brain_timer.start(4000)
        except Exception as e:
            self._hud.set_state("idle")
            self._feed_event(f"HUD online · Brain unavailable ({e})")
            # Cycle demo state labels (color stays cyan)
            self._demo_timer.start(4000)

        # Allow Ctrl+C to quit
        signal.signal(signal.SIGINT, lambda *_: self.quit())

    def _build_tray_menu(self):
        menu = QMenu()

        # Show/hide toggle
        toggle = QAction("Show/Hide HUD", menu)
        toggle.triggered.connect(self._toggle_hud)
        menu.addAction(toggle)

        menu.addSeparator()

        # Corner submenu
        corner_menu = menu.addMenu("Move to corner")
        for corner in self.CORNERS:
            act = QAction(corner.replace("_", " ").title(), menu)
            act.triggered.connect(lambda checked=False, c=corner: self._move_to(c))
            corner_menu.addAction(act)
        menu.addMenu(corner_menu)

        # Expand/collapse
        expand = QAction("Refresh (Brain ambient check)", menu)
        expand.triggered.connect(self._refresh_brain)
        menu.addAction(expand)

        menu.addSeparator()

        # Demo state cycle (testing)
        cycle = QAction("Cycle State (Demo)", menu)
        cycle.triggered.connect(self._cycle_demo_state)
        menu.addAction(cycle)

        menu.addSeparator()

        # Quit
        quit_act = QAction("Quit SONIC HUD", menu)
        quit_act.triggered.connect(self.quit)
        menu.addAction(quit_act)

        self._tray.setContextMenu(menu)

        # Left-click toggles HUD
        self._tray.activated.connect(self._on_tray_click)

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_hud()

    def _toggle_hud(self):
        if self._hud.isVisible():
            self._hud.hide()
            self._tray.showMessage(
                "SONIC HUD", "Hidden. Right-click tray icon to show again.",
                QSystemTrayIcon.MessageIcon.Information, 2000
            )
        else:
            self._hud.show()
            self._feed_event("HUD shown")

    def _move_to(self, corner: str):
        self._hud.show_at(corner)
        self._current_corner_idx = self.CORNERS.index(corner)
        self._feed_event(f"HUD moved to {corner.replace('_', ' ')}")

    def _cycle_demo_state(self):
        state = self._demo_states[self._demo_idx % len(self._demo_states)]
        audio = {"idle": 0.05, "listening": 0.6, "thinking": 0.3,
                 "speaking": 0.8, "ready": 0.1, "error": 0.0}.get(state, 0.1)
        # ONLY label text changes — color stays SONIC cyan always
        self._hud.set_state(state)
        self._hud.set_audio_level(audio)
        self._demo_idx += 1

    def _refresh_brain(self):
        """Trigger brain ambient check + show notification."""
        if self._brain is None:
            self._feed_event("Brain not connected")
            return
        try:
            snap = self._brain.ambient_check()
            router = snap.subsystem_status.get("router", {}).get("available")
            self._feed_event(f"Brain: router={router}")
        except Exception as e:
            self._feed_event(f"Brain check failed: {e}")

    def _update_from_brain(self):
        """Update HUD label from brain activity. Color stays cyan."""
        try:
            v = self._brain.pulse.vitals() if self._brain.pulse else {}
            cpu = v.get("cpu_pct")
            if cpu is None:
                cpu = 30
            if cpu > 70:
                self._hud.set_state("thinking")
                self._hud.set_audio_level(0.4)
            elif cpu > 40:
                self._hud.set_state("ready")
                self._hud.set_audio_level(0.1)
            else:
                self._hud.set_state("idle")
                self._hud.set_audio_level(0.05)
        except Exception:
            pass

    def _feed_event(self, message: str):
        """Show a tray notification."""
        try:
            self._tray.showMessage(
                "SONIC HUD", message,
                QSystemTrayIcon.MessageIcon.Information, 3000
            )
        except Exception:
            pass

    def run(self):
        """Start the event loop. Blocks until quit."""
        self._feed_event("SONIC HUD online · Top right corner")
        return self._app.exec()

    def quit(self):
        """Quit the HUD application."""
        self._tray.hide()
        self._hud.close()
        self._app.quit()


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("═" * 70)
    print("  SONIC AI — Floating HUD (always-on-top)")
    print("═" * 70)
    print()
    print("  HUD is now floating in your top-right corner.")
    print()
    print("  Interactions:")
    print("    • Left-click + drag      →  move HUD anywhere")
    print("    • Right-click on HUD     →  cycle corners")
    print("    • Double-click on HUD    →  toggle mini/expanded")
    print()
    print("  Tray icon (system tray) controls:")
    print("    • Left-click            →  toggle show/hide")
    print("    • Right-click           →  menu (corner, quit, etc.)")
    print()
    print("  State cycle: idle → listening → thinking → speaking → ready")
    print()
    print("  Press Ctrl+C in this terminal OR right-click tray → Quit")
    print("═" * 70)
    print()

    launcher = HUDLauncher()
    launcher.run()


if __name__ == "__main__":
    main()
