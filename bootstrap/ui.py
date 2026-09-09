"""SONIC AI Bootstrapper - Premium Cinematic First-Run UI.

Ultra-premium initialization experience with multi-layer intelligence core,
glass status panel, cinematic progress, and state-driven animations.
"""
from __future__ import annotations

import math
import time
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QEasingCurve, QPropertyAnimation,
    QPointF, QRectF, QParallelAnimationGroup, QSequentialAnimationGroup,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QRadialGradient,
    QPen, QBrush, QPainterPath, QFontMetrics,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsDropShadowEffect, QApplication, QGraphicsOpacityEffect,
)

from .detector import Status, DepResult, detect_all, get_system_info
from .state import BootstrapState
from .installer import DependencyInstaller, InstallResult


# ── Animation States ──────────────────────────────────────────────────────
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

                # Map results to stages
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


# ── Intelligence Core Widget ──────────────────────────────────────────────
class IntelligenceCore(QWidget):
    """Multi-layer animated SONIC intelligence core."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0.0
        self._pulse = 0.0
        self._glow_intensity = 0.5
        self._state = CoreState.INITIALIZING
        self._target_glow = 0.5
        self._breath_rate = 0.02
        self.setFixedSize(200, 200)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)  # ~60fps

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
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() // 2, self.height() // 2

        # ── Outer ambient glow ────────────────────────────────────────────
        glow_r = 90 + self._pulse * 10
        glow = QRadialGradient(cx, cy, glow_r)
        alpha = int(self._glow_intensity * 35)
        glow.setColorAt(0.0, QColor(0, 180, 255, alpha))
        glow.setColorAt(0.5, QColor(0, 100, 200, alpha // 3))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(QPointF(cx, cy), glow_r, glow_r)

        # ── Outer orbital ring (very subtle) ──────────────────────────────
        outer_r = 75
        outer_pen = QPen(QColor(100, 140, 180, 40))
        outer_pen.setWidth(1)
        painter.setPen(outer_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(cx, cy), outer_r, outer_r)

        # ── Middle rotating energy ring ──────────────────────────────────
        mid_r = 60
        mid_pen = QPen(QColor(0, 200, 255, int(120 * self._glow_intensity)))
        mid_pen.setWidth(2)
        mid_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(mid_pen)
        rect = QRectF(cx - mid_r, cy - mid_r, mid_r * 2, mid_r * 2)
        painter.drawArc(rect, int(self._angle * 16), 60 * 16)

        # ── Second rotating ring (opposite direction) ─────────────────────
        mid_r2 = 55
        mid_pen2 = QPen(QColor(0, 150, 220, int(80 * self._glow_intensity)))
        mid_pen2.setWidth(1.5)
        painter.setPen(mid_pen2)
        rect2 = QRectF(cx - mid_r2, cy - mid_r2, mid_r2 * 2, mid_r2 * 2)
        painter.drawArc(rect2, int(-self._angle * 0.7 * 16), 45 * 16)

        # ── Inner glowing core ───────────────────────────────────────────
        core_r = 35 + self._pulse * 5
        core_grad = QRadialGradient(cx, cy, core_r)
        core_alpha = int(180 * self._glow_intensity)
        if self._state == CoreState.ERROR:
            core_grad.setColorAt(0.0, QColor(255, 100, 80, core_alpha))
            core_grad.setColorAt(0.5, QColor(200, 60, 50, core_alpha // 2))
        else:
            core_grad.setColorAt(0.0, QColor(0, 220, 255, core_alpha))
            core_grad.setColorAt(0.5, QColor(0, 120, 200, core_alpha // 2))
        core_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(core_grad))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # ── Center luminous orb ──────────────────────────────────────────
        orb_r = 12 + self._pulse * 3
        orb_grad = QRadialGradient(cx, cy, orb_r)
        orb_alpha = int(255 * self._glow_intensity)
        orb_grad.setColorAt(0.0, QColor(255, 255, 255, orb_alpha))
        orb_grad.setColorAt(0.3, QColor(0, 240, 255, orb_alpha // 2))
        orb_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(QBrush(orb_grad))
        painter.drawEllipse(QPointF(cx, cy), orb_r, orb_r)

        # ── Thin decorative arcs ─────────────────────────────────────────
        dec_r = 45
        dec_pen = QPen(QColor(0, 180, 255, int(60 * self._glow_intensity)))
        dec_pen.setWidth(0.5)
        painter.setPen(dec_pen)
        dec_rect = QRectF(cx - dec_r, cy - dec_r, dec_r * 2, dec_r * 2)
        painter.drawArc(dec_rect, int(self._angle * 0.5 * 16), 30 * 16)
        painter.drawArc(dec_rect, int((self._angle * 0.5 + 180) * 16), 30 * 16)

        painter.end()


# ── Stage Pipeline Widget ─────────────────────────────────────────────────
class StagePipeline(QWidget):
    """Horizontal setup stage pipeline."""

    STAGES = [
        ("system", "SYSTEM"),
        ("audio", "AUDIO"),
        ("runtime", "RUNTIME"),
        ("tools", "TOOLS"),
        ("verify", "VERIFY"),
        ("ready", "READY"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = {s[0]: "pending" for s in self.STAGES}
        self.setFixedHeight(40)
        self.setMinimumWidth(500)

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

        for i, (key, label) in enumerate(self.STAGES):
            x = spacing * (i + 1)
            y = h // 2
            state = self._states.get(key, "pending")

            # Connector line
            if i < n - 1:
                next_x = spacing * (i + 2)
                line_pen = QPen(QColor(40, 60, 80))
                line_pen.setWidth(1)
                painter.setPen(line_pen)
                painter.drawLine(int(x + 10), y, int(next_x - 10), y)

            # Stage circle
            if state == "done":
                circle_color = QColor(0, 200, 150)
                painter.setPen(QPen(circle_color, 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 8, 8)

                # Checkmark
                painter.setPen(QPen(QColor(0, 200, 150), 2))
                painter.drawLine(int(x - 3), y, int(x - 1), y + 3)
                painter.drawLine(int(x - 1), y + 3, int(x + 4), y - 3)

            elif state == "active":
                # Pulsing active indicator
                pulse = (math.sin(time.time() * 4) + 1) / 2
                active_color = QColor(0, 180 + int(60 * pulse), 255)
                painter.setPen(QPen(active_color, 2))
                painter.setBrush(QBrush(QColor(0, 180, 255, 40)))
                painter.drawEllipse(QPointF(x, y), 9, 9)

            elif state == "error":
                painter.setPen(QPen(QColor(255, 100, 80), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 8, 8)

                # X mark
                painter.setPen(QPen(QColor(255, 100, 80), 2))
                painter.drawLine(int(x - 3), y - 3, int(x + 3), y + 3)
                painter.drawLine(int(x + 3), y - 3, int(x - 3), y + 3)
            else:
                # Pending
                painter.setPen(QPen(QColor(50, 70, 90), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QPointF(x, y), 6, 6)

            # Label
            label_color = {
                "done": QColor(0, 200, 150),
                "active": QColor(0, 180, 255),
                "error": QColor(255, 100, 80),
            }.get(state, QColor(70, 90, 110))

            painter.setPen(label_color)
            painter.setFont(QFont("Segoe UI", 8))
            label_rect = QRectF(x - 30, y + 14, 60, 16)
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()


# ── Glass Status Panel ────────────────────────────────────────────────────
class GlassStatusPanel(QWidget):
    """Translucent glass diagnostic/status panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self.setMinimumHeight(120)
        self.setMaximumHeight(160)

    def add_item(self, name: str, status: str, message: str):
        self._items.append((name, status, message))
        if len(self._items) > 6:
            self._items = self._items[-6:]
        self.update()

    def clear(self):
        self._items.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Glass background
        bg = QPainterPath()
        bg.addRoundedRect(0, 0, w, h, 10, 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(10, 15, 25, 180)))
        painter.drawPath(bg)

        # Subtle border
        border_pen = QPen(QColor(40, 60, 80, 100))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(0, 0, w, h, 10, 10)

        # Items
        y_offset = 15
        for name, status, message in self._items[:6]:
            # Status icon
            if status == "installed":
                icon_color = QColor(0, 200, 150)
                icon = "✓"
            elif status == "missing":
                icon_color = QColor(255, 180, 50)
                icon = "!"
            elif status == "error":
                icon_color = QColor(255, 100, 80)
                icon = "✗"
            else:
                icon_color = QColor(80, 100, 120)
                icon = "○"

            painter.setPen(icon_color)
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.drawText(15, y_offset + 14, icon)

            # Name
            painter.setPen(QColor(180, 200, 220))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(35, y_offset + 14, name)

            # Message (truncated)
            painter.setPen(QColor(100, 120, 140))
            painter.setFont(QFont("Segoe UI", 9))
            msg_display = message[:40] + "..." if len(message) > 40 else message
            painter.drawText(w - 200, y_offset + 14, msg_display)

            y_offset += 20

        painter.end()


# ── Main Premium UI ──────────────────────────────────────────────────────
class SonicBootUI(QWidget):
    finished = pyqtSignal()

    def __init__(self, state: BootstrapState):
        super().__init__()
        self._state = state
        self._worker = None
        self._results = []
        self._phase = "init"
        self._entry_opacity = 0.0
        self._core_state = CoreState.INITIALIZING

        self.setWindowTitle("SONIC AI")
        self.setMinimumSize(680, 560)
        self.setMaximumSize(680, 560)
        self.setStyleSheet("""
            QWidget {
                background: #060810;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        self._build_ui()
        self._start_entry_animation()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 35, 50, 35)
        layout.setSpacing(8)

        # ── Central Core ──────────────────────────────────────────────────
        core_container = QHBoxLayout()
        core_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._core = IntelligenceCore()
        core_container.addWidget(self._core)

        layout.addLayout(core_container)
        layout.addSpacing(5)

        # ── Title ─────────────────────────────────────────────────────────
        self._title = QLabel("SONIC AI")
        self._title.setFont(QFont("Segoe UI", 32, QFont.Weight.DemiBold))
        self._title.setStyleSheet("color: #d0d8e0; background: transparent; letter-spacing: 2px;")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setGraphicsEffect(self._create_glow(0.3))
        layout.addWidget(self._title)

        # ── Subtitle ──────────────────────────────────────────────────────
        self._subtitle = QLabel("Initializing your personal intelligence")
        self._subtitle.setFont(QFont("Segoe UI", 12))
        self._subtitle.setStyleSheet("color: #6a7a8a; background: transparent;")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._subtitle)

        layout.addSpacing(10)

        # ── Stage Pipeline ────────────────────────────────────────────────
        self._pipeline = StagePipeline()
        pipeline_layout = QHBoxLayout()
        pipeline_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pipeline_layout.addWidget(self._pipeline)
        layout.addLayout(pipeline_layout)

        layout.addSpacing(8)

        # ── Progress Section ──────────────────────────────────────────────
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(15)

        self._progress_label = QLabel("INITIALIZATION")
        self._progress_label.setFont(QFont("Segoe UI", 10))
        self._progress_label.setStyleSheet("color: #5a6a7a; background: transparent; letter-spacing: 1px;")
        progress_layout.addWidget(self._progress_label)

        progress_layout.addStretch()

        self._percent_label = QLabel("0%")
        self._percent_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Light))
        self._percent_label.setStyleSheet("color: #c0d0e0; background: transparent;")
        progress_layout.addWidget(self._percent_label)

        layout.addLayout(progress_layout)

        # ── Progress Track ────────────────────────────────────────────────
        self._progress_track = QWidget()
        self._progress_track.setFixedHeight(3)
        self._progress_track.setStyleSheet("background: transparent;")
        self._progress_value = 0
        layout.addWidget(self._progress_track)

        # ── Status Message ────────────────────────────────────────────────
        self._status_label = QLabel("Preparing your environment...")
        self._status_label.setFont(QFont("Segoe UI", 11))
        self._status_label.setStyleSheet("color: #8090a0; background: transparent; padding: 8px 0;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # ── Glass Status Panel ────────────────────────────────────────────
        self._glass_panel = GlassStatusPanel()
        layout.addWidget(self._glass_panel)

        layout.addSpacing(5)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._skip_btn = QPushButton("Skip optional tools")
        self._skip_btn.setFixedSize(160, 36)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #5a6a7a;
                border: 1px solid #2a3545;
                border-radius: 8px;
                font-size: 11px;
            }
            QPushButton:hover { border: 1px solid #4a5a6a; color: #8a9aaa; }
        """)
        self._skip_btn.clicked.connect(self._skip_optional)
        self._skip_btn.hide()
        btn_layout.addWidget(self._skip_btn)

        self._action_btn = QPushButton("Enter SONIC")
        self._action_btn.setFixedSize(180, 44)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #1a2030, stop:0.5 #2a3545, stop:1 #1a2030);
                color: #c0d0e0;
                border: 1px solid #3a4a5a;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2a3545, stop:0.5 #4a5a6a, stop:1 #2a3545);
                border: 1px solid #5a6a7a;
            }
            QPushButton:disabled {
                background: #0d1018;
                color: #3a4a5a;
                border: 1px solid #1a2030;
            }
        """)
        self._action_btn.clicked.connect(self._on_action)
        self._action_btn.setEnabled(False)
        btn_layout.addWidget(self._action_btn)

        layout.addLayout(btn_layout)

    def _create_glow(self, radius):
        effect = QGraphicsDropShadowEffect()
        effect.setBlurRadius(int(radius * 100))
        effect.setColor(QColor(0, 150, 255, 30))
        effect.setOffset(0, 0)
        return effect

    def _start_entry_animation(self):
        """Cinematic entry animation."""
        self._entry_opacity = 0.0

        # Fade in sequence
        self._fade_timer = QTimer(self)
        self._fade_step = 0
        self._fade_timer.timeout.connect(self._animate_entry)
        self._fade_timer.start(20)

    def _animate_entry(self):
        self._fade_step += 1
        self._entry_opacity = min(1.0, self._fade_step / 25.0)

        # Apply opacity
        self._core.setGraphicsEffect(self._create_fade(self._entry_opacity * 0.8 + 0.2))
        self._title.setGraphicsEffect(self._create_fade(self._entry_opacity))
        self._subtitle.setGraphicsEffect(self._create_fade(min(1.0, self._entry_opacity * 1.2)))

        if self._fade_step >= 25:
            self._fade_timer.stop()
            QTimer.singleShot(300, self._start_detection)

    def _create_fade(self, opacity):
        effect = QGraphicsOpacityEffect()
        effect.setOpacity(opacity)
        return effect

    def _start_detection(self):
        self._phase = "detecting"
        self._core_state = CoreState.CHECKING
        self._core.set_state(CoreState.CHECKING)
        self._status_label.setText("Scanning your environment...")
        self._pipeline.set_stage("system", "active")

        self._worker = WorkerThread(mode="detect")
        self._worker.progress.connect(self._on_progress)
        self._worker.requirement_check.connect(self._on_req_check)
        self._worker.stage_update.connect(self._on_stage_update)
        self._worker.all_done.connect(self._on_detection_done)
        self._worker.start()

    def _on_progress(self, msg: str, pct: int):
        self._progress_value = pct
        self._percent_label.setText(f"{pct}%")
        self._progress_track.update()
        self._status_label.setText(msg)

    def _on_stage_update(self, stage: str, state: str):
        self._pipeline.set_stage(stage, state)
        if state == "active":
            self._core.set_state(CoreState.CHECKING)
        elif state == "done":
            self._core.set_state(CoreState.VERIFYING)

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
            self._core.set_state(CoreState.ERROR)
            self._status_label.setText("Initialization needs attention")
            self._action_btn.setText("Retry")
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
            self._core.set_state(CoreState.ERROR)
            self._status_label.setText(f"Required: {names}")
            self._action_btn.setText("Retry")
            self._action_btn.setEnabled(True)
        elif optional_missing:
            self._core.set_state(CoreState.READY)
            self._pipeline.set_stage("ready", "done")
            self._status_label.setText("SONIC is ready.")
            self._subtitle.setText("Your personal intelligence is initialized.")
            self._action_btn.setText("Enter SONIC  →")
            self._action_btn.setEnabled(True)
            self._skip_btn.show()
        else:
            self._core.set_state(CoreState.READY)
            self._pipeline.set_stage("ready", "done")
            self._status_label.setText("SONIC is ready.")
            self._subtitle.setText("Your personal intelligence is initialized.")
            self._action_btn.setText("Enter SONIC  →")
            self._action_btn.setEnabled(True)

        self._progress_value = 100
        self._percent_label.setText("100%")
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
            self._status_label.setText("Connect required hardware and retry")
            self._action_btn.setText("Retry")
            self._phase = "done"
            return

        self._phase = "done"
        self._state.mark_completed()
        self.finished.emit()

    def paintEvent(self, event):
        """Custom background painting."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # Deep matte background
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(6, 8, 16))
        bg.setColorAt(0.5, QColor(8, 10, 18))
        bg.setColorAt(1.0, QColor(6, 8, 16))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg))
        painter.drawRect(0, 0, w, h)

        # Subtle radial vignette
        vignette = QRadialGradient(w // 2, h // 2, max(w, h) * 0.6)
        vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(0, 0, 0, 80))
        painter.setBrush(QBrush(vignette))
        painter.drawRect(0, 0, w, h)

        # Thin progress track
        if self._progress_value > 0:
            track_y = self._progress_track.y() + 1
            track_w = self.width() - 100
            fill_w = track_w * self._progress_value / 100

            # Track background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(20, 30, 40)))
            painter.drawRoundedRect(50, track_y, track_w, 2, 1, 1)

            # Fill
            if fill_w > 0:
                fill_grad = QLinearGradient(50, 0, 50 + track_w, 0)
                fill_grad.setColorAt(0.0, QColor(0, 150, 220))
                fill_grad.setColorAt(0.7, QColor(0, 200, 255))
                fill_grad.setColorAt(1.0, QColor(0, 150, 220))
                painter.setBrush(QBrush(fill_grad))
                painter.drawRoundedRect(50, track_y, int(fill_w), 2, 1, 1)

        painter.end()
