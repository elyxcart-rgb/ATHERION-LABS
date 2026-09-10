"""SONIC AI — Ultra Premium Splash Screen.

Unique professional startup animation:
- Neural network visualization (AI brain)
- Hexagonal grid background
- DNA-style double helix
- Connected particle constellation
- Typography assembly animation
- Premium entry/exit transitions
"""
from __future__ import annotations

import math
import random
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QPen, QBrush, QPainterPath,
)
from PyQt6.QtWidgets import QWidget


class SonicSplash(QWidget):
    """Ultra premium splash with neural network + hex grid + DNA helix."""

    def __init__(self, on_done=None) -> None:
        super().__init__()
        self._on_done = on_done
        self._progress = 0.0
        self._tick_count = 0
        self._done = False
        self._phase = 0  # 0=assemble, 1=loading, 2=ready
        self._phase_time = 0
        self._intro_alpha = 0.0
        self._ready_alpha = 0.0
        self._pulse = 0.0

        # Neural network nodes
        self._nn_nodes = []
        self._nn_connections = []
        self._init_neural_network()

        # Hex grid
        self._hex_offset = 0.0

        # DNA helix
        self._dna_angle = 0.0

        # Constellation particles
        self._constellation = []
        self._init_constellation()

        # Typography animation
        self._letters = list("SONIC")
        self._letter_progress = [0.0] * 5

        self.setWindowTitle("SONIC AI")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 720)

        # Animation timer (~60fps)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        # Auto-finish timer
        self._finish_timer = QTimer(self)
        self._finish_timer.setSingleShot(True)
        self._finish_timer.timeout.connect(self._finish)
        self._finish_timer.start(5500)

        # Progress animation
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._advance_progress)
        self._progress_timer.start(25)

    def _init_neural_network(self) -> None:
        """Create AI brain-like neural network."""
        cx, cy = 260, 280
        # Create nodes in a brain-like cluster
        for i in range(35):
            angle = random.uniform(0, math.pi * 2)
            radius = random.uniform(20, 130)
            x = cx + math.cos(angle) * radius
            y = cy + math.sin(angle) * radius * 0.7  # Slightly oval
            self._nn_nodes.append({
                "x": x, "y": y,
                "vx": 0, "vy": 0,
                "pulse": random.uniform(0, math.pi * 2),
                "size": random.uniform(2, 5),
                "layer": random.randint(0, 2),
            })

        # Create connections (like synapses)
        for i in range(len(self._nn_nodes)):
            for j in range(i + 1, len(self._nn_nodes)):
                n1, n2 = self._nn_nodes[i], self._nn_nodes[j]
                dist = math.hypot(n1["x"] - n2["x"], n1["y"] - n2["y"])
                if dist < 100 and random.random() < 0.4:
                    self._nn_connections.append({
                        "from": i, "to": j,
                        "signal_progress": random.uniform(0, 1),
                        "active": random.random() < 0.3,
                    })

    def _init_constellation(self) -> None:
        """Create connected star particles."""
        for _ in range(50):
            self._constellation.append({
                "x": random.uniform(20, 500),
                "y": random.uniform(20, 700),
                "vx": random.uniform(-0.2, 0.2),
                "vy": random.uniform(-0.2, 0.2),
                "twinkle": random.uniform(0, math.pi * 2),
                "size": random.uniform(0.5, 2),
            })

    def _advance_progress(self) -> None:
        if self._progress < 100:
            remaining = 100 - self._progress
            self._progress += max(0.2, remaining * 0.035)

    def _tick(self) -> None:
        self._tick_count += 1
        self._pulse = (math.sin(self._tick_count * 0.05) + 1) / 2
        self._phase_time += 1
        self._hex_offset += 0.2
        self._dna_angle += 2.5

        # Phase transitions
        if self._phase == 0 and self._phase_time > 80:
            self._phase = 1
            self._phase_time = 0
        elif self._phase == 1 and self._progress >= 100:
            self._phase = 2
            self._phase_time = 0

        # Alpha animations
        if self._phase == 0:
            self._intro_alpha = min(1.0, self._phase_time / 60)
        if self._phase == 2:
            self._ready_alpha = min(1.0, self._phase_time / 30)

        # Letter assembly animation
        for i in range(5):
            delay = i * 12
            if self._phase_time > delay:
                self._letter_progress[i] = min(1.0, self._letter_progress[i] + 0.05)

        # Neural network pulse
        for node in self._nn_nodes:
            node["pulse"] += 0.08

        # Signal propagation through connections
        for conn in self._nn_connections:
            if conn["active"]:
                conn["signal_progress"] += 0.02
                if conn["signal_progress"] > 1.0:
                    conn["signal_progress"] = 0.0
                    conn["active"] = random.random() < 0.3

        # Constellation drift
        for star in self._constellation:
            star["x"] += star["vx"]
            star["y"] += star["vy"]
            star["twinkle"] += 0.03
            # Wrap around
            if star["x"] < 0: star["x"] = 520
            if star["x"] > 520: star["x"] = 0
            if star["y"] < 0: star["y"] = 720
            if star["y"] > 720: star["y"] = 0

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, 280

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 1: Deep space gradient
        # ═══════════════════════════════════════════════════════════════════
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(2, 4, 12))
        bg.setColorAt(0.3, QColor(6, 8, 18))
        bg.setColorAt(0.7, QColor(4, 6, 14))
        bg.setColorAt(1.0, QColor(2, 4, 10))
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 24, 24)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 2: Constellation background
        # ═══════════════════════════════════════════════════════════════════
        for star in self._constellation:
            twinkle = (math.sin(star["twinkle"]) + 1) / 2
            alpha = int(30 + twinkle * 50)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(150, 180, 220, alpha)))
            painter.drawEllipse(QPointF(star["x"], star["y"]),
                              star["size"], star["size"])

        # Connect nearby constellation stars
        const_pen = QPen(QColor(80, 120, 180, 15))
        const_pen.setWidth(1)
        painter.setPen(const_pen)
        for i in range(len(self._constellation)):
            for j in range(i + 1, min(i + 5, len(self._constellation))):
                s1, s2 = self._constellation[i], self._constellation[j]
                dist = math.hypot(s1["x"] - s2["x"], s1["y"] - s2["y"])
                if dist < 80:
                    alpha = int(15 * (1 - dist / 80))
                    const_pen.setColor(QColor(80, 120, 180, alpha))
                    painter.setPen(const_pen)
                    painter.drawLine(QPointF(s1["x"], s1["y"]),
                                   QPointF(s2["x"], s2["y"]))

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 3: Hexagonal grid
        # ═══════════════════════════════════════════════════════════════════
        hex_alpha = int(12 + self._pulse * 8)
        hex_pen = QPen(QColor(0, 160, 240, hex_alpha))
        hex_pen.setWidth(1)
        painter.setPen(hex_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        hex_size = 30
        hex_h = hex_size * math.sqrt(3)
        for row in range(-1, int(h / hex_h) + 2):
            for col in range(-1, int(w / (hex_size * 1.5)) + 2):
                x = col * hex_size * 1.5
                y = row * hex_h + (col % 2) * hex_h / 2
                y += self._hex_offset % hex_h
                if 0 < x < w and 0 < y < h:
                    self._draw_hexagon(painter, x, y, hex_size * 0.45)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 4: DNA Double Helix
        # ═══════════════════════════════════════════════════════════════════
        helix_alpha = int(60 + self._pulse * 40)
        helix_width = 60
        helix_height = 300
        helix_top = cy - 100

        # Draw helix strands
        for strand in range(2):
            strand_offset = math.pi * strand
            points = []
            for i in range(50):
                t = i / 49
                y = helix_top + t * helix_height
                x = cx + math.sin(self._dna_angle * 0.02 + t * math.pi * 4 + strand_offset) * helix_width
                points.append(QPointF(x, y))

            # Draw strand line
            strand_pen = QPen(QColor(0, 200, 255, helix_alpha))
            strand_pen.setWidth(2)
            strand_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(strand_pen)
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])

        # Draw cross-connections (rungs)
        rung_pen = QPen(QColor(0, 180, 255, helix_alpha // 2))
        rung_pen.setWidth(1)
        painter.setPen(rung_pen)
        for i in range(0, 50, 4):
            t = i / 49
            y = helix_top + t * helix_height
            x1 = cx + math.sin(self._dna_angle * 0.02 + t * math.pi * 4) * helix_width
            x2 = cx + math.sin(self._dna_angle * 0.02 + t * math.pi * 4 + math.pi) * helix_width
            painter.drawLine(QPointF(x1, y), QPointF(x2, y))

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 5: Neural Network
        # ═══════════════════════════════════════════════════════════════════
        # Draw connections first (behind nodes)
        for conn in self._nn_connections:
            n1 = self._nn_nodes[conn["from"]]
            n2 = self._nn_nodes[conn["to"]]

            if conn["active"]:
                # Animated signal
                alpha = int(40 + self._pulse * 30)
                conn_pen = QPen(QColor(0, 220, 255, alpha))
            else:
                alpha = int(15 + self._pulse * 10)
                conn_pen = QPen(QColor(0, 140, 200, alpha))
            conn_pen.setWidth(1)
            painter.setPen(conn_pen)
            painter.drawLine(QPointF(n1["x"], n1["y"]),
                           QPointF(n2["x"], n2["y"]))

            # Signal dot
            if conn["active"]:
                prog = conn["signal_progress"]
                sx = n1["x"] + (n2["x"] - n1["x"]) * prog
                sy = n1["y"] + (n2["y"] - n1["y"]) * prog
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(0, 240, 255, int(150 * (1 - prog)))))
                painter.drawEllipse(QPointF(sx, sy), 3, 3)

        # Draw nodes
        for node in self._nn_nodes:
            pulse = (math.sin(node["pulse"]) + 1) / 2
            node_alpha = int(100 + pulse * 100)

            # Outer glow
            glow_r = node["size"] * 3
            glow = QRadialGradient(node["x"], node["y"], glow_r)
            glow.setColorAt(0.0, QColor(0, 200, 255, node_alpha // 4))
            glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(node["x"], node["y"]),
                              glow_r, glow_r)

            # Core node
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 220, 255, node_alpha)))
            painter.drawEllipse(QPointF(node["x"], node["y"]),
                              node["size"], node["size"])

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 6: Central Core Energy
        # ═══════════════════════════════════════════════════════════════════
        core_r = 25 + self._pulse * 8
        core_grad = QRadialGradient(cx, cy, core_r)
        core_alpha = int(180 + self._pulse * 75)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, core_alpha))
        core_grad.setColorAt(0.2, QColor(0, 240, 255, core_alpha // 2))
        core_grad.setColorAt(0.5, QColor(0, 180, 255, core_alpha // 4))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 7: Rotating Rings
        # ═══════════════════════════════════════════════════════════════════
        # Outer hexagonal ring
        ring_pen = QPen(QColor(0, 200, 255, int(50 + self._pulse * 30)))
        ring_pen.setWidth(2)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        self._draw_hexagon(painter, cx, cy, 80 + self._pulse * 5)

        # Inner rotating arc
        arc_pen = QPen(QColor(0, 220, 255, int(80 + self._pulse * 50)))
        arc_pen.setWidth(3)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        r_inner = 50
        rect_inner = QRectF(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2)
        painter.drawArc(rect_inner, int(self._tick_count * 3), 60 * 16)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 8: SONIC Title (Assembly Animation)
        # ═══════════════════════════════════════════════════════════════════
        title_y = cy + 160
        total_width = 0
        letter_widths = []
        title_font = QFont("Segoe UI", 48, QFont.Weight.Bold)
        painter.setFont(title_font)
        for letter in self._letters:
            fm = painter.fontMetrics()
            lw = fm.horizontalAdvance(letter)
            letter_widths.append(lw)
            total_width += lw + 8
        total_width -= 8  # Remove last gap

        start_x = (w - total_width) / 2
        for i, letter in enumerate(self._letters):
            prog = self._letter_progress[i]
            if prog <= 0:
                continue

            lx = start_x + sum(letter_widths[:i]) + i * 8
            ly = title_y

            # Each letter fades in from different direction
            offset_y = int((1 - prog) * 30)
            alpha = int(255 * prog)

            # Letter glow
            letter_glow = QRadialGradient(lx + letter_widths[i] / 2, ly, 40)
            letter_glow.setColorAt(0.0, QColor(0, 200, 255, alpha // 6))
            letter_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(letter_glow))
            painter.drawEllipse(QPointF(lx + letter_widths[i] / 2, ly + 10),
                              40, 30)

            # Letter text
            painter.setPen(QColor(0, 240, 255, alpha))
            painter.drawText(QRectF(lx, ly + offset_y, letter_widths[i], 60),
                           Qt.AlignmentFlag.AlignCenter, letter)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 9: Subtitle with fade
        # ═══════════════════════════════════════════════════════════════════
        sub_alpha = int(160 * self._intro_alpha)
        sub_font = QFont("Segoe UI", 12, QFont.Weight.Light)
        painter.setFont(sub_font)
        painter.setPen(QColor(120, 160, 200, sub_alpha))
        painter.drawText(QRectF(0, title_y + 65, w, 25),
                       Qt.AlignmentFlag.AlignCenter,
                       "A R T I F I C I A L   I N T E L L I G E N C E")

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 10: Decorative accent lines
        # ═══════════════════════════════════════════════════════════════════
        accent_y = title_y + 100
        accent_alpha = int(50 + self._pulse * 30)
        accent_pen = QPen(QColor(0, 180, 255, accent_alpha))
        accent_pen.setWidth(1)
        painter.setPen(accent_pen)

        # Left accent
        painter.drawLine(cx - 140, accent_y, cx - 30, accent_y)
        # Right accent
        painter.drawLine(cx + 30, accent_y, cx + 140, accent_y)

        # Center diamond
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 200, 255, accent_alpha + 20)))
        diamond = QPainterPath()
        diamond.moveTo(cx, accent_y - 5)
        diamond.lineTo(cx + 6, accent_y)
        diamond.lineTo(cx, accent_y + 5)
        diamond.lineTo(cx - 6, accent_y)
        diamond.closeSubpath()
        painter.drawPath(diamond)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 11: Progress Bar (Premium)
        # ═══════════════════════════════════════════════════════════════════
        bar_y = accent_y + 40
        bar_w = 280
        bar_h = 3
        bar_x = (w - bar_w) / 2

        # Bar background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(15, 25, 35)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        # Bar fill
        fill_w = bar_w * min(self._progress, 100) / 100
        if fill_w > 0:
            # Fill glow
            fill_glow = QRadialGradient(bar_x + fill_w, bar_y + 1, 12)
            fill_glow.setColorAt(0.0, QColor(0, 220, 255, 50))
            fill_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(fill_glow))
            painter.drawEllipse(QPointF(bar_x + fill_w, bar_y + 1), 12, 6)

            # Fill gradient
            bar_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            bar_grad.setColorAt(0.0, QColor(0, 140, 200))
            bar_grad.setColorAt(0.7, QColor(0, 210, 255))
            bar_grad.setColorAt(1.0, QColor(0, 240, 255))
            painter.setBrush(QBrush(bar_grad))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 12: Status Text
        # ═══════════════════════════════════════════════════════════════════
        status_font = QFont("Segoe UI", 9, QFont.Weight.Light)
        painter.setFont(status_font)
        painter.setPen(QColor(80, 120, 160, int(140 * self._intro_alpha)))

        pct = min(int(self._progress), 100)
        if self._phase == 0:
            status_text = "INITIALIZING NEURAL CORE"
        elif self._phase == 2:
            status_text = "SYSTEM READY"
        else:
            status_text = f"LOADING  {pct}%"

        painter.drawText(QRectF(0, bar_y + 14, w, 20),
                       Qt.AlignmentFlag.AlignCenter, status_text)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 13: "LIMITED TIME FREE" Banner
        # ═══════════════════════════════════════════════════════════════════
        banner_y = h - 110
        banner_h = 65

        # Banner glow
        banner_glow = QRadialGradient(cx, banner_y + banner_h // 2, 140)
        banner_glow.setColorAt(0.0, QColor(0, 200, 255, int(12 * self._intro_alpha)))
        banner_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(banner_glow))
        painter.drawEllipse(QPointF(cx, banner_y + banner_h // 2), 140, 35)

        # Banner border
        banner_border = QPen(QColor(0, 180, 255, int(60 * self._intro_alpha)))
        banner_border.setWidth(1)
        painter.setPen(banner_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(60, banner_y, w - 120, banner_h), 8, 8)

        # Main text
        banner_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
        painter.setFont(banner_font)
        painter.setPen(QColor(0, 240, 255, int(255 * self._intro_alpha)))
        painter.drawText(QRectF(0, banner_y + 8, w, 30),
                       Qt.AlignmentFlag.AlignCenter, "LIMITED TIME FREE")

        # Sub text
        small_font = QFont("Segoe UI", 9, QFont.Weight.Light)
        painter.setFont(small_font)
        painter.setPen(QColor(80, 140, 180, int(140 * self._intro_alpha)))
        painter.drawText(QRectF(0, banner_y + 40, w, 18),
                       Qt.AlignmentFlag.AlignCenter,
                       "All features unlocked during beta period")

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 14: Version
        # ═══════════════════════════════════════════════════════════════════
        from version import APP_VERSION
        ver_font = QFont("Segoe UI", 8, QFont.Weight.Light)
        painter.setFont(ver_font)
        painter.setPen(QColor(50, 70, 90, int(80 * self._intro_alpha)))
        painter.drawText(QRectF(0, h - 30, w, 20),
                       Qt.AlignmentFlag.AlignCenter, f"v{APP_VERSION}")

        painter.end()

    def _draw_hexagon(self, painter: QPainter, cx: float, cy: float, size: float) -> None:
        """Draw a hexagon at the given position."""
        path = QPainterPath()
        for i in range(6):
            angle = math.radians(60 * i - 30)
            x = cx + size * math.cos(angle)
            y = cy + size * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()
        painter.drawPath(path)

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._progress_timer.stop()
        if self._on_done:
            self._on_done()
