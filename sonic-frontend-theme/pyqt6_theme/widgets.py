"""
SONIC AI — Premium Widget System

Platinum-black material design. Cyan = intelligent status only.
"Less interface. More intelligence."
"""

from __future__ import annotations
import math
import random
import numpy as np

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QRectF, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QFont, QFontDatabase, QFontMetrics,
    QIcon, QLinearGradient, QPalette, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF, QRadialGradient, QRegion,
)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .theme import C, HU, qcol, DEFAULT_UI_COLOR
from .icons import svg_pixmap

# ── Font ────────────────────────────────────────────────────────────────────
_FONT_REGISTERED = False

def _font(size: int, bold: bool = False) -> QFont:
    global _FONT_REGISTERED
    if not _FONT_REGISTERED:
        _FONT_REGISTERED = True
        try:
            from pathlib import Path
            _fp = Path(__file__).resolve().parent.parent / "config" / "fonts" / "Orbitron[wght].ttf"
            if _fp.exists():
                QFontDatabase.addApplicationFont(str(_fp))
        except Exception:
            pass
    f = QFont("Orbitron", max(6, int(size)))
    if bold:
        f.setWeight(QFont.Weight.Bold)
    return f


# ── Hex grid cache ──────────────────────────────────────────────────────────
_HEX_CACHE = {}

def _hex_path(cx: float, cy: float, r: float) -> QPainterPath:
    key = (int(cx), int(cy), int(r))
    if key in _HEX_CACHE:
        return _HEX_CACHE[key]
    path = QPainterPath()
    for i in range(6):
        a = math.radians(60 * i - 30)
        px = cx + r * math.cos(a)
        py = cy + r * math.sin(a)
        if i == 0:
            path.moveTo(px, py)
        else:
            path.lineTo(px, py)
    path.closeSubpath()
    _HEX_CACHE[key] = path
    return path


# ── Path helpers ────────────────────────────────────────────────────────────
def _ang_path(w: float, h: float, cuts) -> QPainterPath:
    cs = {"tl": 0, "tr": 0, "br": 0, "bl": 0}
    for corner, size in (cuts or []):
        if corner in cs:
            cs[corner] = max(0, int(size))
    path = QPainterPath()
    path.moveTo(0, cs["tl"])
    path.lineTo(cs["tl"], 0)
    path.lineTo(w - cs["tr"], 0)
    path.lineTo(w, cs["tr"])
    path.lineTo(w, h - cs["br"])
    path.lineTo(w - cs["br"], h)
    path.lineTo(cs["bl"], h)
    path.lineTo(0, h - cs["bl"])
    path.closeSubpath()
    return path


# ── Premium surface painting ────────────────────────────────────────────────

def _paint_marks(p: QPainter, W: float, H: float, marks: dict, sym_size: int = 7):
    if not marks:
        return
    p.setFont(_font(sym_size, True))
    for corner, sym in marks.items():
        if corner == "tl":
            x, y = 6, 8
        elif corner == "tr":
            x, y = W - 6, 8
        elif corner == "br":
            x, y = W - 6, H - 6
        elif corner == "bl":
            x, y = 6, H - 6
        else:
            continue
        p.setPen(QPen(qcol(HU.TEXT, 80), 1))
        p.drawText(QPointF(x, y), sym)


def _paint_ang_border(p: QPainter, path: QPainterPath, border: QColor, hover: bool = False):
    """2-layer precision border — core + subtle highlight."""
    p.setBrush(Qt.BrushStyle.NoBrush)
    b = QColor(border)
    if hover:
        b = b.lighter(120)
    r, g, bv = b.red(), b.green(), b.blue()
    # Core line
    p.setPen(QPen(QColor(r, g, bv, 80), 0.8))
    p.drawPath(path)
    # Highlight edge
    p.setPen(QPen(QColor(min(255, r + 30), min(255, g + 30), min(255, bv + 30), 25), 0.5))
    p.drawPath(path)


def _paint_gradient_fill(p: QPainter, path: QPainterPath, fill: QColor, W: float, H: float):
    """Subtle vertical gradient — premium material depth."""
    grad = QLinearGradient(0, 0, 0, H)
    base = QColor(fill)
    top = base.lighter(110)
    mid = base
    dark = QColor(max(0, base.red() - 6), max(0, base.green() - 6), max(0, base.blue() - 6), base.alpha())
    shadow = QColor(max(0, base.red() - 12), max(0, base.green() - 12), max(0, base.blue() - 12), base.alpha())
    grad.setColorAt(0.0, top)
    grad.setColorAt(0.3, mid)
    grad.setColorAt(0.75, dark)
    grad.setColorAt(1.0, shadow)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawPath(path)


def _paint_inner_glow(p: QPainter, path: QPainterPath, W: float, H: float, color: QColor, intensity: float = 0.08):
    """Single center glow — restrained, premium."""
    g = QRadialGradient(W / 2, H / 2, max(W, H) * 0.5)
    c = QColor(color)
    c.setAlphaF(min(intensity, 0.15))
    g.setColorAt(0.0, c)
    g.setColorAt(0.5, QColor(c.red(), c.green(), c.blue(), int(c.alpha() * 0.4)))
    g.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setBrush(QBrush(g))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)


def _paint_top_edge(p: QPainter, W: float, H: float, color: QColor, thickness: int = 1):
    """Top-edge highlight — fades at edges."""
    grad = QLinearGradient(0, 0, W, 0)
    c = QColor(color)
    grad.setColorAt(0.0, QColor(c.red(), c.green(), c.blue(), 0))
    grad.setColorAt(0.2, QColor(c.red(), c.green(), c.blue(), 40))
    grad.setColorAt(0.8, QColor(c.red(), c.green(), c.blue(), 40))
    grad.setColorAt(1.0, QColor(c.red(), c.green(), c.blue(), 0))
    p.setPen(QPen(QBrush(grad), thickness))
    p.drawLine(QPointF(3, 0), QPointF(W - 3, 0))


def _paint_hex_pattern(p: QPainter, W: float, H: float, color: QColor, spacing: int = 70, alpha: int = 2):
    """Ultra-subtle computational grid — barely visible."""
    hr = spacing * 0.48
    rows = int(H / (spacing * 0.866)) + 2
    cols = int(W / spacing) + 2
    gc = QColor(color)
    gc.setAlpha(alpha)
    p.setPen(QPen(gc, 0.2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for row in range(rows):
        for col in range(cols):
            cx = col * spacing + (spacing / 2 if row % 2 else 0)
            cy = row * spacing * 0.866
            if -spacing < cx < W + spacing and -spacing < cy < H + spacing:
                hex_p = _hex_path(cx, cy, hr)
                p.drawPath(hex_p)


# ── HudPanel ────────────────────────────────────────────────────────────────

class HudPanel(QWidget):
    """Premium glass panel — metallic gradient, precision borders."""

    def __init__(self, parent=None, *, cuts=None, border=HU.BORDER, fill=HU.FILL,
                 glow=True, text="", text_color=HU.GOLD, marks=None,
                 font_size=7, align="l"):
        super().__init__(parent)
        self._cuts = cuts
        self._border = qcol(border)
        self._fill = qcol(fill)
        self._glow = glow
        self._text = text
        self._text_color = qcol(text_color)
        self._marks = marks or {}
        self._fs = font_size
        self._align = align
        self._tick = 0.0
        self._breath = 0.0
        self.setMinimumHeight(20)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(120)

    def _step(self):
        self._tick += 0.025
        self._breath = (math.sin(self._tick * 0.6) + 1.0) * 0.5
        self.update()

    def set_text(self, text: str):
        self._text = text
        self.update()

    def set_text_color(self, color: str):
        self._text_color = qcol(color)
        self.update()

    def set_marks(self, marks: dict):
        self._marks = marks or {}
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if W < 2 or H < 2:
            return
        path = _ang_path(W, H, self._cuts)
        _paint_gradient_fill(p, path, self._fill, W, H)
        if self._glow:
            intensity = 0.02 + self._breath * 0.02
            _paint_inner_glow(p, path, W, H, qcol(HU.METALLIC), intensity)
        p.setClipPath(path)
        _paint_top_edge(p, W, H, self._border)
        p.setClipping(False)
        _paint_ang_border(p, path, self._border)
        _paint_marks(p, W, H, self._marks)
        if self._text:
            p.setFont(_font(self._fs, True))
            p.setPen(QPen(self._text_color, 1))
            flag = Qt.AlignmentFlag.AlignVCenter
            flag |= Qt.AlignmentFlag.AlignLeft if self._align == "l" else Qt.AlignmentFlag.AlignCenter
            p.drawText(QRectF(8, 0, W - 16, H), flag, self._text)


# ── HudHeader ───────────────────────────────────────────────────────────────

class HudHeader(HudPanel):
    """Section header — clean platinum text, minimal."""

    def __init__(self, text, *, cuts=None, mark="", color=HU.GOLD, font_size=7):
        cuts = cuts if cuts is not None else []
        super().__init__(
            text=text, cuts=cuts, border=HU.BORDER, fill=HU.FILL, glow=False,
            text_color=color, marks={"tr": mark} if mark else {}, font_size=font_size, align="l",
        )
        self.setFixedHeight(22)


# ── HudButton ───────────────────────────────────────────────────────────────

class HudButton(QPushButton):
    """Precision button — subtle metallic surface, tactile feedback."""

    def __init__(self, text="", *, cuts=None, border=HU.BORDER, fill=HU.FILL,
                 color=HU.GOLD, marks=None, font_size=8, icon=None,
                 icon_color=None, icon_size=13):
        super().__init__(text)
        self._cuts = cuts
        self._border = qcol(border)
        self._fill = qcol(fill)
        self._color = qcol(color)
        self._marks = marks or {}
        self._fs = font_size
        self._icon = icon
        self._icon_color = icon_color or color
        self._icon_size = icon_size
        self._tick = 0.0
        self._energy = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(50)

    def _step(self):
        self._tick += 0.05
        if self._energy > 0.01:
            self._energy *= 0.85
        self.update()

    def set_icon(self, icon, color=None, px=None):
        self._icon = icon
        if color:
            self._icon_color = color
        if px:
            self._icon_size = px
        self.update()

    def set_theme(self, *, border=None, fill=None, color=None):
        if border:
            self._border = qcol(border)
        if fill:
            self._fill = qcol(fill)
        if color:
            self._color = qcol(color)
        self.update()

    def mousePressEvent(self, e):
        self._energy = 1.0
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if W < 2 or H < 2:
            return
        hover = self.underMouse()
        down = self.isDown()
        checked = self.isChecked()
        path = _ang_path(W, H, self._cuts)
        fill = QColor(self._fill)
        if hover:
            fill = fill.lighter(115)
        if down:
            fill = fill.lighter(125)
        _paint_gradient_fill(p, path, fill, W, H)
        if self._energy > 0.02:
            _paint_inner_glow(p, path, W, H, self._border, 0.10 * self._energy)
        if hover and not down:
            _paint_inner_glow(p, path, W, H, self._border, 0.05)
        _paint_ang_border(p, path, self._border, hover)
        _paint_marks(p, W, H, self._marks)
        if checked:
            p.setPen(QPen(qcol(HU.GREEN, 140), 1.5))
            p.drawLine(QPointF(6, H - 1), QPointF(W - 6, H - 1))
        col = QColor(self._color)
        if hover:
            col = col.lighter(110)
        if down:
            col = col.lighter(120)
        if checked:
            col = qcol(HU.GREEN)
        has_icon = bool(self._icon and self._icon in _ICON_PATHS)
        if has_icon:
            pm = svg_pixmap(self._icon, col.name(), self._icon_size)
            if self.text():
                ix = (H - pm.height()) / 2.0
                p.drawPixmap(QPointF(6, ix), pm)
                p.setPen(QPen(col, 1))
                p.setFont(_font(self._fs, True))
                p.drawText(QRectF(self._icon_size + 10, 0, W - self._icon_size - 16, H),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                           self.text())
            else:
                p.drawPixmap(QPointF((W - pm.width()) / 2.0, (H - pm.height()) / 2.0), pm)
        else:
            p.setPen(QPen(col, 1))
            p.setFont(_font(self._fs, True))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


# ── HudLineEdit ─────────────────────────────────────────────────────────────

class HudLineEdit(QLineEdit):
    """Premium command input — clean focus, platinum accent."""

    def __init__(self, parent=None, *, cuts=None, border=HU.BORDER, prompt="\u25b8"):
        super().__init__(parent)
        self._cuts = cuts if cuts is not None else [("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)]
        self._border = qcol(border)
        self._prompt = prompt
        self._glow = 0.0
        self._tick = 0.0
        self._scan_x = 0.0
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.PlaceholderText, qcol(HU.DIM))
        pal.setColor(QPalette.ColorRole.Text, qcol(HU.TEXT))
        pal.setColor(QPalette.ColorRole.Highlight, qcol(HU.GLOW))
        self.setPalette(pal)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none; padding-left: 24px; }"
        )
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._tick_fn)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._timer.start()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._timer.start()

    def _tick_fn(self):
        target = 1.0 if self.hasFocus() else 0.0
        self._glow += (target - self._glow) * 0.08
        if abs(target - self._glow) < 0.005:
            self._glow = target
        self._tick += 0.05
        if self._glow > 0.1:
            self._scan_x = (self._scan_x + 1.5) % (self.width() + 40)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        if W > 2 and H > 2:
            path = _ang_path(W, H, self._cuts)
            fill = QColor(HU.FILL)
            if self._glow > 0.02:
                f2 = qcol(HU.FILL2)
                fill = QColor(
                    int(fill.red() + (f2.red() - fill.red()) * self._glow),
                    int(fill.green() + (f2.green() - fill.green()) * self._glow),
                    int(fill.blue() + (f2.blue() - fill.blue()) * self._glow),
                )
            _paint_gradient_fill(p, path, fill, W, H)
            if self._glow > 0.02:
                _paint_inner_glow(p, path, W, H, self._border, 0.06 * self._glow)
                # Subtle platinum focus border
                focus_col = QColor(qcol(HU.METALLIC))
                focus_col.setAlpha(int(60 * self._glow))
                p.setPen(QPen(focus_col, 0.8))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                # Thin scan line
                if self._scan_x > 0 and self._scan_x < W:
                    scan_col = QColor(qcol(HU.METALLIC, int(12 * self._glow)))
                    p.setPen(QPen(scan_col, 0.5))
                    p.drawLine(QPointF(self._scan_x, 2), QPointF(self._scan_x, H - 2))
            _paint_ang_border(p, path, self._border, hover=self.underMouse())
            # Prompt symbol
            f = _font(9, True)
            p.setPen(QPen(qcol(HU.DIM, int(50 + 60 * self._glow)), 1))
            p.setFont(f)
            fm = QFontMetrics(f)
            p.drawText(QPointF(9, (H - fm.height()) / 2 + fm.ascent()), self._prompt)
        super().paintEvent(e)


# ── HudCanvas (AI Consciousness Core) ───────────────────────────────────────

class HudCanvas(QWidget):
    """Premium AI Core — layered consciousness visualization.

    Visual layers:
    1. Deep void background
    2. Soft platinum ambient glow
    3. Ultra-subtle hex grid texture
    4. Ambient micro-particles (slow drift)
    5. Plasma aura (state + audio reactive)
    6. Concentric energy rings (audio reactive)
    7. 3D particle sphere (state-driven color, NO size expansion)
    8. Status chip + minimal corner accents
    """

    _N = 2400
    _PARTICLE_SIZE = 0.6
    _ROTATION_SPEED = 0.18
    _TILT_X = 15.0
    _SPHERE_RADIUS = 2.25
    _FOV_DEG = 45.0
    _CAM_DIST = 9.0

    _PLATINUM = (0.82, 0.84, 0.88)
    _GLOW_CORE = (0.60, 0.62, 0.66)
    _BG = QColor(5, 7, 10)

    def __init__(self, face_path: str = "", assistant_name: str = "SONIC", parent=None,
                 viz_manager=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.muted = False
        self.speaking = False
        self.state = "INITIALISING"
        self._assistant_name = assistant_name
        self._audio_level = 0.0
        self._audio_freq = 0.0

        self._viz_manager = viz_manager
        self._sonic_live = None

        self._tick = 0
        self._blink = True
        self._blink_tick = 0
        self._smooth_audio = 0.0
        self._smooth_freq = 0.0
        self._peak_audio = 0.0

        # Ambient particles — minimal, slow
        self._particles = []
        for _ in range(14):
            self._particles.append({
                "x": random.random(),
                "y": random.random(),
                "vx": (random.random() - 0.5) * 0.0006,
                "vy": (random.random() - 0.5) * 0.0004,
                "size": random.uniform(0.4, 1.0),
                "alpha": random.randint(8, 28),
                "phase": random.random() * math.pi * 2,
            })

        # Fibonacci sphere
        phi = math.pi * (math.sqrt(5.0) - 1.0)
        i_arr = np.arange(self._N, dtype=np.float64)
        y = 1.0 - (i_arr / (self._N - 1)) * 2.0
        r_at_y = np.sqrt(np.clip(1.0 - y * y, 0.0, 1.0))
        theta = phi * i_arr
        pts = np.stack([np.cos(theta) * r_at_y, y, np.sin(theta) * r_at_y], axis=1)
        rng = np.random.default_rng(42)
        jitter = rng.normal(0.0, 0.010, pts.shape)
        pts = pts + jitter
        norms = np.linalg.norm(pts, axis=1, keepdims=True)
        norms = np.where(norms < 1e-6, 1e-6, norms)
        pts = pts / norms
        self._base = pts * self._SPHERE_RADIUS

        self._angle_y = 0.0
        self._angle_x = self._TILT_X

        # Per-particle noise for audio-reactive displacement
        rng2 = np.random.default_rng(99)
        self._particle_noise = rng2.uniform(0.0, 1.0, self._N)
        self._particle_phase = rng2.uniform(0.0, math.pi * 2, self._N)

        # Wave propagation phase
        self._wave_phase = 0.0

        # Idle render flag — paint once on first idle tick
        self._idle_rendered = False

        # Visualization state tracking
        self._viz_energy = 0.0          # smooth energy for particle displacement
        self._viz_state_blend = 0.0     # 0=idle, 1=fully active
        self._viz_turbulence = 0.0      # internal circulation factor
        self._state_prev = "IDLE"
        self._state_blend_timer = 0.0   # transition interpolation timer
        self._debug_force = 0.0         # forced deformation for testing (0=off, 0.0-1.0=forced)
        self._debug_log_counter = 0

        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(33)

    @property
    def audio_level(self):
        return self._audio_level

    @audio_level.setter
    def audio_level(self, v: float):
        self._audio_level = max(0.0, min(1.0, v))

    @property
    def audio_freq(self):
        return self._audio_freq

    @audio_freq.setter
    def audio_freq(self, v: float):
        self._audio_freq = max(0.0, min(1.0, v))

    def set_viz_manager(self, manager):
        self._viz_manager = manager

    def set_sonic_live(self, sonic_live):
        self._sonic_live = sonic_live

    def set_debug_force(self, value: float):
        """Force orb deformation for visual testing. 0=off, 0.0-1.0=forced energy."""
        self._debug_force = max(0.0, min(1.0, value))
        print(f"[ORB DEBUG] Force deformation set to {self._debug_force:.2f}")

    def _step(self):
        self._tick += 1

        # ── Audio input ──
        raw_mic = 0.0
        raw_freq = 0.0
        is_mic_active = False
        is_tts_active = False
        if self._sonic_live is not None:
            try:
                # Always read audio levels — mic while listening, TTS while speaking
                raw_mic = self._sonic_live._viz_level
                raw_freq = self._sonic_live._viz_freq
                self._audio_level = raw_mic
                self._audio_freq = raw_freq
            except Exception:
                pass

        # ── Viz manager (smoothed values + state) ──
        viz_mgr_connected = self._viz_manager is not None
        _lvl, _frq, state_label = 0.0, 0.0, "IDLE"
        if viz_mgr_connected:
            _lvl, _frq, state_label = self._viz_manager.tick()
            if not self.muted:
                self.state = state_label
                self.speaking = (state_label == "SPEAKING")
            self._smooth_audio = _lvl
            self._smooth_freq = _frq
            self._peak_audio = max(self._smooth_audio, self._peak_audio * 0.92)
            is_mic_active = self._viz_manager.is_mic_active
            is_tts_active = self._viz_manager.is_tts_active
            is_user_speaking = self._viz_manager.is_user_speaking
        else:
            target = self._audio_level
            cur = self._smooth_audio
            if target > cur:
                self._smooth_audio += (target - cur) * 0.40
            else:
                self._smooth_audio += (target - cur) * 0.06
            self._peak_audio = max(self._smooth_audio, self._peak_audio * 0.88)
            tgt_f = self._audio_freq
            cur_f = self._smooth_freq
            if tgt_f > cur_f:
                self._smooth_freq += (tgt_f - cur_f) * 0.35
            else:
                self._smooth_freq += (tgt_f - cur_f) * 0.06
            is_mic_active = False
            is_tts_active = False
            is_user_speaking = False

        # ── Check if there is REAL audio activity (TTS speaking OR user voice) ──
        # Also detect activity from raw _audio_level when no viz_manager
        _has_raw_audio = (self._audio_level > 0.02)
        has_audio = (
            self._debug_force > 0
            or is_tts_active
            or is_user_speaking
            or _has_raw_audio
        )

        # SLEEPING (offline) or IDLE (online, no audio): slow idle rotation only
        is_sleeping = (state_label == "SLEEPING")
        is_idle = (state_label == "IDLE")

        if not has_audio:
            # ── IDLE/SLEEPING: slow rotation only, no audio reactivity ──
            self._viz_energy = 0.0
            self._viz_turbulence = 0.0
            self._viz_state_blend = 1.0
            self._smooth_audio = 0.0
            self._smooth_freq = 0.0
            self._peak_audio = 0.0
            self.speaking = False

            # Rotation only (slow)
            state_speed = {
                "IDLE": 0.3, "SLEEPING": 0.3,
            }
            mult = state_speed.get(self.state, 0.3)
            speed = self._ROTATION_SPEED * mult
            self._angle_y += speed

            # No particle drift, no turbulence, no wave phase advance
            # Render once on first idle tick
            if not self._idle_rendered:
                self._idle_rendered = True
                self.update()
            return

        # ── ANIMATE: real audio activity (TTS or user voice) ──
        self._idle_rendered = False

        # Visualization energy (for particle displacement)
        if self._debug_force > 0:
            self._viz_energy = self._debug_force
        else:
            target_energy = self._peak_audio
            if target_energy > self._viz_energy:
                self._viz_energy += (target_energy - self._viz_energy) * 0.45
            else:
                self._viz_energy += (target_energy - self._viz_energy) * 0.08

        # Wave phase for surface propagation
        self._wave_phase += self._viz_energy * 0.15 + 0.012

        # State-specific turbulence
        state_turb = {
            "IDLE": 0.03, "LISTENING": 0.18, "THINKING": 0.55,
            "SPEAKING": 0.35, "PROCESSING": 0.50, "EXECUTING": 0.30,
            "SLEEPING": 0.02,
        }
        target_turb = state_turb.get(self.state, 0.03)
        if self.speaking:
            target_turb = max(target_turb, 0.35)
        self._viz_turbulence += (target_turb - self._viz_turbulence) * 0.12

        # State transition blend
        if self._state_prev != self.state:
            self._state_prev = self.state
            self._state_blend_timer = 0.0
        self._state_blend_timer = min(1.0, self._state_blend_timer + 0.08)
        self._viz_state_blend = self._state_blend_timer

        # Rotation (faster when audio active)
        state_speed = {
            "IDLE": 0.6, "LISTENING": 1.4, "THINKING": 2.0,
            "SPEAKING": 1.2, "PROCESSING": 1.8, "EXECUTING": 1.4,
            "SLEEPING": 0.3,
        }
        mult = state_speed.get(self.state, 0.8)
        if self.speaking:
            mult *= 1.3
        speed = self._ROTATION_SPEED * mult * (1.0 + self._smooth_freq * 0.10)
        self._angle_y += speed

        # Ambient micro-particles (only when audio active)
        for pt in self._particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]
            pt["phase"] += 0.012
            if pt["x"] < 0 or pt["x"] > 1:
                pt["vx"] *= -1
            if pt["y"] < 0 or pt["y"] > 1:
                pt["vy"] *= -1

        # Debug logging (every ~90 ticks = ~3s)
        self._debug_log_counter += 1
        if self._debug_log_counter >= 90:
            self._debug_log_counter = 0
            disp_max = self._viz_energy * 0.60
            print(f"[ORB DEBUG] State: {self.state} | VizMgr: {'ON' if viz_mgr_connected else 'OFF'} "
                  f"| Mic raw: {raw_mic:.3f} | Smooth: {self._smooth_audio:.3f} "
                  f"| Peak: {self._peak_audio:.3f} | Energy: {self._viz_energy:.3f} "
                  f"| Turb: {self._viz_turbulence:.3f} | Deform max: {disp_max:.3f} "
                  f"| Force: {self._debug_force:.2f}")

        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        cx, cy = W / 2, H / 2
        fw = min(W, H)

        viz = self._peak_audio ** 0.7

        # ── Layer 1: Deep void ──
        bg = QRadialGradient(W / 2, H * 0.4, max(W, H) * 0.85)
        bg.setColorAt(0.0, QColor(8, 10, 16))
        bg.setColorAt(0.3, QColor(5, 7, 12))
        bg.setColorAt(0.6, self._BG)
        bg.setColorAt(1.0, QColor(2, 3, 5))
        p.fillRect(self.rect(), QBrush(bg))

        # ── Layer 2: Ambient platinum glow ──
        ambient_r = fw * 0.40
        ambient = QRadialGradient(cx, cy, ambient_r)
        state_alpha = {
            "IDLE": 8, "LISTENING": 18, "THINKING": 14,
            "SPEAKING": 22, "PROCESSING": 16,
        }
        a_val = state_alpha.get(self.state, 8)
        a_val = int(a_val + viz * 30)
        if self.speaking:
            a_val = min(55, a_val + 12)
        # Platinum glow, not cyan
        ambient.setColorAt(0.0, QColor(160, 170, 185, a_val))
        ambient.setColorAt(0.4, QColor(100, 110, 130, int(a_val * 0.35)))
        ambient.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(ambient))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), ambient_r, ambient_r)

        # ── Layer 3: Ultra-subtle hex grid ──
        _paint_hex_pattern(p, W, H, qcol(HU.METALLIC), spacing=80, alpha=1)

        # ── Layer 4: Ambient micro-particles ──
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            px_x = pt["x"] * W
            px_y = pt["y"] * H
            pulse = 0.6 + 0.4 * math.sin(pt["phase"])
            a = int(pt["alpha"] * pulse)
            dist = math.sqrt((px_x - cx) ** 2 + (px_y - cy) ** 2) / (fw * 0.5)
            a = int(a * max(0.1, 1.0 - dist * 0.6))
            if a > 2:
                p.setBrush(QBrush(QColor(140, 150, 165, a)))
                p.drawEllipse(QPointF(px_x, px_y), pt["size"], pt["size"])

        focal = (H / 2) / math.tan(math.radians(self._FOV_DEG) / 2)
        cam = self._CAM_DIST
        orb_r = self._SPHERE_RADIUS * (focal / cam) * (1.0 + self._viz_energy * 0.06)

        # ── Layer 5: Plasma aura — platinum/cyan state-reactive ──
        aura_layers = {
            "IDLE": [(1.05, 6)],
            "LISTENING": [(1.07, 16), (1.12, 10)],
            "THINKING": [(1.07, 12), (1.12, 8)],
            "SPEAKING": [(1.07, 24), (1.12, 16), (1.18, 8)],
            "PROCESSING": [(1.07, 14), (1.12, 9)],
        }
        layers = aura_layers.get(self.state, [(1.05, 6)])
        if self.speaking:
            layers = [(1.07, 24), (1.12, 16), (1.18, 8)]

        for ai, (r_mult, base_a) in enumerate(layers):
            aura_r = orb_r * (r_mult + viz * 0.08)
            aura = QRadialGradient(QPointF(cx, cy), aura_r)
            a_adj = int(base_a + viz * 80)
            # Layer 0: platinum, Layer 1+: subtle cyan tint
            if ai == 0:
                aura.setColorAt(0.0, QColor(140, 155, 175, max(0, a_adj)))
                aura.setColorAt(0.4, QColor(80, 95, 120, max(0, int(a_adj * 0.4))))
            else:
                aura.setColorAt(0.0, QColor(0, 140, 180, max(0, int(a_adj * 0.7))))
                aura.setColorAt(0.4, QColor(0, 80, 120, max(0, int(a_adj * 0.3))))
            aura.setColorAt(1.0, QColor(5, 7, 10, 0))
            p.setBrush(QBrush(aura))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(cx, cy), aura_r, aura_r)

        # ── Layer 6: Concentric rings (audio active only) ──
        if viz > 0.01:
            for ri in range(3):
                rr = orb_r * (1.04 + ri * 0.03 + viz * 0.04)
                ra = int(45 * (1.0 - ri * 0.25) * viz)
                p.setPen(QPen(QColor(0, 130, 170, max(0, ra)), 0.7))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), rr, rr)

        # ── Layer 7: 3D particle sphere (audio-reactive) ──
        cos_x = math.cos(math.radians(self._angle_x))
        sin_x = math.sin(math.radians(self._angle_x))
        cos_y = math.cos(math.radians(self._angle_y))
        sin_y = math.sin(math.radians(self._angle_y))

        # Audio-reactive sphere radius — controlled expansion (capped)
        audio_radius_scale = 1.0 + self._viz_energy * 0.10
        current_radius = self._SPHERE_RADIUS * audio_radius_scale

        # Compute per-particle radial displacement
        t = self._tick * 0.01
        noise_val = self._particle_noise
        phase = self._particle_phase

        # Wave propagation: each particle gets a phase-shifted audio response
        wave = np.sin(phase * 3.0 + self._wave_phase + self._tick * 0.04)

        # Radial displacement: energy * noise * wave — visible deformation
        radial_push = self._viz_energy * 0.45 * (noise_val * 0.6 + wave * 0.4)
        # Internal circulation: state-driven particle drift
        circ_angle = phase + t * self._viz_turbulence * 4.0
        circ_push = self._viz_turbulence * 0.18 * np.sin(circ_angle)

        # Apply displacement to base positions
        pts = self._base.copy()
        norms = np.linalg.norm(pts, axis=1, keepdims=True)
        norms = np.where(norms < 1e-6, 1e-6, norms)
        unit_pts = pts / norms
        displaced = unit_pts * (current_radius + radial_push + circ_push)[:, np.newaxis]

        # ── PAINT DIAGNOSTICS (every ~90 frames) ──
        if self._debug_log_counter == 0 and self._tick > 10:
            _dn = np.linalg.norm(displaced, axis=1)
            _bn = np.linalg.norm(self._base, axis=1)
            print(f"[ORB RENDER] base_r: {_bn.min():.2f}-{_bn.max():.2f} "
                  f"| disp_r: {_dn.min():.2f}-{_dn.max():.2f} "
                  f"| delta: {_dn.mean() - _bn.mean():+.3f} "
                  f"| energy: {self._viz_energy:.3f}")

        # Rotate
        x1 = displaced[:, 0] * cos_y + displaced[:, 2] * sin_y
        z1 = -displaced[:, 0] * sin_y + displaced[:, 2] * cos_y
        y1 = displaced[:, 1]
        y2 = y1 * cos_x - z1 * sin_x
        z2 = y1 * sin_x + z1 * cos_x

        vz = cam - z2
        vz = np.where(vz < 0.1, 0.1, vz)
        sx = (x1 * focal) / vz + cx
        sy = -(y2 * focal) / vz + cy

        depth_factor = np.clip((z2 + current_radius) / (2 * current_radius), 0.0, 1.0)
        alpha_arr = np.clip(depth_factor, 0.08, 1.0) * 0.85

        order = np.argsort(vz)[::-1]
        base_r = max(0.5, self._PARTICLE_SIZE * (fw / 768) * 1.0)

        n_buckets = 20
        bucket_data = [[] for _ in range(n_buckets)]
        for idx in order:
            px_x, px_y = float(sx[idx]), float(sy[idx])
            if px_x < -10 or px_x > W + 10 or px_y < -10 or px_y > H + 10:
                continue
            df = depth_factor[idx]
            b = int(df * (n_buckets - 1) + 0.5)
            bucket_data[b].append((px_x, px_y, df, alpha_arr[idx]))

        # State-based particle color — platinum base, state tint
        if self.state in ("THINKING", "PROCESSING"):
            core_r, core_g, core_b = 0.65, 0.72, 0.82
        elif self.state == "LISTENING":
            core_r, core_g, core_b = 0.50, 0.72, 0.88
        elif self.speaking or self.state == "SPEAKING":
            core_r, core_g, core_b = 0.45, 0.78, 0.95
        else:
            core_r, core_g, core_b = self._GLOW_CORE

        audio_glow = self._smooth_audio * 0.7 + viz * 0.3
        p.setPen(Qt.PenStyle.NoPen)
        for b_idx in range(n_buckets):
            for px_x, px_y, df, al in bucket_data[b_idx]:
                # Platinum base, state tint
                if df > 0.6:
                    r_c = min(1.0, self._PLATINUM[0] * (1.0 + audio_glow * 0.5))
                    g_c = min(1.0, self._PLATINUM[1] * (1.0 + audio_glow * 0.5))
                    b_c = min(1.0, self._PLATINUM[2] * (1.0 + audio_glow * 0.6))
                else:
                    r_c = min(1.0, self._PLATINUM[0] * df + core_r * (1 - df) + audio_glow * 0.3)
                    g_c = min(1.0, self._PLATINUM[1] * df + core_g * (1 - df) + audio_glow * 0.35)
                    b_c = min(1.0, self._PLATINUM[2] * df + core_b * (1 - df) + audio_glow * 0.4)
                cr = int(r_c * 255)
                cg = int(g_c * 255)
                cb = int(b_c * 255)
                ca = int(min(255, al * 255 * (1.0 + viz * 0.5)))
                # Audio-reactive particle size: particles grow with energy
                pr = base_r * (0.5 + df * 0.5 + self._viz_energy * 0.45)
                p.setBrush(QBrush(QColor(cr, cg, cb, ca)))
                p.drawEllipse(QPointF(px_x, px_y), pr, pr)

        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── Layer 8: Minimal corner accents ──
        bl = int(fw * 0.028)
        hl, hr_ = cx - fw // 2, cx + fw // 2
        ht, hb = cy - fw // 2, cy + fw // 2
        p.setPen(QPen(qcol(HU.METALLIC, 50), 0.8))
        for bx, by, ddx, ddy in [(hl, ht, 1, 1), (hr_, ht, -1, 1), (hl, hb, 1, -1), (hr_, hb, -1, -1)]:
            p.drawLine(QPointF(bx, by), QPointF(bx + ddx * bl, by))
            p.drawLine(QPointF(bx, by), QPointF(bx, by + ddy * bl))

        # ── Status chip ──
        sy_chip = cy + fw * 0.40
        state_text = {
            "IDLE": "\u25cf  STANDBY", "LISTENING": "\u25c9  LISTENING",
            "THINKING": "\u25ce  THINKING", "SPEAKING": "\u25c9  SPEAKING",
            "PROCESSING": "\u2b21  PROCESSING", "EXECUTING": "\u25b8  EXECUTING",
            "ERROR": "\u2298  ERROR", "SLEEPING": "\u25cb  OFFLINE",
            "STARTING": "\u25ce  STARTING", "CONFIGURING": "\u25ce  CONFIGURING",
            "CONNECTING": "\u25ce  CONNECTING", "ONLINE": "\u25c9  ONLINE",
            "OFFLINE": "\u25cb  OFFLINE", "RECONNECTING": "\u25ce  RECONNECTING",
        }
        if self.muted:
            txt, col = "\u2298  MUTED", qcol(HU.RED)
        else:
            txt = state_text.get(self.state, f"\u25cf  {self.state}")
            # Status color: mostly platinum, cyan only for active states
            if self.state in ("LISTENING", "SPEAKING"):
                col = qcol(HU.CYAN)
            elif self.state in ("THINKING", "PROCESSING", "EXECUTING"):
                col = qcol(HU.GOLD)
            elif self.state == "ERROR":
                col = qcol(HU.RED)
            elif self.state == "SLEEPING":
                col = qcol(HU.DIM)
            else:
                col = qcol(HU.TEXT)

        p.setFont(_font(9, True))
        tw = max(p.fontMetrics().horizontalAdvance(txt), 80)
        chip_w, chip_h = tw + 24, 24
        chip_x, chip_y = cx - chip_w / 2, sy_chip - 2
        # Chip background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(8, 10, 16, 220)))
        chip_path = _ang_path(chip_w, chip_h, [("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)])
        chip_path.translate(chip_x, chip_y)
        p.drawPath(chip_path)
        _paint_ang_border(p, chip_path, col)
        p.setPen(QPen(col, 1))
        p.drawText(QRectF(chip_x, chip_y, chip_w, chip_h),
                   Qt.AlignmentFlag.AlignCenter, txt)

        p.end()


# ── SciGauge ────────────────────────────────────────────────────────────────

class SciGauge(QWidget):
    """Precision radial gauge — aerospace-grade arc indicator."""

    _START = 135
    _SWEEP = 270

    def __init__(self, label: str, color: str = C.PRI, parent=None):
        super().__init__(parent)
        self._label = label
        self._color = color
        self._value = 0.0
        self._text = "--"
        self._tick = 0.0
        self.setFixedHeight(62)
        self.setMinimumWidth(108)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(50)

    def _step(self):
        self._tick += 0.04
        self.update()

    def set_value(self, pct: float, text: str):
        self._value = max(0.0, min(100.0, pct))
        self._text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        a_r = 18.0
        cxm = W / 2
        cya = a_r + 6
        rect = QRectF(cxm - a_r, cya - a_r, a_r * 2, a_r * 2)

        # Background arc — dark metallic
        bg_pen = QPen(qcol(HU.BORDER, 40), 2.5)
        bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(bg_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(rect, int(self._START * 16), int(self._SWEEP * 16))

        # Value arc
        if self._value > 0.1:
            sweep = self._SWEEP * (self._value / 100.0)
            val_col = QColor(self._color)
            val_pen = QPen(val_col, 2.5)
            val_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(val_pen)
            p.drawArc(rect, int(self._START * 16), int(-sweep * 16))
            # Subtle glow
            glow_col = QColor(val_col)
            glow_col.setAlpha(20)
            glow_pen = QPen(glow_col, 5.0)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(glow_pen)
            p.drawArc(rect, int(self._START * 16), int(-sweep * 16))

        # Value text
        p.setFont(_font(9, True))
        p.setPen(QPen(qcol(HU.TEXT), 1))
        p.drawText(QRectF(0, cya - 8, W, 16), Qt.AlignmentFlag.AlignCenter, self._text)

        # Label
        p.setFont(_font(6, True))
        p.setPen(QPen(qcol(HU.DIM), 1))
        p.drawText(QRectF(0, cya + 10, W, 14), Qt.AlignmentFlag.AlignCenter, self._label)

        p.end()


# ── AmbientBackdrop ─────────────────────────────────────────────────────────

class AmbientBackdrop(QWidget):
    """Environmental depth layer — deep cinematic background, minimal particles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._t = 0.0
        self._particles = []
        for _ in range(10):
            self._particles.append({
                "x": random.random(),
                "y": random.random(),
                "vx": (random.random() - 0.5) * 0.0004,
                "vy": (random.random() - 0.5) * 0.0003,
                "size": random.uniform(0.3, 0.8),
                "alpha": random.randint(6, 20),
                "phase": random.random() * math.pi * 2,
            })
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(100)

    def _step(self):
        self._t += 0.025
        for pt in self._particles:
            pt["x"] += pt["vx"]
            pt["y"] += pt["vy"]
            pt["phase"] += 0.006
            if pt["x"] < 0 or pt["x"] > 1:
                pt["vx"] *= -1
            if pt["y"] < 0 or pt["y"] > 1:
                pt["vy"] *= -1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        if W < 2 or H < 2:
            return

        # Layer 1: Deep void
        bg = QRadialGradient(W * 0.3, H * 0.25, max(W, H) * 0.9)
        bg.setColorAt(0.0, QColor(7, 9, 14))
        bg.setColorAt(0.3, QColor(5, 7, 11))
        bg.setColorAt(0.6, QColor(C.BG))
        bg.setColorAt(1.0, QColor(2, 3, 5))
        p.fillRect(self.rect(), QBrush(bg))

        # Layer 2: Subtle radial warmth
        cx, cy = W / 2, H / 2
        ambient_r = max(W, H) * 0.45
        ambient = QRadialGradient(cx, cy * 0.8, ambient_r)
        ambient.setColorAt(0.0, QColor(80, 85, 100, 4))
        ambient.setColorAt(0.5, QColor(40, 45, 60, 2))
        ambient.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(QBrush(ambient))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy * 0.8), ambient_r, ambient_r)

        # Layer 3: Ambient micro-particles
        p.setPen(Qt.PenStyle.NoPen)
        for pt in self._particles:
            px_x = pt["x"] * W
            px_y = pt["y"] * H
            pulse = 0.5 + 0.5 * math.sin(pt["phase"])
            a = int(pt["alpha"] * pulse)
            dist = math.sqrt((px_x - cx) ** 2 + (px_y - cy) ** 2) / (max(W, H) * 0.5)
            a = int(a * max(0.08, 1.0 - dist * 0.7))
            if a > 1:
                p.setBrush(QBrush(QColor(100, 110, 130, a)))
                p.drawEllipse(QPointF(px_x, px_y), pt["size"], pt["size"])

        # Layer 4: Minimal edge brackets
        bl = 18
        p.setPen(QPen(qcol(HU.METALLIC, 30), 0.8))
        for bx, by, dx, dy in [(0, 0, 1, 1), (W, 0, -1, 1), (0, H, 1, -1), (W, H, -1, -1)]:
            p.drawLine(bx, by, bx + dx * bl, by)
            p.drawLine(bx, by, bx, by + dy * bl)


# ── SciFrame ────────────────────────────────────────────────────────────────

class SciFrame(QWidget):
    """Panel skin — clean metallic edges."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def paintEvent(self, _):
        p = QPainter(self)
        W, H = self.width(), self.height()
        if W < 2 or H < 2:
            return
        grad = QLinearGradient(0, 0, 0, H)
        grad.setColorAt(0.0, qcol(HU.FILL2))
        grad.setColorAt(0.5, qcol(HU.FILL))
        grad.setColorAt(1.0, qcol(C.BG))
        p.fillRect(self.rect(), QBrush(grad))
        p.setPen(QPen(qcol(HU.BORDER, 60), 0.6))
        p.drawLine(0, 0, W, 0)
        bl = 8
        p.setPen(QPen(qcol(HU.METALLIC, 40), 0.8))
        for bx, by, dx, dy in [(0, 0, 1, 1), (W - 1, 0, -1, 1), (0, H - 1, 1, -1), (W - 1, H - 1, -1, -1)]:
            p.drawLine(bx, by, bx + dx * bl, by)
            p.drawLine(bx, by, bx, by + dy * bl)


# ── SciEqualizer ────────────────────────────────────────────────────────────

class SciEqualizer(QWidget):
    """Minimal equalizer strip — platinum bars."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self._t = 0.0
        self.setFixedSize(36, 22)
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._tmr.start(40)

    def set_active(self, active: bool):
        self._active = active
        self.update()

    def _step(self):
        if self._active:
            self._t += 0.10
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        N, bw = 7, 4
        x0 = (W - N * bw) / 2
        for i in range(N):
            if self._active:
                h = 3 + abs(math.sin(self._t + i * 0.85)) * (H - 6)
                # Platinum bars with subtle cyan tint
                col = QColor.fromHsvF(0.53, 0.15, 0.85, 200)
            else:
                h = 2
                col = qcol(HU.BORDER, 80)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawRoundedRect(QRectF(x0 + i * bw, H - h, bw - 1, h), 1, 1)
            if self._active:
                cap_col = QColor(col).lighter(115)
                p.setBrush(QBrush(cap_col))
                p.drawRoundedRect(QRectF(x0 + i * bw, H - h - 1, bw - 1, 1), 1, 1)


# ── HueWheel ────────────────────────────────────────────────────────────────

class HueWheel(QWidget):
    """Circular color picker with draggable handle."""

    hue_picked = pyqtSignal(str)
    hue_committed = pyqtSignal(str)

    _RING = 16

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue = 0.53
        self._drag = False
        self.set_color(initial_hex)

    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()
        ang = math.atan2(dy, dx)
        return (ang / (2 * math.pi)) % 1.0

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._ring_rect()
        center = rect.center()
        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)
        r = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx = center.x() + r * math.cos(ang)
        hy = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#030303"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)

    def mousePressEvent(self, e):
        self._drag = True
        self._hue = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())


# ── Icon paths reference ────────────────────────────────────────────────────
_ICON_PATHS = {
    "mic", "mic_off", "send", "mute", "volume2", "volume_x",
    "settings", "plugin", "brain", "download", "upload",
    "key", "copy", "x", "camera", "monitor",
}
