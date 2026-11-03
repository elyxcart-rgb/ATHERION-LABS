"""SONIC Apex — Apple-Level Design System.

Shared design tokens, components, and utilities for premium UI.
All windows import from here for consistent Apple-level aesthetics.
"""
from __future__ import annotations

import math
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QPointF, QRectF, pyqtSignal,
    QEventLoop, QParallelAnimationGroup,
)
from PyQt6.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QFont,
    QPen, QBrush, QPainterPath, QFontMetrics, QPixmap, QIcon,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QSizePolicy, QDialog, QApplication,
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
# APPLE DIALOG (replaces QMessageBox) — Apple-Level Premium
# ═════════════════════════════════════════════════════════════════════════════

class _AppleDialogIcon(QWidget):
    """iOS-style icon glyph drawn with QPainter — no external assets."""

    SIZE = 44

    def __init__(self, variant: str = "info", parent=None):
        super().__init__(parent)
        self._variant = variant
        self.setFixedSize(self.SIZE, self.SIZE)

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = cy = self.SIZE / 2
        bg = {
            "info": QColor(Tokens.ACCENT),
            "success": QColor(Tokens.SUCCESS),
            "warning": QColor(Tokens.WARNING),
            "error": QColor(Tokens.ERROR),
            "question": QColor("#bf5af2"),
        }.get(self._variant, QColor(Tokens.ACCENT))

        if self._variant == "warning":
            # Triangle for warning
            path = QPainterPath()
            r = self.SIZE / 2 - 1
            path.moveTo(cx, 3)
            path.lineTo(self.SIZE - 3, self.SIZE - 4)
            path.lineTo(3, self.SIZE - 4)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawPath(path)
            # White "!"
            p.setPen(QPen(QColor("white"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx, cy - 7), QPointF(cx, cy + 3))
            p.setBrush(QBrush(QColor("white")))
            p.drawEllipse(QPointF(cx, cy + 8), 2, 2)
        else:
            # Circle for everything else
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawEllipse(2, 2, self.SIZE - 4, self.SIZE - 4)

            p.setPen(QPen(QColor("white"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            if self._variant == "success":
                # Checkmark
                path = QPainterPath()
                path.moveTo(cx - 9, cy + 1)
                path.lineTo(cx - 3, cy + 7)
                path.lineTo(cx + 10, cy - 7)
                p.drawPath(path)
            elif self._variant == "error":
                # X
                p.drawLine(QPointF(cx - 8, cy - 8), QPointF(cx + 8, cy + 8))
                p.drawLine(QPointF(cx + 8, cy - 8), QPointF(cx - 8, cy + 8))
            elif self._variant == "info":
                # "i" — dot above, line below
                p.setBrush(QBrush(QColor("white")))
                p.drawEllipse(QPointF(cx, cy - 8), 2.5, 2.5)
                p.drawLine(QPointF(cx, cy - 3), QPointF(cx, cy + 10))
            elif self._variant == "question":
                # "?" — arc + dot
                p.setPen(QPen(QColor("white"), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                arc_rect = QRectF(cx - 7, cy - 10, 14, 14)
                p.drawArc(arc_rect, 60 * 16, 180 * 16)
                p.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy + 6))
                p.setBrush(QBrush(QColor("white")))
                p.drawEllipse(QPointF(cx, cy + 11), 2, 2)
        p.end()


class AppleDialog(QDialog):
    """Apple-style modal dialog — replaces QMessageBox.

    Backward-compatible constructor:
        AppleDialog(title, message, buttons=None, parent=None)

    New (optional) keyword args:
        variant:      'info' | 'success' | 'warning' | 'error' | 'question'
        details:      optional secondary body text (rendered smaller, dimmer)
        cancellable:  if True (default), Escape dismisses with result=None
        primary_index: index of the button activated by Enter/Space (default 0)

    Backward-compatible methods:
        exec()                  — inherited from QDialog, blocks modally
        get_result() -> str|None — returns clicked button text, or None on cancel
        close()                 — inherited
    """

    def __init__(self, title: str, message: str,
                 buttons: list[tuple[str, str]] = None,
                 parent=None,
                 *,
                 variant: str = "info",
                 details: str = "",
                 cancellable: bool = True,
                 primary_index: int = 0):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        self._result = None
        self._buttons = list(buttons) if buttons else [("OK", "primary")]
        self._primary_index = (
            primary_index if 0 <= primary_index < len(self._buttons) else 0
        )
        self._cancellable = cancellable
        self._drag_pos = None

        self._build_ui(title, message, variant, details)
        self._adjust_size()
        self._center_on_parent()
        # Start invisible, fade in after layout settles
        self.setWindowOpacity(0.0)
        QTimer.singleShot(0, self._fade_in)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self, title: str, message: str, variant: str, details: str):
        # Container with rounded corners + shadow
        self._container = QFrame(self)
        self._container.setObjectName("AppleDialogContainer")
        self._container.setStyleSheet(f"""
            QFrame#AppleDialogContainer {{
                background: {Tokens.BG_ELEVATED};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: {Tokens.R_XL}px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(self._container)
        shadow.setBlurRadius(60)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 12)
        self._container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

        root = QVBoxLayout(self._container)
        root.setContentsMargins(Tokens.XXL, Tokens.XL, Tokens.XXL, Tokens.LG)
        root.setSpacing(0)

        # ── Header: icon + title ─────────────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(Tokens.MD)
        header.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._icon = _AppleDialogIcon(variant, self._container)
        header.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setSpacing(6)
        title_col.setContentsMargins(0, 2, 0, 0)

        title_lbl = QLabel(title)
        title_lbl.setFont(Tokens.font(15, QFont.Weight.DemiBold))
        title_lbl.setStyleSheet(
            f"color: {Tokens.TEXT_PRIMARY}; background: transparent;"
        )
        title_lbl.setWordWrap(True)
        title_lbl.setObjectName("AppleDialogTitle")
        title_col.addWidget(title_lbl)

        msg_lbl = QLabel(message)
        msg_lbl.setFont(Tokens.font(13))
        msg_lbl.setStyleSheet(
            f"color: {Tokens.TEXT_SECONDARY}; background: transparent;"
        )
        msg_lbl.setWordWrap(True)
        msg_lbl.setTextFormat(Qt.TextFormat.PlainText)
        msg_lbl.setObjectName("AppleDialogMessage")
        title_col.addWidget(msg_lbl)

        header.addLayout(title_col, 1)
        root.addLayout(header)

        # ── Optional details block ──────────────────────────────────────
        if details:
            root.addSpacing(Tokens.LG)
            details_lbl = QLabel(details)
            details_lbl.setFont(Tokens.font(12))
            details_lbl.setStyleSheet(
                f"color: {Tokens.TEXT_TERTIARY}; background: transparent;"
            )
            details_lbl.setWordWrap(True)
            details_lbl.setTextFormat(Qt.TextFormat.PlainText)
            root.addWidget(details_lbl)

        # ── Buttons row ─────────────────────────────────────────────────
        root.addSpacing(Tokens.XL)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(Tokens.SM)
        btn_row.addStretch(1)

        self._btn_widgets: list[AppleButton] = []
        for i, (text, role) in enumerate(self._buttons):
            btn = AppleButton(text, style=role)
            btn.setMinimumWidth(110)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _checked=False, t=text: self._on_click(t))
            if i == self._primary_index:
                btn.setDefault(True)
                btn.setAutoDefault(True)
            btn_row.addWidget(btn)
            self._btn_widgets.append(btn)

        root.addLayout(btn_row)

        # Focus the primary button by default
        if self._btn_widgets:
            self._btn_widgets[self._primary_index].setFocus()

    # ── Sizing & positioning ──────────────────────────────────────────────

    def _adjust_size(self):
        # Let the container compute its size hint based on content
        self._container.adjustSize()
        hint = self._container.sizeHint()
        # Sensible bounds — clamp so the dialog never looks ridiculous
        w = max(360, min(560, hint.width()))
        # Container is exactly w wide; let height follow content but cap
        self._container.setFixedWidth(w)
        self._container.adjustSize()
        h = max(160, min(420, self._container.sizeHint().height()))
        self.resize(w + 2, h + 2)  # +2 for the 1px outer border feel

    def _center_on_parent(self):
        parent = self.parentWidget()
        if parent is not None and parent.isVisible():
            pg = parent.frameGeometry()
            self.move(
                pg.x() + (pg.width() - self.width()) // 2,
                pg.y() + (pg.height() - self.height()) // 2,
            )
            return
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.move(
                avail.x() + (avail.width() - self.width()) // 2,
                avail.y() + (avail.height() - self.height()) // 2,
            )

    def _fade_in(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._fade_anim = anim

    # ── Public API (backward-compatible) ──────────────────────────────────

    def get_result(self):
        """Returns clicked button text, or None if dismissed (Escape / close)."""
        return self._result

    def _on_click(self, text: str):
        self._result = text
        self.accept()

    # ── Keyboard handling ─────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._activate_primary()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._cancellable:
                self._result = None
                self.reject()
            event.accept()
            return
        # Tab cycles through buttons
        if event.key() == Qt.Key.Key_Tab:
            if self._btn_widgets:
                cur = self._btn_widgets.index(self.focusWidget()) \
                    if self.focusWidget() in self._btn_widgets else -1
                nxt = (cur + 1) % len(self._btn_widgets)
                self._btn_widgets[nxt].setFocus()
                event.accept()
                return
        super().keyPressEvent(event)

    def _activate_primary(self):
        if not self._btn_widgets:
            return
        text = self._buttons[self._primary_index][0]
        self._on_click(text)

    # ── Drag support ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ── Convenience static helpers ────────────────────────────────────────

    @staticmethod
    def show_info(parent, title: str, message: str, **kwargs):
        return AppleDialog(title, message, buttons=[("OK", "primary")],
                           parent=parent, variant="info", **kwargs)

    @staticmethod
    def show_success(parent, title: str, message: str, **kwargs):
        return AppleDialog(title, message, buttons=[("OK", "primary")],
                           parent=parent, variant="success", **kwargs)

    @staticmethod
    def show_warning(parent, title: str, message: str, **kwargs):
        return AppleDialog(title, message, buttons=[("OK", "primary")],
                           parent=parent, variant="warning", **kwargs)

    @staticmethod
    def show_error(parent, title: str, message: str, **kwargs):
        return AppleDialog(title, message, buttons=[("OK", "primary")],
                           parent=parent, variant="error", **kwargs)

    @staticmethod
    def show_question(parent, title: str, message: str,
                      ok_text: str = "OK", cancel_text: str = "Cancel",
                      destructive: bool = False, **kwargs):
        primary_role = "destructive" if destructive else "primary"
        return AppleDialog(
            title, message,
            buttons=[(cancel_text, "secondary"), (ok_text, primary_role)],
            parent=parent, variant="question", **kwargs,
        )


# ═════════════════════════════════════════════════════════════════════════════
# APPLE TOAST — non-modal notification, auto-dismisses
# ═════════════════════════════════════════════════════════════════════════════

class AppleToast(QWidget):
    """Apple-style toast — slides in from bottom-right, auto-dismisses.

    Usage:
        AppleToast.show(parent, "Saved successfully", variant="success")
    """

    def __init__(self, message: str, variant: str = "info",
                 duration_ms: int = 3500, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._duration_ms = duration_ms
        self._build_ui(message, variant)
        self._position()
        self.setWindowOpacity(0.0)
        QTimer.singleShot(0, self._slide_in)
        QTimer.singleShot(duration_ms, self._slide_out)

    def _build_ui(self, message: str, variant: str):
        container = QFrame(self)
        container.setStyleSheet(f"""
            QFrame {{
                background: {Tokens.BG_ELEVATED};
                border: 1px solid {Tokens.BORDER_LIGHT};
                border-radius: 14px;
            }}
        """)
        shadow = QGraphicsDropShadowEffect(container)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 6)
        container.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        row = QHBoxLayout(container)
        row.setContentsMargins(14, 12, 18, 12)
        row.setSpacing(10)

        icon = _AppleDialogIcon(variant, container)
        icon.setFixedSize(28, 28)
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)

        lbl = QLabel(message)
        lbl.setFont(Tokens.font(13, QFont.Weight.Medium))
        lbl.setStyleSheet(
            f"color: {Tokens.TEXT_PRIMARY}; background: transparent;"
        )
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(360)
        row.addWidget(lbl, 1, Qt.AlignmentFlag.AlignVCenter)

        self._container = container
        self.adjustSize()

    def _position(self):
        # Anchor to the parent's bottom-right; fall back to primary screen.
        parent = self.parentWidget()
        if parent and parent.isVisible():
            pg = parent.frameGeometry()
            x = pg.right() - self.width() - 24
            y = pg.bottom() - self.height() - 24
        else:
            screen = QApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                x = avail.right() - self.width() - 24
                y = avail.bottom() - self.height() - 24
            else:
                x, y = 0, 0
        self._target_pos = QPoint(x, y)
        self.move(x, y + 16)  # start 16px below for slide animation

    def _slide_in(self):
        anim = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(220)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)

        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(260)
        slide.setStartValue(self.pos())
        slide.setEndValue(self._target_pos)
        slide.setEasingCurve(QEasingCurve.Type.OutCubic)

        anim.addAnimation(fade)
        anim.addAnimation(slide)
        anim.start()
        self._in_anim = anim

    def _slide_out(self):
        anim = QParallelAnimationGroup(self)
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(200)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InCubic)

        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(220)
        slide.setStartValue(self.pos())
        end = QPoint(self.pos().x(), self.pos().y() + 12)
        slide.setEndValue(end)
        slide.setEasingCurve(QEasingCurve.Type.InCubic)

        anim.addAnimation(fade)
        anim.addAnimation(slide)
        anim.finished.connect(self.close)
        anim.start()
        self._out_anim = anim

    @staticmethod
    def notify(parent, message: str, variant: str = "info",
               duration_ms: int = 3500) -> "AppleToast":
        """Static convenience: build, show, and return the toast widget.

        Usage:
            AppleToast.notify(self, "Saved successfully", variant="success")
        """
        t = AppleToast(message, variant=variant, duration_ms=duration_ms,
                       parent=parent)
        # Use the QWidget show() directly — instance method is shadowed by
        # our static helper above, but here we're inside the class so it works.
        from PyQt6.QtWidgets import QWidget as _QW
        _QW.show(t)
        return t


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
        p.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), 90 * 16, -span)

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
