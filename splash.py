"""SONIC AI — Premium Cinematic Splash Screen.

Ultra-premium loading animation with multi-layer effects:
- Rotating energy rings with different speeds
- Particle systems (dust, sparks, energy trails)
- Holographic grid background
- Dynamic text reveal with glitch effect
- Light rays and lens flare
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
    """Premium cinematic splash screen with multi-layer effects."""

    def __init__(self, on_done=None) -> None:
        super().__init__()
        self._on_done = on_done
        self._progress = 0.0
        self._angle = 0.0
        self._pulse = 0.0
        self._done = False
        self._phase = 0  # 0=intro, 1=loading, 2=ready
        self._phase_time = 0
        self._intro_alpha = 0.0
        self._ready_alpha = 0.0
        self._glitch_offset = 0
        self._scan_line = 0
        self._grid_offset = 0
        self._rays_angle = 0

        # Particle systems
        self._dust_particles = []
        self._spark_particles = []
        self._energy_trails = []

        # Stars
        self._stars = []
        for _ in range(80):
            self._stars.append({
                "x": random.randint(0, 600),
                "y": random.randint(0, 800),
                "size": random.uniform(0.5, 2.0),
                "twinkle": random.uniform(0, math.pi * 2),
            })

        self.setWindowTitle("SONIC AI")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 700)

        # Animation timer (~60fps)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

        # Auto-finish timer
        self._finish_timer = QTimer(self)
        self._finish_timer.setSingleShot(True)
        self._finish_timer.timeout.connect(self._finish)
        self._finish_timer.start(5000)

        # Progress animation
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._advance_progress)
        self._progress_timer.start(25)

    def _advance_progress(self) -> None:
        if self._progress < 100:
            remaining = 100 - self._progress
            self._progress += max(0.2, remaining * 0.035)

    def _tick(self) -> None:
        self._angle += 1.8
        self._pulse = (math.sin(self._angle * 0.04) + 1) / 2
        self._phase_time += 1
        self._grid_offset += 0.3
        self._rays_angle += 0.5
        self._scan_line = (self._scan_line + 2) % self.height()

        # Phase transitions
        if self._phase == 0 and self._phase_time > 60:
            self._phase = 1
            self._phase_time = 0
        elif self._phase == 1 and self._progress >= 100:
            self._phase = 2
            self._phase_time = 0

        # Intro alpha
        if self._phase == 0:
            self._intro_alpha = min(1.0, self._phase_time / 40)
        if self._phase == 2:
            self._ready_alpha = min(1.0, self._phase_time / 30)

        # Glitch effect (random during loading)
        if self._phase == 1 and random.random() < 0.03:
            self._glitch_offset = random.randint(-3, 3)
        else:
            self._glitch_offset = 0

        # Spawn dust particles
        if len(self._dust_particles) < 40:
            self._dust_particles.append({
                "x": random.uniform(0, self.width()),
                "y": self.height() + 10,
                "vx": random.uniform(-0.3, 0.3),
                "vy": random.uniform(-1.5, -0.5),
                "life": 1.0,
                "size": random.uniform(1, 3),
            })

        # Spawn spark particles from center
        if len(self._spark_particles) < 15 and self._progress < 95:
            cx, cy = self.width() // 2, self.height() // 2 - 60
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(1, 3)
            self._spark_particles.append({
                "x": cx,
                "y": cy,
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed,
                "life": 1.0,
                "size": random.uniform(1, 2.5),
            })

        # Spawn energy trails
        if len(self._energy_trails) < 8 and self._phase == 1:
            cx, cy = self.width() // 2, self.height() // 2 - 60
            self._energy_trails.append({
                "x": cx + random.uniform(-60, 60),
                "y": cy + random.uniform(-60, 60),
                "target_x": cx,
                "target_y": cy,
                "life": 1.0,
                "progress": 0,
            })

        # Update particles
        for p in self._dust_particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] -= 0.008
        self._dust_particles = [p for p in self._dust_particles if p["life"] > 0]

        for p in self._spark_particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.98
            p["vy"] *= 0.98
            p["life"] -= 0.025
        self._spark_particles = [p for p in self._spark_particles if p["life"] > 0]

        for t in self._energy_trails:
            t["progress"] += 0.03
            t["life"] -= 0.015
            t["x"] += (t["target_x"] - t["x"]) * 0.1
            t["y"] += (t["target_y"] - t["y"]) * 0.1
        self._energy_trails = [t for t in self._energy_trails if t["life"] > 0]

        # Update stars twinkle
        for s in self._stars:
            s["twinkle"] += 0.05

        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w // 2, h // 2 - 60

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 1: Deep space background
        # ═══════════════════════════════════════════════════════════════════
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(4, 6, 14))
        bg.setColorAt(0.3, QColor(8, 10, 20))
        bg.setColorAt(0.7, QColor(6, 8, 16))
        bg.setColorAt(1.0, QColor(4, 6, 14))
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, w, h, 24, 24)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 2: Star field
        # ═══════════════════════════════════════════════════════════════════
        for s in self._stars:
            twinkle = (math.sin(s["twinkle"]) + 1) / 2
            alpha = int(40 + twinkle * 60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(180, 200, 220, alpha)))
            painter.drawEllipse(QPointF(s["x"], s["y"]), s["size"], s["size"])

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 3: Holographic grid
        # ═══════════════════════════════════════════════════════════════════
        grid_alpha = int(15 + self._pulse * 10)
        grid_pen = QPen(QColor(0, 180, 255, grid_alpha))
        grid_pen.setWidth(1)

        # Horizontal grid lines
        for i in range(0, h, 40):
            y = (i + self._grid_offset) % h
            painter.setPen(grid_pen)
            painter.drawLine(0, int(y), w, int(y))

        # Vertical grid lines (perspective effect)
        for i in range(0, w, 40):
            x = (i + self._grid_offset * 0.5) % w
            painter.setPen(grid_pen)
            painter.drawLine(int(x), 0, int(x), h)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 4: Light rays / lens flare
        # ═══════════════════════════════════════════════════════════════════
        ray_alpha = int(20 + self._pulse * 15)
        for i in range(6):
            angle = self._rays_angle + i * 60
            ray_len = 180 + self._pulse * 30
            ray_x = cx + math.cos(math.radians(angle)) * ray_len
            ray_y = cy + math.sin(math.radians(angle)) * ray_len

            ray_grad = QLinearGradient(cx, cy, ray_x, ray_y)
            ray_grad.setColorAt(0.0, QColor(0, 200, 255, ray_alpha))
            ray_grad.setColorAt(0.5, QColor(0, 150, 255, ray_alpha // 3))
            ray_grad.setColorAt(1.0, QColor(0, 0, 0, 0))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(ray_grad))

            path = QPainterPath()
            path.moveTo(cx, cy)
            dx = math.cos(math.radians(angle - 5)) * ray_len
            dy = math.sin(math.radians(angle - 5)) * ray_len
            path.lineTo(cx + dx, cy + dy)
            dx2 = math.cos(math.radians(angle + 5)) * ray_len
            dy2 = math.sin(math.radians(angle + 5)) * ray_len
            path.lineTo(cx + dx2, cy + dy2)
            path.closeSubpath()
            painter.drawPath(path)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 5: Outer ambient glow
        # ═══════════════════════════════════════════════════════════════════
        glow_r = 140 + self._pulse * 25
        glow = QRadialGradient(cx, cy, glow_r)
        glow_alpha = int(35 + self._pulse * 25)
        glow.setColorAt(0.0, QColor(0, 200, 255, glow_alpha))
        glow.setColorAt(0.4, QColor(0, 120, 200, glow_alpha // 4))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 6: Rotating energy rings (3 layers)
        # ═══════════════════════════════════════════════════════════════════
        # Outer ring (slow)
        ring1_pen = QPen(QColor(0, 200, 255, int(60 + self._pulse * 40)))
        ring1_pen.setWidth(2)
        painter.setPen(ring1_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        r1 = 70
        rect1 = QRectF(cx - r1, cy - r1, r1 * 2, r1 * 2)
        painter.drawArc(rect1, int(self._angle * 8), 60 * 16)
        painter.drawArc(rect1, int(self._angle * 8 + 180 * 16), 60 * 16)

        # Middle ring (medium)
        ring2_pen = QPen(QColor(0, 220, 255, int(80 + self._pulse * 50)))
        ring2_pen.setWidth(2)
        ring2_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(ring2_pen)
        r2 = 55
        rect2 = QRectF(cx - r2, cy - r2, r2 * 2, r2 * 2)
        painter.drawArc(rect2, int(-self._angle * 12), 45 * 16)

        # Inner ring (fast)
        ring3_pen = QPen(QColor(0, 240, 255, int(100 + self._pulse * 60)))
        ring3_pen.setWidth(3)
        ring3_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(ring3_pen)
        r3 = 42
        rect3 = QRectF(cx - r3, cy - r3, r3 * 2, r3 * 2)
        painter.drawArc(rect3, int(self._angle * 18), 30 * 16)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 7: Orbital dots
        # ═══════════════════════════════════════════════════════════════════
        for i in range(8):
            dot_angle = self._angle * 2 + i * 45
            dot_r = 65
            dx = cx + math.cos(math.radians(dot_angle)) * dot_r
            dy = cy + math.sin(math.radians(dot_angle)) * dot_r
            dot_alpha = int(120 + self._pulse * 80)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 220, 255, dot_alpha)))
            painter.drawEllipse(QPointF(dx, dy), 2, 2)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 8: Inner glowing core
        # ═══════════════════════════════════════════════════════════════════
        core_r = 30 + self._pulse * 6
        core_grad = QRadialGradient(cx, cy, core_r)
        core_alpha = int(200 + self._pulse * 55)
        core_grad.setColorAt(0.0, QColor(0, 240, 255, core_alpha))
        core_grad.setColorAt(0.4, QColor(0, 180, 255, core_alpha // 2))
        core_grad.setColorAt(0.8, QColor(0, 100, 200, core_alpha // 6))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 9: Center luminous orb
        # ═══════════════════════════════════════════════════════════════════
        orb_r = 12 + self._pulse * 4
        orb_grad = QRadialGradient(cx, cy, orb_r)
        orb_alpha = int(255 * self._intro_alpha)
        orb_grad.setColorAt(0.0, QColor(255, 255, 255, orb_alpha))
        orb_grad.setColorAt(0.3, QColor(0, 240, 255, orb_alpha // 2))
        orb_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(orb_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 10: Energy trails
        # ═══════════════════════════════════════════════════════════════════
        for t in self._energy_trails:
            alpha = int(t["life"] * 150)
            trail_len = int(t["progress"] * 20)
            trail_pen = QPen(QColor(0, 220, 255, alpha))
            trail_pen.setWidth(1)
            trail_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(trail_pen)
            # Draw trail from current position to target
            for i in range(trail_len):
                px = t["x"] + random.uniform(-2, 2)
                py = t["y"] + random.uniform(-2, 2)
                painter.drawEllipse(QPointF(px, py), 1, 1)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 11: Spark particles
        # ═══════════════════════════════════════════════════════════════════
        for p in self._spark_particles:
            alpha = int(p["life"] * 200)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 240, 255, alpha)))
            painter.drawEllipse(QPointF(p["x"], p["y"]), p["size"], p["size"])

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 12: Dust particles (rising)
        # ═══════════════════════════════════════════════════════════════════
        for p in self._dust_particles:
            alpha = int(p["life"] * 60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(100, 180, 220, alpha)))
            painter.drawEllipse(QPointF(p["x"], p["y"]), p["size"], p["size"])

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 13: Scan line effect
        # ═══════════════════════════════════════════════════════════════════
        scan_pen = QPen(QColor(0, 200, 255, 8))
        scan_pen.setWidth(2)
        painter.setPen(scan_pen)
        painter.drawLine(0, self._scan_line, w, self._scan_line)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 14: SONIC AI title with glow
        # ═══════════════════════════════════════════════════════════════════
        title_alpha = int(255 * self._intro_alpha)

        # Title glow
        glow_title = QRadialGradient(cx, cy + 90, 100)
        glow_title.setColorAt(0.0, QColor(0, 200, 255, title_alpha // 8))
        glow_title.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_title))
        painter.drawEllipse(QPointF(cx, cy + 90), 100, 40)

        # Title text
        title_font = QFont("Segoe UI", 38, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(0, 220, 255, title_alpha))
        title_rect = QRectF(self._glitch_offset, cy + 65, w, 55)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "SONIC")

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 15: Subtitle with fade-in
        # ═══════════════════════════════════════════════════════════════════
        sub_alpha = int(180 * self._intro_alpha)
        sub_font = QFont("Segoe UI", 13, QFont.Weight.Light)
        painter.setFont(sub_font)
        painter.setPen(QColor(140, 180, 210, sub_alpha))
        sub_rect = QRectF(0, cy + 120, w, 30)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "ARTIFICIAL  INTELLIGENCE")

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 16: Thin decorative lines
        # ═══════════════════════════════════════════════════════════════════
        line_alpha = int(40 + self._pulse * 20)
        line_pen = QPen(QColor(0, 180, 255, line_alpha))
        line_pen.setWidth(1)

        # Left line
        painter.setPen(line_pen)
        painter.drawLine(cx - 120, cy + 145, cx - 20, cy + 145)

        # Right line
        painter.drawLine(cx + 20, cy + 145, cx + 120, cy + 145)

        # Center diamond
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 200, 255, line_alpha + 20)))
        diamond = QPainterPath()
        diamond.moveTo(cx, cy + 140)
        diamond.lineTo(cx + 5, cy + 145)
        diamond.lineTo(cx, cy + 150)
        diamond.lineTo(cx - 5, cy + 145)
        diamond.closeSubpath()
        painter.drawPath(diamond)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 17: Progress bar (premium style)
        # ═══════════════════════════════════════════════════════════════════
        bar_w = 280
        bar_h = 4
        bar_x = (w - bar_w) / 2
        bar_y = cy + 175

        # Bar background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(20, 30, 40)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2, 2)

        # Bar fill with glow
        fill_w = bar_w * min(self._progress, 100) / 100
        if fill_w > 0:
            # Fill glow
            fill_glow = QRadialGradient(bar_x + fill_w, bar_y + 2, 15)
            fill_glow.setColorAt(0.0, QColor(0, 220, 255, 60))
            fill_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setBrush(QBrush(fill_glow))
            painter.drawEllipse(QPointF(bar_x + fill_w, bar_y + 2), 15, 8)

            # Fill bar
            bar_grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            bar_grad.setColorAt(0.0, QColor(0, 150, 220))
            bar_grad.setColorAt(0.7, QColor(0, 220, 255))
            bar_grad.setColorAt(1.0, QColor(0, 240, 255))
            painter.setBrush(QBrush(bar_grad))
            painter.drawRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2, 2)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 18: Loading text
        # ═══════════════════════════════════════════════════════════════════
        load_font = QFont("Segoe UI", 9, QFont.Weight.Light)
        painter.setFont(load_font)
        painter.setPen(QColor(100, 140, 170, int(150 * self._intro_alpha)))
        pct = min(int(self._progress), 100)

        if self._phase == 0:
            load_text = "INITIALIZING"
        elif self._phase == 2:
            load_text = "READY"
        else:
            load_text = f"LOADING  {pct}%"

        load_rect = QRectF(0, bar_y + 16, w, 20)
        painter.drawText(load_rect, Qt.AlignmentFlag.AlignCenter, load_text)

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 19: LIMITED TIME FREE banner (premium)
        # ═══════════════════════════════════════════════════════════════════
        banner_y = h - 100
        banner_h = 60

        # Banner glow
        banner_glow = QRadialGradient(cx, banner_y + banner_h // 2, 150)
        banner_glow.setColorAt(0.0, QColor(0, 200, 255, int(15 * self._intro_alpha)))
        banner_glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(banner_glow))
        painter.drawEllipse(QPointF(cx, banner_y + banner_h // 2), 150, 40)

        # Banner border
        banner_border = QPen(QColor(0, 200, 255, int(80 * self._intro_alpha)))
        banner_border.setWidth(1)
        painter.setPen(banner_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(QRectF(50, banner_y, w - 100, banner_h), 10, 10)

        # "LIMITED TIME FREE" text
        banner_font = QFont("Segoe UI", 18, QFont.Weight.Bold)
        painter.setFont(banner_font)
        painter.setPen(QColor(0, 240, 255, int(255 * self._intro_alpha)))
        text_rect = QRectF(0, banner_y + 6, w, 30)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, "LIMITED TIME FREE")

        # Sub-text
        small_font = QFont("Segoe UI", 9, QFont.Weight.Light)
        painter.setFont(small_font)
        painter.setPen(QColor(100, 180, 220, int(160 * self._intro_alpha)))
        sub_rect2 = QRectF(0, banner_y + 38, w, 18)
        painter.drawText(sub_rect2, Qt.AlignmentFlag.AlignCenter, "All features unlocked during beta period")

        # ═══════════════════════════════════════════════════════════════════
        # LAYER 20: Version
        # ═══════════════════════════════════════════════════════════════════
        from version import APP_VERSION
        ver_font = QFont("Segoe UI", 8, QFont.Weight.Light)
        painter.setFont(ver_font)
        painter.setPen(QColor(60, 80, 100, int(100 * self._intro_alpha)))
        ver_rect = QRectF(0, h - 30, w, 20)
        painter.drawText(ver_rect, Qt.AlignmentFlag.AlignCenter, f"v{APP_VERSION}")

        painter.end()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self._progress_timer.stop()
        if self._on_done:
            self._on_done()
