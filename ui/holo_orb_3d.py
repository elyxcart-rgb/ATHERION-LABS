"""SONIC AI — Holographic 3D Orb.

A true 3D-projected holographic sphere: multi-layer refraction, iridescent
surface highlight, rotating equatorial rings, animated pulse rings, scan
beams crossing the orb, holographic data ribbons, and a brightness state
that responds to "voice activity" input.

Pure PyQt6 (no external 3D engine required). Uses analytic projection of a
sphere with proper shading.

Public API:
    HoloOrb3D(parent=None, size=320)
    .set_state(state: str)        # "idle"|"listening"|"thinking"|"speaking"|"ready"|"error"
    .set_audio_level(level: float)  # 0..1 (drives orb pulse + waveform response)
    .set_text(text: str)          # status text under the orb
    .set_color(r, g, b)           # override accent color
"""
from __future__ import annotations

import math
import random
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, QPropertyAnimation
from PyQt6.QtGui import (
    QColor, QPainter, QLinearGradient, QRadialGradient, QPen, QBrush, QPainterPath,
    QFont,
)
from PyQt6.QtWidgets import QWidget


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _project_sphere(samples: int, radius: float, cx: float, cy: float,
                    rot_x: float, rot_y: float, rot_z: float):
    """Yield (x, y, z_normalized) for sphere samples, sorted by z (far→near)."""
    pts = []
    for i in range(samples):
        theta = 2 * math.pi * i / samples
        # Sphere parametric
        for j in range(samples // 2):
            phi = math.pi * j / (samples // 2)
            x0 = radius * math.sin(phi) * math.cos(theta)
            y0 = radius * math.cos(phi)
            z0 = radius * math.sin(phi) * math.sin(theta)

            # Rotate around X
            x1 = x0
            y1 = y0 * math.cos(rot_x) - z0 * math.sin(rot_x)
            z1 = y0 * math.sin(rot_x) + z0 * math.cos(rot_x)

            # Rotate around Y
            x2 = x1 * math.cos(rot_y) + z1 * math.sin(rot_y)
            y2 = y1
            z2 = -x1 * math.sin(rot_y) + z1 * math.cos(rot_y)

            # Rotate around Z
            x3 = x2 * math.cos(rot_z) - y2 * math.sin(rot_z)
            y3 = x2 * math.sin(rot_z) + y2 * math.cos(rot_z)

            # Project (simple orthographic)
            pts.append((cx + x3, cy + y3, z2))

    # Sort by z ascending (far points first)
    pts.sort(key=lambda p: p[2])
    return pts


# ═════════════════════════════════════════════════════════════════════════════
# HoloOrb3D
# ═════════════════════════════════════════════════════════════════════════════

class HoloOrb3D(QWidget):
    """True 3D holographic sphere with iridescent shading."""

    clicked = pyqtSignal()

    STATE_COLORS = {
        "idle":      QColor(0, 200, 220),       # cyan
        "listening": QColor(0, 230, 180),       # cyan-green
        "thinking":  QColor(170, 100, 255),     # violet
        "speaking":  QColor(80, 200, 255),      # blue-cyan
        "ready":     QColor(60, 230, 130),      # emerald
        "error":     QColor(255, 80, 80),       # red
        "scanning":  QColor(255, 180, 80),      # amber
    }

    def __init__(self, parent=None, size: int = 320):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

        self._tick = 0
        self._state = "idle"
        self._audio_level = 0.0
        self._target_audio = 0.0
        self._rot_x = 0.4
        self._rot_y = 0.0
        self._rot_z = 0.0
        self._color = self.STATE_COLORS["idle"]
        self._status_text = "ONLINE"
        self._halo_alpha = 0.6

        # Orbital particles
        self._particles = [
            {"angle": random.uniform(0, 2 * math.pi),
             "radius": random.uniform(0.78, 1.18),
             "height": random.uniform(-0.4, 0.4),
             "speed": random.uniform(0.005, 0.018),
             "size": random.uniform(0.8, 2.0),
             "alpha": random.uniform(80, 200),
             "phase": random.uniform(0, math.pi * 2)}
            for _ in range(60)
        ]

        # Pulse rings (expanding outward)
        self._pulse_rings = [{"radius": 0,
                              "alpha": 0.0,
                              "phase": i * 1.6} for i in range(3)]

        # Animated beams (sweeping across the orb)
        self._beams = [{"angle": i * 120, "speed": 0.8 + i * 0.2}
                       for i in range(3)]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick_anim)
        self._timer.start(20)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        self._state = state
        if state in self.STATE_COLORS:
            self._color = self.STATE_COLORS[state]

    def set_audio_level(self, level: float):
        self._target_audio = max(0.0, min(1.0, level))

    def set_text(self, text: str):
        self._status_text = text
        self.update()

    def set_color(self, r: int, g: int, b: int):
        self._color = QColor(r, g, b)

    def get_color(self) -> QColor:
        return self._color

    # ── Animation ────────────────────────────────────────────────────────────

    def _tick_anim(self):
        self._tick += 1
        self._rot_y += 0.012
        self._rot_x = 0.4 + math.sin(self._tick * 0.005) * 0.12
        # Smooth audio level
        self._audio_level += (self._target_audio - self._audio_level) * 0.15

        # Particles
        for p in self._particles:
            p["angle"] += p["speed"]

        # Pulse rings
        for ring in self._pulse_rings:
            ring["radius"] += 1.4
            ring["alpha"] = max(0, 0.65 - ring["radius"] / 130)
            if ring["radius"] > 130:
                ring["radius"] = 0
                ring["alpha"] = 0.65

        # Beams
        for b in self._beams:
            b["angle"] = (b["angle"] + b["speed"]) % 360

        self.update()

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h = self.width(), self.height()
        cx = w / 2
        cy = h / 2
        base_r = min(w, h) * 0.36
        # Pulse radius responds to audio level
        audio_boost = 1.0 + self._audio_level * 0.18
        radius = base_r * audio_boost

        c = self._color

        # ── Layer 1: Atmosphere bloom (huge radial gradient) ────────────────
        bloom_r = min(w, h) * 0.55
        bloom = QRadialGradient(cx, cy, bloom_r)
        bloom.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 100))
        bloom.setColorAt(0.4, QColor(c.red(), c.green(), c.blue(), 30))
        bloom.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bloom))
        painter.drawEllipse(QPointF(cx, cy), bloom_r, bloom_r)

        # ── Layer 2: Outer pulse rings ──────────────────────────────────────
        for ring in self._pulse_rings:
            if ring["alpha"] < 0.01:
                continue
            r = base_r * 1.3 + ring["radius"]
            pen = QPen(QColor(c.red(), c.green(), c.blue(),
                              int(ring["alpha"] * 180)), 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # ── Layer 3: Iridescent sphere surface (3D-projected) ──────────────
        samples = 32
        sphere_pts = _project_sphere(samples, radius, cx, cy,
                                      self._rot_x, self._rot_y, self._rot_z)
        # Draw back-to-front (already sorted)
        # Lighting parameters
        light_x, light_y, light_z = -0.5, -0.6, 0.7
        # Build a colored pixel field via radial gradients at each pixel
        # (faster: just draw circles with depth-sorted colors)
        for px, py, pz in sphere_pts:
            # Normalize z to [0, 1] (1 = closest)
            z_norm = (pz + radius) / (2 * radius)
            # Light dot product (simulated)
            n_dot_l = (-px + cx) / radius * light_x + (-py + cy) / radius * light_y + light_z * 0.5
            brightness = max(0.05, (n_dot_l + 1) / 2) * z_norm
            irid = (math.sin((px - cx) * 0.03 + self._tick * 0.05) + 1) / 2
            base_color = QColor(
                int(c.red() * brightness * (0.6 + 0.4 * irid)),
                int(c.green() * brightness * (0.6 + 0.4 * (1 - irid))),
                int(c.blue() * brightness * (0.7 + 0.3 * irid)),
                int(220 * z_norm),
            )
            point_size = 1.6 + 0.8 * z_norm + self._audio_level * 1.5
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(base_color))
            painter.drawEllipse(QPointF(px, py), point_size, point_size)

        # ── Layer 4: Specular highlight (small bright spot) ─────────────────
        spec_x = cx + radius * 0.35 * math.cos(self._rot_y * 0.3)
        spec_y = cy - radius * 0.4
        spec_r = radius * 0.32
        spec_grad = QRadialGradient(spec_x, spec_y, spec_r)
        spec_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        spec_grad.setColorAt(0.4, QColor(c.red(), c.green(), c.blue(), 80))
        spec_grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        painter.setBrush(QBrush(spec_grad))
        painter.drawEllipse(QPointF(spec_x, spec_y), spec_r, spec_r)

        # ── Layer 5: Equatorial rings (rotating) ────────────────────────────
        for ring_i, ring_r_factor in enumerate([1.05, 1.15, 1.25]):
            ring_r = radius * ring_r_factor
            ring_alpha = max(30, 150 - ring_i * 40)
            ring_pen = QPen(QColor(c.red(), c.green(), c.blue(), ring_alpha), 1)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # Tilted ellipse
            from PyQt6.QtGui import QTransform
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(math.degrees(self._rot_y) + ring_i * 30)
            painter.scale(1.0, 0.25 + ring_i * 0.08)
            painter.drawEllipse(QPointF(0, 0), ring_r, ring_r)
            painter.restore()

        # ── Layer 6: Crosshair beams sweeping the orb ───────────────────────
        for beam in self._beams:
            ang = math.radians(beam["angle"])
            radius_b = radius * 1.45
            x1 = cx + math.cos(ang) * radius_b
            y1 = cy + math.sin(ang) * radius_b
            x2 = cx - math.cos(ang) * radius_b
            y2 = cy - math.sin(ang) * radius_b
            beam_pen = QPen(QColor(c.red(), c.green(), c.blue(), 70), 1)
            painter.setPen(beam_pen)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
            # Bright endpoint dots
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 200)))
            painter.drawEllipse(QPointF(x1, y1), 3, 3)
            painter.drawEllipse(QPointF(x2, y2), 3, 3)

        # ── Layer 7: Orbital particles ──────────────────────────────────────
        for p in self._particles:
            orbit_r = radius * p["radius"]
            ang = p["angle"]
            ox = cx + math.cos(ang) * orbit_r
            # Compute world-space y based on tilt + orbit height
            oy = cy + math.sin(ang) * orbit_r * 0.4 + p["height"] * orbit_r * 0.6
            flicker = (math.sin(self._tick * 0.1 + p["phase"]) + 1) / 2
            alpha = int(p["alpha"] * (0.4 + 0.6 * flicker))
            # Trail line
            tx = cx + math.cos(ang - 0.05) * orbit_r
            ty = cy + math.sin(ang - 0.05) * orbit_r * 0.4 + p["height"] * orbit_r * 0.6
            trail_pen = QPen(QColor(c.red(), c.green(), c.blue(), alpha // 2), 1)
            painter.setPen(trail_pen)
            painter.drawLine(QPointF(tx, ty), QPointF(ox, oy))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawEllipse(QPointF(ox, oy), p["size"], p["size"])

        # ── Layer 8: Inner pulsing core (audio-reactive) ────────────────────
        core_r = radius * 0.18 + self._audio_level * radius * 0.25
        core_grad = QRadialGradient(cx, cy, core_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 240))
        core_grad.setColorAt(0.5, QColor(c.red(), c.green(), c.blue(), 180))
        core_grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ── Layer 9: Status text under the orb ──────────────────────────────
        status_font = QFont("Consolas", 10, QFont.Weight.Bold)
        status_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        painter.setFont(status_font)
        text = self._status_text.upper()
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)
        tx = (w - tw) / 2
        ty = h - 22
        # Backing pill
        pill_x = tx - 10
        pill_y = ty - 4
        pill_w = tw + 20
        pill_h = fm.height() + 8
        pill_grad = QLinearGradient(pill_x, pill_y, pill_x, pill_y + pill_h)
        pill_grad.setColorAt(0.0, QColor(255, 255, 255, 12))
        pill_grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 20))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(pill_grad))
        painter.drawRoundedRect(int(pill_x), int(pill_y),
                                 int(pill_w), int(pill_h), 12, 12)
        # Text
        painter.setPen(QColor(c.red(), c.green(), c.blue(), 220))
        painter.drawText(QPointF(tx, ty + fm.ascent() - 2), text)

        painter.end()
