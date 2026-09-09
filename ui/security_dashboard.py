"""SONIC AI — Security Dashboard.

Visual security status display for the main UI.
Shows real-time security metrics, threats, and protection status.
"""
from __future__ import annotations

import time
from datetime import datetime
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QRadialGradient, QLinearGradient,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGraphicsDropShadowEffect,
)


class SecurityMeter(QWidget):
    """Circular security health meter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 100
        self._target = 100
        self._pulse = 0
        self.setFixedSize(120, 120)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)

    def set_value(self, v: int):
        self._target = max(0, min(100, v))

    def _tick(self):
        self._value += (self._target - self._value) * 0.1
        self._pulse = (self._pulse + 3) % 360
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = 60, 60
        r = 45

        # Background ring
        bg_pen = QPen(QColor(30, 40, 50))
        bg_pen.setWidth(8)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Value ring
        if self._value >= 80:
            color = QColor(0, 200, 150)
        elif self._value >= 50:
            color = QColor(255, 180, 50)
        else:
            color = QColor(255, 80, 80)

        val_pen = QPen(color)
        val_pen.setWidth(8)
        val_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(val_pen)

        span = int(self._value * 3.6 * 16)
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.drawArc(rect, 90 * 16, -span)

        # Center text
        p.setPen(QColor(200, 220, 240))
        p.setFont(QFont("Segoe UI", 20, QFont.Weight.DemiBold))
        p.drawText(QRectF(cx - 30, cy - 18, 60, 36),
                   Qt.AlignmentFlag.AlignCenter, f"{int(self._value)}")

        p.setPen(QColor(100, 120, 140))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(cx - 30, cy + 14, 60, 16),
                   Qt.AlignmentFlag.AlignCenter, "HEALTH")

        p.end()


class ThreatIndicator(QWidget):
    """Small threat count indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0
        self._label = "Threats"
        self.setFixedSize(80, 40)

    def set_count(self, c: int):
        self._count = c
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._count > 0:
            color = QColor(255, 100, 80)
        else:
            color = QColor(0, 200, 150)

        p.setPen(color)
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, 80, 24),
                   Qt.AlignmentFlag.AlignCenter, str(self._count))

        p.setPen(QColor(100, 120, 140))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(QRectF(0, 24, 80, 16),
                   Qt.AlignmentFlag.AlignCenter, self._label)

        p.end()


class StatusDot(QWidget):
    """Small status dot with label."""

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._label = label
        self._active = False
        self.setFixedSize(100, 20)

    def set_active(self, a: bool):
        self._active = a
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(0, 200, 150) if self._active else QColor(80, 100, 120)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(color))
        p.drawEllipse(QPointF(8, 10), 4, 4)

        p.setPen(QColor(160, 180, 200))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(QRectF(18, 0, 80, 20),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self._label)

        p.end()


class SecurityDashboard(QWidget):
    """Security status dashboard for the main UI."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stats = {}
        self.setMinimumHeight(200)
        self.setMaximumHeight(280)

        self._build_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)

        # Header
        header = QLabel("SECURITY STATUS")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        header.setStyleSheet("color: #8090a0; letter-spacing: 2px; background: transparent;")
        layout.addWidget(header)

        # Main row
        main_row = QHBoxLayout()
        main_row.setSpacing(20)

        # Left: Health meter
        left_col = QVBoxLayout()
        left_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._meter = SecurityMeter()
        left_col.addWidget(self._meter, alignment=Qt.AlignmentFlag.AlignCenter)

        main_row.addLayout(left_col)

        # Center: Status indicators
        center_col = QVBoxLayout()
        center_col.setSpacing(4)

        self._dot_rate = StatusDot("Rate Limiter")
        self._dot_audit = StatusDot("Audit Log")
        self._dot_ids = StatusDot("Intrusion DS")
        self._dot_session = StatusDot("Sessions")
        self._dot_sandbox = StatusDot("Code Sandbox")

        center_col.addWidget(self._dot_rate)
        center_col.addWidget(self._dot_audit)
        center_col.addWidget(self._dot_ids)
        center_col.addWidget(self._dot_session)
        center_col.addWidget(self._dot_sandbox)

        main_row.addLayout(center_col)

        # Right: Threats
        right_col = QVBoxLayout()
        right_col.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._threats_hour = ThreatIndicator()
        self._threats_hour._label = "Threats/hr"
        right_col.addWidget(self._threats_hour, alignment=Qt.AlignmentFlag.AlignCenter)

        self._threats_total = ThreatIndicator()
        self._threats_total._label = "Total 24h"
        right_col.addWidget(self._threats_total, alignment=Qt.AlignmentFlag.AlignCenter)

        main_row.addLayout(right_col)

        layout.addLayout(main_row)

        # Footer
        self._footer = QLabel("Last updated: --")
        self._footer.setFont(QFont("Segoe UI", 8))
        self._footer.setStyleSheet("color: #5a6a7a; background: transparent;")
        layout.addWidget(self._footer)

    def _refresh(self):
        try:
            from security.advanced import get_security_status
            stats = get_security_status()
            self._stats = stats

            # Update meter
            health = 100
            issues = stats.get("audit_log", {})
            if not issues.get("valid", True):
                health -= 30

            threats = stats.get("intrusion_detection", {})
            if threats.get("threats_last_hour", 0) > 5:
                health -= 20
            if threats.get("blocked_count", 0) > 0:
                health -= 10

            rate = stats.get("rate_limiter", {})
            if rate.get("locked_keys", 0) > 0:
                health -= 15

            self._meter.set_value(health)

            # Update dots
            self._dot_rate.set_active(rate.get("locked_keys", 0) == 0)
            self._dot_audit.set_active(issues.get("valid", True))
            self._dot_ids.set_active(threats.get("threats_last_hour", 0) < 3)
            self._dot_session.set_active(stats.get("active_sessions", 0) < 10)
            self._dot_sandbox.set_active(True)

            # Update threats
            self._threats_hour.set_count(threats.get("threats_last_hour", 0))
            self._threats_total.set_count(threats.get("total_threats_24h", 0))

            self._footer.setText(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

        except Exception as e:
            self._footer.setText(f"Security module: {e}")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Glass background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(10, 15, 25, 200)))
        p.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

        # Border
        border = QPen(QColor(30, 50, 70, 120))
        border.setWidth(1)
        p.setPen(border)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 10, 10)

        p.end()
