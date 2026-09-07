"""
SONIC Frontend Theme — Live Demo
Run: python demo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSizePolicy, QFrame,
)

from pyqt6_theme import (
    C, HU, qcol,
    HudPanel, HudHeader, HudButton, HudLineEdit, HudCanvas,
    SciGauge, AmbientBackdrop, SciFrame, SciEqualizer, HueWheel,
)


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SONIC — Frontend Theme Demo")
        self.setMinimumSize(1100, 750)
        self.resize(1100, 750)

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)

        self._backdrop = AmbientBackdrop(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── HEADER ──
        hdr = self._build_header()
        root.addWidget(hdr)

        # ── BODY ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # LEFT PANEL — nav + gauges
        left = self._build_left()
        body.addWidget(left, stretch=0)

        # CENTER — HUD canvas
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        self.hud = HudCanvas("", "SONIC")
        self.hud.speaking = False
        self.hud.state = "LISTENING"
        center_layout.addWidget(self.hud, stretch=1)

        # Right under HUD: color picker demo
        color_row = QHBoxLayout()
        color_row.setContentsMargins(20, 10, 20, 10)
        color_row.setSpacing(20)

        self._wheel = HueWheel(HU.GOLD)
        self._wheel.hue_committed.connect(self._on_color)
        color_row.addStretch()
        color_row.addWidget(self._wheel)

        wheel_info = QVBoxLayout()
        wheel_info.setSpacing(4)
        lbl = QLabel("DRAG TO CHANGE ACCENT COLOR")
        lbl.setFont(QFont("Courier New", 8))
        lbl.setStyleSheet(f"color: {HU.DIM}; background: transparent;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wheel_info.addWidget(lbl)

        self._color_preview = QLabel()
        self._color_preview.setFixedSize(40, 40)
        self._color_preview.setStyleSheet(
            f"background: {HU.GOLD}; border: 2px solid {HU.BORDER}; border-radius: 20px;"
        )
        preview_row = QHBoxLayout()
        preview_row.addStretch()
        preview_row.addWidget(self._color_preview)
        preview_row.addStretch()
        wheel_info.addLayout(preview_row)
        color_row.addLayout(wheel_info)
        color_row.addStretch()
        center_layout.addLayout(color_row)

        body.addLayout(center_layout, stretch=5)

        # RIGHT PANEL — log + status
        right = self._build_right()
        body.addWidget(right, stretch=0)

        root.addLayout(body, stretch=1)

        # ── COMMAND BAR ──
        cmd = self._build_cmd_bar()
        root.addWidget(cmd)

        # ── FOOTER ──
        foot = self._build_footer()
        root.addWidget(foot)

        # Timer for clock
        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Simulate audio pulse
        self._audio_t = 0.0
        self._audio_tmr = QTimer(self)
        self._audio_tmr.timeout.connect(self._pulse)
        self._audio_tmr.start(50)

    def _tick_clock(self):
        import time
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _pulse(self):
        import math
        self._audio_t += 0.08
        level = (math.sin(self._audio_t) * 0.5 + 0.5) * 0.4
        freq = (math.sin(self._audio_t * 1.7) * 0.5 + 0.5) * 0.6
        self.hud.audio_level = level
        self.hud.audio_freq = freq

    def _on_color(self, hex_color: str):
        self._color_preview.setStyleSheet(
            f"background: {hex_color}; border: 2px solid {HU.BORDER}; border-radius: 20px;"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        self._backdrop.setGeometry(cw.rect())

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #111114, stop:1 #070708);
            border-bottom: 1px solid {C.BORDER_B};
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_MED):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 8))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_badge("SONIC AI", C.PRI_DIM))
        lay.addSpacing(10)
        lay.addWidget(_badge("SONIC OS v2.0", HU.GOLD_D))
        lay.addStretch()

        title = QLabel("SONIC")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Orbitron", 19))
        title.setStyleSheet(f"color: {HU.TEXT}; background: transparent; letter-spacing: 3px;")
        lay.addWidget(title)
        lay.addStretch()

        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Orbitron", 14))
        self._clock_lbl.setStyleSheet(f"color: {HU.BRIGHT}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Courier New", 7))
        self._date_lbl.setStyleSheet(f"color: {HU.DIM}; background: transparent;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lay.addWidget(self._date_lbl)
        return w

    def _build_left(self) -> QWidget:
        w = HudPanel(cuts=[("tl", 12), ("tr", 12), ("bl", 12), ("br", 12)],
                     border=HU.BORDER, fill=HU.FILL, glow=True, marks={"tl": "M", "br": "M"})
        w.setFixedWidth(160)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(9, 10, 9, 10)
        lay.setSpacing(4)

        nav_hdr = HudHeader("NAVIGATION", mark="M", color=HU.BRIGHT)
        lay.addWidget(nav_hdr)
        lay.addSpacing(2)

        nav_items = ["Home", "Chat", "Voice", "Memory", "Settings"]
        for i, label in enumerate(nav_items):
            btn = HudButton(label,
                            cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
                            border=HU.BORDER, fill=HU.FILL2, color=HU.BRIGHT,
                            font_size=7, marks={"tr": ">"},
                            icon_color=HU.DIM, icon_size=14)
            btn.setFixedHeight(28)
            if i == 0:
                btn.set_theme(border=HU.BRIGHT, fill=HU.FILL2, color=HU.GOLD)
            lay.addWidget(btn)

        lay.addSpacing(4)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {HU.BORDER}; max-height: 1px;")
        lay.addWidget(sep)
        lay.addSpacing(2)

        hdr = HudHeader("SYS MONITOR", mark="M")
        lay.addWidget(hdr)
        lay.addSpacing(2)

        self._gauge_cpu = SciGauge("CPU", C.PRI)
        self._gauge_mem = SciGauge("MEM", C.PRI_DIM)
        self._gauge_gpu = SciGauge("GPU", "#00e5ff")
        self._gauge_net = SciGauge("NET", C.PRI_DIM)
        for g in [self._gauge_cpu, self._gauge_mem, self._gauge_gpu, self._gauge_net]:
            lay.addWidget(g)

        # Animate gauges
        self._gauge_t = 0.0
        self._gauge_tmr = QTimer(self)
        self._gauge_tmr.timeout.connect(self._anim_gauges)
        self._gauge_tmr.start(2000)
        self._anim_gauges()

        lay.addStretch(1)
        return w

    def _anim_gauges(self):
        import math, random
        self._gauge_t += 1.0
        t = self._gauge_t
        cpu = 30 + 25 * math.sin(t * 0.3) + random.uniform(-5, 5)
        mem = 55 + 10 * math.sin(t * 0.2)
        gpu = 45 + 20 * math.sin(t * 0.4)
        net = 20 + 15 * math.sin(t * 0.5)
        self._gauge_cpu.set_value(max(0, min(100, cpu)), f"{cpu:.0f}%")
        self._gauge_mem.set_value(max(0, min(100, mem)), f"{mem:.0f}%")
        self._gauge_gpu.set_value(max(0, min(100, gpu)), f"{gpu:.0f}%")
        self._gauge_net.set_value(max(0, min(100, net)), f"{net:.0f}%")

    def _build_right(self) -> QWidget:
        w = HudPanel(cuts=[("tl", 12), ("tr", 12), ("bl", 12), ("br", 12)],
                     border=HU.BORDER, fill=HU.FILL, glow=True, marks={"tr": "M", "bl": "M"})
        w.setFixedWidth(340)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        lay.addWidget(HudHeader("ACTIVITY LOG", mark=">"))

        log_box = HudPanel(cuts=[("tl", 8), ("tr", 8), ("bl", 8), ("br", 8)],
                           border=HU.BORDER, fill=HU.FILL)
        log_lay = QVBoxLayout(log_box)
        log_lay.setContentsMargins(6, 6, 6, 6)
        log_text = QLabel(
            "SYS: Theme loaded successfully\n"
            "SYS: Particle sphere active\n"
            "SYS: Accent color: #00e5ff\n"
            "SYS: Font: Orbitron\n"
            "SONIC: All systems nominal\n"
            "YOU: Show me the theme\n"
            "SONIC: Here it is. Drag the wheel\n"
            "       to change accent color."
        )
        log_text.setFont(QFont("Courier New", 9))
        log_text.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        log_text.setWordWrap(True)
        log_lay.addWidget(log_text)
        lay.addWidget(log_box, stretch=1)

        lay.addWidget(HudHeader("STATUS", mark=">"))
        status_box = HudPanel(cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                              border=HU.BORDER, fill=HU.FILL2, marks={"tl": "o"})
        srow = QHBoxLayout(status_box)
        srow.setContentsMargins(10, 3, 10, 3)
        srow.setSpacing(8)
        st = QLabel("SYSTEM NOMINAL")
        st.setFont(QFont("Courier New", 7))
        st.setStyleSheet(f"color: {HU.GREEN}; background: transparent;")
        srow.addWidget(st)
        srow.addStretch()
        sst = QLabel("SESS: ACTIVE")
        sst.setFont(QFont("Courier New", 6))
        sst.setStyleSheet(f"color: {HU.DIM}; background: transparent;")
        srow.addWidget(sst)
        lay.addWidget(status_box)
        lay.addStretch()
        return w

    def _build_cmd_bar(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {HU.FILL2}, stop:1 {HU.FILL});
            border-top: 1px solid {HU.BORDER};
        """)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(12, 6, 12, 6)
        outer.setSpacing(5)

        # Mode buttons
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addStretch()
        for i, label in enumerate(["Chat Mode", "Voice Mode", "Auto Mode"]):
            btn = HudButton(label,
                            cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
            btn.setFixedSize(138, 26)
            if i == 0:
                btn.set_theme(border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT)
            mode_row.addWidget(btn)
        mode_row.addStretch()
        outer.addLayout(mode_row)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(6)
        inp = HudLineEdit()
        inp.setPlaceholderText("Message SONIC...")
        inp.setFont(QFont("Courier New", 9))
        inp.setFixedHeight(36)
        input_row.addWidget(inp, stretch=1)

        send = HudButton("SEND",
                         cuts=[("tl", 8), ("tr", 8), ("bl", 8), ("br", 8)],
                         border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=8)
        send.setFixedSize(104, 36)
        input_row.addWidget(send)
        outer.addLayout(input_row)

        # Quick actions
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_row.addStretch()
        for label in ["Web Search", "Code", "Summarize", "Create Image"]:
            btn = HudButton(label,
                            cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
            btn.setFixedSize(122, 24)
            quick_row.addWidget(btn)
        quick_row.addStretch()
        outer.addLayout(quick_row)

        return w

    def _build_footer(self) -> QWidget:
        w = HudPanel(cuts=[("tl", 0), ("tr", 0), ("bl", 6), ("br", 6)],
                     border=HU.BORDER, fill=HU.FILL, glow=False)
        w.setFixedHeight(22)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=HU.DIM):
            l = QLabel(txt)
            l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("ONLINE", HU.GREEN))
        lay.addSpacing(10)
        lay.addWidget(_fl("[F4] Mute"))
        lay.addWidget(_fl("[F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("SONIC AI"))
        lay.addWidget(_fl("CORE v2.0", HU.GOLD_D))
        return w


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = DemoWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
