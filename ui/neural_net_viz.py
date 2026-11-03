"""SONIC AI — Neural Network Visualizer.

Animated neural network with layers of nodes that fire (light up) when
activated. Connections between nodes carry pulsing energy along their
length. Used as a cinematic background / "thinking" indicator.

Public API:
    NeuralNetViz(parent=None, layers=[6, 10, 10, 6])
    .set_activity(level: float)   # 0..1, drives firing rate
    .set_color(r, g, b)
    .fire_at_layer(layer_index)   # force-pulse a layer
"""
from __future__ import annotations

import math
import random
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QLinearGradient, QPen, QBrush, QFont,
)
from PyQt6.QtWidgets import QWidget


class NeuralNetViz(QWidget):
    """Animated multi-layer neural network."""

    def __init__(self, parent=None, layers: list[int] | None = None,
                 width: int = 720, height: int = 280):
        super().__init__(parent)
        self._width = width
        self._height = height
        self.setFixedSize(width, height)

        self._layers = layers or [6, 10, 10, 6]
        self._tick = 0
        self._activity = 0.4
        self._color = QColor(0, 200, 255)

        # Generate nodes
        self._nodes: list[list[dict]] = []
        for layer_i, count in enumerate(self._layers):
            layer_nodes = []
            x = self._x_for_layer(layer_i)
            for j in range(count):
                y = self._y_for_node(j, count)
                layer_nodes.append({
                    "x": x, "y": y,
                    "activation": random.uniform(0, 1),
                    "target_activation": 0.5,
                    "radius": 4.0 + random.uniform(0, 2),
                    "phase": random.uniform(0, math.pi * 2),
                    "glow": 0.0,
                })
            self._nodes.append(layer_nodes)

        # Generate connections (each node connects to every node in next layer)
        self._connections: list[dict] = []
        for li in range(len(self._layers) - 1):
            for a in self._nodes[li]:
                for b in self._nodes[li + 1]:
                    weight = random.uniform(0.3, 1.0) * random.choice([-1, 1])
                    self._connections.append({
                        "from": (li, self._nodes[li].index(a)),
                        "to":   (li + 1, self._nodes[li + 1].index(b)),
                        "weight": weight,
                        "signal": 0.0,         # current signal strength along wire
                        "speed": random.uniform(0.4, 1.6),
                    })

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_anim)
        self._timer.start(30)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_activity(self, level: float):
        self._activity = max(0.0, min(1.0, level))

    def set_color(self, r: int, g: int, b: int):
        self._color = QColor(r, g, b)

    def fire_at_layer(self, layer_index: int):
        if 0 <= layer_index < len(self._nodes):
            for n in self._nodes[layer_index]:
                n["target_activation"] = 1.0

    # ── Internals ────────────────────────────────────────────────────────────

    def _x_for_layer(self, i: int) -> float:
        margin = 60
        usable = self._width - 2 * margin
        if len(self._layers) <= 1:
            return self._width / 2
        return margin + usable * i / (len(self._layers) - 1)

    def _y_for_node(self, j: int, count: int) -> float:
        margin = 30
        usable = self._height - 2 * margin
        if count <= 1:
            return self._height / 2
        return margin + usable * j / (count - 1)

    def _tick_anim(self):
        self._tick += 1

        # Fire random nodes based on activity
        fire_rate = self._activity * 0.08
        for layer in self._nodes:
            for n in layer:
                # Decay current activation toward base
                if random.random() < fire_rate:
                    n["target_activation"] = random.uniform(0.4, 1.0)
                else:
                    n["target_activation"] *= 0.92

                # Smooth
                n["activation"] += (n["target_activation"] - n["activation"]) * 0.2
                # Glow trail
                target_glow = n["activation"] * 200
                n["glow"] += (target_glow - n["glow"]) * 0.1

        # Propagate signals along connections
        for conn in self._connections:
            li, ai = conn["from"]
            lj, bj = conn["to"]
            a_node = self._nodes[li][ai]
            # Signal carries the source activation
            wave = math.sin(self._tick * 0.05 + conn["speed"] * 4) * 0.5 + 0.5
            conn["signal"] = abs(conn["weight"]) * a_node["activation"] * wave

        self.update()

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self._color

        # Background ambient
        bg_grad = QLinearGradient(0, 0, 0, self._height)
        bg_grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 12))
        bg_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_grad))
        painter.drawRect(0, 0, self._width, self._height)

        # Connections (drawn first, behind nodes)
        for conn in self._connections:
            li, ai = conn["from"]
            lj, bj = conn["to"]
            a = self._nodes[li][ai]
            b = self._nodes[lj][bj]
            sig = conn["signal"]
            base_alpha = int(30 + abs(conn["weight"]) * 80)
            sig_alpha = int(min(255, sig * 220))
            color = QColor(c.red(), c.green(), c.blue(), base_alpha)
            sig_color = QColor(255, 255, 255, sig_alpha)

            # Draw base wire
            pen = QPen(color, 0.8)
            painter.setPen(pen)
            painter.drawLine(QPointF(a["x"], a["y"]), QPointF(b["x"], b["y"]))

            # Draw signal pulse (bright dot partway along)
            if sig > 0.3:
                t = (math.sin(self._tick * 0.05 + conn["speed"] * 4) + 1) / 2
                sx = a["x"] + (b["x"] - a["x"]) * t
                sy = a["y"] + (b["y"] - a["y"]) * t
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(sig_color))
                painter.drawEllipse(QPointF(sx, sy), 1.8 + sig, 1.8 + sig)

        # Nodes
        for layer_i, layer in enumerate(self._nodes):
            for n in layer:
                act = n["activation"]
                r = n["radius"] + act * 4

                # Outer halo
                halo_r = r * 3
                halo_grad = QLinearGradient(n["x"] - halo_r, n["y"] - halo_r,
                                            n["x"] + halo_r, n["y"] + halo_r)
                halo_alpha = int(act * 130)
                halo_grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), halo_alpha))
                halo_grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(halo_grad))
                painter.drawEllipse(QPointF(n["x"], n["y"]), halo_r, halo_r)

                # Core orb
                orb_color = QColor(
                    int(255 * act),
                    int(255 * act),
                    int(255 * act),
                    int(220 + act * 35),
                )
                painter.setBrush(QBrush(orb_color))
                painter.drawEllipse(QPointF(n["x"], n["y"]), r, r)

                # Colored ring
                ring_pen = QPen(QColor(c.red(), c.green(), c.blue(),
                                       int(180 * act + 50)), 1)
                painter.setPen(ring_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(n["x"], n["y"]), r + 2, r + 2)

        # Layer labels
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.setPen(QColor(c.red(), c.green(), c.blue(), 160))
        labels = ["INPUT", "HIDDEN", "HIDDEN", "OUTPUT"]
        for li, layer in enumerate(self._nodes):
            x = layer[0]["x"] if layer else self._x_for_layer(li)
            label = labels[li] if li < len(labels) else f"L{li}"
            rect = QRectF(x - 30, 4, 60, 14)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()
