"""SONIC AI Bootstrapper — HOLOGRAPHIC + HOLLYWOOD CINEMATIC First-Run UI.

Beyond sci-fi: iridescent holographic title with animated shimmer, cinematic
lens-flare hero, volumetric light beams, parallax depth layers, perspective
grid backdrop, ribbon particles, deep focus gradient rings.

Public surface (kept stable for `bootstrap/__init__.py`):
    - CoreState                      (state enum)
    - WorkerThread(QThread)          (signals: progress, requirement_check,
                                      requirement_install, all_done, stage_update)
    - IntelligenceCore(QWidget)      (set_state)
    - StagePipeline(QWidget)         (STAGES, set_stage)
    - GlassStatusPanel(QWidget)      (add_item, clear)
    - SonicBootUI(QWidget)           (finished signal)
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QEasingCurve, QPropertyAnimation,
    QPointF, QRectF, QParallelAnimationGroup, QSize, QSizeF,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QRadialGradient,
    QPen, QBrush, QPainterPath, QFontDatabase, QFontMetrics, QImage,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QApplication, QGraphicsOpacityEffect,
    QSizePolicy,
)

from .detector import Status, DepResult, detect_all, get_system_info
from .state import BootstrapState
from .installer import DependencyInstaller, InstallResult
from apple_design import (
    Tokens, AppleButton, AppleCard, AppleProgressBar,
    AppleCheckmark, fade_in, slide_up, create_glow, create_shadow,
)


# ═════════════════════════════════════════════════════════════════════════════
# State
# ═════════════════════════════════════════════════════════════════════════════

class CoreState:
    INITIALIZING = "initializing"
    CHECKING = "checking"
    INSTALLING = "installing"
    VERIFYING = "verifying"
    READY = "ready"
    ERROR = "error"


class WorkerThread(QThread):
    progress = pyqtSignal(str, int)
    requirement_check = pyqtSignal(object)
    requirement_install = pyqtSignal(str, object)
    all_done = pyqtSignal(bool, str)
    stage_update = pyqtSignal(str, str)  # stage_name, state

    def __init__(self, mode="detect"):
        super().__init__()
        self.mode = mode
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        if self.mode == "detect":
            self._run_detection()
        elif self.mode == "install":
            self._run_installation()

    def _run_detection(self):
        try:
            self.stage_update.emit("system", "active")
            self.progress.emit("Scanning system environment...", 5)
            sys_info = get_system_info()
            self.progress.emit(f"Detected: {sys_info.os_name} {sys_info.architecture}", 10)

            self.stage_update.emit("system", "done")
            self.stage_update.emit("audio", "active")
            self.progress.emit("Checking audio services...", 15)

            results = detect_all()
            total = len(results)

            for i, result in enumerate(results):
                if self._cancel:
                    return

                pct = 15 + int(75 * (i / total))

                if result.id in ("mic_check", "speaker_check", "portaudio"):
                    self.stage_update.emit("audio", "active" if result.status != Status.INSTALLED else "done")
                elif result.id in ("python_runtime", "qt_runtime", "vc_redist_x64"):
                    self.stage_update.emit("runtime", "active" if result.status != Status.INSTALLED else "done")
                elif result.id in ("playwright_chromium", "ffmpeg", "vlc", "opencode"):
                    self.stage_update.emit("tools", "active" if result.status != Status.INSTALLED else "done")

                status_msg = {
                    Status.INSTALLED: result.name,
                    Status.MISSING: result.name,
                    Status.CHECK_FAILED: result.name,
                }.get(result.status, result.name)

                self.progress.emit(status_msg, pct)
                self.requirement_check.emit(result)
                self.msleep(120)

            self.stage_update.emit("verify", "active")
            self.progress.emit("Verification complete", 95)
            self.stage_update.emit("verify", "done")
            self.all_done.emit(True, "Detection complete")
        except Exception as e:
            self.stage_update.emit("error", "active")
            self.all_done.emit(False, str(e))

    def _run_installation(self):
        try:
            from ..sonic_ai.bootstrap.manifest import manifest
        except ImportError:
            import json
            from pathlib import Path
            manifest_path = Path(__file__).parent.parent / "manifest.json"
            with open(manifest_path) as f:
                manifest = json.load(f)

        installer = DependencyInstaller(
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct)
        )

        requirements = manifest.get("requirements", [])
        missing = [req for req in requirements if req.get("required") and not req.get("bundled")]

        total = len(missing)
        if total == 0:
            self.all_done.emit(True, "All required dependencies are bundled")
            return

        installed_count = 0
        for i, req in enumerate(missing):
            if self._cancel:
                self.all_done.emit(False, "Installation cancelled")
                return

            self.stage_update.emit("installing", "active")
            self.progress.emit(f"Installing {req['name']}...", int(100 * (i / total)))
            result = installer.install(req["id"], req)
            self.requirement_install.emit(req["id"], result)

            if result.success or result.requires_manual:
                installed_count += 1

        self.stage_update.emit("installing", "done")
        self.progress.emit("Installation complete", 100)
        self.all_done.emit(True, f"{installed_count}/{total} dependencies addressed")


# ═════════════════════════════════════════════════════════════════════════════
# HOLOGRAPHIC BACKDROP — perspective grid + parallax + ribbons + beams
# ═════════════════════════════════════════════════════════════════════════════

class _HoloBackdrop(QWidget):
    """Hollywood cinematic backdrop: perspective floor, parallax particles,
    volumetric light beams, animated data ribbons, iridescent corners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tick = 0

        # Three-layer parallax particles (different speeds for depth)
        self._particles_far = [
            {"x": random.uniform(0, 1), "y": random.uniform(0, 1),
             "speed": random.uniform(0.0002, 0.0006), "size": random.uniform(0.4, 0.9),
             "alpha": random.uniform(30, 70)}
            for _ in range(40)
        ]
        self._particles_mid = [
            {"x": random.uniform(0, 1), "y": random.uniform(0, 1),
             "speed": random.uniform(0.0006, 0.0014), "size": random.uniform(0.6, 1.3),
             "alpha": random.uniform(60, 110)}
            for _ in range(35)
        ]
        self._particles_near = [
            {"x": random.uniform(0, 1), "y": random.uniform(0, 1),
             "speed": random.uniform(0.0014, 0.0028), "size": random.uniform(1.0, 2.0),
             "alpha": random.uniform(90, 160)}
            for _ in range(20)
        ]

        # Animated ribbon data streams (horizontal lines that fade in/out)
        self._ribbons = [
            {"y_frac": random.uniform(0.05, 0.95), "speed": random.uniform(0.3, 1.2),
             "width": random.uniform(0.05, 0.18), "alpha": random.uniform(20, 60),
             "hue": random.choice([0, 1, 2])}  # 0=cyan,1=violet,2=white
            for _ in range(6)
        ]

        # Volumetric beam angles (slow rotation)
        self._beam_angles = [0.0, 120.0, 240.0]

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(33)  # ~30fps for backdrop (cheaper than 60)

    def _on_tick(self):
        self._tick += 1
        for layer in (self._particles_far, self._particles_mid, self._particles_near):
            for p in layer:
                p["y"] += p["speed"]
                if p["y"] > 1.0:
                    p["y"] = -0.02
                    p["x"] = random.uniform(0, 1)
        for beam in self._beam_angles:
            beam.__iadd__(0.08) if False else None  # placeholder
        # actually update beams
        self._beam_angles[0] = (self._beam_angles[0] + 0.08) % 360
        self._beam_angles[1] = (self._beam_angles[1] + 0.06) % 360
        self._beam_angles[2] = (self._beam_angles[2] + 0.10) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx_c = w / 2

        # ── 1. Deep cinematic black + radial atmosphere ──────────────────────
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(1, 2, 6)))
        painter.drawRect(0, 0, w, h)

        # Soft cyan-violet radial from upper-middle (cinematic key light)
        atmos = QRadialGradient(cx_c, h * 0.32, max(w, h) * 0.85)
        atmos.setColorAt(0.0, QColor(20, 60, 110, 70))
        atmos.setColorAt(0.35, QColor(30, 20, 80, 35))
        atmos.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(atmos))
        painter.drawRect(0, 0, w, h)

        # ── 2. Perspective grid floor (Hollywood "infinity floor") ──────────
        vp_y = h * 0.55  # vanishing point y
        vp_x = cx_c
        painter.setPen(QPen(QColor(0, 200, 255, 30), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Horizontal lines getting closer to vanishing point
        grid_lines = 12
        for i in range(1, grid_lines + 1):
            t = i / grid_lines
            y = vp_y + (h - vp_y) * (t * t)  # accelerate outward
            alpha = int(20 + 40 * (1 - t))
            painter.setPen(QPen(QColor(0, 200, 255, alpha), 1))
            painter.drawLine(0, int(y), w, int(y))
        # Converging vertical lines (toward vanishing point)
        v_lines = 21
        for i in range(v_lines):
            t = i / (v_lines - 1)
            x_bottom = -w * 0.5 + w * 1.5 * t
            painter.setPen(QPen(QColor(0, 200, 255, 22), 1))
            painter.drawLine(int(x_bottom), h, int(vp_x), int(vp_y))

        # ── 3. Hex lattice overlay (faint) ───────────────────────────────────
        hex_r = 30
        hex_w = hex_r * math.sqrt(3)
        hex_h = hex_r * 1.5
        painter.setPen(QPen(QColor(0, 200, 255, 10), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        row = 0
        y = -hex_r
        while y < h + hex_r:
            x_offset = (hex_w / 2) if row % 2 else 0
            x = -hex_w
            while x < w + hex_w:
                cxh = x + x_offset
                cyh = y
                pts = []
                for k in range(6):
                    ang = math.radians(60 * k + 30)
                    pts.append(QPointF(cxh + hex_r * math.cos(ang),
                                       cyh + hex_r * math.sin(ang)))
                path = QPainterPath()
                path.moveTo(pts[0])
                for pt in pts[1:]:
                    path.lineTo(pt)
                path.closeSubpath()
                painter.drawPath(path)
                x += hex_w
            row += 1
            y += hex_h

        # ── 4. Volumetric light beams (3 cones radiating from top) ──────────
        for i, base_ang in enumerate(self._beam_angles):
            ang = math.radians(base_ang - 90)  # pointing down-ish
            beam_w = max(w, h) * 1.3
            tip_x = cx_c
            tip_y = h * 0.05
            end_x = tip_x + math.cos(ang) * beam_w
            end_y = tip_y + math.sin(ang) * beam_w

            beam_grad = QLinearGradient(tip_x, tip_y, end_x, end_y)
            hue_color = [QColor(0, 200, 255), QColor(150, 80, 255), QColor(255, 200, 120)][i % 3]
            beam_grad.setColorAt(0.0, QColor(hue_color.red(), hue_color.green(), hue_color.blue(), 30))
            beam_grad.setColorAt(0.4, QColor(hue_color.red(), hue_color.green(), hue_color.blue(), 10))
            beam_grad.setColorAt(1.0, QColor(hue_color.red(), hue_color.green(), hue_color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(beam_grad))
            # Triangle: tip + wide base at the end
            perp = math.radians(base_ang - 90 + 90)  # perpendicular to beam
            base_w = beam_w * 0.35
            bx1 = end_x + math.cos(perp) * base_w
            by1 = end_y + math.sin(perp) * base_w
            bx2 = end_x - math.cos(perp) * base_w
            by2 = end_y - math.sin(perp) * base_w
            path = QPainterPath()
            path.moveTo(QPointF(tip_x, tip_y))
            path.lineTo(QPointF(bx1, by1))
            path.lineTo(QPointF(bx2, by2))
            path.closeSubpath()
            painter.drawPath(path)

        # ── 5. Data ribbons (horizontal streams, fade-in/out across screen) ──
        for rib in self._ribbons:
            t = (math.sin(self._tick * 0.005 * rib["speed"] + rib["y_frac"] * 6) + 1) / 2
            base_y = rib["y_frac"] * h
            line_len = rib["width"] * w
            # Moving horizontal segment
            offset = ((self._tick * rib["speed"]) % (w + line_len)) - line_len
            x1 = offset
            x2 = offset + line_len
            hue = [QColor(0, 220, 255), QColor(170, 100, 255), QColor(220, 230, 255)][rib["hue"]]
            alpha = int(rib["alpha"] * t)
            pen = QPen(QColor(hue.red(), hue.green(), hue.blue(), alpha))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLine(int(x1), int(base_y), int(x2), int(base_y))
            # Tiny end-points (data packet markers)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(hue.red(), hue.green(), hue.blue(), min(255, alpha + 60))))
            painter.drawEllipse(QPointF(x1, base_y), 1.6, 1.6)
            painter.drawEllipse(QPointF(x2, base_y), 1.6, 1.6)

        # ── 6. Parallax particles (3 depth layers) ───────────────────────────
        for layer, color_mod in (
            (self._particles_far, (0, 140, 200)),
            (self._particles_mid, (0, 200, 255)),
            (self._particles_near, (180, 240, 255)),
        ):
            for p in layer:
                px = p["x"] * w
                py = p["y"] * h
                alpha = int(p["alpha"] * (0.5 + 0.5 * math.sin(self._tick * 0.08 + p["x"] * 12)))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(color_mod[0], color_mod[1], color_mod[2], alpha)))
                painter.drawEllipse(QPointF(px, py), p["size"], p["size"])

        # ── 7. Animated HUD corner brackets (chic, asymmetric) ──────────────
        bracket_len = 28
        bracket_w = 2
        for corner_i, (sx, sy, dx1, dy1, dx2, dy2) in enumerate([
            (0, 0, 1, 0, 0, 1),                # TL → right, down
            (w, 0, -1, 0, 0, 1),               # TR → left, down
            (0, h, 1, 0, 0, -1),               # BL → right, up
            (w, h, -1, 0, 0, -1),              # BR → left, up
        ]):
            margin = 16
            x0 = sx + (margin * (-1 if sx > 0 else 1))
            y0 = sy + (margin * (-1 if sy > 0 else 1))
            pulse = (math.sin(self._tick * 0.04 + corner_i * 1.6) + 1) / 2
            base_alpha = 70 + int(40 * pulse)
            # Holographic hue shift per corner
            if corner_i == 0 or corner_i == 3:
                hue_c = QColor(0, 220, 255, base_alpha)
            else:
                hue_c = QColor(180, 120, 255, base_alpha)
            pen = QPen(hue_c, bracket_w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            # L-bracket: two lines forming an L
            painter.drawLine(int(x0), int(y0),
                             int(x0 + dx1 * bracket_len), int(y0 + dy1 * bracket_len))
            painter.drawLine(int(x0), int(y0),
                             int(x0 + dx2 * bracket_len), int(y0 + dy2 * bracket_len))
            # Glowing dot at corner
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(hue_c))
            painter.drawEllipse(QPointF(x0, y0), 2.4, 2.4)

        # ── 8. Subtle horizontal scan lines (filmic grain) ──────────────────
        scan_pen = QPen(QColor(0, 200, 255, 8), 1)
        painter.setPen(scan_pen)
        for y in range(0, h, 3):
            if (y // 3 + self._tick) % 2 == 0:
                painter.drawLine(0, y, w, y)

        painter.end()


# ═════════════════════════════════════════════════════════════════════════════
# CINEMATIC HERO WIDGET — replaces SonicBootAnimation
# Paints: lens flare + centerpiece rings + iridescent title + shimmer ribbon
# ═════════════════════════════════════════════════════════════════════════════

class _CinematicHero(QWidget):
    """Holographic hero: lens flare orb + multi-layer iridescent rings + animated
    gradient title with horizontal shimmer ribbon. All in ONE widget so the
    parent layout cannot accidentally double-render text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tick = 0
        self._state = CoreState.INITIALIZING
        self._shimmer_phase = 0.0
        self._title_reveal = 0.0  # 0..1 letter-by-letter reveal
        self._subtitle_alpha = 0.0
        self._ring_pulse = 0.0
        self.setFixedSize(720, 240)

        # Pre-compute orbital particles
        self._orbital_particles = [
            {"angle": random.uniform(0, 2 * math.pi), "speed": random.uniform(0.005, 0.018),
             "radius": random.uniform(55, 95), "size": random.uniform(0.6, 1.4),
             "alpha": random.uniform(80, 180), "phase": random.uniform(0, math.pi * 2)}
            for _ in range(40)
        ]

        # Reveal animation (timed entry of the title)
        self._reveal_timer = QTimer(self)
        self._reveal_timer.timeout.connect(self._tick_reveal)
        self._reveal_timer.start(28)

        # Main paint timer
        self._paint_timer = QTimer(self)
        self._paint_timer.timeout.connect(self._on_tick)
        self._paint_timer.start(20)

    def set_state(self, state: str):
        self._state = state

    def _tick_reveal(self):
        # Letter reveal: ramp from 0 to 1 over ~1.5s, then idle
        if self._title_reveal < 1.0:
            self._title_reveal = min(1.0, self._title_reveal + 0.025)
        if self._subtitle_alpha < 1.0:
            self._subtitle_alpha = min(1.0, self._subtitle_alpha + 0.04)
        self.update()

    def _on_tick(self):
        self._tick += 1
        self._shimmer_phase = (self._tick * 0.012) % 1.0
        self._ring_pulse = (math.sin(self._tick * 0.06) + 1) / 2
        for p in self._orbital_particles:
            p["angle"] += p["speed"]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()

        # ── Anchor point: orbital center sits in middle of widget ─────────
        cx, cy = w / 2, h * 0.40

        accent = QColor(Tokens.CYAN)
        success = QColor(Tokens.SUCCESS)
        danger = QColor(Tokens.ERROR)
        violet = QColor(170, 100, 255)
        platinum = QColor(220, 230, 245)

        # State-driven ring hue
        if self._state == CoreState.ERROR:
            ring_color = danger
        elif self._state == CoreState.READY:
            ring_color = success
        else:
            ring_color = accent

        # ── 1. Massive radial atmosphere (cinematic bloom) ──────────────────
        bloom_r = max(w, h) * 0.55
        bloom = QRadialGradient(cx, cy, bloom_r)
        bloom.setColorAt(0.0, QColor(ring_color.red(), ring_color.green(),
                                     ring_color.blue(), 90))
        bloom.setColorAt(0.25, QColor(0, 80, 180, 50))
        bloom.setColorAt(0.6, QColor(40, 20, 100, 20))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bloom))
        painter.drawRect(0, 0, w, h)

        # ── 2. Lens flare (horizontal streak through center) ───────────────
        flare_color = ring_color if self._state != CoreState.ERROR else violet
        flare_grad = QLinearGradient(0, cy, w, cy)
        flare_grad.setColorAt(0.0, QColor(flare_color.red(), flare_color.green(),
                                          flare_color.blue(), 0))
        flare_grad.setColorAt(0.35, QColor(flare_color.red(), flare_color.green(),
                                            flare_color.blue(), 35))
        flare_grad.setColorAt(0.5, QColor(255, 255, 255, 80))
        flare_grad.setColorAt(0.65, QColor(flare_color.red(), flare_color.green(),
                                            flare_color.blue(), 35))
        flare_grad.setColorAt(1.0, QColor(flare_color.red(), flare_color.green(),
                                          flare_color.blue(), 0))
        painter.setPen(QPen(QBrush(flare_grad), 2))
        painter.drawLine(0, int(cy), int(w), int(cy))
        # Lens flare halo (bright spot at center)
        halo_r = 90 + self._ring_pulse * 12
        halo = QRadialGradient(cx, cy, halo_r)
        halo.setColorAt(0.0, QColor(255, 255, 255, 220))
        halo.setColorAt(0.2, QColor(flare_color.red(), flare_color.green(),
                                    flare_color.blue(), 180))
        halo.setColorAt(0.5, QColor(flare_color.red(), flare_color.green(),
                                    flare_color.blue(), 50))
        halo.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(cx, cy), halo_r, halo_r)

        # ── 3. Multi-layer iridescent rings ─────────────────────────────────
        for i, base_r in enumerate([40, 55, 72, 88, 102]):
            pulse_r = base_r + self._ring_pulse * 3 * (i + 1) * 0.6
            alpha = max(20, 110 - i * 18)
            if i == 0:
                pen = QPen(QColor(platinum.red(), platinum.green(),
                                  platinum.blue(), alpha), 2)
            elif i == 1:
                pen = QPen(QColor(ring_color.red(), ring_color.green(),
                                  ring_color.blue(), alpha), 2)
            elif i == 2:
                pen = QPen(QColor(violet.red(), violet.green(),
                                  violet.blue(), alpha), 1)
            else:
                pen = QPen(QColor(ring_color.red(), ring_color.green(),
                                  ring_color.blue(), alpha), 1)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), pulse_r, pulse_r)
        # Tick marks on outer ring
        outer_r = 102
        painter.setPen(QPen(QColor(ring_color.red(), ring_color.green(),
                                   ring_color.blue(), 120), 1))
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            x1 = cx + (outer_r - 3) * math.cos(rad)
            y1 = cy + (outer_r - 3) * math.sin(rad)
            x2 = cx + (outer_r + 3) * math.cos(rad)
            y2 = cy + (outer_r + 3) * math.sin(rad)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Rotating energy arcs (2 in opposite directions)
        arc1_r = 90
        arc2_r = 70
        arc1_pen = QPen(QColor(ring_color.red(), ring_color.green(),
                                ring_color.blue(), 200), 3)
        arc1_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc1_pen)
        rect1 = QRectF(cx - arc1_r, cy - arc1_r, arc1_r * 2, arc1_r * 2)
        painter.drawArc(rect1, int(self._tick * 2.5 * 16), 80 * 16)
        arc2_pen = QPen(QColor(violet.red(), violet.green(),
                                violet.blue(), 150), 2)
        arc2_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc2_pen)
        rect2 = QRectF(cx - arc2_r, cy - arc2_r, arc2_r * 2, arc2_r * 2)
        painter.drawArc(rect2, int(-self._tick * 1.7 * 16), 60 * 16)

        # Inner core orb
        core_r = 28 + self._ring_pulse * 5
        core_grad = QRadialGradient(cx, cy, core_r)
        core_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        core_grad.setColorAt(0.3, QColor(platinum.red(), platinum.green(),
                                         platinum.blue(), 200))
        core_grad.setColorAt(0.7, QColor(ring_color.red(), ring_color.green(),
                                         ring_color.blue(), 130))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ── 4. Orbital particles (parade around the orb) ───────────────────
        for p in self._orbital_particles:
            r = p["radius"]
            ang = p["angle"]
            px = cx + math.cos(ang) * r
            py = cy + math.sin(ang) * r
            flicker = (math.sin(self._tick * 0.1 + p["phase"]) + 1) / 2
            alpha = int(p["alpha"] * (0.4 + 0.6 * flicker))
            # Trail: draw small line from center-out for streak effect
            trail_x = cx + math.cos(ang) * (r - 4)
            trail_y = cy + math.sin(ang) * (r - 4)
            trail_pen = QPen(QColor(ring_color.red(), ring_color.green(),
                                    ring_color.blue(), alpha // 2), 1)
            painter.setPen(trail_pen)
            painter.drawLine(QPointF(trail_x, trail_y), QPointF(px, py))
            # Dot
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(255, 255, 255, alpha)))
            painter.drawEllipse(QPointF(px, py), p["size"], p["size"])

        # ── 5. HOLOGRAPHIC TITLE — gradient + shimmer ribbon ──────────────
        # Title painted BELOW the orbital orb, with a horizontal shimmer
        # band that sweeps L→R. Letter-reveal via per-letter alpha.
        # Position: title baseline sits at h*0.78 — guaranteed inside widget.
        title_y = h * 0.70
        title = "SONIC APEX"
        title_font = QFont("Segoe UI", 36, QFont.Weight.Black)
        title_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4.0)
        painter.setFont(title_font)
        fm = painter.fontMetrics()
        title_w = fm.horizontalAdvance(title)
        title_h = fm.height()
        title_x = (w - title_w) / 2

        # Per-letter rendering with cumulative alpha (letter reveal)
        n_chars = len(title)
        reveal_threshold = self._title_reveal
        for i, ch in enumerate(title):
            char_progress = max(0.0, min(1.0,
                                         (reveal_threshold - i / n_chars) * n_chars))
            if char_progress <= 0:
                continue
            char_w = fm.horizontalAdvance(ch)
            char_x = title_x + fm.horizontalAdvance(title[:i])
            # Multi-stop gradient: cyan → white → violet → cyan
            grad = QLinearGradient(char_x, title_y, char_x + char_w, title_y + title_h)
            grad.setColorAt(0.0, QColor(0, 220, 255, int(255 * char_progress)))
            grad.setColorAt(0.5, QColor(255, 255, 255, int(255 * char_progress)))
            grad.setColorAt(1.0, QColor(180, 120, 255, int(255 * char_progress)))
            painter.setPen(QColor(0, 0, 0, 0))  # avoid pen artifacts
            # Manually draw glyph using path fill so we can apply gradient
            path = QPainterPath()
            path.addText(QPointF(char_x, title_y + fm.ascent()), title_font, ch)
            painter.fillPath(path, QBrush(grad))

        # Shimmer ribbon (sweeping white highlight)
        ribbon_x = self._shimmer_phase * (title_w + 200) - 100
        ribbon_grad = QLinearGradient(ribbon_x - 60, title_y,
                                      ribbon_x + 60, title_y)
        ribbon_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        ribbon_grad.setColorAt(0.5, QColor(255, 255, 255, 110))
        ribbon_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        # Clip to title path area
        clip_path = QPainterPath()
        clip_path.addText(QPointF(title_x, title_y + fm.ascent()), title_font, title)
        painter.setClipPath(clip_path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(ribbon_grad))
        painter.drawRect(int(title_x - 10), int(title_y),
                           int(title_w + 20), int(title_h + 8))
        painter.setClipping(False)

        # ── 6. Subtitle (separate row, well below title) ───────────────────
        # Positioned at h*0.90 — guaranteed inside widget bounds, no overlap.
        subtitle_y = h * 0.90
        subtitle_font = QFont("Consolas", 10, QFont.Weight.Bold)
        subtitle_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        painter.setFont(subtitle_font)
        sub_fm = painter.fontMetrics()
        subtitle = "// SYSTEM READY // ALL SYSTEMS NOMINAL" if self._state == CoreState.READY \
                   else "// INITIALIZING NEURAL CORE"
        sub_w = sub_fm.horizontalAdvance(subtitle)
        sub_x = (w - sub_w) / 2
        # Subtle backing pill for legibility
        pill_x = sub_x - 14
        pill_y = subtitle_y - 6
        pill_w = sub_w + 28
        pill_h = sub_fm.height() + 12
        pill_grad = QLinearGradient(pill_x, pill_y, pill_x, pill_y + pill_h)
        pill_grad.setColorAt(0.0, QColor(255, 255, 255, 18))
        pill_grad.setColorAt(1.0, QColor(0, 200, 255, 8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(pill_grad))
        painter.drawRoundedRect(int(pill_x), int(pill_y),
                                 int(pill_w), int(pill_h), 14, 14)
        # Subtitle text (subtle iridescent color)
        sub_color = QColor(200, 220, 240, int(220 * self._subtitle_alpha))
        painter.setPen(sub_color)
        painter.drawText(QPointF(sub_x, subtitle_y + sub_fm.ascent() - 2),
                         subtitle)

        # ── 7. Side accent rails (cinematic frame) ─────────────────────────
        rail_color = QColor(ring_color.red(), ring_color.green(),
                            ring_color.blue(), 80)
        rail_pen = QPen(rail_color, 1)
        painter.setPen(rail_pen)
        rail_y = title_y + title_h / 2
        # Left horizontal accent line
        painter.drawLine(28, int(rail_y), 90, int(rail_y))
        # Right horizontal accent line
        painter.drawLine(int(w - 90), int(rail_y), int(w - 28), int(rail_y))
        # End dots
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(rail_color))
        painter.drawEllipse(QPointF(28, rail_y), 2.5, 2.5)
        painter.drawEllipse(QPointF(w - 28, rail_y), 2.5, 2.5)
        painter.drawEllipse(QPointF(90, rail_y), 2.0, 2.0)
        painter.drawEllipse(QPointF(w - 90, rail_y), 2.0, 2.0)

        painter.end()


# ═════════════════════════════════════════════════════════════════════════════
# Stage Pipeline — same as before (tachometer nodes + animated flow)
# ═════════════════════════════════════════════════════════════════════════════

class StagePipeline(QWidget):
    """6-stage sci-fi pipeline with tachometer-style nodes and animated flow."""

    STAGES = [
        ("system",   "SYSTEM"),
        ("audio",    "AUDIO"),
        ("runtime",  "RUNTIME"),
        ("tools",    "TOOLS"),
        ("verify",   "VERIFY"),
        ("ready",    "READY"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = {s[0]: "pending" for s in self.STAGES}
        self._tick_count = 0
        self.setFixedHeight(58)
        self.setMinimumWidth(560)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(40)

    def _on_tick(self):
        self._tick_count += 1
        self.update()

    def set_stage(self, name: str, state: str):
        if name in self._states:
            self._states[name] = state
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(self.STAGES)
        spacing = w / (n + 1)

        accent = QColor(Tokens.CYAN)
        success = QColor(Tokens.SUCCESS)
        danger = QColor(Tokens.ERROR)
        pending = QColor(255, 255, 255, 50)

        for i, (key, label) in enumerate(self.STAGES):
            x = spacing * (i + 1)
            y = h // 2 - 6
            state = self._states.get(key, "pending")

            if i < n - 1:
                next_x = spacing * (i + 2)
                if state == "done":
                    line_color = success
                    line_pen = QPen(line_color)
                    line_pen.setWidth(2)
                    painter.setPen(line_pen)
                    painter.drawLine(int(x + 14), y, int(next_x - 14), y)
                elif state == "active":
                    line_pen = QPen(accent)
                    line_pen.setWidth(2)
                    line_pen.setStyle(Qt.PenStyle.DashLine)
                    line_pen.setDashOffset(-self._tick_count)
                    painter.setPen(line_pen)
                    painter.drawLine(int(x + 14), y, int(next_x - 14), y)
                    pulse_pos = (self._tick_count * 2) % (next_x - x - 28)
                    pulse_pen = QPen(accent)
                    pulse_pen.setWidth(3)
                    pulse_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(pulse_pen)
                    painter.drawPoint(QPointF(x + 14 + pulse_pos, y))
                elif state == "error":
                    line_pen = QPen(danger)
                    line_pen.setWidth(2)
                    painter.setPen(line_pen)
                    painter.drawLine(int(x + 14), y, int(next_x - 14), y)
                else:
                    line_pen = QPen(pending)
                    line_pen.setWidth(1)
                    painter.setPen(line_pen)
                    painter.drawLine(int(x + 14), y, int(next_x - 14), y)

            if state == "done":
                outer_pen = QPen(QColor(success.red(), success.green(), success.blue(), 60))
                outer_pen.setWidth(1)
                painter.setPen(outer_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 16, 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(success))
                painter.drawEllipse(QPointF(x, y), 10, 10)
                painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                path = QPainterPath()
                path.moveTo(x - 4, y)
                path.lineTo(x - 1, y + 3)
                path.lineTo(x + 4, y - 3)
                painter.drawPath(path)

            elif state == "active":
                pulse = (math.sin(self._tick_count * 0.3) + 1) / 2
                ring_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(),
                                       int(40 + 40 * pulse)))
                ring_pen.setWidth(1)
                painter.setPen(ring_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 16 + pulse * 4, 16 + pulse * 4)
                inner_pen = QPen(accent)
                inner_pen.setWidth(2)
                painter.setPen(inner_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 10, 10)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(accent))
                painter.drawEllipse(QPointF(x, y), 5, 5)

            elif state == "error":
                outer_pen = QPen(QColor(danger.red(), danger.green(), danger.blue(), 80))
                outer_pen.setWidth(1)
                painter.setPen(outer_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 16, 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(danger))
                painter.drawEllipse(QPointF(x, y), 10, 10)
                painter.setPen(QPen(QColor(255, 255, 255), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(int(x - 3), int(y - 3), int(x + 3), int(y + 3))
                painter.drawLine(int(x + 3), int(y - 3), int(x - 3), int(y + 3))

            else:
                outer_pen = QPen(pending)
                outer_pen.setWidth(1)
                outer_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(outer_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 14, 14)
                painter.setPen(QColor(120, 140, 160, 120))
                painter.setFont(Tokens.font_mono(8, QFont.Weight.Bold))
                num_rect = QRectF(x - 6, y - 6, 12, 12)
                painter.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, f"0{i+1}")

            label_color = {
                "done": success,
                "active": accent,
                "error": danger,
            }.get(state, QColor(120, 140, 160))

            painter.setPen(label_color)
            painter.setFont(Tokens.font_mono(9, QFont.Weight.Bold))
            label_rect = QRectF(x - 32, y + 24, 64, 14)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()


# ═════════════════════════════════════════════════════════════════════════════
# Glass Status Panel — widened columns so labels NEVER truncate
# ═════════════════════════════════════════════════════════════════════════════

class GlassStatusPanel(QWidget):
    """Sci-fi detection results panel — wide mono rows that never truncate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[QFrame] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._list_layout = QVBoxLayout()
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        outer.addLayout(self._list_layout)
        self.setMinimumHeight(140)
        self.setMaximumHeight(300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def add_item(self, name: str, status: str, message: str):
        row = self._make_row(name, status, message)
        self._list_layout.addWidget(row)
        self._rows.append(row)
        while len(self._rows) > 6:
            old = self._rows.pop(0)
            self._list_layout.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        # NOTE: We deliberately do NOT call slide_up() here.
        # slide_up() captures widget.pos() at the moment of addWidget(),
        # which is BEFORE the layout has activated. That makes every new
        # row animate back to (0,0), stacking them on top of each other.
        # Using opacity-only fade-in is safe and still feels premium.
        fade_in(row, duration=220)

    def clear(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows.clear()

    def _make_row(self, name: str, status: str, message: str) -> QFrame:
        status_map = {
            "installed": (Tokens.SUCCESS, "✓", "OK"),
            "missing":   (Tokens.WARNING, "!", "OPT"),
            "error":     (Tokens.ERROR,   "✕", "ERR"),
        }
        color, glyph, badge = status_map.get(status, (Tokens.TEXT_TERTIARY, "○", "—"))

        row = QFrame()
        row.setObjectName("DetectionRow")
        row.setStyleSheet(f"""
            QFrame#DetectionRow {{
                background: rgba(20, 30, 50, 0.55);
                border: 1px solid rgba(0, 200, 255, 22);
                border-left: 3px solid {color};
                border-radius: {Tokens.R_SM}px;
            }}
        """)
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.setFixedHeight(34)

        h = QHBoxLayout(row)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(10)

        # Glyph
        glyph_lbl = QLabel(glyph)
        glyph_lbl.setFont(Tokens.font_mono(11, QFont.Weight.Bold))
        glyph_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        glyph_lbl.setFixedWidth(14)
        h.addWidget(glyph_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # Mono name — WIDENED to 220px to fit "PLAYWRIGHT CHROMIUM" etc.
        # (~18 chars × 11px @ mono bold ≈ 198px + padding = 220px safe)
        name_lbl = QLabel(name.upper())
        name_lbl.setFont(Tokens.font_mono(11, QFont.Weight.Bold))
        name_lbl.setStyleSheet(
            f"color: {Tokens.TEXT_PRIMARY}; background: transparent; border: none; "
            f"letter-spacing: 0.5px;"
        )
        name_lbl.setFixedWidth(220)
        name_lbl.setMinimumWidth(220)
        h.addWidget(name_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # Message (mono, dim) — keeps full text; clip with ellipsis only if truly huge
        max_msg_len = 60
        msg = message[:max_msg_len] + "…" if len(message) > max_msg_len else message
        msg_lbl = QLabel(msg)
        msg_lbl.setFont(Tokens.font_mono(10))
        msg_lbl.setStyleSheet(
            f"color: {Tokens.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        h.addWidget(msg_lbl, 1, Qt.AlignmentFlag.AlignVCenter)

        # Mono badge
        badge_lbl = QLabel(badge)
        badge_lbl.setFont(Tokens.font_mono(8, QFont.Weight.Bold))
        badge_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none; "
            f"letter-spacing: 1.5px;"
        )
        badge_lbl.setFixedWidth(38)
        h.addWidget(badge_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        return row


# ═════════════════════════════════════════════════════════════════════════════
# IntelligenceCore — kept for backward compat. Delegates to _CinematicHero.
# ═════════════════════════════════════════════════════════════════════════════

class IntelligenceCore(QWidget):
    """Sci-fi intelligence core — multi-layer rings with holographic accent."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self._pulse = 0.0
        self._glow_intensity = 0.5
        self._state = CoreState.INITIALIZING
        self._target_glow = 0.5
        self._breath_rate = 0.02
        self._pulse_rings: list[dict] = []
        self.setFixedSize(260, 260)

        for i in range(3):
            self._pulse_rings.append({"radius": i * 35, "alpha": 0.0, "phase": i * 1.2})

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_state(self, state: str):
        self._state = state
        if state == CoreState.INITIALIZING:
            self._target_glow = 0.4
            self._breath_rate = 0.015
        elif state == CoreState.CHECKING:
            self._target_glow = 0.6
            self._breath_rate = 0.025
        elif state == CoreState.INSTALLING:
            self._target_glow = 0.8
            self._breath_rate = 0.035
        elif state == CoreState.VERIFYING:
            self._target_glow = 0.7
            self._breath_rate = 0.03
        elif state == CoreState.READY:
            self._target_glow = 1.0
            self._breath_rate = 0.02
        elif state == CoreState.ERROR:
            self._target_glow = 0.3
            self._breath_rate = 0.01

    def _tick(self):
        self._angle += 1.8
        self._pulse = (math.sin(self._angle * self._breath_rate) + 1) / 2
        self._glow_intensity += (self._target_glow - self._glow_intensity) * 0.05
        for ring in self._pulse_rings:
            ring["radius"] += 0.6
            ring["alpha"] = max(0, 0.6 - (ring["radius"] / 110))
            if ring["radius"] > 110:
                ring["radius"] = 0
                ring["alpha"] = 0.6
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() // 2, self.height() // 2
        accent = QColor(Tokens.CYAN)
        danger = QColor(Tokens.ERROR)
        violet = QColor(170, 100, 255)

        for ring in self._pulse_rings:
            if ring["alpha"] <= 0:
                continue
            pen = QPen(QColor(accent.red(), accent.green(), accent.blue(),
                              int(ring["alpha"] * 100 * self._glow_intensity)))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(cx, cy), ring["radius"], ring["radius"])

        glow_r = 95 + self._pulse * 10
        glow = QRadialGradient(cx, cy, glow_r)
        alpha = int(self._glow_intensity * 50)
        glow.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), alpha))
        glow.setColorAt(0.5, QColor(violet.red(), violet.green(), violet.blue(), alpha // 3))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        outer_r = 85
        outer_pen = QPen(QColor(255, 255, 255, 35))
        outer_pen.setWidth(1)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        painter.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(),
                                    int(120 * self._glow_intensity)), 1))
        for deg in range(0, 360, 30):
            rad = math.radians(deg)
            inner_r = outer_r - 4
            outer_tick_r = outer_r + 1
            x1 = cx + inner_r * math.cos(rad)
            y1 = cy + inner_r * math.sin(rad)
            x2 = cx + outer_tick_r * math.cos(rad)
            y2 = cy + outer_tick_r * math.sin(rad)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        mid_r = 68
        mid_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(),
                               int(150 * self._glow_intensity)))
        mid_pen.setWidth(2)
        mid_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(mid_pen)
        rect = QRectF(cx - mid_r, cy - mid_r, mid_r * 2, mid_r * 2)
        painter.drawArc(rect, int(self._angle * 16), 60 * 16)

        mid_r2 = 60
        mid_pen2 = QPen(QColor(violet.red(), violet.green(), violet.blue(),
                                int(100 * self._glow_intensity)))
        mid_pen2.setWidth(2)
        painter.setPen(mid_pen2)
        rect2 = QRectF(cx - mid_r2, cy - mid_r2, mid_r2 * 2, mid_r2 * 2)
        painter.drawArc(rect2, int(-self._angle * 0.7 * 16), 45 * 16)

        core_r = 38 + self._pulse * 5
        core_grad = QRadialGradient(cx, cy, core_r)
        core_alpha = int(200 * self._glow_intensity)
        if self._state == CoreState.ERROR:
            core_grad.setColorAt(0.0, QColor(danger.red(), danger.green() - 60, danger.blue(), core_alpha))
            core_grad.setColorAt(0.5, QColor(danger.red() - 50, 60, 50, core_alpha // 2))
        else:
            core_grad.setColorAt(0.0, QColor(accent.red(), accent.green() + 20, accent.blue(), core_alpha))
            core_grad.setColorAt(0.5, QColor(violet.red(), violet.green(), violet.blue(), core_alpha // 2))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        orb_r = 14 + self._pulse * 3
        orb_grad = QRadialGradient(cx, cy, orb_r)
        orb_alpha = int(255 * self._glow_intensity)
        orb_grad.setColorAt(0.0, QColor(255, 255, 255, orb_alpha))
        orb_grad.setColorAt(0.3, QColor(accent.red(), accent.green() + 40, accent.blue(), orb_alpha // 2))
        orb_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(orb_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        cx_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(),
                              int(80 * self._glow_intensity)))
        cx_pen.setWidth(1)
        painter.setPen(cx_pen)
        for dx, dy in [(0, -outer_r - 8), (0, outer_r + 8),
                        (-outer_r - 8, 0), (outer_r + 8, 0)]:
            painter.drawEllipse(QPointF(cx + dx, cy + dy), 2, 2)

        painter.end()


# ═════════════════════════════════════════════════════════════════════════════
# Sci-Fi Progress Bar — gradient with scan highlight
# ═════════════════════════════════════════════════════════════════════════════

class _SciFiProgressBar(QWidget):
    """Gradient progress bar with glowing edge + animated scan highlight."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._tick = 0
        self.setFixedHeight(8)
        self.setMinimumWidth(400)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(40)

    def _on_tick(self):
        self._tick += 1
        self.update()

    def setValue(self, v: int):
        self._value = max(0, min(100, int(v)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(20, 30, 45)))
        painter.drawRoundedRect(0, 0, w, h, h / 2, h / 2)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        border_pen = QPen(QColor(0, 200, 255, 40))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.drawRoundedRect(0, 0, w - 1, h - 1, h / 2, h / 2)

        if self._value <= 0:
            painter.end()
            return

        fill_w = int((w - 2) * self._value / 100)
        if fill_w < 1:
            painter.end()
            return
        grad = QLinearGradient(0, 0, fill_w, 0)
        grad.setColorAt(0.0, QColor(0, 180, 220))
        grad.setColorAt(0.7, QColor(0, 230, 255))
        grad.setColorAt(1.0, QColor(255, 255, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(1, 1, fill_w, h - 2, (h - 2) / 2, (h - 2) / 2)

        edge_x = fill_w
        scan_pen = QPen(QColor(255, 255, 255, 180))
        scan_pen.setWidth(2)
        painter.setPen(scan_pen)
        painter.drawLine(int(edge_x), 1, int(edge_x), h - 1)

        scan_pos = (self._tick * 3) % max(fill_w, 1)
        glow_grad = QRadialGradient(scan_pos, h / 2, 16)
        glow_grad.setColorAt(0.0, QColor(255, 255, 255, 90))
        glow_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_grad))
        painter.drawRoundedRect(1, 1, fill_w, h - 2, (h - 2) / 2, (h - 2) / 2)

        painter.end()


# ═════════════════════════════════════════════════════════════════════════════
# Main Premium UI — HOLOGRAPHIC + CINEMATIC LAYOUT
# ═════════════════════════════════════════════════════════════════════════════

class SonicBootUI(QWidget):
    """Holographic + Hollywood cinematic first-run UI."""

    finished = pyqtSignal()

    def __init__(self, state: BootstrapState):
        super().__init__()
        self._state = state
        self._worker = None
        self._results = []
        self._phase = "init"
        self._start_time = time.monotonic()

        self.setWindowTitle("SONIC Apex")
        self.setFixedSize(820, 720)
        self.setStyleSheet(f"""
            QWidget {{
                background: #010206;
                color: {Tokens.TEXT_PRIMARY};
                font-family: {Tokens.FONT};
            }}
        """)

        self._build_ui()

    def _build_ui(self):
        # ── Holographic backdrop (drawn first, behind everything) ───────────
        self._backdrop = _HoloBackdrop(self)
        self._backdrop.setGeometry(0, 0, self.width(), self.height())
        self._backdrop.lower()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 22, 40, 22)
        layout.setSpacing(0)

        # ── Top HUD bar ─────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        sys_tag = QLabel("SONIC.APEX // HOLOFRAME ONLINE")
        sys_tag.setFont(Tokens.font_mono(9, QFont.Weight.Bold))
        sys_tag.setStyleSheet(
            f"color: {Tokens.CYAN}; background: transparent; letter-spacing: 1.8px;"
        )
        top_bar.addWidget(sys_tag)
        top_bar.addStretch()
        self._clock_lbl = QLabel("")
        self._clock_lbl.setFont(Tokens.font_mono(9, QFont.Weight.Bold))
        self._clock_lbl.setStyleSheet(
            f"color: {Tokens.TEXT_TERTIARY}; background: transparent; letter-spacing: 1.8px;"
        )
        top_bar.addWidget(self._clock_lbl)
        layout.addLayout(top_bar)

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

        layout.addSpacing(8)

        # ── CINEMATIC HERO (replaces SonicBootAnimation) ────────────────────
        # Owns: lens flare + iridescent rings + shimmer title + subtitle pill.
        # Sits in its own widget so the parent QLayout CANNOT accidentally
        # double-render or overlap the title/subtitle.
        self._hero = _CinematicHero(self)
        hero_holder = QHBoxLayout()
        hero_holder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_holder.setContentsMargins(0, 0, 0, 0)
        hero_holder.addWidget(self._hero)
        layout.addLayout(hero_holder)

        layout.addSpacing(10)

        # ── Stage Pipeline ─────────────────────────────────────────────────
        self._pipeline = StagePipeline()
        self._pipeline.hide()
        pipeline_layout = QHBoxLayout()
        pipeline_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pipeline_layout.setContentsMargins(0, 0, 0, 0)
        pipeline_layout.addWidget(self._pipeline)
        layout.addLayout(pipeline_layout)

        layout.addSpacing(14)

        # ── Progress Section ───────────────────────────────────────────────
        progress_row = QHBoxLayout()
        progress_row.setSpacing(12)

        self._progress_label = QLabel("[ STATUS ]")
        self._progress_label.setFont(Tokens.font_mono(9, QFont.Weight.Bold))
        self._progress_label.setStyleSheet(
            f"color: {Tokens.TEXT_TERTIARY}; background: transparent; letter-spacing: 1.8px;"
        )
        self._progress_label.hide()
        progress_row.addWidget(self._progress_label)

        progress_row.addStretch()

        self._percent_label = QLabel("000%")
        self._percent_label.setFont(Tokens.font_mono(13, QFont.Weight.Bold))
        self._percent_label.setStyleSheet(
            f"color: {Tokens.CYAN}; background: transparent; letter-spacing: 1px;"
        )
        self._percent_label.hide()
        progress_row.addWidget(self._percent_label)

        layout.addLayout(progress_row)

        layout.addSpacing(6)

        # ── Progress Bar (sci-fi) ──────────────────────────────────────────
        self._scifi_progress = _SciFiProgressBar()
        self._scifi_progress.hide()
        layout.addWidget(self._scifi_progress)

        layout.addSpacing(8)

        # ── Status message ─────────────────────────────────────────────────
        self._status_label = QLabel(">> Preparing your environment...")
        self._status_label.setFont(Tokens.font_mono(11))
        self._status_label.setStyleSheet(
            f"color: {Tokens.TEXT_SECONDARY}; background: transparent;"
        )
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.hide()
        layout.addWidget(self._status_label)

        layout.addSpacing(10)

        # ── Glass Status Panel (widened columns — no truncation) ───────────
        self._glass_panel = GlassStatusPanel()
        self._glass_panel.hide()
        layout.addWidget(self._glass_panel, 1)

        layout.addSpacing(8)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self._skip_btn = AppleButton("SKIP OPTIONAL TOOLS", style="ghost")
        self._skip_btn.setFixedHeight(40)
        self._skip_btn.clicked.connect(self._skip_optional)
        self._skip_btn.hide()
        btn_layout.addWidget(self._skip_btn)

        self._action_btn = AppleButton("ENTER SONIC  →", style="primary")
        self._action_btn.setFixedSize(220, 44)
        self._action_btn.clicked.connect(self._on_action)
        self._action_btn.setEnabled(False)
        self._action_btn.hide()
        btn_layout.addWidget(self._action_btn)

        layout.addLayout(btn_layout)

    def _update_clock(self):
        self._clock_lbl.setText(datetime.now().strftime("%H:%M:%S // %Y.%m.%d"))

    # ── Public API (kept stable) ────────────────────────────────────────────

    def _on_cinematic_complete(self):
        # Kept for API compat. Now fades the UI in immediately.
        self._fade_in_setup_ui()

    def _fade_in_setup_ui(self):
        # Reveal hero fully
        self._hero._title_reveal = 1.0
        self._hero._subtitle_alpha = 1.0

        for w in (
            self._pipeline,
            self._progress_label, self._percent_label,
            self._scifi_progress, self._status_label,
            self._glass_panel, self._action_btn,
        ):
            w.show()

        fade_in(self._pipeline, duration=380)
        QTimer.singleShot(80, lambda: fade_in(self._progress_label, duration=320))
        QTimer.singleShot(160, lambda: fade_in(self._percent_label, duration=320))
        QTimer.singleShot(240, lambda: slide_up(self._scifi_progress, duration=380, offset=10))
        QTimer.singleShot(320, lambda: fade_in(self._status_label, duration=320))
        QTimer.singleShot(400, lambda: fade_in(self._glass_panel, duration=380))
        QTimer.singleShot(540, lambda: slide_up(self._action_btn, duration=420, offset=12))

        QTimer.singleShot(700, self._start_detection)

    def _start_detection(self):
        self._phase = "detecting"
        self._hero.set_state(CoreState.CHECKING)
        self._status_label.setText(">> Scanning your environment...")
        self._pipeline.set_stage("system", "active")

        self._worker = WorkerThread(mode="detect")
        self._worker.progress.connect(self._on_progress)
        self._worker.requirement_check.connect(self._on_req_check)
        self._worker.stage_update.connect(self._on_stage_update)
        self._worker.all_done.connect(self._on_detection_done)
        self._worker.start()

    def _on_progress(self, msg: str, pct: int):
        self._percent_label.setText(f"{pct:03d}%")
        self._scifi_progress.setValue(pct)
        self._status_label.setText(f">> {msg}")

    def _on_stage_update(self, stage: str, state: str):
        self._pipeline.set_stage(stage, state)
        if state == "active":
            self._hero.set_state(CoreState.CHECKING)
        elif state == "done":
            self._hero.set_state(CoreState.VERIFYING)

    def _on_req_check(self, result: DepResult):
        self._results.append(result)
        status_str = {
            Status.INSTALLED: "installed",
            Status.MISSING: "missing",
            Status.CHECK_FAILED: "error",
        }.get(result.status, "unknown")
        self._glass_panel.add_item(result.name, status_str, result.message)

    def _on_detection_done(self, success: bool, msg: str):
        if not success:
            self._hero.set_state(CoreState.ERROR)
            self._status_label.setText(">> INITIALIZATION NEEDS ATTENTION")
            self._action_btn.setText("RETRY")
            self._action_btn.setEnabled(True)
            return

        required_missing = [r for r in self._results
                           if r.status == Status.MISSING and r.id in
                           ("mic_check", "speaker_check", "internet_check", "disk_space")]

        optional_missing = [r for r in self._results
                           if r.status == Status.MISSING and r.id in
                           ("playwright_chromium", "ffmpeg", "vlc", "opencode")]

        self._pipeline.set_stage("ready", "active")

        if required_missing:
            names = ", ".join(r.name for r in required_missing)
            self._hero.set_state(CoreState.ERROR)
            self._status_label.setText(f">> REQUIRED MISSING: {names}")
            self._action_btn.setText("RETRY")
            self._action_btn.setEnabled(True)
        else:
            self._hero.set_state(CoreState.READY)
            self._pipeline.set_stage("ready", "done")
            self._status_label.setText(">> SONIC IS READY")
            self._action_btn.setText("ENTER SONIC  →")
            self._action_btn.setEnabled(True)

        if not optional_missing:
            self._skip_btn.hide()
        else:
            self._skip_btn.show()

        self._percent_label.setText("100%")
        self._scifi_progress.setValue(100)
        self._state.set_system_info({
            "os": str(self._results),
            "check_time": str(time.time())
        })

    def _skip_optional(self):
        for r in self._results:
            if r.status == Status.MISSING:
                self._state.mark_optional_skipped(r.id)
        self._phase = "done"
        self._state.mark_completed()
        self.finished.emit()

    def _on_action(self):
        if self._phase == "done":
            self.finished.emit()
            return

        required_missing = [r for r in self._results
                           if r.status == Status.MISSING and r.id in
                           ("mic_check", "speaker_check", "internet_check", "disk_space")]

        if required_missing:
            self._status_label.setText(">> CONNECT REQUIRED HARDWARE AND RETRY")
            self._action_btn.setText("RETRY")
            self._phase = "done"
            return

        self._phase = "done"
        self._state.mark_completed()
        self.finished.emit()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_backdrop'):
            self._backdrop.setGeometry(0, 0, self.width(), self.height())