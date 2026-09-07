"""SONIC AI Bootstrapper - First-Run UI.

Polished setup screen shown on first launch.
Displays dependency checking progress with animated visuals.
"""
from __future__ import annotations

import sys
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QEasingCurve, QPropertyAnimation
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QGraphicsDropShadowEffect, QApplication
)

from .detector import Status, DepResult, detect_all, get_system_info
from .state import BootstrapState
from .installer import DependencyInstaller, InstallResult


class WorkerThread(QThread):
    progress = pyqtSignal(str, int)
    requirement_check = pyqtSignal(object)
    requirement_install = pyqtSignal(str, object)
    all_done = pyqtSignal(bool, str)

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
            self.progress.emit("Checking system requirements...", 5)
            sys_info = get_system_info()
            self.progress.emit(f"OS: {sys_info.os_name} {sys_info.os_build} ({sys_info.architecture})", 10)

            results = detect_all()
            total = len(results)
            for i, result in enumerate(results):
                if self._cancel:
                    return
                pct = 10 + int(80 * (i / total))
                status_icon = {
                    Status.INSTALLED: "[OK]",
                    Status.MISSING: "[!!]",
                    Status.CHECK_FAILED: "[??]",
                    Status.NOT_APPLICABLE: "[--]",
                }.get(result.status, "[??]")
                self.progress.emit(f"{status_icon} {result.name}: {result.message}", pct)
                self.requirement_check.emit(result)
                self.msleep(150)

            self.progress.emit("System check complete", 95)
            self.all_done.emit(True, "Detection complete")
        except Exception as e:
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
        missing = []
        for req in requirements:
            if req.get("required") and not req.get("bundled"):
                missing.append(req)

        total = len(missing)
        if total == 0:
            self.all_done.emit(True, "All required dependencies are bundled")
            return

        installed_count = 0
        for i, req in enumerate(missing):
            if self._cancel:
                self.all_done.emit(False, "Installation cancelled")
                return

            self.progress.emit(f"Installing {req['name']}...", int(100 * (i / total)))
            result = installer.install(req["id"], req)
            self.requirement_install.emit(req["id"], result)

            if result.success or result.requires_manual:
                installed_count += 1

        self.progress.emit("Installation complete", 100)
        self.all_done.emit(True, f"{installed_count}/{total} dependencies addressed")


class GlowRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._rotate)
        self._timer.start(30)
        self.setFixedSize(120, 120)

    def _rotate(self):
        self._angle = (self._angle + 3) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() // 2, self.height() // 2
        radius = 50

        for i in range(3):
            offset = i * 120
            alpha = max(0, 200 - i * 60)
            pen = QPen(QColor(192, 192, 192, alpha))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawArc(
                cx - radius, cy - radius, radius * 2, radius * 2,
                (self._angle + offset) * 16, 90 * 16
            )

        painter.end()


class SonicBootUI(QWidget):
    finished = pyqtSignal()

    def __init__(self, state: BootstrapState):
        super().__init__()
        self._state = state
        self._worker = None
        self._results = []
        self._phase = "init"
        self.setWindowTitle("SONIC AI - First Run Setup")
        self.setMinimumSize(700, 520)
        self.setMaximumSize(700, 520)
        self.setStyleSheet("""
            QWidget {
                background: #080c14;
                color: #e0e0e0;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        self._build_ui()
        QTimer.singleShot(500, self._start_detection)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(15)

        header = QHBoxLayout()
        header.setSpacing(15)

        self._glow = GlowRing()
        header.addWidget(self._glow)

        title_layout = QVBoxLayout()
        title = QLabel("SONIC AI")
        title.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title.setStyleSheet("color: #C0C0C0; background: transparent;")
        title_layout.addWidget(title)

        subtitle = QLabel("First Run Setup")
        subtitle.setFont(QFont("Segoe UI", 12))
        subtitle.setStyleSheet("color: #8899aa; background: transparent;")
        title_layout.addWidget(subtitle)
        header.addLayout(title_layout)
        header.addStretch()

        layout.addLayout(header)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #C0C0C0, stop:1 #080c14); max-height: 1px;")
        layout.addWidget(line)

        self._status_label = QLabel("Preparing your system...")
        self._status_label.setFont(QFont("Segoe UI", 11))
        self._status_label.setStyleSheet("color: #ccddeeff; background: transparent; padding: 5px;")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._detail_label = QLabel("")
        self._detail_label.setFont(QFont("Consolas", 9))
        self._detail_label.setStyleSheet("color: #667788; background: transparent; padding: 2px 5px;")
        self._detail_label.setWordWrap(True)
        self._detail_label.setMaximumHeight(60)
        layout.addWidget(self._detail_label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        self._progress.setFixedHeight(22)
        self._progress.setStyleSheet("""
            QProgressBar {
                background: #111822;
                border: 1px solid #1a2535;
                border-radius: 11px;
                text-align: center;
                color: #ffffff;
                font-size: 10px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #606060, stop:0.5 #C0C0C0, stop:1 #606060);
                border-radius: 10px;
            }
        """)
        layout.addWidget(self._progress)

        self._log_frame = QFrame()
        self._log_frame.setStyleSheet("background: #0a0f18; border: 1px solid #1a2535; border-radius: 8px; padding: 8px;")
        self._log_frame.setMinimumHeight(120)
        self._log_frame.setMaximumHeight(160)
        log_layout = QVBoxLayout(self._log_frame)
        log_layout.setContentsMargins(10, 8, 10, 8)

        self._log_label = QLabel("")
        self._log_label.setFont(QFont("Consolas", 9))
        self._log_label.setStyleSheet("color: #8899aa; background: transparent;")
        self._log_label.setWordWrap(True)
        self._log_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        log_layout.addWidget(self._log_label)
        layout.addWidget(self._log_frame)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._skip_btn = QPushButton("Skip Optional")
        self._skip_btn.setFixedSize(140, 36)
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #8899aa;
                border: 1px solid #334455;
                border-radius: 8px;
                font-size: 11px;
            }
            QPushButton:hover { border: 1px solid #C0C0C0; color: #C0C0C0; }
        """)
        self._skip_btn.clicked.connect(self._skip_optional)
        self._skip_btn.hide()
        btn_layout.addWidget(self._skip_btn)

        self._action_btn = QPushButton("Start SONIC")
        self._action_btn.setFixedSize(160, 40)
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._action_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #333333, stop:0.5 #808080, stop:1 #333333);
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #444444, stop:0.5 #A0A0A0, stop:1 #444444); }
            QPushButton:disabled { background: #1a2535; color: #556677; }
        """)
        self._action_btn.clicked.connect(self._on_action)
        self._action_btn.setEnabled(False)
        btn_layout.addWidget(self._action_btn)

        layout.addLayout(btn_layout)

        self._log_lines = []

    def _add_log(self, msg: str):
        self._log_lines.append(msg)
        if len(self._log_lines) > 8:
            self._log_lines = self._log_lines[-8:]
        self._log_label.setText("\n".join(self._log_lines))

    def _start_detection(self):
        self._phase = "detecting"
        self._status_label.setText("Checking system requirements...")
        self._worker = WorkerThread(mode="detect")
        self._worker.progress.connect(self._on_progress)
        self._worker.requirement_check.connect(self._on_req_check)
        self._worker.all_done.connect(self._on_detection_done)
        self._worker.start()

    def _on_progress(self, msg: str, pct: int):
        self._progress.setValue(pct)
        self._detail_label.setText(msg)

    def _on_req_check(self, result: DepResult):
        self._results.append(result)
        icon = {
            Status.INSTALLED: "  [OK]",
            Status.MISSING: "  [!!]",
            Status.CHECK_FAILED: "  [??]",
        }.get(result.status, "  [--]")
        self._add_log(f"{icon} {result.name}: {result.message}")

    def _on_detection_done(self, success: bool, msg: str):
        if not success:
            self._status_label.setText(f"Detection failed: {msg}")
            self._action_btn.setText("Retry")
            self._action_btn.setEnabled(True)
            return

        required_missing = [r for r in self._results
                           if r.status == Status.MISSING and r.id in
                           ("mic_check", "speaker_check", "internet_check", "disk_space")]

        optional_missing = [r for r in self._results
                           if r.status == Status.MISSING and r.id in
                           ("playwright_chromium", "ffmpeg", "vlc", "opencode")]

        if required_missing:
            names = ", ".join(r.name for r in required_missing)
            self._status_label.setText(f"Required components missing: {names}")
            self._action_btn.setText("Fix & Continue")
            self._action_btn.setEnabled(True)
            self._add_log(f"MISSING REQUIRED: {names}")
        elif optional_missing:
            self._status_label.setText("All required components ready! Optional tools available below.")
            self._action_btn.setText("Start SONIC")
            self._action_btn.setEnabled(True)
            self._skip_btn.show()
            names = ", ".join(r.name for r in optional_missing)
            self._add_log(f"Optional available: {names}")
        else:
            self._status_label.setText("All systems ready!")
            self._action_btn.setText("Start SONIC")
            self._action_btn.setEnabled(True)
            self._add_log("All checks passed")

        self._progress.setValue(100)
        self._state.set_system_info({
            "os": str(self._results),
            "check_time": str(__import__("time").time())
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
            self._add_log("Please connect required hardware and try again")
            self._status_label.setText("Connect missing hardware and click Retry")
            self._action_btn.setText("Retry")
            self._phase = "done"
            return

        self._phase = "done"
        self._state.mark_completed()
        self.finished.emit()
