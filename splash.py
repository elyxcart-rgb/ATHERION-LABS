"""SONIC AI — Clean Splash Screen.

Minimal, elegant startup:
- Centered logo with glow
- Animated circular spinner
- "Starting up..." text
- Dark background
"""
from __future__ import annotations

import math
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QPen, QBrush, QPainterPath, QPixmap, QRegion,
)
from PyQt6.QtWidgets import QWidget


class SonicSplash(QWidget):
    """Clean splash — centered logo, spinner, minimal."""

    def __init__(self, on_done=None) -> None:
        super().__init__()
        self._on_done = on_done
        self._progress = 0.0
        self._done = False
        self._tick_count = 0
        self._alpha = 0.0

        # ── Theme colors ──
        self._C_BG = QColor("#0a0c10")
        self._C_PRI = QColor("#00d9ff")
        self._C_PRI_DIM = QColor("#004d66")

        # Load SONIC logo
        self._logo = self._load_logo()

        self.setWindowTitle("SONIC AI")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 400)

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

    def _tick(self) -> None:
        self._tick_count += 1
        self._alpha = min(1.0, self._tick_count / 40)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 - 20

        # ═══════════════════════════════════════════════════════════════
        # LAYER 1: Background
        # ═══════════════════════════════════════════════════════════════
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#0a0c10"))
        bg.setColorAt(0.5, QColor("#080a0e"))
        bg.setColorAt(1.0, QColor("#0a0c10"))
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, w, h)

        # ═══════════════════════════════════════════════════════════════
        # LAYER 2: Subtle background dots
        # ═══════════════════════════════════════════════════════════════
        dot_alpha = int(15 + math.sin(self._tick_count * 0.02) * 5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 217, 255, dot_alpha)))
        for row in range(0, h, 40):
            for col in range(0, w, 40):
                offset = 20 if (row // 40) % 2 else 0
                painter.drawEllipse(QPointF(col + offset, row), 1, 1)

        # ═══════════════════════════════════════════════════════════════
        # LAYER 3: Logo with glow
        # ═══════════════════════════════════════════════════════════════
        logo_size = 80
        logo_x = cx - logo_size // 2
        logo_y = cy - logo_size // 2 - 30

        if not self._logo.isNull():
            # Glow behind logo
            glow_r = 60
            glow_alpha = int(40 + math.sin(self._tick_count * 0.04) * 15)
            glow = QRadialGradient(cx, cy - 30, glow_r)
            glow.setColorAt(0.0, QColor(0, 150, 200, glow_alpha))
            glow.setColorAt(0.5, QColor(0, 100, 150, glow_alpha // 3))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(cx, cy - 30), glow_r, glow_r)

            # Draw logo
            scaled = self._logo.scaled(
                logo_size, logo_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Circular mask
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
            # Fallback: draw "◈" symbol
            symbol_alpha = int(200 * self._alpha)
            glow_r = 50
            glow = QRadialGradient(cx, cy - 30, glow_r)
            glow.setColorAt(0.0, QColor(0, 150, 200, 50))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(cx, cy - 30), glow_r, glow_r)

            painter.setFont(QFont("Segoe UI", 40, QFont.Weight.Bold))
            painter.setPen(QColor(0, 217, 255, symbol_alpha))
            painter.drawText(QRectF(logo_x, logo_y, logo_size, logo_size),
                           Qt.AlignmentFlag.AlignCenter, "◈")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 4: SONIC text
        # ═══════════════════════════════════════════════════════════════
        text_alpha = int(220 * self._alpha)
        text_y = logo_y + logo_size + 20

        painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        painter.setPen(QColor(0, 217, 255, text_alpha))
        painter.drawText(QRectF(0, text_y, w, 35),
                       Qt.AlignmentFlag.AlignCenter, "SONIC")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 5: Circular spinner
        # ═══════════════════════════════════════════════════════════════
        spinner_y = text_y + 50
        spinner_r = 18

        # Background circle (dim)
        bg_circle_alpha = int(30 * self._alpha)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        bg_pen = QPen(QColor(0, 77, 102, bg_circle_alpha))
        bg_pen.setWidth(2)
        painter.setPen(bg_pen)
        painter.drawEllipse(QPointF(cx, spinner_y), spinner_r, spinner_r)

        # Rotating arc
        arc_alpha = int(200 * self._alpha)
        arc_pen = QPen(QColor(0, 217, 255, arc_alpha))
        arc_pen.setWidth(3)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        arc_rect = QRectF(cx - spinner_r, spinner_y - spinner_r,
                         spinner_r * 2, spinner_r * 2)
        start_angle = self._tick_count * 8  # rotation speed
        span_angle = 90 * 16  # 90 degrees in 1/16th degree units
        painter.drawArc(arc_rect, start_angle, span_angle)

        # Small dot at arc tip
        dot_angle = math.radians(start_angle / 16)
        dot_x = cx + spinner_r * math.cos(dot_angle)
        dot_y = spinner_y - spinner_r * math.sin(dot_angle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 234, 255, arc_alpha)))
        painter.drawEllipse(QPointF(dot_x, dot_y), 3, 3)

        # ═══════════════════════════════════════════════════════════════
        # LAYER 6: "Starting up..." text
        # ═══════════════════════════════════════════════════════════════
        status_alpha = int(120 * self._alpha)
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Light))
        painter.setPen(QColor(107, 122, 138, status_alpha))
        painter.drawText(QRectF(0, spinner_y + 30, w, 20),
                       Qt.AlignmentFlag.AlignCenter, "Starting up...")

        # ═══════════════════════════════════════════════════════════════
        # LAYER 7: Version
        # ═══════════════════════════════════════════════════════════════
        from version import APP_VERSION
        ver_alpha = int(50 * self._alpha)
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Light))
        painter.setPen(QColor(74, 85, 104, ver_alpha))
        painter.drawText(QRectF(0, h - 35, w, 20),
                       Qt.AlignmentFlag.AlignCenter, f"v{APP_VERSION}")

        painter.end()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._progress_timer.stop()
        if self._on_done:
            self._on_done()
