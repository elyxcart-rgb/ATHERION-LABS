"""SONIC AI — Floating HUD (clean minimal version).

Always-on-top overlay. Small, cyan-themed, no over-design.

  ┌──────────────────────────────────────────┐
  │                                          │
  │   ◯       READY              16:51:52     │
  │   ↑                                 ••• │
  │   orb                                  │   ← only 1 subtle dot, no over-decoration
  └──────────────────────────────────────────┘

Visual rules:
  - ALWAYS SONIC cyan (no per-state color shifts — keep theme consistent)
  - Single capsule shape
  - Mini orb (left, ~36px), state label, time
  - No hex grid, no ribbons, no CPU bar — minimum decoration
  - Subtle pulsing dot on the right (only when audio active)

Public API:
    FloatingHUD()
    .show_at("top_right"|"top_left"|"bottom_right"|"bottom_left")
    .set_state(str)              # updates label text only (color stays cyan)
    .set_audio_level(0..1)        # pulses the orb + right dot
    .close()
    .get_stats() -> dict
"""
from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PyQt6.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QPen, QBrush,
    QFont, QPainterPath, QPixmap, QIcon, QAction, QMouseEvent,
)
from PyQt6.QtWidgets import (
    QWidget, QLabel, QSizePolicy, QGraphicsDropShadowEffect, QApplication,
    QSystemTrayIcon, QMenu,
)

from ui.mini_holo_orb import MiniHoloOrb


# ═════════════════════════════════════════════════════════════════════════════
# SONIC theme — only cyan + dim gray
# ═════════════════════════════════════════════════════════════════════════════

SONIC_CYAN      = QColor(0, 220, 255)
SONIC_CYAN_DIM  = QColor(0, 200, 255, 140)
SONIC_VIOLET    = QColor(170, 100, 255)
SURFACE_BG      = QColor(12, 18, 32, 235)
TEXT_PRIMARY    = QColor(220, 240, 255)
TEXT_SECONDARY  = QColor(140, 170, 200)


# ═════════════════════════════════════════════════════════════════════════════
# Capsule backdrop — minimal: gradient fill + thin cyan border
# ═════════════════════════════════════════════════════════════════════════════

class _CapsuleBackdrop(QWidget):
    """Just paints the capsule background + border. Nothing else."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio = 0.0
        self._target_audio = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_audio_level(self, level: float):
        self._target_audio = max(0.0, min(1.0, level))

    def _tick(self):
        self._audio += (self._target_audio - self._audio) * 0.15
        # Only repaint when audio changes noticeably
        if abs(self._target_audio - self._audio) > 0.005:
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r = h / 2

        # Vertical gradient
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(18, 28, 48, 240))
        bg.setColorAt(1.0, QColor(6, 10, 22, 240))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(0, 0, w, h, r, r)

        # Subtle inner top highlight (1px line near top)
        hl = QLinearGradient(0, 0, 0, 4)
        hl.setColorAt(0.0, QColor(255, 255, 255, 30))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hl))
        # Clip to capsule shape
        clip = QPainterPath()
        clip.addRoundedRect(0, 0, w, h, r, r)
        p.setClipPath(clip)
        p.drawRect(0, 0, w, 4)
        p.setClipping(False)

        # Thin cyan border
        border = QPen(SONIC_CYAN, 1)
        border.setColor(SONIC_CYAN_DIM)
        p.setPen(border)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)

        # Subtle pulsing dot on the right when audio active
        if self._audio > 0.05:
            cx = w - 14
            cy = h / 2
            glow = QRadialGradient(cx, cy, 12)
            alpha = int(self._audio * 150)
            glow.setColorAt(0.0, QColor(SONIC_CYAN.red(), SONIC_CYAN.green(),
                                         SONIC_CYAN.blue(), alpha))
            glow.setColorAt(1.0, QColor(SONIC_CYAN.red(), SONIC_CYAN.green(),
                                         SONIC_CYAN.blue(), 0))
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), 6, 6)
            p.setBrush(QBrush(QColor(SONIC_CYAN.red(), SONIC_CYAN.green(),
                                      SONIC_CYAN.blue(), 220)))
            p.drawEllipse(QPointF(cx, cy), 2, 2)

        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# FloatingHUD — minimal, always cyan
# ═════════════════════════════════════════════════════════════════════════════

class FloatingHUD(QWidget):
    """Compact SONIC floating HUD — minimal capsule, cyan theme."""

    def __init__(self, brain=None):
        super().__init__()
        self._brain = brain
        self._expanded = False
        self._state = "idle"
        self._dragging = False
        self._drag_offset = None

        # Always on top, frameless, tool window (no taskbar entry)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Compact size
        self._compact_size = QSize(220, 60)
        self.resize(self._compact_size)

        # Backdrop (just fills background)
        self._backdrop = _CapsuleBackdrop(self)
        self._backdrop.setGeometry(0, 0, self.width(), self.height())

        # Mini orb (fixed cyan — always SONIC theme color)
        self._orb = MiniHoloOrb(self, size=36)
        self._orb.set_state("idle")
        self._orb.set_color(0, 220, 255)  # always cyan
        self._orb.move(8, 12)

        # State label (always cyan)
        self._state_lbl = QLabel("READY", self)
        self._state_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._state_lbl.setStyleSheet(
            f"color: {SONIC_CYAN.name()}; "
            f"background: transparent; letter-spacing: 2.5px;"
        )
        self._state_lbl.setGeometry(56, 8, 120, 18)
        self._state_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        # Time label (dim)
        self._time_lbl = QLabel("", self)
        self._time_lbl.setFont(QFont("Consolas", 13))
        self._time_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY.name()}; "
            f"background: transparent; letter-spacing: 1px;"
        )
        self._time_lbl.setGeometry(56, 30, 140, 22)
        self._time_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._update_time()

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 220, 255, 60))
        self.setGraphicsEffect(shadow)

        # Mouse event handling
        self.setMouseTracking(True)

        # Time tick
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    # ── Public ───────────────────────────────────────────────────────────────

    def show_at(self, corner: str = "top_right"):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.show()
            return
        geo = screen.availableGeometry()
        if corner == "top_right":
            x, y = geo.right() - self.width() - 20, geo.top() + 20
        elif corner == "top_left":
            x, y = geo.left() + 20, geo.top() + 20
        elif corner == "bottom_right":
            x, y = geo.right() - self.width() - 20, geo.bottom() - self.height() - 20
        elif corner == "bottom_left":
            x, y = geo.left() + 20, geo.bottom() - self.height() - 20
        else:
            x, y = geo.right() - self.width() - 20, geo.top() + 20
        self.move(x, y)
        self.show()

    def set_state(self, state: str):
        """Just updates the label text. Color stays cyan always."""
        self._state = state
        # ORB stays cyan (do NOT change color based on state — keep theme)
        # Only pass non-color state info to orb (audio level drives animation)
        # Label
        label_map = {
            "idle":      "READY",
            "listening": "LISTENING",
            "thinking":  "THINKING",
            "speaking":  "SPEAKING",
            "ready":     "READY",
            "error":     "ERROR",
            "scanning":  "SCANNING",
        }
        self._state_lbl.setText(label_map.get(state, state.upper()))

    def set_audio_level(self, level: float):
        """0..1 — pulses the orb + right-side dot."""
        # Orb's audio level still changes (for visual life)
        self._orb.set_audio_level(level)
        self._backdrop.set_audio_level(level)

    def get_stats(self) -> dict:
        return {
            "state": self._state,
            "always_on_top": True,
            "size": f"{self.width()}x{self.height()}",
            "color": "cyan",
        }

    # ── Mouse handling ───────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self._cycle_corner()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._dragging:
            self._dragging = False
            event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self._brain is not None and hasattr(self._brain, "ambient_check"):
            self._brain.ambient_check()
        event.accept()

    # ── Internals ────────────────────────────────────────────────────────────

    def _tick(self):
        self._update_time()

    def _update_time(self):
        self._time_lbl.setText(datetime.now().strftime("%H:%M:%S"))

    def _cycle_corner(self):
        corners = ["top_right", "top_left", "bottom_left", "bottom_right"]
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        for corner in corners:
            self.show_at(corner)
            # Don't cycle on its own — just return after this show
            return
        self.show_at("top_right")
