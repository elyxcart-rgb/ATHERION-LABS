"""SONIC AI — Voice Waveform Visualizer.

Cinematic audio-reactive waveform. Used as a "speaking / listening"
indicator.

Public API:
    WaveformViz(parent=None, width=720, height=120, bars=48)
    .set_level(level: float)             # 0..1 — drives bar heights
    .push_sample(sample: float)          # 0..1 — incremental drive
    .set_active(bool)                    # True = animated pulse
    .set_color(r, g, b)
"""
from __future__ import annotations

import math
import random
from collections import deque
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QLinearGradient, QPen, QBrush, QFont,
)
from PyQt6.QtWidgets import QWidget


class WaveformViz(QWidget):
    """Audio-reactive waveform with rolling history."""

    def __init__(self, parent=None, width: int = 720, height: int = 120, bars: int = 48):
        super().__init__(parent)
        self._width = width
        self._height = height
        self._bars = bars
        self.setFixedSize(width, height)

        # Rolling history of bar heights (0..1)
        self._history: deque[float] = deque([0.1] * bars, maxlen=bars)
        self._level = 0.0
        self._target_level = 0.1
        self._tick = 0
        self._active = True
        self._color = QColor(0, 220, 255)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_anim)
        self._timer.start(40)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_level(self, level: float):
        self._target_level = max(0.0, min(1.0, level))

    def push_sample(self, sample: float):
        self._history.append(max(0.0, min(1.0, sample)))
        self._target_level = max(0.0, min(1.0, sample))

    def set_active(self, active: bool):
        self._active = active

    def set_color(self, r: int, g: int, b: int):
        self._color = QColor(r, g, b)

    # ── Internals ────────────────────────────────────────────────────────────

    def _tick_anim(self):
        self._tick += 1
        if self._active:
            # Smooth level
            self._level += (self._target_level - self._level) * 0.18
            # Add noise + drift
            noise = (random.random() - 0.5) * 0.15
            new_sample = max(0.05, min(1.0, self._level + noise))
            self._history.append(new_sample)
            # Slowly decay target so we don't stay pinned
            self._target_level *= 0.97
            if self._target_level < 0.05:
                self._target_level = 0.05
        else:
            # Settle to baseline
            self._history.append(0.05)
            self._level = 0.05
        self.update()

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self._color
        w = self._width
        h = self._height

        # Background
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(0, 0, 0, 60))
        bg.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 18))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(0, 0, w, h, 8, 8)

        # Centerline
        center_pen = QPen(QColor(c.red(), c.green(), c.blue(), 50), 1)
        painter.setPen(center_pen)
        painter.drawLine(0, h // 2, w, h // 2)

        # Bars
        bar_w = w / self._bars
        gap = bar_w * 0.35
        for i, value in enumerate(self._history):
            bar_height = max(2.0, value * (h * 0.92))
            x = i * bar_w + gap / 2
            y = (h - bar_height) / 2
            # Color gradient: bottom→top from accent to white
            grad = QLinearGradient(0, y + bar_height, 0, y)
            grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 180))
            grad.setColorAt(0.5, QColor(
                min(255, c.red() + 60),
                min(255, c.green() + 60),
                min(255, c.blue() + 60), 220))
            grad.setColorAt(1.0, QColor(255, 255, 255, 240))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(int(x), int(y), int(bar_w - gap),
                                     int(bar_height), 2, 2)

        # Top reflective glow
        if self._active and self._level > 0.2:
            glow = QLinearGradient(0, 0, 0, h * 0.4)
            glow.setColorAt(0.0, QColor(255, 255, 255, int(40 * self._level)))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawRect(0, 0, w, int(h * 0.4))

        # Label
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.setPen(QColor(c.red(), c.green(), c.blue(), 180))
        painter.drawText(QRectF(8, h - 18, 100, 14),
                          Qt.AlignmentFlag.AlignLeft, "CHANNEL 01")

        # Frequency indicator (fake)
        freq_label = f"{self._level * 100:>5.1f}%"
        painter.drawText(QRectF(w - 108, h - 18, 100, 14),
                          Qt.AlignmentFlag.AlignRight, freq_label)

        painter.end()
