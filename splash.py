"""SONIC AI — Animated Splash Screen.

Loading animation with SONIC branding and 'Limited Time Free' banner.
Pure PyQt6 — no external dependencies.
"""
from __future__ import annotations

import math
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QFontMetrics, QPen, QBrush, QPainterPath,
)
from PyQt6.QtWidgets import QWidget


class SonicSplash(QWidget):
    """Animated splash screen with pulsing orb and loading bar."""

    def __init__(self, on_done=None) -> None:
        super().__init__()
        self._on_done = on_done
        self._progress = 0.0
        self._angle = 0.0
        self._pulse = 0.0
        self._particles = []
        self._orb_radius = 40
        self._loaded = False
        self._done = False

        self.setWindowTitle("SONIC AI")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(480, 640)

        # ── Animation timer ──────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

        # ── Auto-finish timer ────────────────────────────────────────────
        self._finish_timer = QTimer(self)
        self._finish_timer.setSingleShot(True)
        self._finish_timer.timeout.connect(self._finish)
        self._finish_timer.start(4000)  # 4 seconds total

        # ── Progress animation ───────────────────────────────────────────
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._advance_progress)
        self._progress_timer.start(30)

    def _advance_progress(self) -> None:
        if self._progress < 100:
            # Smooth easing
            remaining = 100 - self._progress
            self._progress += max(0.3, remaining * 0.04)

    def _tick(self) -> None:
        self._angle += 2.5
        self._pulse = (math.sin(self._angle * 0.05) + 1) / 2  # 0..1

        # Spawn particles
        if len(self._particles) < 20 and self._progress < 95:
            import random
            self._particles.append({
                "x": 240 + random.uniform(-30, 30),
                "y": 320,
                "vx": random.uniform(-0.5, 0.5),
                "vy": random.uniform(-2.5, -1.0),
                "life": 1.0,
                "size": random.uniform(2, 5),
            })

        # Update particles
        for p in self._particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] -= 0.015

        self._particles = [p for p in self._particles if p["life"] > 0]

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 - 40

        # ── Background (dark with subtle gradient) ───────────────────────
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(8, 10, 18))
        bg.setColorAt(0.5, QColor(12, 14, 24))
        bg.setColorAt(1.0, QColor(8, 10, 18))
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 20, 20)

        # ── Outer glow ───────────────────────────────────────────────────
        glow_size = 160 + self._pulse * 20
        glow = QRadialGradient(cx, cy, glow_size)
        glow_alpha = int(40 + self._pulse * 30)
        glow.setColorAt(0.0, QColor(0, 212, 255, glow_alpha))
        glow.setColorAt(0.5, QColor(0, 150, 255, glow_alpha // 3))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), glow_size, glow_size)

        # ── Orb (inner ring) ─────────────────────────────────────────────
        ring_pen = QPen(QColor(0, 212, 255, 180), 3)
        painter.setPen(ring_pen)
        ring_r = 50
        painter.drawEllipse(QPointF(cx, cy), ring_r, ring_r)

        # ── Rotating arc ─────────────────────────────────────────────────
        arc_pen = QPen(QColor(0, 212, 255, 220), 4)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        arc_r = 50
        rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
        painter.drawArc(rect, int(self._angle * 16), 90 * 16)

        # ── Inner orb (solid glow) ──────────────────────────────────────
        orb_r = self._orb_radius + self._pulse * 5
        orb_grad = QRadialGradient(cx, cy, orb_r)
        orb_grad.setColorAt(0.0, QColor(0, 240, 255, 255))
        orb_grad.setColorAt(0.3, QColor(0, 180, 255, 200))
        orb_grad.setColorAt(0.6, QColor(0, 100, 200, 80))
        orb_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(orb_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # ── Core (bright center) ────────────────────────────────────────
        core_r = 15 + self._pulse * 3
        core_grad = QRadialGradient(cx, cy, core_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        core_grad.setColorAt(0.4, QColor(0, 240, 255, 200))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ── Particles ────────────────────────────────────────────────────
        for p in self._particles:
            alpha = int(p["life"] * 180)
            col = QColor(0, 212, 255, alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(col))
            painter.drawEllipse(QPointF(p["x"], p["y"]), p["size"], p["size"])

        # ── SONIC AI title ──────────────────────────────────────────────
        title_font = QFont("Segoe UI", 32, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(0, 212, 255, 240))
        title_rect = QRectF(0, cy + 70, w, 50)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "SONIC AI")

        # ── Subtitle ─────────────────────────────────────────────────────
        sub_font = QFont("Segoe UI", 11)
        painter.setFont(sub_font)
        painter.setPen(QColor(150, 180, 200, 160))
        sub_rect = QRectF(0, cy + 118, w, 30)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "Your AI Assistant")

        # ── Progress bar ─────────────────────────────────────────────────
        bar_w = 300
        bar_h = 6
        bar_x = (w - bar_w) / 2
        bar_y = cy + 170

        # Bar background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(30, 40, 50)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 3, 3)

        # Bar fill
        fill_w = bar_w * min(self._progress, 100) / 100
        if fill_w > 0:
            bar_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            bar_grad.setColorAt(0.0, QColor(0, 180, 255))
            bar_grad.setColorAt(0.5, QColor(0, 240, 255))
            bar_grad.setColorAt(1.0, QColor(0, 212, 255))
            painter.setBrush(QBrush(bar_grad))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 3, 3)

        # ── Loading text ─────────────────────────────────────────────────
        load_font = QFont("Segoe UI", 10)
        painter.setFont(load_font)
        painter.setPen(QColor(120, 140, 160, 200))
        load_rect = QRectF(0, bar_y + 20, w, 20)
        pct = min(int(self._progress), 100)
        painter.drawText(load_rect, Qt.AlignmentFlag.AlignCenter, f"Loading... {pct}%")

        # ── Limited Time Free banner ────────────────────────────────────
        banner_y = h - 90
        banner_h = 52

        # Banner background with gradient
        banner_bg = QLinearGradient(0, banner_y, 0, banner_y + banner_h)
        banner_bg.setColorAt(0.0, QColor(0, 212, 255, 30))
        banner_bg.setColorAt(1.0, QColor(0, 212, 255, 10))
        painter.setPen(QPen(QColor(0, 212, 255, 100), 1))
        painter.setBrush(QBrush(banner_bg))
        painter.drawRoundedRect(QRectF(40, banner_y, w - 80, banner_h), 12, 12)

        # "LIMITED TIME FREE" text
        banner_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(banner_font)
        painter.setPen(QColor(0, 240, 255))
        text_rect = QRectF(0, banner_y + 2, w, 30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "LIMITED TIME FREE")

        # Sub-text
        small_font = QFont("Segoe UI", 9)
        painter.setFont(small_font)
        painter.setPen(QColor(100, 180, 220, 180))
        sub_rect2 = QRectF(0, banner_y + 32, w, 18)
        painter.drawText(sub_rect2, Qt.AlignmentFlag.AlignCenter, "Get all features free during beta")

        # ── Bottom version ───────────────────────────────────────────────
        ver_font = QFont("Segoe UI", 8)
        painter.setFont(ver_font)
        painter.setPen(QColor(80, 100, 120, 120))
        ver_rect = QRectF(0, h - 30, w, 20)
        painter.drawText(ver_rect, Qt.AlignmentFlag.AlignCenter, "v1.0.2")

        painter.end()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._progress_timer.stop()
        if self._on_done:
            self._on_done()
