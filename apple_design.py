"""SONIC Apex — Apple-Level Design System.

Shared design tokens, components, and utilities for premium UI.
All windows import from here for consistent Apple-level aesthetics.
"""
from __future__ import annotations

import math
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRectF, pyqtSignal,
    QEventLoop,
)
from PyQt6.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QFont,
    QPen, QBrush, QPainterPath, QFontMetrics, QPixmap, QIcon,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QSizePolicy,
)


# ═════════════════════════════════════════════════════════════════════════════
# DESIGN TOKENS
# ═════════════════════════════════════════════════════════════════════════════

class Tokens:
    """Apple-level design tokens — consistent spacing, color, typography."""

    # ── Colors ────────────────────────────────────────────────────────────
    BG_PRIMARY = "#000000"        # Pure black (Apple-style)
    BG_SECONDARY = "#0a0a0a"     # Near-black
    BG_ELEVATED = "#1c1c1e"      # Elevated surface
    BG_CARD = "#1c1c1e"          # Card background
    BG_CARD_HOVER = "#2c2c2e"    # Card hover

    SURFACE_1 = "#1c1c1e"        # Primary surface
    SURFACE_2 = "#2c2c2e"        # Secondary surface
    SURFACE_3 = "#3a3a3c"        # Tertiary surface

    BORDER = "rgba(255, 255, 255, 0.08)"
    BORDER_LIGHT = "rgba(255, 255, 255, 0.12)"
    BORDER_FOCUS = "rgba(0, 217, 255, 0.5)"

    TEXT_PRIMARY = "#ffffff"      # Primary text
    TEXT_SECONDARY = "#8e8e93"    # Secondary text (Apple gray)
    TEXT_TERTIARY = "#636366"     # Tertiary text
    TEXT_DISABLED = "#48484a"     # Disabled text

    ACCENT = "#0a84ff"           # Apple blue
    ACCENT_HOVER = "#409cff"     # Blue hover
    ACCENT_PRESS = "#0070e0"     # Blue pressed

    SUCCESS = "#30d158"          # Apple green
    WARNING = "#ff9f0a"          # Apple orange
    ERROR = "#ff453a"            # Apple red

    CYAN = "#00d9ff"             # SONIC cyan accent

    # ── Spacing ──────────────────────────────────────────────────────────
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32
    XXXL = 48

    # ── Border Radius ────────────────────────────────────────────────────
    R_SM = 8
    R_MD = 12
    R_LG = 16
    R_XL = 20
    R_FULL = 9999

    # ── Typography ───────────────────────────────────────────────────────
    FONT = "SF Pro Display, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    FONT_MONO = "SF Mono, 'Cascadia Code', 'Consolas', monospace"

    @classmethod
    def font(cls, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        f = QFont("SF Pro Display", size)
        f.setWeight(weight)
        return f

    @classmethod
    def font_mono(cls, size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
        f = QFont("SF Mono", size)
        f.setWeight(weight)
        return f


# ═════════════════════════════════════════════════════════════════════════════
# APPLE BUTTON
# ═════════════════════════════════════════════════════════════════════════════

class AppleButton(QPushButton):
    """Apple-style button with smooth hover/press animations."""

    def __init__(self, text: str, style: str = "primary", parent=None):
        """
        style: 'primary' | 'secondary' | 'ghost' | 'destructive'
        """
        super().__init__(text, parent)
        self._style = style
        self._hover = False
        self._pressed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)
        self.setMinimumWidth(120)
        self.setFont(Tokens.font(13, QFont.Weight.Medium))
        self._update_style()

    def _update_style(self):
        styles = {
            "primary": f"""
                QPushButton {{
                    background: {Tokens.ACCENT};
                    color: #ffffff;
                    border: none;
                    border-radius: {Tokens.R_MD}px;
                    padding: 0 24px;
                    font-weight: 500;
                }}
                QPushButton:hover {{ background: {Tokens.ACCENT_HOVER}; }}
                QPushButton:pressed {{ background: {Tokens.ACCENT_PRESS}; }}
                QPushButton:disabled {{
                    background: {Tokens.SURFACE_2};
                    color: {Tokens.TEXT_DISABLED};
                }}
            """,
            "secondary": f"""
                QPushButton {{
                    background: {Tokens.SURFACE_2};
                    color: {Tokens.TEXT_PRIMARY};
                    border: 1px solid {Tokens.BORDER_LIGHT};
                    border-radius: {Tokens.R_MD}px;
                    padding: 0 24px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: {Tokens.SURFACE_3};
                    border-color: rgba(255,255,255,0.15);
                }}
                QPushButton:pressed {{ background: {Tokens.SURFACE_2}; }}
                QPushButton:disabled {{
                    background: {Tokens.SURFACE_1};
                    color: {Tokens.TEXT_DISABLED};
                    border-color: {Tokens.BORDER};
                }}
            """,
            "ghost": f"""
                QPushButton {{
                    background: transparent;
                    color: {Tokens.ACCENT};
                    border: none;
                    border-radius: {Tokens.R_MD}px;
                    padding: 0 16px;
                    font-weight: 500;
                }}
                QPushButton:hover {{ background: rgba(10, 132, 255, 0.1); }}
                QPushButton:pressed {{ background: rgba(10, 132, 255, 0.15); }}
                QPushButton:disabled {{ color: {Tokens.TEXT_DISABLED}; }}
            """,
            "destructive": f"""
                QPushButton {{
                    background: {Tokens.ERROR};
                    color: #ffffff;
                    border: none;
                    border-radius: {Tokens.R_MD}px;
                    padding: 0 24px;
                    font-weight: 500;
                }}
                QPushButton:hover {{ background: #ff6961; }}
                QPushButton:pressed {{ background: #e03e36; }}
                QPushButton:disabled {{
                    background: {Tokens.SURFACE_2};
                    color: {Tokens.TEXT_DISABLED};
                }}
            """,
        }
        self.setStyleSheet(styles.get(self._style, styles["primary"]))


# ═════════════════════════════════════════════════════════════════════════════
# APPLE INPUT FIELD
# ═════════════════════════════════════════════════════════════════════════════

class AppleInput(QLineEdit):
    """Apple-style text input with focus animation."""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(40)
        self.setFont(Tokens.font(13))
        self.setStyleSheet(f"""
            QLineEdit {{
                background: {Tokens.SURFACE_1};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_SM}px;
                padding: 0 12px;
                color: {Tokens.TEXT_PRIMARY};
                selection-background-color: rgba(10, 132, 255, 0.3);
            }}
            QLineEdit:focus {{
                border: 1px solid {Tokens.ACCENT};
                background: {Tokens.SURFACE_2};
            }}
            QLineEdit::placeholder {{
                color: {Tokens.TEXT_TERTIARY};
            }}
        """)


# ═════════════════════════════════════════════════════════════════════════════
# APPLE CARD
# ═════════════════════════════════════════════════════════════════════════════

class AppleCard(QWidget):
    """Apple-style card with subtle border and elevation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AppleCard {{
                background: {Tokens.BG_CARD};
                border: 1px solid {Tokens.BORDER};
                border-radius: {Tokens.R_LG}px;
            }}
        """)


# ═════════════════════════════════════════════════════════════════════════════
# APPLE STEP INDICATOR
# ═════════════════════════════════════════════════════════════════════════════

class AppleStepIndicator(QWidget):
    """Minimal Apple-style step progress with dots and connecting line."""

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self._count = count
        self._current = 0
        self.setFixedHeight(48)

    def set_current(self, idx: int):
        self._current = idx
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        n = self._count
        if n == 0:
            return

        margin = 60
        usable = w - margin * 2
        spacing = usable / max(n - 1, 1)
        cy = h // 2

        # Draw connecting line
        line_pen = QPen(QColor(255, 255, 255, 20))
        line_pen.setWidth(1)
        p.setPen(line_pen)
        p.drawLine(int(margin), cy, int(margin + usable), cy)

        # Draw active line
        if self._current > 0:
            active_pen = QPen(QColor(Tokens.ACCENT))
            active_pen.setWidth(2)
            p.setPen(active_pen)
            p.drawLine(int(margin), cy, int(margin + self._current * spacing), cy)

        # Draw dots
        for i in range(n):
            x = int(margin + i * spacing)

            if i < self._current:
                # Completed
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(Tokens.ACCENT)))
                p.drawEllipse(QPointF(x, cy), 5, 5)
            elif i == self._current:
                # Active
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(Tokens.ACCENT)))
                p.drawEllipse(QPointF(x, cy), 7, 7)
                # Outer ring
                ring_pen = QPen(QColor(10, 132, 255, 60))
                ring_pen.setWidth(1)
                p.setPen(ring_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(x, cy), 11, 11)
            else:
                # Pending
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(255, 255, 255, 20)))
                p.drawEllipse(QPointF(x, cy), 4, 4)

        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# APPLE PROGRESS BAR
# ═════════════════════════════════════════════════════════════════════════════

class AppleProgressBar(QWidget):
    """Minimal Apple-style thin progress bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.setFixedHeight(3)

    def setValue(self, val: int):
        self._value = max(0, min(100, val))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        radius = h / 2

        # Track
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 15)))
        p.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        # Fill
        fill_w = w * self._value / 100
        if fill_w > 0:
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0.0, QColor(Tokens.ACCENT))
            grad.setColorAt(1.0, QColor(Tokens.CYAN))
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(QRectF(0, 0, fill_w, h), radius, radius)

        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# APPLE GLASS OVERLAY
# ═════════════════════════════════════════════════════════════════════════════

class AppleGlassOverlay(QWidget):
    """Full-screen dark overlay with centered content — Apple modal style."""

    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0, 0, 0, 0.7);")

    def mousePressEvent(self, event):
        # Click outside dismisses
        pass


# ═════════════════════════════════════════════════════════════════════════════
# APPLE DIALOG (replaces QMessageBox)
# ═════════════════════════════════════════════════════════════════════════════

class AppleDialog(QWidget):
    """Apple-style modal dialog — replaces ugly QMessageBox."""

    def __init__(self, title: str, message: str, buttons: list[tuple[str, str]] = None,
                 parent=None):
        """
        buttons: list of (text, role) where role is 'primary' | 'secondary' | 'destructive'
        """
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(380, 200)
        self._result = None
        self._buttons = buttons or [("OK", "primary")]
        self._drag_pos = None
        self._closed = False
        self._build_ui(title, message)

    def exec(self):
        """Show modal and block until closed."""
        from PyQt6.QtWidgets import QApplication
        self.show()
        self.raise_()
        self.activateWindow()
        # Block until closed
        loop = QEventLoop()
        self._loop = loop
        self.destroyed.connect(lambda: loop.quit() if not loop.isRunning() else None)
        loop.exec()

    def close(self):
        self._closed = True
        self._result = self._result
        super().close()
        if hasattr(self, '_loop') and self._loop.isRunning():
            self._loop.quit()

    def _build_ui(self, title: str, message: str):
        # Background
        self._bg = QWidget(self)
        self._bg.setGeometry(0, 0, 380, 200)
        self._bg.setStyleSheet(f"""
            QWidget {{
                background: {Tokens.BG_ELEVATED};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: {Tokens.R_XL}px;
            }}
        """)

        layout = QVBoxLayout(self._bg)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(0)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setFont(Tokens.font(15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {Tokens.TEXT_PRIMARY}; background: transparent;")
        layout.addWidget(title_lbl)

        layout.addSpacing(8)

        # Message
        msg_lbl = QLabel(message)
        msg_lbl.setFont(Tokens.font(13))
        msg_lbl.setStyleSheet(f"color: {Tokens.TEXT_SECONDARY}; background: transparent;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        for text, role in self._buttons:
            btn = AppleButton(text, style=role)
            btn.setFixedSize(max(80, len(text) * 9 + 30), 32)
            btn.clicked.connect(lambda checked, r=role, t=text: self._on_click(r, t))
            btn_row.addWidget(btn)

        layout.addLayout(btn_row)

        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 8)
        self._bg.setGraphicsEffect(shadow)

    def _on_click(self, role: str, text: str):
        self._result = text
        self.close()

    def get_result(self) -> str:
        return self._result

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


# ═════════════════════════════════════════════════════════════════════════════
# APPLE STATUS DOT
# ═════════════════════════════════════════════════════════════════════════════

class AppleStatusDot(QWidget):
    """Small animated status indicator dot."""

    def __init__(self, color: QColor = None, size: int = 8, parent=None):
        super().__init__(parent)
        self._color = color or QColor(Tokens.SUCCESS)
        self._size = size
        self.setFixedSize(size + 4, size + 4)

    def set_color(self, color: QColor):
        self._color = color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() // 2, self.height() // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(self._color))
        p.drawEllipse(QPointF(cx, cy), self._size / 2, self._size / 2)
        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# APPLE CHECKMARK ANIMATION
# ═════════════════════════════════════════════════════════════════════════════

class AppleCheckmark(QWidget):
    """Animated checkmark circle — success confirmation."""

    def __init__(self, size: int = 64, parent=None):
        super().__init__(parent)
        self._size = size
        self._progress = 0.0
        self.setFixedSize(size, size)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        if self._progress < 1.0:
            self._progress = min(1.0, self._progress + 0.04)
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self._size // 2, self._size // 2
        r = self._size // 2 - 2

        # Circle
        circle_pen = QPen(QColor(Tokens.SUCCESS), 2)
        circle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(circle_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Animated circle drawing
        span = int(360 * 16 * self._progress)
        p.drawArc(QPointF(cx, cy), r * 2, r * 2, 90 * 16, -span)

        # Checkmark
        if self._progress > 0.6:
            check_progress = min(1.0, (self._progress - 0.6) / 0.4)
            p.setPen(QPen(QColor(Tokens.SUCCESS), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))

            # Checkmark points
            x1, y1 = cx - r * 0.3, cy
            x2, y2 = cx - r * 0.05, cy + r * 0.3
            x3, y3 = cx + r * 0.35, cy - r * 0.25

            if check_progress < 0.5:
                t = check_progress * 2
                ex = x1 + (x2 - x1) * t
                ey = y1 + (y2 - y1) * t
                p.drawLine(int(x1), int(y1), int(ex), int(ey))
            else:
                t = (check_progress - 0.5) * 2
                ex = x2 + (x3 - x2) * t
                ey = y2 + (y3 - y2) * t
                p.drawLine(int(x1), int(y1), int(x2), int(y2))
                p.drawLine(int(x2), int(y2), int(ex), int(ey))

        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# APPLE GLOW EFFECT
# ═════════════════════════════════════════════════════════════════════════════

def create_glow(color: QColor = None, radius: int = 20, offset: int = 0) -> QGraphicsDropShadowEffect:
    """Create a subtle glow effect."""
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(radius)
    effect.setColor(color or QColor(Tokens.ACCENT))
    effect.setOffset(0, offset)
    return effect


def create_shadow(radius: int = 20, color: QColor = None, dy: int = 4) -> QGraphicsDropShadowEffect:
    """Create a drop shadow."""
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(radius)
    effect.setColor(color or QColor(0, 0, 0, 60))
    effect.setOffset(0, dy)
    return effect


# ═════════════════════════════════════════════════════════════════════════════
# HELPER: Smooth fade-in for widgets
# ═════════════════════════════════════════════════════════════════════════════

def fade_in(widget: QWidget, duration: int = 300, start: float = 0.0, end: float = 1.0):
    """Smooth opacity fade-in animation."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity")
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    # Keep reference
    widget._fade_anim = anim
    return anim


def slide_up(widget: QWidget, duration: int = 300, offset: int = 20):
    """Smooth slide-up + fade animation."""
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)

    start_pos = widget.pos()
    widget.move(start_pos.x(), start_pos.y() + offset)

    anim_group = QPropertyAnimation(effect, b"opacity")
    anim_group.setDuration(duration)
    anim_group.setStartValue(0.0)
    anim_group.setEndValue(1.0)
    anim_group.setEasingCurve(QEasingCurve.Type.OutCubic)

    pos_anim = QPropertyAnimation(widget, b"pos")
    pos_anim.setDuration(duration)
    pos_anim.setStartValue(widget.pos())
    pos_anim.setEndValue(start_pos)
    pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    from PyQt6.QtCore import QParallelAnimationGroup
    group = QParallelAnimationGroup()
    group.addAnimation(anim_group)
    group.addAnimation(pos_anim)
    group.start()
    widget._slide_anim = group
    return group
