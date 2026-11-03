"""SONIC AI — Apple-Level Splash Screen.

Premium first-impression experience:
- Pure black base with subtle radial cyan glow
- SONIC logo with breathing glow halo
- Spinner with trail (Apple activity-indicator style)
- "SONIC Apex" title + subtle subtitle
- Version + status pill at bottom
- Smooth fade-in on entry, fade-out on finish

Public surface:
    - SonicSplash(parent=None, on_done=None)
"""
from __future__ import annotations

import math
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QPen, QBrush, QPainterPath, QPixmap, QRegion,
)
from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect

from apple_design import Tokens


class SonicSplash(QWidget):
    """Apple-style splash — centered logo, spinner, premium typography."""

    def __init__(self, on_done=None, parent=None) -> None:
        super().__init__(parent)
        self._on_done = on_done
        self._progress = 0.0
        self._done = False
        self._tick_count = 0
        self._alpha = 0.0

        # Load SONIC logo (tries .png first, falls back to .ico)
        self._logo = self._load_logo()

        self.setWindowTitle("SONIC AI")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 520)

        # Animation timer (~60fps)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        # Auto-finish timer
        self._finish_timer = QTimer(self)
        self._finish_timer.setSingleShot(True)
        self._finish_timer.timeout.connect(self._finish)
        self._finish_timer.start(3500)

        # Progress animation
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._advance_progress)
        self._progress_timer.start(30)

        # Smooth fade-in: start invisible, fade up over first 600ms
        self.setWindowOpacity(0.0)
        QTimer.singleShot(20, self._fade_in)

    def _load_logo(self) -> QPixmap:
        """Load SONIC logo from config directory."""
        candidates = [
            Path(__file__).resolve().parent / "config" / "sonic.png",
            Path(__file__).resolve().parent / "sonic-frontend-theme" / "config" / "sonic.png",
            Path(__file__).resolve().parent / "config" / "sonic.ico",
        ]
        for path in candidates:
            if path.exists():
                pix = QPixmap(str(path))
                if not pix.isNull():
                    return pix
        return QPixmap()

    def _advance_progress(self) -> None:
        if self._progress < 100:
            remaining = 100 - self._progress
            self._progress += max(0.3, remaining * 0.04)

    def _fade_in(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(600)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._fade_anim = anim

    def _fade_out(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(380)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self._after_fade_out)
        anim.start()
        self._fade_anim = anim

    def _after_fade_out(self):
        if self._on_done:
            self._on_done()

    def _tick(self) -> None:
        self._tick_count += 1
        self._alpha = min(1.0, self._tick_count / 40)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 - 30

        accent = QColor(Tokens.CYAN)
        white = QColor("#ffffff")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 1: Pure-black base + soft radial glow
        # ═══════════════════════════════════════════════════════════════
        painter.setBrush(QBrush(QColor(0, 0, 0)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, w, h)

        # Soft radial ambient glow (Apple-style hero lighting)
        glow_radius = max(w, h) * 0.6
        radial = QRadialGradient(cx, cy, glow_radius)
        radial.setColorAt(0.0, QColor(0, 100, 160, 26))
        radial.setColorAt(0.4, QColor(0, 60, 110, 12))
        radial.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(radial))
        painter.drawRect(0, 0, w, h)

        # ═══════════════════════════════════════════════════════════════
        # LAYER 2: Subtle dot grid (Apple-style fine texture)
        # ═══════════════════════════════════════════════════════════════
        dot_alpha = int(20 + math.sin(self._tick_count * 0.02) * 6)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(accent.red(), accent.green(), accent.blue(), dot_alpha)))
        for row in range(0, h, 36):
            for col in range(0, w, 36):
                offset = 18 if (row // 36) % 2 else 0
                painter.drawEllipse(QPointF(col + offset, row), 0.8, 0.8)

        # ═══════════════════════════════════════════════════════════════
        # LAYER 3: Logo with breathing glow halo
        # ═══════════════════════════════════════════════════════════════
        logo_size = 96
        logo_x = cx - logo_size // 2
        logo_y = cy - logo_size // 2 - 50

        # Breathing glow
        glow_r = 75 + math.sin(self._tick_count * 0.04) * 8
        glow_alpha = int(60 + math.sin(self._tick_count * 0.04) * 20)
        glow = QRadialGradient(cx, cy - 50, glow_r)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue() - 40, glow_alpha))
        glow.setColorAt(0.5, QColor(0, 100, 150, glow_alpha // 3))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy - 50), glow_r, glow_r)

        if not self._logo.isNull():
            scaled = self._logo.scaled(
                logo_size, logo_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            mask = QPixmap(logo_size, logo_size)
            mask.fill(Qt.GlobalColor.transparent)
            mask_painter = QPainter(mask)
            mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            mask_painter.setBrush(QBrush(QColor(Qt.GlobalColor.white)))
            mask_painter.setPen(Qt.PenStyle.NoPen)
            mask_painter.drawEllipse(0, 0, logo_size, logo_size)
            mask_painter.end()

            result = QPixmap(logo_size, logo_size)
            result.fill(Qt.GlobalColor.transparent)
            result_painter = QPainter(result)
            result_painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            result_painter.setClipRegion(QRegion(mask.mask()))
            result_painter.drawPixmap(0, 0, scaled)
            result_painter.end()

            painter.setOpacity(self._alpha)
            painter.drawPixmap(logo_x, logo_y, result)
            painter.setOpacity(1.0)
        else:
            # Fallback: draw "◈" diamond symbol
            symbol_alpha = int(220 * self._alpha)
            painter.setFont(Tokens.font_mono(40, QFont.Weight.Bold))
            painter.setPen(QColor(accent.red(), accent.green(), accent.blue(), symbol_alpha))
            painter.drawText(QRectF(logo_x, logo_y, logo_size, logo_size),
                           Qt.AlignmentFlag.AlignCenter, "◈")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 4: Title "SONIC Apex" (split typography — SONIC bold, Apex light)
        # ═══════════════════════════════════════════════════════════════
        text_alpha = int(255 * self._alpha)
        title_y = logo_y + logo_size + 32

        # "SONIC" — primary word, bold, cyan
        sonic_font = Tokens.font(28, QFont.Weight.Bold)
        painter.setFont(sonic_font)
        sonic_metrics = painter.fontMetrics()
        sonic_width = sonic_metrics.horizontalAdvance("SONIC")

        # "Apex" — accent word, light, dim cyan
        apex_font = Tokens.font(28, QFont.Weight.Light)
        painter.setFont(apex_font)
        apex_metrics = painter.fontMetrics()
        apex_width = apex_metrics.horizontalAdvance(" Apex")

        total_w = sonic_width + apex_width
        start_x = (w - total_w) // 2

        # Draw "SONIC"
        painter.setFont(sonic_font)
        painter.setPen(QColor(accent.red(), accent.green(), accent.blue(), text_alpha))
        sonic_rect = QRectF(start_x, title_y, sonic_width, 36)
        painter.drawText(sonic_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "SONIC")

        # Draw " Apex"
        painter.setFont(apex_font)
        painter.setPen(QColor(200, 220, 235, text_alpha))
        apex_rect = QRectF(start_x + sonic_width, title_y, apex_width + 6, 36)
        painter.drawText(apex_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, " Apex")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 5: Apple-style activity spinner (rotating arc with dot)
        # ═══════════════════════════════════════════════════════════════
        spinner_y = title_y + 70
        spinner_r = 16

        # Dim background ring
        bg_pen = QPen(QColor(255, 255, 255, 22))
        bg_pen.setWidth(2)
        painter.setPen(bg_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, spinner_y), spinner_r, spinner_r)

        # Bright rotating arc
        arc_alpha = int(220 * self._alpha)
        arc_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), arc_alpha))
        arc_pen.setWidth(2)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        arc_rect = QRectF(cx - spinner_r, spinner_y - spinner_r,
                         spinner_r * 2, spinner_r * 2)
        start_angle = self._tick_count * 8
        span_angle = 110 * 16  # 110° arc
        painter.drawArc(arc_rect, start_angle, span_angle)

        # Small leading dot at arc tip
        dot_angle = math.radians(start_angle / 16)
        dot_x = cx + spinner_r * math.cos(dot_angle)
        dot_y = spinner_y - spinner_r * math.sin(dot_angle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(white.red(), white.green(), white.blue(), arc_alpha)))
        painter.drawEllipse(QPointF(dot_x, dot_y), 2.5, 2.5)

        # ═══════════════════════════════════════════════════════════════
        # LAYER 6: "Initializing" status text
        # ═══════════════════════════════════════════════════════════════
        status_alpha = int(180 * self._alpha)
        painter.setFont(Tokens.font(11))
        painter.setPen(QColor(180, 195, 215, status_alpha))
        painter.drawText(QRectF(0, spinner_y + 30, w, 18),
                       Qt.AlignmentFlag.AlignCenter, "Initializing…")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 7: Version footer (subtle pill)
        # ═══════════════════════════════════════════════════════════════
        from version import APP_VERSION
        version_text = f"v{APP_VERSION}"
        ver_alpha = int(110 * self._alpha)

        # Pill background
        pill_font = Tokens.font(9, QFont.Weight.Medium)
        painter.setFont(pill_font)
        fm = painter.fontMetrics()
        pill_w = fm.horizontalAdvance(version_text) + 20
        pill_h = 20
        pill_x = (w - pill_w) // 2
        pill_y = h - 38

        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)
        path = QPainterPath()
        path.addRoundedRect(pill_rect, pill_h / 2, pill_h / 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 18)))
        painter.drawPath(path)

        # Version text
        painter.setFont(pill_font)
        painter.setPen(QColor(180, 195, 215, ver_alpha))
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, version_text)

        painter.end()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._progress_timer.stop()
        # Smooth fade-out before triggering on_done
        self._fade_out()
