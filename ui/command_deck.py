"""SONIC AI — JARVIS Command Deck.

The ultimate cinematic dashboard. Every subsystem of the JARVIS brain is
plumbed into a single 1100×720 HUD:

    ┌──────────────────────────────────────────────────────────────────────────┐
    │ TOP HUD BAR:   [SONIC.JARVIS ONLINE]   time + world pulse vitals strip   │
    ├──────────────────────────────────┬───────────────────────────────────────┤
    │                                  │                                       │
    │      3D HOLOGRAPHIC ORB          │   LIVE TASK FEED                       │
    │      (audio reactive, stateful)  │   (routed actions + memories)         │
    │      + status text               │   (ambient suggestions)               │
    │                                  │                                       │
    ├──────────────────────────────────┴───────────────────────────────────────┤
    │                                                                          │
    │            ANIMATED NEURAL NETWORK VISUALIZATION                         │
    │            (firing neurons + signal propagation)                        │
    │                                                                          │
    ├──────────────────────────────────┬───────────────────────────────────────┤
    │  VOICE WAVEFORM                  │   SYSTEM HEALTH                        │
    │  (audio-reactive bars)           │   (CPU / RAM / disk / battery)        │
    │                                  │   (Self-Heal diagnostics)             │
    ├──────────────────────────────────┴───────────────────────────────────────┤
    │  CONSOLE: [input field]    [SEND]    voice biometric status               │
    └──────────────────────────────────────────────────────────────────────────┘

Public API:
    CommandDeck(parent=None)
    .brain() -> JarvisBrain
    .set_command_handler(fn)   # fn(command_text) -> response_text
    .show_deck()
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

# UTF-8 stdout (Windows cp1252 safety)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QLinearGradient, QRadialGradient, QPen, QBrush, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QLineEdit,
    QTextEdit, QGraphicsDropShadowEffect, QSizePolicy, QApplication, QDialog,
)

from apple_design import Tokens
from ui.holo_orb_3d import HoloOrb3D
from ui.neural_net_viz import NeuralNetViz
from ui.waveform_viz import WaveformViz
from core.jarvis_brain import JarvisBrain
from core.world_pulse import WorldPulse


# ═════════════════════════════════════════════════════════════════════════════
# Background painter (reuses backdrop idea but tuned for the deck)
# ═════════════════════════════════════════════════════════════════════════════

class _DeckBackdrop(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(40)

    def _on_tick(self):
        self._tick += 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        # Deep base
        p.fillRect(0, 0, w, h, QColor(2, 4, 10))
        # Atmosphere
        cx, cy = w / 2, h * 0.38
        bloom = QRadialGradient(cx, cy, max(w, h) * 0.7)
        bloom.setColorAt(0.0, QColor(20, 50, 100, 80))
        bloom.setColorAt(0.4, QColor(20, 10, 60, 40))
        bloom.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bloom))
        p.drawRect(0, 0, w, h)
        # Animated hex grid (sparse)
        import math
        hex_r = 26
        hex_w = hex_r * math.sqrt(3)
        hex_h = hex_r * 1.5
        p.setPen(QPen(QColor(0, 200, 255, 8), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        row = 0
        y = -hex_r
        while y < h + hex_r:
            x_offset = (hex_w / 2) if row % 2 else 0
            x = -hex_w
            while x < w + hex_w:
                pts = []
                for k in range(6):
                    ang = math.radians(60 * k + 30)
                    pts.append((x + x_offset + hex_r * math.cos(ang),
                                y + hex_r * math.sin(ang)))
                from PyQt6.QtGui import QPainterPath
                path = QPainterPath()
                path.moveTo(QPointF(pts[0][0], pts[0][1]))
                for px, py in pts[1:]:
                    path.lineTo(QPointF(px, py))
                path.closeSubpath()
                p.drawPath(path)
                x += hex_w
            row += 1
            y += hex_h
        # HUD corner brackets
        for sx, sy, dx1, dy1, dx2, dy2 in [
            (0, 0, 1, 0, 0, 1),
            (w, 0, -1, 0, 0, 1),
            (0, h, 1, 0, 0, -1),
            (w, h, -1, 0, 0, -1),
        ]:
            margin = 12
            x0 = sx + (-margin if sx > 0 else margin)
            y0 = sy + (-margin if sy > 0 else margin)
            pulse = (math.sin(self._tick * 0.04 + (sx + sy)) + 1) / 2
            alpha = 80 + int(40 * pulse)
            pen = QPen(QColor(0, 220, 255, alpha), 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(int(x0), int(y0),
                       int(x0 + dx1 * 22), int(y0 + dy1 * 22))
            p.drawLine(int(x0), int(y0),
                       int(x0 + dx2 * 22), int(y0 + dy2 * 22))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(0, 220, 255, alpha)))
            p.drawEllipse(QPointF(x0, y0), 2.4, 2.4)
        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# Vital strip
# ═════════════════════════════════════════════════════════════════════════════

class _VitalStrip(QWidget):
    """Compact horizontal strip showing CPU/RAM/Battery/Network."""

    def __init__(self, parent=None, pulse: WorldPulse | None = None):
        super().__init__(parent)
        self._pulse = pulse or WorldPulse()
        self.setFixedHeight(22)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self):
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        v = self._pulse.vitals()
        w = self.width()
        h = self.height()

        # Backdrop pill
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(255, 255, 255, 12))
        bg.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(0, 0, w, h, 6, 6)

        chips = []
        if v.get("cpu_pct") is not None:
            chips.append(("CPU", f"{v['cpu_pct']:.0f}%",
                          QColor(0, 220, 255)))
        if v.get("ram_pct") is not None:
            chips.append(("RAM", f"{v['ram_pct']:.0f}%",
                          QColor(170, 100, 255)))
        if v.get("battery_pct") is not None:
            chips.append(("BAT", f"{v['battery_pct']:.0f}%",
                          QColor(60, 230, 130)))
        if v.get("disk_pct") is not None:
            chips.append(("DSK", f"{v['disk_pct']:.0f}%",
                          QColor(255, 180, 80)))

        x = 8
        for label, value, color in chips:
            # Mini bar
            pct_val = 0.0
            try:
                pct_val = float(value.rstrip("%")) / 100
            except Exception:
                pct_val = 0.0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, 25)))
            p.drawRoundedRect(int(x), int(h * 0.4), 60, int(h * 0.35), 2, 2)
            p.setBrush(QBrush(color))
            p.drawRoundedRect(int(x), int(h * 0.4),
                                int(60 * pct_val), int(h * 0.35), 2, 2)
            # Label
            p.setPen(QColor(220, 230, 240, 200))
            p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            p.drawText(int(x + 66), int(h * 0.78), f"{label} {value}")
            x += 130
        # Time on the right
        p.setPen(QColor(0, 220, 255, 200))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        time_str = v.get("local_time", "")
        p.drawText(int(w - 12 - 70), int(h * 0.78), time_str)

        p.end()


# ═════════════════════════════════════════════════════════════════════════════
# Suggestion feed
# ═════════════════════════════════════════════════════════════════════════════

class _FeedPanel(QTextEdit):
    """Routed-action / suggestion / memory log feed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QTextEdit {{
                background: rgba(8, 14, 26, 200);
                border: 1px solid rgba(0, 200, 255, 60);
                border-radius: {Tokens.R_SM}px;
                color: {Tokens.TEXT_PRIMARY};
                font-family: {Tokens.FONT_MONO};
                font-size: 11px;
                padding: 8px;
            }}
        """)
        self._html_lines = []
        self._append_line("─" * 32, color="#6e7e94", bold=True)
        self._append_line("[JARVIS] Online. Awaiting directive.",
                          color="#00d9ff", bold=True)
        self._append_line("─" * 32, color="#6e7e94", bold=True)

    def _append_line(self, text: str, color: str = "#cad6e2", bold: bool = False):
        ts = datetime.now().strftime("%H:%M:%S")
        weight = "bold" if bold else "normal"
        line = (
            f'<div style="margin:2px 0;">'
            f'<span style="color:#4a5e75;">{ts}</span> '
            f'<span style="color:{color}; font-weight:{weight};">{text}</span>'
            f'</div>'
        )
        self._html_lines.append(line)
        self.setHtml("".join(self._html_lines[-200:]))
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def log_route(self, route_action: str, route_args: dict, response: str):
        self._append_line(f"ROUTED → {route_action.upper()}",
                          color="#00d9ff", bold=True)
        if route_args:
            args_str = ", ".join(f"{k}={v}" for k, v in route_args.items())
            self._append_line(f"  args: {args_str}", color="#9bb0c8")
        self._append_line(f"  ↳ {response[:200]}", color="#cad6e2")

    def log_suggestion(self, title: str, reason: str, confidence: float):
        pct = int(confidence * 100)
        self._append_line(f"SUGGEST [{pct:>3}%] {title}",
                          color="#b78bff", bold=True)
        self._append_line(f"  ↳ {reason[:200]}", color="#9bb0c8")

    def log_health(self, summary: str, details: list[str]):
        self._append_line(f"HEALTH  {summary}", color="#ff9f0a", bold=True)
        for d in details[:5]:
            self._append_line(f"  • {d}", color="#9bb0c8")

    def log_misc(self, text: str, color: str = "#cad6e2"):
        self._append_line(text, color=color)


# ═════════════════════════════════════════════════════════════════════════════
# Command Deck
# ═════════════════════════════════════════════════════════════════════════════

class CommandDeck(QWidget):
    """The cinematic JARVIS command deck."""

    console_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SONIC JARVIS — Command Deck")
        self.setFixedSize(1280, 800)
        self._brain = JarvisBrain()
        self._pulse = WorldPulse()
        self._command_handler = None
        self._build_ui()
        self._populate_initial_state()
        self._start_background_tasks()

    def brain(self) -> JarvisBrain:
        return self._brain

    def set_command_handler(self, fn):
        """Set the function that converts a command string to a response."""
        self._command_handler = fn

    def _build_ui(self):
        # Backdrop
        self._backdrop = _DeckBackdrop(self)
        self._backdrop.setGeometry(0, 0, self.width(), self.height())
        self._backdrop.lower()

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)

        # ── Top HUD bar ─────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        # Brand
        brand = QLabel("SONIC.JARVIS // COMMAND DECK")
        brand.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        brand.setStyleSheet(
            f"color: {Tokens.CYAN}; background: transparent; letter-spacing: 2px;"
        )
        top_bar.addWidget(brand)

        top_bar.addStretch()

        # Vital strip
        self._vital_strip = _VitalStrip(self, pulse=self._pulse)
        self._vital_strip.setMinimumWidth(620)
        top_bar.addWidget(self._vital_strip)

        root.addLayout(top_bar)

        # ── Mid row: orb (left) + feed (right) ──────────────────────────────
        mid_row = QHBoxLayout()
        mid_row.setSpacing(14)

        # Orb column
        orb_col = QVBoxLayout()
        orb_col.setSpacing(8)
        orb_card = QFrame()
        orb_card.setStyleSheet(
            "QFrame { background: rgba(8, 14, 26, 160); "
            "border: 1px solid rgba(0, 200, 255, 80); border-radius: 14px; }"
        )
        orb_card.setFixedSize(360, 360)
        orb_inner = QVBoxLayout(orb_card)
        orb_inner.setContentsMargins(10, 10, 10, 10)
        orb_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._orb = HoloOrb3D(self, size=320)
        self._orb.set_state("idle")
        self._orb.set_text("ONLINE")
        orb_inner.addWidget(self._orb)
        orb_col.addWidget(orb_card)

        # Status subtitle
        self._orb_subtitle = QLabel("STATE: IDLE  •  READY FOR DIRECTIVE")
        self._orb_subtitle.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._orb_subtitle.setStyleSheet(
            "color: #9bb0c8; background: transparent; letter-spacing: 1.5px;"
        )
        self._orb_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb_col.addWidget(self._orb_subtitle)

        # Memory + voice biometric stats
        self._memory_lbl = QLabel("MEMORY: 0  •  USERS: 0")
        self._memory_lbl.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self._memory_lbl.setStyleSheet(
            "color: #6e7e94; background: transparent; letter-spacing: 1.2px;"
        )
        self._memory_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orb_col.addWidget(self._memory_lbl)

        mid_row.addLayout(orb_col)

        # Feed column
        feed_col = QVBoxLayout()
        feed_lbl = QLabel("▌ LIVE TASK FEED")
        feed_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        feed_lbl.setStyleSheet(
            "color: #00d9ff; background: transparent; letter-spacing: 1.8px;"
        )
        feed_col.addWidget(feed_lbl)

        self._feed = _FeedPanel()
        feed_col.addWidget(self._feed, 1)
        mid_row.addLayout(feed_col, 1)

        root.addLayout(mid_row, 0)

        # ── Neural net visualization ─────────────────────────────────────────
        nn_lbl = QLabel("▌ NEURAL CORTEX")
        nn_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        nn_lbl.setStyleSheet(
            "color: #00d9ff; background: transparent; letter-spacing: 1.8px;"
        )
        root.addWidget(nn_lbl)

        nn_card = QFrame()
        nn_card.setStyleSheet(
            "QFrame { background: rgba(8, 14, 26, 140); "
            "border: 1px solid rgba(0, 200, 255, 60); border-radius: 12px; }"
        )
        nn_card.setFixedHeight(220)
        nn_inner = QVBoxLayout(nn_card)
        nn_inner.setContentsMargins(8, 8, 8, 8)
        self._nn_viz = NeuralNetViz(self, width=1200, height=200)
        nn_inner.addWidget(self._nn_viz)
        root.addWidget(nn_card)

        # ── Bottom row: waveform + health ────────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        wave_col = QVBoxLayout()
        wave_lbl = QLabel("▌ AUDIO CHANNEL")
        wave_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        wave_lbl.setStyleSheet(
            "color: #00d9ff; background: transparent; letter-spacing: 1.8px;"
        )
        wave_col.addWidget(wave_lbl)
        self._wave = WaveformViz(self, width=620, height=120, bars=32)
        wave_col.addWidget(self._wave)
        bottom_row.addLayout(wave_col, 1)

        health_col = QVBoxLayout()
        health_lbl = QLabel("▌ SYSTEM HEALTH")
        health_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        health_lbl.setStyleSheet(
            "color: #00d9ff; background: transparent; letter-spacing: 1.8px;"
        )
        health_col.addWidget(health_lbl)

        self._health_lbl = QLabel("Running diagnostics…")
        self._health_lbl.setFont(QFont("Consolas", 10))
        self._health_lbl.setStyleSheet(
            "color: #cad6e2; background: rgba(8, 14, 26, 140); "
            f"border: 1px solid rgba(0, 200, 255, 60); border-radius: {Tokens.R_SM}px; "
            "padding: 10px;"
        )
        self._health_lbl.setFixedHeight(120)
        self._health_lbl.setWordWrap(True)
        health_col.addWidget(self._health_lbl)
        bottom_row.addLayout(health_col, 1)

        root.addLayout(bottom_row, 0)

        # ── Console input ────────────────────────────────────────────────────
        console_lbl = QLabel("▌ DIRECTIVE CONSOLE")
        console_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        console_lbl.setStyleSheet(
            "color: #00d9ff; background: transparent; letter-spacing: 1.8px;"
        )
        root.addWidget(console_lbl)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Speak or type a directive — e.g. 'open chrome', 'what's on my screen?', 'remind me at 5pm to call mom'")
        self._input.setFont(QFont("Consolas", 12))
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(8, 14, 26, 200);
                border: 1px solid rgba(0, 200, 255, 80);
                border-radius: {Tokens.R_SM}px;
                color: {Tokens.TEXT_PRIMARY};
                padding: 10px;
                selection-background-color: rgba(0, 200, 255, 60);
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(0, 220, 255, 180);
            }}
        """)
        self._input.setFixedHeight(44)
        self._input.returnPressed.connect(self._on_submit)
        input_row.addWidget(self._input, 1)

        send_btn = QPushButton("EXECUTE")
        send_btn.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Tokens.CYAN};
                color: #001018;
                border: none;
                border-radius: {Tokens.R_SM}px;
                padding: 0 22px;
                font-weight: 800;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{ background: #2ee6ff; }}
            QPushButton:pressed {{ background: #00b8d9; }}
        """)
        send_btn.setFixedHeight(44)
        send_btn.setFixedWidth(140)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.clicked.connect(self._on_submit)
        input_row.addWidget(send_btn)

        root.addLayout(input_row)

    def _populate_initial_state(self):
        """Show what's already wired up at startup."""
        status = self._brain.status()
        for k, v in status.items():
            if k == "timestamp":
                continue
            avail = "✓" if v.get("available") else "○"
            self._feed.log_misc(f"  {avail} {k.upper()}", color="#6e7e94")

        # Seed a few memories so the system shows life
        self._brain.memory.remember("User is CEO of Atherion Labs", kind="fact", importance=0.95)
        self._brain.memory.remember("SONIC AI is the user's Jarvis-class desktop assistant",
                                     kind="project", importance=0.9)
        self._brain.memory.remember("User prefers Roman Urdu mixed with English in conversation",
                                     kind="preference", importance=0.85)
        self._brain.proactive.record_event("open_app", context={"focused_app": "code"})

    def _start_background_tasks(self):
        # Run initial health check after 1.5s
        QTimer.singleShot(1500, self._run_health_check)
        # Refresh health every 30s
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._run_health_check)
        self._health_timer.start(30000)
        # Drive orb pulse with simulated audio activity (rotates states)
        self._orb_timer = QTimer(self)
        self._orb_timer.timeout.connect(self._cycle_orb_demo)
        self._orb_timer.start(4000)
        # Drive NN activity with vitals
        self._nn_timer = QTimer(self)
        self._nn_timer.timeout.connect(self._drive_nn)
        self._nn_timer.start(500)
        # Drive waveform with simulated amplitude
        self._wave_timer = QTimer(self)
        self._wave_timer.timeout.connect(self._drive_wave)
        self._wave_timer.start(150)
        # Memory + biometric stats refresh
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(2500)

    def _cycle_orb_demo(self):
        """Cycle through orb states for visual demo."""
        states = ["idle", "listening", "thinking", "speaking", "ready"]
        idx = (states.index(self._orb._state) + 1) % len(states) if self._orb._state in states else 0
        new_state = states[idx]
        self._orb.set_state(new_state)
        self._orb.set_text(new_state.upper())
        self._orb_subtitle.setText(f"STATE: {new_state.upper()}  •  SIMULATED INPUT")

    def _drive_nn(self):
        # Activity proportional to CPU usage
        try:
            v = self._pulse.vitals()
            cpu = v.get("cpu_pct", 30) or 30
            self._nn_viz.set_activity(min(1.0, cpu / 100.0 + 0.2))
        except Exception:
            self._nn_viz.set_activity(0.4)

    def _drive_wave(self):
        import random
        # Simulate audio level fluctuating
        base = 0.15 + random.random() * 0.6
        self._wave.push_sample(base)

    def _refresh_stats(self):
        mem_stats = self._brain.memory.get_stats()
        vp_stats = self._brain.memory.get_stats()
        users = self._brain.memory.count()
        try:
            from core.voice_biometric import VoiceBiometric
            vb = VoiceBiometric()
            users_enrolled = len(vb.list_users())
        except Exception:
            users_enrolled = 0
        self._memory_lbl.setText(
            f"MEMORY: {mem_stats['total']}  •  PATTERNS: {self._brain.proactive.count_events()}  •  USERS: {users_enrolled}"
        )

    def _run_health_check(self):
        report = self._brain.healer.full_health_check(auto_repair=True)
        lines = []
        crit = sum(1 for d in report.diagnostics if d.severity == "critical")
        warn = sum(1 for d in report.diagnostics if d.severity == "warning")
        ok = sum(1 for d in report.diagnostics if d.severity == "ok")
        summary = f"OVERALL: {report.overall.upper()}  •  {crit} critical  •  {warn} warning  •  {ok} ok  •  {report.duration_ms:.0f}ms"
        details = []
        for d in report.diagnostics:
            if d.severity in ("warning", "critical"):
                details.append(f"[{d.severity.upper()}] {d.title} — {d.detail}")
        for d in report.diagnostics[:3]:
            if d.severity == "ok":
                details.append(f"[OK] {d.title}")
        if report.auto_repairs:
            details.append(f"AUTO-REPAIRED: {len(report.auto_repairs)}")
        self._health_lbl.setText(summary + "\n" + "\n".join(details[:4]))
        self._feed.log_health(report.summary(), details)

    def _on_submit(self):
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self._feed.log_misc(f">>> {text}", color="#ffffff")
        self._orb.set_state("thinking")
        self._orb.set_text("PROCESSING")
        self._orb_subtitle.setText("STATE: THINKING  •  ROUTING…")
        self._nn_viz.set_activity(0.95)
        self._nn_viz.fire_at_layer(2)

        # Run brain.think in a worker so UI stays responsive
        QTimer.singleShot(50, lambda: self._execute_think(text))

    def _execute_think(self, text: str):
        try:
            result = self._brain.think(text, with_screen=False)
            self._feed.log_route(result.route.action, result.route.args, result.response)
            for s in result.suggestions[:2]:
                self._feed.log_suggestion(s.title, s.reason, s.confidence)
            # Speak the response (or print)
            self._brain.say(result.response)
            self._orb.set_state("speaking")
            self._orb.set_text("RESPONSE READY")
            self._orb_subtitle.setText(
                f"STATE: SPEAKING  •  {result.route.action.upper()}  •  {result.elapsed_ms:.0f}ms"
            )
            # Drive waveform with response amplitude
            import random
            for _ in range(8):
                self._wave.push_sample(0.5 + random.random() * 0.5)
        except Exception as e:
            self._feed.log_misc(f"ERROR: {e}", color="#ff453a")
            self._orb.set_state("error")
            self._orb.set_text("ERROR")
            self._orb_subtitle.setText("STATE: ERROR  •  SEE FEED")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_backdrop"):
            self._backdrop.setGeometry(0, 0, self.width(), self.height())


# ═════════════════════════════════════════════════════════════════════════════
# Demo launcher
# ═════════════════════════════════════════════════════════════════════════════

def show_deck_demo(grab_screenshot: bool = False, output_path: str | None = None):
    """Launch the deck in a Qt event loop. Optionally save a screenshot."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    deck = CommandDeck()
    deck.show()

    # Pre-fire a demo directive so the screenshot looks alive
    def _demo():
        deck._feed.log_misc("─ DEMO SEQUENCE INITIATED ─", color="#ff9f0a", bold=False)
        deck._input.setText("open chrome")
        deck._on_submit()
    QTimer.singleShot(800, _demo)

    if grab_screenshot:
        def _grab():
            deck._orb.set_state("ready")
            deck._orb.set_text("SYSTEM READY")
            deck._orb_subtitle.setText("STATE: READY  •  ALL SYSTEMS NOMINAL")
            pix = deck.grab()
            if output_path:
                pix.save(output_path, "PNG")
                print(f"[deck] screenshot saved → {output_path}")
            QTimer.singleShot(400, app.quit)
        QTimer.singleShot(4000, _grab)

    app.exec()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--shot", help="save screenshot to this path")
    args = p.parse_args()
    show_deck_demo(grab_screenshot=bool(args.shot),
                    output_path=args.shot)
