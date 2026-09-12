"""
Hologram Mode — Screen Annotation & Drawing Overlay
Allow SONIC to draw directly on the user's screen with arrows, circles,
rectangles, text labels, and freehand annotations.
"""
import sys
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont, QBrush, QPainterPath, QPolygonF,
)
from PyQt6.QtWidgets import QApplication, QWidget


class AnnotationType(str, Enum):
    ARROW = "arrow"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"
    TEXT = "text"
    FREEHAND = "freehand"
    HIGHLIGHT = "highlight"
    SPOTLIGHT = "spotlight"


@dataclass
class Annotation:
    ann_type: AnnotationType
    x1: float
    y1: float
    x2: float = 0.0
    y2: float = 0.0
    text: str = ""
    color: str = "#00d4ff"
    thickness: int = 3
    font_size: int = 18
    duration: float = 5.0
    opacity: float = 0.9
    points: list = None

    def __post_init__(self):
        if self.points is None:
            self.points = []


class HologramOverlay(QWidget):
    """Transparent fullscreen overlay for screen annotations."""

    def __init__(self):
        super().__init__()
        self.annotations: list[Annotation] = []
        self._fading = False
        self._setup_window()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.setGeometry(geo)

    def add_annotation(self, annotation: Annotation):
        self.annotations.append(annotation)
        self.show()
        self.update()

        if annotation.duration > 0:
            QTimer.singleShot(
                int(annotation.duration * 1000),
                lambda: self._remove_annotation(annotation),
            )

    def _remove_annotation(self, annotation: Annotation):
        if annotation in self.annotations:
            self.annotations.remove(annotation)
            self.update()
            if not self.annotations:
                self.hide()

    def clear_all(self):
        self.annotations.clear()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for ann in self.annotations:
            self._draw_annotation(painter, ann)

        painter.end()

    def _draw_annotation(self, painter: QPainter, ann: Annotation):
        color = QColor(ann.color)
        color.setAlphaF(ann.opacity)
        pen = QPen(color, ann.thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        if ann.ann_type == AnnotationType.ARROW:
            self._draw_arrow(painter, ann)
        elif ann.ann_type == AnnotationType.CIRCLE:
            self._draw_circle(painter, ann)
        elif ann.ann_type == AnnotationType.RECTANGLE:
            self._draw_rectangle(painter, ann)
        elif ann.ann_type == AnnotationType.TEXT:
            self._draw_text(painter, ann)
        elif ann.ann_type == AnnotationType.FREEHAND:
            self._draw_freehand(painter, ann)
        elif ann.ann_type == AnnotationType.HIGHLIGHT:
            self._draw_highlight(painter, ann)
        elif ann.ann_type == AnnotationType.SPOTLIGHT:
            self._draw_spotlight(painter, ann)

    def _draw_arrow(self, painter: QPainter, ann: Annotation):
        start = QPointF(ann.x1, ann.y1)
        end = QPointF(ann.x2, ann.y2)
        painter.drawLine(start, end)

        import math
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_len = 15
        arrow_angle = 0.5

        p1 = QPointF(
            end.x() - arrow_len * math.cos(angle - arrow_angle),
            end.y() - arrow_len * math.sin(angle - arrow_angle),
        )
        p2 = QPointF(
            end.x() - arrow_len * math.cos(angle + arrow_angle),
            end.y() - arrow_len * math.sin(angle + arrow_angle),
        )
        painter.setBrush(QBrush(QColor(ann.color)))
        painter.drawPolygon(QPolygonF([end, p1, p2]))

    def _draw_circle(self, painter: QPainter, ann: Annotation):
        cx = (ann.x1 + ann.x2) / 2
        cy = (ann.y1 + ann.y2) / 2
        rx = abs(ann.x2 - ann.x1) / 2
        ry = abs(ann.y2 - ann.y1) / 2
        painter.drawEllipse(QPointF(cx, cy), rx, ry)

    def _draw_rectangle(self, painter: QPainter, ann: Annotation):
        rect = QRectF(ann.x1, ann.y1, ann.x2 - ann.x1, ann.y2 - ann.y1)
        painter.drawRect(rect)

    def _draw_text(self, painter: QPainter, ann: Annotation):
        font = QFont("Segoe UI", ann.font_size, QFont.Weight.Bold)
        painter.setFont(font)

        bg_color = QColor(ann.color)
        bg_color.setAlphaF(0.3)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)

        metrics = painter.fontMetrics()
        text_rect = metrics.boundingRect(ann.text)
        padding = 10
        bg_rect = QRectF(
            ann.x1 - padding,
            ann.y1 - text_rect.height() - padding,
            text_rect.width() + padding * 2,
            text_rect.height() + padding * 2,
        )
        painter.drawRoundedRect(bg_rect, 8, 8)

        painter.setPen(QPen(QColor(ann.color)))
        painter.drawText(QPointF(ann.x1, ann.y1), ann.text)

    def _draw_freehand(self, painter: QPainter, ann: Annotation):
        if not ann.points:
            return
        path = QPainterPath()
        path.moveTo(ann.points[0][0], ann.points[0][1])
        for pt in ann.points[1:]:
            path.lineTo(pt[0], pt[1])
        painter.drawPath(path)

    def _draw_highlight(self, painter: QPainter, ann: Annotation):
        color = QColor(ann.color)
        color.setAlphaF(0.25)
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(ann.x1, ann.y1, ann.x2 - ann.x1, ann.y2 - ann.y1)
        painter.drawRoundedRect(rect, 12, 12)

    def _draw_spotlight(self, painter: QPainter, ann: Annotation):
        screen = self.geometry()
        mask = QColor(0, 0, 0, 150)
        painter.setBrush(QBrush(mask))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, screen.width(), screen.height())

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        cx, cy = ann.x1, ann.y1
        radius = max(ann.x2, 100)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

        color = QColor(ann.color)
        color.setAlphaF(0.5)
        pen = QPen(color, 3)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)


class HologramManager:
    """Manages the hologram overlay and annotations."""

    def __init__(self):
        self._overlay: Optional[HologramOverlay] = None
        self._initialized = False
        self._thread: Optional[threading.Thread] = None

    def _ensure_overlay(self):
        if self._initialized and self._overlay:
            return

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        self._overlay = HologramOverlay()
        self._initialized = True

    def add_annotation(self, annotation: Annotation):
        self._ensure_overlay()
        if self._overlay:
            QTimer.singleShot(0, lambda: self._overlay.add_annotation(annotation))

    def clear(self):
        if self._overlay:
            QTimer.singleShot(0, self._overlay.clear_all)

    def add_arrow(self, x1, y1, x2, y2, color="#00d4ff", duration=5.0):
        self.add_annotation(Annotation(
            ann_type=AnnotationType.ARROW,
            x1=x1, y1=y1, x2=x2, y2=y2,
            color=color, duration=duration,
        ))

    def add_circle(self, x1, y1, x2, y2, color="#00d4ff", duration=5.0):
        self.add_annotation(Annotation(
            ann_type=AnnotationType.CIRCLE,
            x1=x1, y1=y1, x2=x2, y2=y2,
            color=color, duration=duration,
        ))

    def add_text(self, x, y, text, color="#00d4ff", font_size=18, duration=5.0):
        self.add_annotation(Annotation(
            ann_type=AnnotationType.TEXT,
            x1=x, y1=y, text=text,
            color=color, font_size=font_size, duration=duration,
        ))

    def add_highlight(self, x1, y1, x2, y2, color="#ffcc00", duration=5.0):
        self.add_annotation(Annotation(
            ann_type=AnnotationType.HIGHLIGHT,
            x1=x1, y1=y1, x2=x2, y2=y2,
            color=color, duration=duration,
        ))

    def spotlight(self, x, y, radius=150, color="#00d4ff", duration=5.0):
        self.add_annotation(Annotation(
            ann_type=AnnotationType.SPOTLIGHT,
            x1=x, y1=y, x2=radius,
            color=color, duration=duration,
        ))

    def rectangle(self, x1, y1, x2, y2, color="#00d4ff", duration=5.0):
        self.add_annotation(Annotation(
            ann_type=AnnotationType.RECTANGLE,
            x1=x1, y1=y1, x2=x2, y2=y2,
            color=color, duration=duration,
        ))


_manager: HologramManager | None = None


def get_hologram_manager() -> HologramManager:
    global _manager
    if _manager is None:
        _manager = HologramManager()
    return _manager


async def hologram_mode(parameters: dict, **kwargs) -> str:
    """Tool handler for hologram_mode."""
    action = parameters.get("action", "annotate")
    manager = get_hologram_manager()

    if action == "annotate":
        ann_type = parameters.get("type", "arrow")
        x1 = parameters.get("x1", 100)
        y1 = parameters.get("y1", 100)
        x2 = parameters.get("x2", 300)
        y2 = parameters.get("y2", 300)
        text = parameters.get("text", "")
        color = parameters.get("color", "#00d4ff")
        duration = parameters.get("duration", 5.0)

        if ann_type == "arrow":
            manager.add_arrow(x1, y1, x2, y2, color, duration)
        elif ann_type == "circle":
            manager.add_circle(x1, y1, x2, y2, color, duration)
        elif ann_type == "text":
            manager.add_text(x1, y1, text, color, parameters.get("font_size", 18), duration)
        elif ann_type == "highlight":
            manager.add_highlight(x1, y1, x2, y2, color, duration)
        elif ann_type == "rectangle":
            manager.rectangle(x1, y1, x2, y2, color, duration)
        elif ann_type == "spotlight":
            manager.spotlight(x1, y1, x2, color, duration)
        else:
            return f"Unknown annotation type: {ann_type}"

        return f"Annotation added: {ann_type} (auto-clears in {duration}s)"

    elif action == "clear":
        manager.clear()
        return "All annotations cleared."

    return f"Unknown hologram action: {action}. Use: annotate, clear"
