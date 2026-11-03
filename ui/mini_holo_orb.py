"""SONIC AI — Mini Holographic Orb.

A compact 3D-projected holographic sphere for use inside the floating HUD.
Smaller, faster, fewer particles than the full HoloOrb3D — designed
to feel "alive" without burning CPU.

Public API:
    MiniHoloOrb(parent=None, size=44)
    .set_state(state)         # "idle"|"listening"|"thinking"|"speaking"|"ready"|"error"
    .set_audio_level(level)   # 0..1
    .set_color(r, g, b)
"""
from __future__ import annotations

import math
import random
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import (
    QColor, QPainter, QRadialGradient, QLinearGradient, QPen, QBrush,
)
from PyQt6.QtWidgets import QWidget


class MiniHoloOrb(QWidget):
    """Compact holographic sphere — the SONIC brand mark."""

    STATE_COLORS = {
        "idle":      QColor(0, 200, 220),
        "listening": QColor(0, 230, 180),
        "thinking":  QColor(170, 100, 255),
        "speaking":  QColor(80, 200, 255),
        "ready":     QColor(60, 230, 130),
        "error":     QColor(255, 80, 80),
        "scanning":  QColor(255, 180, 80),
    }

    def __init__(self, parent=None, size: int = 44):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

        self._tick = 0
        self._state = "idle"
        self._audio = 0.0
        self._target_audio = 0.0
        self._color = self.STATE_COLORS["idle"]
        self._particles = [
            {"angle": random.uniform(0, 2 * math.pi),
             "radius": random.uniform(0.85, 1.15),
             "size": random.uniform(0.6, 1.4),
             "alpha": random.uniform(80, 200),
             "speed": random.uniform(0.005, 0.025),
             "phase": random.uniform(0, math.pi * 2)}
            for _ in range(12)
        ]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_anim)
        self._timer.start(30)

    def set_state(self, state: str):
        self._state = state
        if state in self.STATE_COLORS:
            self._color = self.STATE_COLORS[state]

    def set_audio_level(self, level: float):
        self._target_audio = max(0.0, min(1.0, level))

    def set_color(self, r: int, g: int, b: int):
        self._color = QColor(r, g, b)

    def _tick_anim(self):
        self._tick += 1
        self._audio += (self._target_audio - self._audio) * 0.15
        for p in self._particles:
            p["angle"] += p["speed"]
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        c = self._color
        r = min(self.width(), self.height()) * 0.34 * (1 + self._audio * 0.15)
        pulse = (math.sin(self._tick * 0.08) + 1) / 2

        # Atmosphere bloom
        bloom = QRadialGradient(cx, cy, r * 2.2)
        bloom.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 110))
        bloom.setColorAt(0.4, QColor(c.red(), c.green(), c.blue(), 35))
        bloom.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bloom))
        p.drawEllipse(QPointF(cx, cy), r * 2.2, r * 2.2)

        # Outer ring with tick marks
        outer_r = r * 1.05
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 120), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), outer_r, outer_r)
        # Tilted equatorial ring
        p.save()
        p.translate(cx, cy)
        p.rotate(math.degrees(self._tick * 0.5))
        p.scale(1.0, 0.3)
        p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 160), 1))
        p.drawEllipse(QPointF(0, 0), outer_r * 0.95, outer_r * 0.95)
        p.restore()

        # Tick marks every 45°
        for deg in range(0, 360, 45):
            rad = math.radians(deg)
            x1 = cx + (outer_r - 2) * math.cos(rad)
            y1 = cy + (outer_r - 2) * math.sin(rad)
            x2 = cx + (outer_r + 2) * math.cos(rad)
            y2 = cy + (outer_r + 2) * math.sin(rad)
            p.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 180), 1))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Inner core sphere (radial gradient)
        inner_r = r * 0.65 + pulse * 2
        inner_grad = QRadialGradient(cx, cy, inner_r)
        inner_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        inner_grad.setColorAt(0.4, QColor(c.red(), c.green() + 30, c.blue(), 200))
        inner_grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(inner_grad))
        p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # Specular highlight
        sx = cx - r * 0.2
        sy = cy - r * 0.25
        spec = QRadialGradient(sx, sy, r * 0.4)
        spec.setColorAt(0.0, QColor(255, 255, 255, 230))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(spec))
        p.drawEllipse(QPointF(sx, sy), r * 0.4, r * 0.4)

        # Orbital particles
        for part in self._particles:
            ox = cx + math.cos(part["angle"]) * part["radius"] * outer_r
            oy = cy + math.sin(part["angle"]) * part["radius"] * outer_r * 0.4
            flicker = (math.sin(self._tick * 0.1 + part["phase"]) + 1) / 2
            alpha = int(part["alpha"] * (0.4 + 0.6 * flicker))
            p.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            p.drawEllipse(QPointF(ox, oy), part["size"], part["size"])

        p.end()
