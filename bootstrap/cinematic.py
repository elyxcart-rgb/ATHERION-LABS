"""SONIC AI — Cinematic Boot Animation.

Ultra-premium first-run opening sequence:
- VOID → SPARK → FORMING → ACTIVATING → REVEAL → INITIALIZING → READY
- Layered intelligence core with breathing motion
- Signature asymmetric orbital arc
- System scan with status labels
- Seamless transition to setup UI
"""
from __future__ import annotations

import math
import random
from enum import Enum
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QFont, QPen, QBrush, QPainterPath, QFontMetrics,
)
from PyQt6.QtWidgets import QWidget


# ── Boot States ──────────────────────────────────────────────────────────
class BootState(Enum):
    VOID = "void"              # 0.00-0.35s — black void
    SPARK = "spark"            # 0.35-0.75s — intelligence spark
    FORMING = "forming"        # 0.75-1.25s — rings form
    ACTIVATING = "activating"  # 1.25-1.80s — orbital system activates
    REVEAL = "reveal"          # 1.80-2.30s — SONIC AI appears
    SUBTITLE = "subtitle"      # 2.30-2.70s — subtitle appears
    INITIALIZING = "initializing"  # 2.70s+ — real setup begins
    READY = "ready"            # setup complete
    ERROR = "error"            # setup failed


# ── Theme Colors (matching SONIC design system) ──────────────────────────
class _C:
    BG = "#05070a"
    BG2 = "#0a0d12"
    PRI = "#00d9ff"
    PRI_DIM = "#004d66"
    PRI_VIVID = "#00eaff"
    TEXT = "#c8cdd4"
    TEXT_DIM = "#4a5568"
    METALLIC = "#4a5568"
    BORDER = "#1e2530"


class SonicBootAnimation(QWidget):
    """Cinematic boot animation for first-run experience."""

    boot_complete = pyqtSignal()  # emitted when cinematic sequence finishes
    state_changed = pyqtSignal(str)  # emits current boot state

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = BootState.VOID
        self._tick_count = 0
        self._state_time = 0
        self._pulse = 0.0
        self._breath = 0.0

        # Core animation parameters
        self._core_alpha = 0.0
        self._core_scale = 0.0
        self._ring_alpha = 0.0
        self._scan_angle = 0.0
        self._scan_active = False

        # Text animation
        self._title_alpha = 0.0
        self._title_offset = 20.0
        self._subtitle_alpha = 0.0
        self._subtitle_offset = 15.0
        self._sonic_alpha = 0.0
        self._ai_alpha = 0.0

        # Particles (minimal)
        self._particles = []
        for _ in range(12):
            self._particles.append({
                "angle": random.uniform(0, math.pi * 2),
                "radius": random.uniform(50, 90),
                "speed": random.uniform(0.005, 0.015),
                "size": random.uniform(0.8, 2.0),
                "alpha": random.uniform(0.3, 0.8),
            })

        # Signature asymmetric orbital arc
        self._arc_angle = 0.0
        self._arc_alpha = 0.0

        # Status labels for scan phase
        self._scan_labels = ["SYSTEM", "AUDIO", "RUNTIME", "TOOLS", "MEMORY"]
        self._scan_label_index = 0
        self._scan_label_alpha = 0.0

        # Setup state (set by external code)
        self._setup_state = "init"
        self._setup_progress = 0
        self._setup_message = ""

        # Reduced motion
        self._reduced_motion = False

        # Timer (~60fps)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        # Boot sequence timer
        self._boot_timer = QTimer(self)
        self._boot_timer.setSingleShot(True)
        self._boot_timer.timeout.connect(self._advance_boot_state)

        # Start the cinematic sequence
        self._start_boot_sequence()

    def _start_boot_sequence(self):
        """Begin the cinematic boot sequence."""
        self._state = BootState.VOID
        self._state_time = 0
        self._boot_timer.start(350)  # 0.35s void
        self.state_changed.emit(self._state.value)

    def _advance_boot_state(self):
        """Advance to the next boot state."""
        if self._state == BootState.VOID:
            self._state = BootState.SPARK
            self._boot_timer.start(400)  # 0.40s spark
        elif self._state == BootState.SPARK:
            self._state = BootState.FORMING
            self._boot_timer.start(500)  # 0.50s forming
        elif self._state == BootState.FORMING:
            self._state = BootState.ACTIVATING
            self._boot_timer.start(550)  # 0.55s activating
        elif self._state == BootState.ACTIVATING:
            self._state = BootState.REVEAL
            self._boot_timer.start(500)  # 0.50s reveal
        elif self._state == BootState.REVEAL:
            self._state = BootState.SUBTITLE
            self._boot_timer.start(400)  # 0.40s subtitle
        elif self._state == BootState.SUBTITLE:
            self._state = BootState.INITIALIZING
            self._boot_timer.start(300)  # brief pause
            self.boot_complete.emit()
        elif self._state == BootState.READY:
            # Final state — settled
            pass
        elif self._state == BootState.ERROR:
            # Error state — settled
            pass

        self._state_time = 0
        self.state_changed.emit(self._state.value)

    def set_setup_state(self, state: str, progress: int = 0, message: str = ""):
        """Update with real setup state from backend."""
        self._setup_state = state
        self._setup_progress = progress
        self._setup_message = message

        if state == "ready":
            self._state = BootState.READY
            self.state_changed.emit("ready")
        elif state == "error":
            self._state = BootState.ERROR
            self.state_changed.emit("error")

    def set_reduced_motion(self, enabled: bool):
        """Enable reduced motion mode."""
        self._reduced_motion = enabled

    def _tick(self):
        """Main animation tick (~60fps)."""
        self._tick_count += 1
        self._state_time += 1
        self._pulse = (math.sin(self._tick_count * 0.04) + 1) / 2
        self._breath = (math.sin(self._tick_count * 0.025) + 1) / 2

        # State-specific animations
        if self._state == BootState.VOID:
            self._core_alpha = 0.0
            self._core_scale = 0.0

        elif self._state == BootState.SPARK:
            progress = min(1.0, self._state_time / 40)
            self._core_alpha = progress * 0.6
            self._core_scale = progress * 0.3

        elif self._state == BootState.FORMING:
            progress = min(1.0, self._state_time / 50)
            self._core_alpha = 0.6 + progress * 0.4
            self._core_scale = 0.3 + progress * 0.7
            self._ring_alpha = progress

        elif self._state == BootState.ACTIVATING:
            progress = min(1.0, self._state_time / 55)
            self._core_alpha = 1.0
            self._core_scale = 1.0
            self._ring_alpha = 1.0
            self._arc_alpha = progress
            self._scan_active = True
            self._scan_angle += 3.0

        elif self._state == BootState.REVEAL:
            progress = min(1.0, self._state_time / 50)
            self._title_alpha = progress
            self._title_offset = 20 * (1 - progress)
            self._arc_alpha = 1.0

        elif self._state == BootState.SUBTITLE:
            progress = min(1.0, self._state_time / 40)
            self._subtitle_alpha = progress
            self._subtitle_offset = 15 * (1 - progress)

        elif self._state == BootState.INITIALIZING:
            # Settled state — breathing continues
            self._title_alpha = 1.0
            self._subtitle_alpha = 1.0
            self._arc_alpha = 0.8 + self._pulse * 0.2

        elif self._state == BootState.READY:
            # Calm settled state
            self._title_alpha = 1.0
            self._subtitle_alpha = 1.0
            self._arc_alpha = 0.6 + self._pulse * 0.1

        elif self._state == BootState.ERROR:
            # Error state — dim
            self._title_alpha = 0.7
            self._subtitle_alpha = 0.5
            self._arc_alpha = 0.3

        # Update particles
        for p in self._particles:
            if not self._reduced_motion:
                p["angle"] += p["speed"]
            # Breathing radius
            p["current_radius"] = p["radius"] + self._breath * 5

        # Update signature arc
        if not self._reduced_motion:
            self._arc_angle += 0.8

        # Update scan labels
        if self._scan_active and self._state == BootState.ACTIVATING:
            label_progress = self._state_time / 55
            self._scan_label_index = min(
                len(self._scan_labels) - 1,
                int(label_progress * len(self._scan_labels))
            )
            self._scan_label_alpha = min(1.0, (label_progress * len(self._scan_labels)) % 1.0)

        self.update()

    def paintEvent(self, event) -> None:
        """Render the cinematic boot animation."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 - 20

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 1: Deep void background
        # ═══════════════════════════════════════════════════════════════════
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor("#05070a"))
        bg.setColorAt(0.5, QColor("#0a0d12"))
        bg.setColorAt(1.0, QColor("#05070a"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRect(0, 0, w, h)

        # Subtle radial vignette
        vignette = QRadialGradient(cx, cy, max(w, h) * 0.5)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 60))
        painter.setBrush(QBrush(vignette))
        painter.drawRect(0, 0, w, h)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 2: Intelligence Core (only if alpha > 0)
        # ═══════════════════════════════════════════════════════════════════
        if self._core_alpha > 0.01:
            self._paint_core(painter, cx, cy)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 3: Signature asymmetric orbital arc
        # ═══════════════════════════════════════════════════════════════════
        if self._arc_alpha > 0.01:
            self._paint_signature_arc(painter, cx, cy)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 4: Micro particles
        # ═══════════════════════════════════════════════════════════════════
        if self._core_alpha > 0.1:
            self._paint_particles(painter, cx, cy)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 5: Scan line (during ACTIVATING)
        # ═══════════════════════════════════════════════════════════════════
        if self._scan_active and self._state in (BootState.ACTIVATING, BootState.REVEAL):
            self._paint_scan(painter, cx, cy)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 6: Title "SONIC" + "AI"
        # ═══════════════════════════════════════════════════════════════════
        if self._title_alpha > 0.01:
            self._paint_title(painter, w, cy)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 7: Subtitle
        # ═══════════════════════════════════════════════════════════════════
        if self._subtitle_alpha > 0.01:
            self._paint_subtitle(painter, w, cy)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 8: Status labels (scan phase)
        # ═══════════════════════════════════════════════════════════════════
        if self._state == BootState.ACTIVATING and self._scan_label_alpha > 0.1:
            self._paint_scan_labels(painter, cx, cy)

        painter.end()

    def _paint_core(self, painter: QPainter, cx: int, cy: int) -> None:
        """Paint the multi-layered intelligence core."""
        # Outer ambient glow
        glow_r = 80 * self._core_scale + self._breath * 8
        glow = QRadialGradient(cx, cy, glow_r)
        glow_alpha = int(self._core_alpha * 25)
        glow.setColorAt(0.0, QColor(0, 200, 255, glow_alpha))
        glow.setColorAt(0.4, QColor(0, 120, 200, glow_alpha // 3))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # Outer ring (thin, static)
        if self._ring_alpha > 0.01:
            outer_r = 65 * self._core_scale
            outer_pen = QPen(QColor(30, 57, 74, int(self._ring_alpha * 40)))
            outer_pen.setWidth(1)
            painter.setPen(outer_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # Rotating energy ring 1
        if self._ring_alpha > 0.01:
            ring1_r = 52 * self._core_scale
            ring1_pen = QPen(QColor(0, 217, 255, int(self._ring_alpha * 80)))
            ring1_pen.setWidth(2)
            ring1_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(ring1_pen)
            rect1 = QRectF(cx - ring1_r, cy - ring1_r, ring1_r * 2, ring1_r * 2)
            painter.drawArc(rect1, int(self._tick_count * 2), 50 * 16)

        # Rotating energy ring 2 (opposite direction)
        if self._ring_alpha > 0.01:
            ring2_r = 45 * self._core_scale
            ring2_pen = QPen(QColor(0, 150, 200, int(self._ring_alpha * 50)))
            ring2_pen.setWidth(1)
            painter.setPen(ring2_pen)
            rect2 = QRectF(cx - ring2_r, cy - ring2_r, ring2_r * 2, ring2_r * 2)
            painter.drawArc(rect2, int(-self._tick_count * 1.5), 40 * 16)

        # Inner glass core
        core_r = 28 * self._core_scale + self._breath * 3
        core_grad = QRadialGradient(cx, cy, core_r)
        core_alpha = int(self._core_alpha * 200)
        if self._state == BootState.ERROR:
            core_grad.setColorAt(0.0, QColor(255, 100, 80, core_alpha))
            core_grad.setColorAt(0.5, QColor(200, 60, 50, core_alpha // 2))
        else:
            core_grad.setColorAt(0.0, QColor(224, 228, 234, core_alpha))  # Platinum
            core_grad.setColorAt(0.3, QColor(0, 217, 255, core_alpha // 2))
            core_grad.setColorAt(0.7, QColor(0, 150, 200, core_alpha // 4))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Center luminous orb
        orb_r = 8 * self._core_scale + self._pulse * 2
        orb_grad = QRadialGradient(cx, cy, orb_r)
        orb_alpha = int(self._core_alpha * 255)
        orb_grad.setColorAt(0.0, QColor(255, 255, 255, orb_alpha))
        orb_grad.setColorAt(0.4, QColor(0, 234, 255, orb_alpha // 2))
        orb_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(orb_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

    def _paint_signature_arc(self, painter: QPainter, cx: int, cy: int) -> None:
        """Paint SONIC's signature asymmetric orbital arc."""
        arc_r = 70
        arc_pen = QPen(QColor(0, 217, 255, int(self._arc_alpha * 60)))
        arc_pen.setWidth(2)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)

        # Asymmetric arc — 120 degrees, offset
        start_angle = int(self._arc_angle)
        span_angle = 120 * 16
        rect = QRectF(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2)
        painter.drawArc(rect, start_angle, span_angle)

        # Secondary smaller arc (60 degrees, offset by 180)
        arc2_pen = QPen(QColor(0, 150, 200, int(self._arc_alpha * 30)))
        arc2_pen.setWidth(1)
        painter.setPen(arc2_pen)
        arc2_r = 58
        rect2 = QRectF(cx - arc2_r, cy - arc2_r, arc2_r * 2, arc2_r * 2)
        painter.drawArc(rect2, start_angle + 180 * 16, 60 * 16)

    def _paint_particles(self, painter: QPainter, cx: int, cy: int) -> None:
        """Paint micro particles orbiting the core."""
        for p in self._particles:
            r = p.get("current_radius", p["radius"])
            px = cx + math.cos(p["angle"]) * r * self._core_scale
            py = cy + math.sin(p["angle"]) * r * self._core_scale
            alpha = int(p["alpha"] * self._core_alpha * 150)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 200, 255, alpha)))
            painter.drawEllipse(QPointF(px, py), p["size"], p["size"])

    def _paint_scan(self, painter: QPainter, cx: int, cy: int) -> None:
        """Paint radial scan line."""
        scan_r = 90 * self._core_scale
        scan_pen = QPen(QColor(0, 217, 255, 20))
        scan_pen.setWidth(1)
        painter.setPen(scan_pen)

        angle_rad = math.radians(self._scan_angle)
        ex = cx + math.cos(angle_rad) * scan_r
        ey = cy + math.sin(angle_rad) * scan_r
        painter.drawLine(QPointF(cx, cy), QPointF(ex, ey))

    def _paint_title(self, painter: QPainter, w: int, cy: int) -> None:
        """Paint SONIC AI title with kinetic typography."""
        title_y = cy + 100

        # "SONIC" — main title
        sonic_alpha = int(self._title_alpha * 255)
        sonic_font = QFont("Segoe UI", 42, QFont.Weight.Bold)
        painter.setFont(sonic_font)
        fm = painter.fontMetrics()
        sonic_width = fm.horizontalAdvance("SONIC")

        # "AI" — accent
        ai_font = QFont("Segoe UI", 42, QFont.Weight.Light)
        painter.setFont(ai_font)
        ai_width = fm.horizontalAdvance("AI")

        total_width = sonic_width + 15 + ai_width
        start_x = (w - total_width) / 2

        # SONIC
        painter.setPen(QColor(0, 217, 255, sonic_alpha))
        painter.setFont(sonic_font)
        painter.drawText(
            QRectF(start_x, title_y + self._title_offset, sonic_width, 60),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "SONIC"
        )

        # AI (slightly delayed, platinum color)
        ai_alpha = int(self._sonic_alpha * 255) if self._sonic_alpha > 0 else int(self._title_alpha * 200)
        painter.setPen(QColor(200, 210, 220, ai_alpha))
        painter.setFont(ai_font)
        painter.drawText(
            QRectF(start_x + sonic_width + 15, title_y + self._title_offset, ai_width, 60),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "AI"
        )

    def _paint_subtitle(self, painter: QPainter, w: int, cy: int) -> None:
        """Paint subtitle text."""
        sub_y = cy + 165
        sub_alpha = int(self._subtitle_alpha * 140)
        sub_font = QFont("Segoe UI", 12, QFont.Weight.Light)
        painter.setFont(sub_font)
        painter.setPen(QColor(74, 85, 104, sub_alpha))

        if self._state == BootState.READY:
            text = "Your personal intelligence is ready."
        elif self._state == BootState.ERROR:
            text = "Initialization needs attention."
        else:
            text = "Your personal intelligence is initializing."

        painter.drawText(
            QRectF(0, sub_y + self._subtitle_offset, w, 25),
            Qt.AlignmentFlag.AlignCenter,
            text
        )

    def _paint_scan_labels(self, painter: QPainter, cx: int, cy: int) -> None:
        """Paint small status labels during scan phase."""
        label_font = QFont("Consolas", 8)
        painter.setFont(label_font)

        for i, label in enumerate(self._scan_labels):
            # Position around the core
            angle = math.radians(-90 + i * 72)  # 72 degrees apart
            label_r = 110
            lx = cx + math.cos(angle) * label_r
            ly = cy + math.sin(angle) * label_r

            # Fade based on scan progress
            if i <= self._scan_label_index:
                alpha = int(self._scan_label_alpha * 100) if i == self._scan_label_index else 80
            else:
                alpha = 0

            painter.setPen(QColor(0, 200, 255, alpha))
            painter.drawText(
                QRectF(lx - 30, ly - 8, 60, 16),
                Qt.AlignmentFlag.AlignCenter,
                label
            )

    def stop(self):
        """Stop all animation timers."""
        self._timer.stop()
        self._boot_timer.stop()

    def cleanup(self):
        """Clean up resources."""
        self.stop()
