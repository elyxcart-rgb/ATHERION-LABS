from __future__ import annotations

import json
import math
import os
import platform
import random
import subprocess
import sys
import threading
import time
from pathlib import Path

import psutil

if platform.system() == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}

# ── Import SONIC theme from sonic-frontend-theme ──────────────────────────────
_SONIC_THEME_DIR = str(Path(__file__).resolve().parent / "sonic-frontend-theme")
if _SONIC_THEME_DIR not in sys.path:
    sys.path.insert(0, _SONIC_THEME_DIR)

from pyqt6_theme import (
    C, HU, qcol, apply_ui_accent, current_palette, retheme_all_widgets,
    DEFAULT_UI_COLOR, svg_pixmap,
    HudPanel, HudHeader, HudButton, HudLineEdit, HudCanvas,
    SciGauge, AmbientBackdrop, SciFrame, SciEqualizer, HueWheel,
)

from PyQt6.QtCore import (
    QEasingCurve, QMimeData, QObject, QPointF, QRectF, QSize, Qt,
    QTimer, QUrl, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QDragEnterEvent, QDropEvent, QFont,
    QFontDatabase, QKeySequence, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap, QRadialGradient, QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QTextEdit, QVBoxLayout, QWidget, QProgressBar,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR   = _base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"


def _read_full_config() -> dict:
    """Read api_keys.json config dict. Returns {} on any error."""
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


_DEFAULT_W, _DEFAULT_H = 980, 700
_MIN_W,     _MIN_H     = 820, 580
_LEFT_W  = 148
_RIGHT_W = 340

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


# ── Windows GPU via NVML DLL (no subprocess, no console window) ──────────────
_nvml_lib: object = None   # cached ctypes DLL
_nvml_ok:  object = None   # None=untested, True=works, False=unavailable


def _nvml_gpu_windows() -> float:
    """Return NVIDIA GPU utilisation % using nvml.dll directly — zero subprocess."""
    global _nvml_lib, _nvml_ok
    if _nvml_ok is False:
        return -1.0
    try:
        import ctypes

        class _Util(ctypes.Structure):
            _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

        if _nvml_lib is None:
            for dll_name in ("nvml", r"C:\Windows\System32\nvml.dll"):
                try:
                    lib = ctypes.WinDLL(dll_name)
                    lib.nvmlInit_v2()
                    _nvml_lib = lib
                    break
                except Exception:
                    continue

        if _nvml_lib is None:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            _nvml_ok = True
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)

        dev = ctypes.c_void_p()
        _nvml_lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
        util = _Util()
        _nvml_lib.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(util))
        _nvml_ok = True
        return float(util.gpu)
    except Exception:
        _nvml_ok = False
        return -1.0


class _SysMetrics:
    def __init__(self):
        self.cpu  = 0.0
        self.mem  = 0.0
        self.net  = 0.0   
        self.gpu  = -1.0  
        self.tmp  = -1.0  
        self._lock = threading.Lock()
        self._last_net = psutil.net_io_counters()
        self._last_net_t = time.time()
        self._running = True
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def _loop(self):
        while self._running:
            try:
                self._update()
            except Exception:
                pass
            time.sleep(1.5)

    def _update(self):
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        nc  = psutil.net_io_counters()
        now = time.time()
        dt  = now - self._last_net_t
        if dt > 0:
            sent = (nc.bytes_sent - self._last_net.bytes_sent) / dt
            recv = (nc.bytes_recv - self._last_net.bytes_recv) / dt
            net  = (sent + recv) / (1024 * 1024)
        else:
            net = 0.0
        self._last_net   = nc
        self._last_net_t = now

        gpu = self._get_gpu()

        tmp = self._get_temp()

        with self._lock:
            self.cpu = cpu
            self.mem = mem
            self.net = net
            self.gpu = gpu
            self.tmp = tmp

    def _get_gpu(self) -> float:
        # pynvml — subprocess-free, works on all platforms if installed
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
        except Exception:
            pass

        # Windows: nvml.dll via ctypes (already cached in _nvml_gpu_windows)
        if _OS == "Windows":
            return _nvml_gpu_windows()

        # Linux / macOS: libnvidia-ml shared lib via ctypes
        try:
            import ctypes
            _lib = "libnvidia-ml.so.1" if _OS == "Linux" else "libnvidia-ml.dylib"

            class _Util(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            nv = ctypes.CDLL(_lib)
            nv.nvmlInit_v2()
            dev = ctypes.c_void_p()
            nv.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(dev))
            u = _Util()
            nv.nvmlDeviceGetUtilizationRates(dev, ctypes.byref(u))
            return float(u.gpu)
        except Exception:
            pass

        return -1.0   # N/A — zero subprocess on all platforms

    def _get_temp(self) -> float:
        # psutil — works on Linux; occasionally Windows with driver support
        try:
            temps = psutil.sensors_temperatures()
            for name in ["coretemp", "k10temp", "cpu_thermal", "acpitz",
                         "cpu-thermal", "zenpower", "it8688"]:
                if name in temps and temps[name]:
                    return temps[name][0].current
            for entries in temps.values():
                if entries:
                    return entries[0].current
        except Exception:
            pass

        # Windows: wmi module (pure Python COM, zero subprocess)
        if _OS == "Windows":
            try:
                import wmi  # type: ignore
                w = wmi.WMI(namespace="root/wmi")
                tz = w.MSAcpi_ThermalZoneTemperature()
                if tz:
                    return (tz[0].CurrentTemperature / 10.0) - 273.15
            except Exception:
                pass

        return -1.0   # N/A — zero subprocess on all platforms

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "cpu": self.cpu,
                "mem": self.mem,
                "net": self.net,
                "gpu": self.gpu,
                "tmp": self.tmp,
            }


_metrics = _SysMetrics()

# HudCanvas, MetricBar — imported from sonic-frontend-theme (pyqt6_theme)

class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {C.TEXT};
                border: none;
                padding: 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                border: none;
                margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER};
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {C.BORDER_B};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = "sonic"   # updated when assistant name changes
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("sonic:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.PRI),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                "sys":  qcol(C.ACC2),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

_FILE_ICONS = {
    "image":   ("🖼", "#00d4ff"), "video":   ("🎬", "#ff6b00"),
    "audio":   ("🎵", "#cc44ff"), "pdf":     ("📄", "#ff4444"),
    "word":    ("📝", "#4488ff"), "excel":   ("📊", "#44bb44"),
    "code":    ("💻", "#ffcc00"), "archive": ("📦", "#ff8844"),
    "pptx":    ("📊", "#ff6622"), "text":    ("📃", "#aaaaaa"),
    "data":    ("🔧", "#88ddff"), "unknown": ("📎", "#888888"),
}
_EXT_TO_CAT = {
    **dict.fromkeys(["jpg","jpeg","png","gif","webp","bmp","tiff","svg","ico"], "image"),
    **dict.fromkeys(["mp4","avi","mov","mkv","wmv","flv","webm","m4v"],         "video"),
    **dict.fromkeys(["mp3","wav","ogg","m4a","aac","flac","wma","opus"],        "audio"),
    **dict.fromkeys(["pdf"],                                                     "pdf"),
    **dict.fromkeys(["doc","docx"],                                              "word"),
    **dict.fromkeys(["xls","xlsx","ods"],                                        "excel"),
    **dict.fromkeys(["ppt","pptx"],                                              "pptx"),
    **dict.fromkeys(["py","js","ts","jsx","tsx","html","css","java","c","cpp",
                     "cs","go","rs","rb","php","swift","kt","sh","sql","lua"],   "code"),
    **dict.fromkeys(["zip","rar","tar","gz","7z","bz2","xz"],                   "archive"),
    **dict.fromkeys(["txt","md","rst","log"],                                    "text"),
    **dict.fromkeys(["csv","tsv","json","xml"],                                  "data"),
}

def _file_category(path: Path) -> str:
    return _EXT_TO_CAT.get(path.suffix.lower().lstrip("."), "unknown")

def _fmt_size(size: int) -> str:
    if   size < 1024:    return f"{size} B"
    elif size < 1024**2: return f"{size/1024:.1f} KB"
    elif size < 1024**3: return f"{size/1024**2:.1f} MB"
    else:                return f"{size/1024**3:.1f} GB"


class FileDropZone(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(100)
        self._current_file: str | None = None
        self._hovering  = False
        self._drag_over = False
        self._dash_offset = 0.0
        self._anim_tmr = QTimer(self)
        self._anim_tmr.timeout.connect(self._animate)
        self._anim_tmr.start(40)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._canvas = _DropCanvas(self)
        layout.addWidget(self._canvas)

    def _animate(self):
        self._dash_offset = (self._dash_offset + 0.8) % 20
        self._canvas.update()

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._drag_over = True; self._canvas.update()

    def dragLeaveEvent(self, e):
        self._drag_over = False; self._canvas.update()

    def dropEvent(self, e: QDropEvent):
        self._drag_over = False
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if Path(path).is_file():
                self._set_file(path)
        self._canvas.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._browse()

    def enterEvent(self, e):
        self._hovering = True; self._canvas.update()

    def leaveEvent(self, e):
        self._hovering = False; self._canvas.update()

    def current_file(self) -> str | None:
        return self._current_file

    def clear_file(self):
        self._current_file = None; self._canvas.update()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select a file for SONIC", str(Path.home()),
            "All Files (*.*);;"
            "Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;"
            "Documents (*.pdf *.docx *.txt *.md *.pptx);;"
            "Data (*.csv *.xlsx *.json *.xml);;"
            "Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;"
            "Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;"
            "Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;"
            "Archives (*.zip *.rar *.tar *.gz *.7z)",
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self._canvas.update()
        self.file_selected.emit(path)


class _DropCanvas(QWidget):
    def __init__(self, zone: FileDropZone):
        super().__init__(zone)
        self._z = zone

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        z    = self._z
        W, H = self.width(), self.height()
        pad  = 6
        rect = QRectF(pad, pad, W - pad * 2, H - pad * 2)

        bg_col = qcol(C.PRI_GHO if z._drag_over else (C.GLASS if z._hovering else C.PANEL))
        p.setBrush(QBrush(bg_col)); p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   border_col = qcol(C.GREEN, 200)
        elif z._drag_over:    border_col = qcol(C.PRI, 230)
        elif z._hovering:     border_col = qcol(C.BORDER_B, 200)
        else:                 border_col = qcol(C.BORDER, 160)

        pen = QPen(border_col, 1.5, Qt.PenStyle.DashLine)
        pen.setDashOffset(z._dash_offset)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, 6, 6)

        if z._current_file:   self._paint_file(p, W, H)
        elif z._drag_over:    self._paint_drag_over(p, W, H)
        else:                 self._paint_idle(p, W, H, z._hovering)

    def _paint_idle(self, p, W, H, hover):
        cx, cy = W / 2, H / 2
        col = qcol(C.PRI_DIM if not hover else C.PRI)
        p.setPen(QPen(col, 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(cx, cy - 14), QPointF(cx, cy + 4))
        p.drawLine(QPointF(cx - 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx + 8, cy - 6), QPointF(cx, cy - 14))
        p.drawLine(QPointF(cx - 14, cy + 4), QPointF(cx + 14, cy + 4))
        p.setFont(QFont("Courier New", 8))
        p.setPen(QPen(qcol(C.PRI_DIM if not hover else C.TEXT), 1))
        p.drawText(QRectF(0, cy + 8, W, 16), Qt.AlignmentFlag.AlignCenter,
                   "Drop file here  or  Click to Browse")
        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(HU.METALLIC), 1))
        p.drawText(QRectF(0, cy + 24, W, 14), Qt.AlignmentFlag.AlignCenter,
                   "Images · Video · Audio · PDF · Docs · Code · Data")

    def _paint_drag_over(self, p, W, H):
        cx, cy = W / 2, H / 2
        p.setFont(QFont("Courier New", 20))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy - 24, W, 32), Qt.AlignmentFlag.AlignCenter, "⬇")
        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.PRI), 1))
        p.drawText(QRectF(0, cy + 12, W, 16), Qt.AlignmentFlag.AlignCenter, "Release to load")

    def _paint_file(self, p, W, H):
        path = Path(self._z._current_file)
        cat  = _file_category(path)
        icon, icon_col = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size_str = _fmt_size(path.stat().st_size)
        ext_str  = path.suffix.upper().lstrip(".") or "FILE"

        block_x, block_w = 10, 60
        p.setFont(QFont("Segoe UI Emoji", 22) if _OS == "Windows" else QFont("Arial", 22))
        p.setPen(QPen(qcol(icon_col), 1))
        p.drawText(QRectF(block_x, 0, block_w, H), Qt.AlignmentFlag.AlignCenter, icon)

        tx = block_x + block_w + 6
        tw = W - tx - 38

        p.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.WHITE), 1))
        name = path.name if len(path.name) <= 34 else path.name[:31] + "..."
        p.drawText(QRectF(tx, H * 0.18, tw, 16),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)

        p.setFont(QFont("Courier New", 7))
        p.setPen(QPen(qcol(C.TEXT_DIM), 1))
        p.drawText(QRectF(tx, H * 0.18 + 18, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{ext_str}  ·  {size_str}")

        p.setFont(QFont("Courier New", 6))
        p.setPen(QPen(qcol(C.BORDER_A), 1))
        par = str(path.parent)
        if len(par) > 42: par = "…" + par[-41:]
        p.drawText(QRectF(tx, H * 0.18 + 34, tw, 12),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, par)

        p.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        p.setPen(QPen(qcol(C.RED, 180), 1))
        p.drawText(QRectF(W - 34, 0, 28, H), Qt.AlignmentFlag.AlignCenter, "✕")

    def mousePressEvent(self, e):
        z = self._z
        if z._current_file and e.pos().x() > self.width() - 34:
            z.clear_file()
        else:
            z.mousePressEvent(e)


class _CameraPreview(QWidget):
    """Floating overlay that briefly shows what the camera captured."""

    _W, _H = 244, 188

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _CameraPreview {{
                background: rgba(0, 6, 10, 242);
                border: 1px solid {C.PRI};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 6)
        lay.setSpacing(4)

        hdr = QHBoxLayout()
        title = QLabel("◈  VISUAL INPUT")
        title.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(title)
        hdr.addStretch()
        close_btn = HudButton("✕",
                               cuts=[("tl", 3), ("tr", 3), ("bl", 3), ("br", 3)],
                               border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        close_btn.setFixedSize(16, 16)
        close_btn.clicked.connect(self.hide)
        hdr.addWidget(close_btn)
        lay.addLayout(hdr)

        self._img_lbl = QLabel()
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setStyleSheet("background: transparent;")
        lay.addWidget(self._img_lbl)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self.hide()

    def show_frame(self, img_bytes: bytes) -> None:
        px = QPixmap()
        px.loadFromData(img_bytes)
        if not px.isNull():
            max_w = self._W - 12
            scaled = px.scaled(
                max_w, 160,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_lbl.setPixmap(scaled)
            self._img_lbl.setFixedSize(scaled.width(), scaled.height())
            self.adjustSize()
        self.show()
        self.raise_()
        self._timer.start(6_000)   # auto-dismiss after 6 s


class SetupOverlay(QWidget):
    done = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            SetupOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)

        detected = {"darwin": "mac", "windows": "windows"}.get(
            _OS.lower(), "linux"
        )
        self._sel_os = detected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(8)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        layout.addWidget(_lbl("◈  INITIALISATION REQUIRED", 13, True))
        layout.addWidget(_lbl("Configure S.O.N.I.C. before first boot.", 9, color=C.PRI_DIM))
        layout.addSpacing(6)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        layout.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._key_input = HudLineEdit()
        self._key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_input.setPlaceholderText("AIza…")
        self._key_input.setFont(QFont("Courier New", 10))
        self._key_input.setFixedHeight(32)
        layout.addWidget(self._key_input)
        layout.addSpacing(12)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep2)
        layout.addSpacing(4)

        layout.addWidget(_lbl("OPERATING SYSTEM", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        det_name = {"windows": "Windows", "mac": "macOS", "linux": "Linux"}[detected]
        layout.addWidget(_lbl(f"Auto-detected: {det_name}", 8, color=C.ACC2,
                               align=Qt.AlignmentFlag.AlignLeft))

        os_row = QHBoxLayout(); os_row.setSpacing(6)
        self._os_btns: dict[str, HudButton] = {}
        for key, label in [("windows","⊞  Windows"),("mac","  macOS"),("linux","🐧  Linux")]:
            btn = HudButton(label,
                            cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=9)
            btn.setFixedHeight(32)
            btn.clicked.connect(lambda _, k=key: self._sel(k))
            os_row.addWidget(btn)
            self._os_btns[key] = btn
        layout.addLayout(os_row)
        self._sel(detected)
        layout.addSpacing(12)

        init_btn = HudButton("▸  INITIALISE SYSTEMS",
                              cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                              border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=10)
        init_btn.setFixedHeight(36)
        init_btn.clicked.connect(self._submit)
        layout.addWidget(init_btn)

    def _sel(self, key: str):
        self._sel_os = key
        pal = {"windows":(C.PRI,C.PRI_GHO),"mac":(C.ACC2,C.GLASS),"linux":(C.GREEN,C.GREEN_D)}
        for k, btn in self._os_btns.items():
            if k == key:
                fg, bg = pal[k]
                btn.set_theme(border=fg, fill=fg, color=bg)
            else:
                btn.set_theme(border=HU.BORDER, fill=HU.FILL, color=HU.DIM)

    def _submit(self):
        key = self._key_input.text().strip()
        if not key:
            return
        self.done.emit(key, self._sel_os)


class AuthOverlay(QWidget):
    """Authentication overlay — login, signup, forgot password."""
    auth_success = pyqtSignal(str, str)  # user_id, email
    skip = pyqtSignal()  # offline mode
    _login_result = pyqtSignal(dict, str)
    _signup_result = pyqtSignal(dict, str)
    _forgot_result = pyqtSignal(dict)
    _google_result = pyqtSignal(dict, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            AuthOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._mode = "login"  # login | signup | forgot | verify
        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(lambda: self._error_lbl.setText(""))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(6)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        self._title_lbl = _lbl("◈  SIGN IN TO SONIC", 13, True)
        layout.addWidget(self._title_lbl)
        self._subtitle_lbl = _lbl("Access your AI from any device.", 9, color=C.PRI_DIM)
        layout.addWidget(self._subtitle_lbl)
        layout.addSpacing(4)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); layout.addWidget(sep)
        layout.addSpacing(4)

        # Email
        layout.addWidget(_lbl("EMAIL", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._email_input = HudLineEdit()
        self._email_input.setPlaceholderText("you@example.com")
        self._email_input.setFont(QFont("Courier New", 10))
        self._email_input.setFixedHeight(32)
        layout.addWidget(self._email_input)
        layout.addSpacing(6)

        # Password
        layout.addWidget(_lbl("PASSWORD", 8, color=C.TEXT_DIM,
                               align=Qt.AlignmentFlag.AlignLeft))
        self._pass_input = HudLineEdit()
        self._pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_input.setPlaceholderText("••••••••")
        self._pass_input.setFont(QFont("Courier New", 10))
        self._pass_input.setFixedHeight(32)
        layout.addWidget(self._pass_input)
        pw_hint = _lbl("6+ characters", 7, color=C.TEXT_DIM)
        layout.addWidget(pw_hint)
        layout.addSpacing(6)

        # Confirm password (signup only)
        self._confirm_row = QWidget()
        confirm_layout = QVBoxLayout(self._confirm_row)
        confirm_layout.setContentsMargins(0, 0, 0, 0)
        confirm_layout.setSpacing(4)
        confirm_layout.addWidget(_lbl("CONFIRM PASSWORD", 8, color=C.TEXT_DIM,
                                       align=Qt.AlignmentFlag.AlignLeft))
        self._confirm_input = HudLineEdit()
        self._confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_input.setPlaceholderText("••••••••")
        self._confirm_input.setFont(QFont("Courier New", 10))
        self._confirm_input.setFixedHeight(32)
        confirm_layout.addWidget(self._confirm_input)
        self._confirm_row.setVisible(False)
        layout.addWidget(self._confirm_row)

        # Error label
        self._error_lbl = _lbl("", 8, color=C.RED)
        layout.addWidget(self._error_lbl)
        layout.addSpacing(4)

        # Primary action button
        self._action_btn = HudButton("▸  SIGN IN",
                                      cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                                      border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=10)
        self._action_btn.setFixedHeight(36)
        self._action_btn.clicked.connect(self._on_action)
        layout.addWidget(self._action_btn)

        # Secondary actions row
        sec_row = QHBoxLayout()
        sec_row.setSpacing(12)
        self._switch_btn = QPushButton("Create account")
        self._switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._switch_btn.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; border: none; font-size: 9px;")
        self._switch_btn.clicked.connect(self._toggle_mode)
        sec_row.addWidget(self._switch_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._forgot_btn = QPushButton("Forgot password?")
        self._forgot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._forgot_btn.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent; border: none; font-size: 9px;")
        self._forgot_btn.clicked.connect(lambda: self._set_mode("forgot"))
        sec_row.addWidget(self._forgot_btn, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(sec_row)

        # Skip / offline
        self._skip_btn = QPushButton("Continue offline")
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; font-size: 8px;")
        self._skip_btn.clicked.connect(self.skip.emit)
        layout.addWidget(self._skip_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Google Sign-In
        self._google_btn = QPushButton("▸  Continue with Google")
        self._google_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._google_btn.setFixedHeight(32)
        google_enabled = get_auth().is_google_configured()
        self._google_btn.setEnabled(google_enabled)
        if not google_enabled:
            self._google_btn.setToolTip("Google Sign-In not configured")
        self._google_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; font-size: 9px; padding: 6px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid {HU.BRIGHT}; color: {HU.BRIGHT};
            }}
            QPushButton:disabled {{
                color: {C.TEXT_DIM}; background: {C.FILL1}; border: 1px solid {C.BORDER};
            }}
        """)
        self._google_btn.clicked.connect(self._do_google_login)
        layout.addWidget(self._google_btn)

        # Loading overlay
        self._loading_lbl = _lbl("Connecting...", 9, color=C.PRI_DIM)
        self._loading_lbl.setVisible(False)
        layout.addWidget(self._loading_lbl)

        # Connect result signals
        self._login_result.connect(self._on_auth_result)
        self._signup_result.connect(self._on_signup_result)
        self._forgot_result.connect(self._on_forgot_result)
        self._google_result.connect(self._on_google_result)

    def _set_mode(self, mode: str):
        self._mode = mode
        self._error_lbl.setText("")
        self._confirm_row.setVisible(mode == "signup")
        if mode == "login":
            self._title_lbl.setText("◈  SIGN IN TO SONIC")
            self._subtitle_lbl.setText("Access your AI from any device.")
            self._action_btn.setText("▸  SIGN IN")
            self._switch_btn.setText("Create account")
            self._forgot_btn.setVisible(True)
        elif mode == "signup":
            self._title_lbl.setText("◈  CREATE ACCOUNT")
            self._subtitle_lbl.setText("Sync your AI across devices.")
            self._action_btn.setText("▸  CREATE ACCOUNT")
            self._switch_btn.setText("Sign in instead")
            self._forgot_btn.setVisible(False)
        elif mode == "forgot":
            self._title_lbl.setText("◈  RESET PASSWORD")
            self._subtitle_lbl.setText("We'll email you a reset link.")
            self._action_btn.setText("▸  SEND RESET LINK")
            self._switch_btn.setText("Back to sign in")
            self._forgot_btn.setVisible(False)
            self._pass_input.setVisible(False)
            self._confirm_row.setVisible(False)
        elif mode == "verify":
            self._title_lbl.setText("◈  CHECK YOUR EMAIL")
            self._subtitle_lbl.setText("Click the link we sent to verify your account.")
            self._action_btn.setVisible(False)
            self._switch_btn.setText("Back to sign in")
            self._forgot_btn.setVisible(False)
            self._pass_input.setVisible(False)
            self._confirm_row.setVisible(False)
            self._email_input.setVisible(False)

    def _toggle_mode(self):
        if self._mode == "login":
            self._set_mode("signup")
        else:
            self._set_mode("login")

    def _on_action(self):
        email = self._email_input.text().strip()
        password = self._pass_input.text()
        if not email or not password:
            self._show_error("Email and password required.")
            return
        if self._mode == "forgot":
            self._do_forgot(email)
        elif self._mode == "signup":
            confirm = self._confirm_input.text()
            if password != confirm:
                self._show_error("Passwords don't match.")
                return
            if len(password) < 6:
                self._show_error("Password must be at least 6 characters.")
                return
            self._do_signup(email, password)
        else:
            self._do_login(email, password)

    def _show_error(self, msg: str):
        self._error_lbl.setText(msg)
        self._error_timer.start(8000)

    def _set_loading(self, loading: bool):
        self._loading_lbl.setVisible(loading)
        self._action_btn.setEnabled(not loading)

    def _do_login(self, email: str, password: str):
        self._set_loading(True)
        self._action_btn.setText("  SIGNING IN...")
        def _run():
            try:
                from auth import get_auth
                result = get_auth().login(email, password)
                self._login_result.emit(result, email)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._login_result.emit({"success": False, "error": str(e)}, email)
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        QTimer.singleShot(30000, lambda: self._on_timeout(thread, "login"))

    def _do_signup(self, email: str, password: str):
        self._set_loading(True)
        self._action_btn.setText("  CREATING ACCOUNT...")
        def _run():
            try:
                from auth import get_auth
                result = get_auth().signup(email, password)
                self._signup_result.emit(result, email)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._signup_result.emit({"success": False, "error": str(e)}, email)
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        QTimer.singleShot(30000, lambda: self._on_timeout(thread, "signup"))

    def _do_forgot(self, email: str):
        self._set_loading(True)
        def _run():
            try:
                from auth import get_auth
                result = get_auth().send_password_reset(email)
                self._forgot_result.emit(result)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._forgot_result.emit({"success": False, "error": str(e)})
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        QTimer.singleShot(30000, lambda: self._on_timeout(thread, "forgot"))

    def _do_google_login(self):
        """Full Google OAuth flow with local callback server."""
        self._set_loading(True)
        self._google_btn.setText("  Opening browser...")
        def _run():
            try:
                from auth import get_auth
                result = get_auth().google_login_with_server()
                self._google_result.emit(result, result.get("email", ""))
            except Exception as e:
                import traceback; traceback.print_exc()
                self._google_result.emit({"success": False, "error": str(e)}, "")
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _on_timeout(self, thread: threading.Thread, mode: str):
        if thread.is_alive():
            self._set_loading(False)
            if mode == "login":
                self._action_btn.setText("\u25b8  SIGN IN")
            elif mode == "signup":
                self._action_btn.setText("\u25b8  CREATE ACCOUNT")
            self._show_error("Operation timed out. Please try again.")

    def _on_auth_result(self, result: dict, email: str):
        self._set_loading(False)
        self._action_btn.setText("\u25b8  SIGN IN")
        if result.get("success"):
            from auth import get_auth
            uid = get_auth().user_id
            if uid:
                self.auth_success.emit(uid, email)
        else:
            self._show_error(result.get("error", "Login failed"))

    def _on_signup_result(self, result: dict, email: str):
        self._set_loading(False)
        self._action_btn.setText("\u25b8  CREATE ACCOUNT")
        if result.get("success"):
            from auth import get_auth
            uid = get_auth().user_id
            if uid:
                self.auth_success.emit(uid, email)
        else:
            self._show_error(result.get("error", "Signup failed"))

    def _on_forgot_result(self, result: dict):
        self._set_loading(False)
        if result.get("success"):
            self._title_lbl.setText("◈  EMAIL SENT")
            self._subtitle_lbl.setText("Check your inbox for the reset link.")
            self._action_btn.setVisible(False)
        else:
            self._show_error(result.get("error", "Failed to send email"))

    def _on_google_result(self, result: dict, email: str):
        self._set_loading(False)
        self._google_btn.setText("\u25b2  Continue with Google")
        if result.get("success"):
            uid = result.get("user_id", "")
            if uid:
                self.auth_success.emit(uid, email)
        else:
            self._show_error(result.get("error", "Google sign-in failed"))


# ═══════════════════════════════════════════════════════════════════════════════
# Onboarding Wizard — First-run multi-step setup
# ═══════════════════════════════════════════════════════════════════════════════

class OnboardingWizard(QWidget):
    """Multi-step first-run setup wizard.
    
    Steps:
    1. Account — Sign up or sign in
    2. Personal Info — Name, phone, location, timezone
    3. API Keys — Gemini, OpenAI, etc.
    4. Preferences — Theme, voice, language
    """
    completed = pyqtSignal(dict)  # Emits final profile data
    skipped = pyqtSignal()
    _account_result = pyqtSignal(dict, str, str)  # result, email, uid

    _STEP_ACCOUNT = 0
    _STEP_PERSONAL = 1
    _STEP_API = 2
    _STEP_PREFS = 3
    _STEP_COUNT = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            OnboardingWizard {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._step = self._STEP_ACCOUNT
        self._data = {}
        self._account_mode = "signup"
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 22, 30, 22)
        layout.setSpacing(6)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        # Progress header
        self._progress_lbl = _lbl("STEP 1 OF 4  ◈  ACCOUNT SETUP", 11, True)
        layout.addWidget(self._progress_lbl)

        self._step_desc = _lbl("Create your SONIC account to sync across devices", 9, color=C.PRI_DIM)
        layout.addWidget(self._step_desc)
        layout.addSpacing(4)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, self._STEP_COUNT)
        self._progress_bar.setValue(1)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: {HU.FILL2};
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background: {HU.BRIGHT};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(self._progress_bar)
        layout.addSpacing(8)

        # Content stack
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        # Build step pages
        self._build_account_step()
        self._build_personal_step()
        self._build_api_step()
        self._build_prefs_step()

        # Initialize account mode UI
        self._set_account_mode("signup")

        # Connect account result signal
        self._account_result.connect(self._on_account_result)

        # Navigation buttons
        nav_row = QHBoxLayout()
        nav_row.setSpacing(12)

        self._back_btn = HudButton("\u2190  BACK",
            cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=9)
        self._back_btn.setFixedHeight(32)
        self._back_btn.clicked.connect(self._go_back)
        self._back_btn.setVisible(False)
        nav_row.addWidget(self._back_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._next_btn = HudButton("\u25b8  CONTINUE",
            cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
            border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=9)
        self._next_btn.setFixedHeight(32)
        self._next_btn.clicked.connect(self._next_step)
        self._next_btn.setVisible(False)
        nav_row.addWidget(self._next_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self._skip_btn = QPushButton("Skip setup")
        self._skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._skip_btn.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; border: none; font-size: 8px;")
        self._skip_btn.clicked.connect(self._on_skip)
        nav_row.addWidget(self._skip_btn, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addLayout(nav_row)

    def keyPressEvent(self, event):
        """Handle Enter/Return to advance steps or finish."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Don't advance if focused on an input field (let it handle its own Enter)
            focused = self.focusWidget()
            from PyQt6.QtWidgets import QLineEdit, QTextEdit
            if isinstance(focused, (QLineEdit, QTextEdit)):
                return super().keyPressEvent(event)
            if self._step == 0:
                # Account step has its own button
                self._on_account_action()
            elif self._next_btn.isVisible():
                self._next_step()
        else:
            super().keyPressEvent(event)

    # ── Step Builders ────────────────────────────────────────────────────

    def _build_account_step(self):
        """Step 1: Account creation (signup/login)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        # Account mode selector
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        self._account_signup_btn = QPushButton("Create Account")
        self._account_signup_btn.setCheckable(True)
        self._account_signup_btn.setChecked(True)
        self._account_signup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._account_signup_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.PRI_DIM}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; padding: 8px 16px; font-size: 9px;
            }}
            QPushButton:checked {{
                color: {HU.BRIGHT}; background: {HU.FILL2}; border: 1px solid {HU.BRIGHT};
            }}
        """)
        self._account_signup_btn.clicked.connect(lambda: self._set_account_mode("signup"))
        mode_row.addWidget(self._account_signup_btn)

        self._account_login_btn = QPushButton("Sign In")
        self._account_login_btn.setCheckable(True)
        self._account_login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._account_login_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.PRI_DIM}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; padding: 8px 16px; font-size: 9px;
            }}
            QPushButton:checked {{
                color: {HU.BRIGHT}; background: {HU.FILL2}; border: 1px solid {HU.BRIGHT};
            }}
        """)
        self._account_login_btn.clicked.connect(lambda: self._set_account_mode("login"))
        mode_row.addWidget(self._account_login_btn)
        mode_row.addStretch()
        lay.addLayout(mode_row)
        lay.addSpacing(8)

        # Auth form (embedded AuthOverlay-style)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        lay.addWidget(sep)
        lay.addSpacing(4)

        self._auth_email = HudLineEdit()
        self._auth_email.setPlaceholderText("you@example.com")
        self._auth_email.setFont(QFont("Courier New", 10))
        self._auth_email.setFixedHeight(32)
        lay.addWidget(_lbl("EMAIL", 8, color=C.TEXT_DIM))
        lay.addWidget(self._auth_email)
        lay.addSpacing(6)

        self._auth_pass = HudLineEdit()
        self._auth_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._auth_pass.setPlaceholderText("\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022")
        self._auth_pass.setFont(QFont("Courier New", 10))
        self._auth_pass.setFixedHeight(32)
        lay.addWidget(_lbl("PASSWORD", 8, color=C.TEXT_DIM))
        lay.addWidget(self._auth_pass)
        pw_hint = _lbl("6+ characters", 7, color=C.TEXT_DIM)
        lay.addWidget(pw_hint)
        lay.addSpacing(6)

        # Confirm password (signup only)
        self._auth_confirm_row = QWidget()
        confirm_lay = QVBoxLayout(self._auth_confirm_row)
        confirm_lay.setContentsMargins(0, 0, 0, 0)
        confirm_lay.setSpacing(4)
        self._auth_confirm = HudLineEdit()
        self._auth_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._auth_confirm.setPlaceholderText("\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022")
        self._auth_confirm.setFont(QFont("Courier New", 10))
        self._auth_confirm.setFixedHeight(32)
        confirm_lay.addWidget(_lbl("CONFIRM PASSWORD", 8, color=C.TEXT_DIM))
        confirm_lay.addWidget(self._auth_confirm)
        lay.addWidget(self._auth_confirm_row)
        lay.addSpacing(6)

        # Error label
        self._auth_error = _lbl("", 8, color=C.RED)
        lay.addWidget(self._auth_error)
        lay.addSpacing(4)

        # Action button
        self._auth_action = HudButton("\u25b8  CREATE ACCOUNT",
            cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
            border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=10)
        self._auth_action.setFixedHeight(36)
        self._auth_action.clicked.connect(self._on_account_action)
        lay.addWidget(self._auth_action)

        # Google Sign-In button
        self._google_btn = QPushButton("\u25b2  Continue with Google")
        self._google_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._google_btn.setFixedHeight(32)
        google_enabled = get_auth().is_google_configured()
        self._google_btn.setEnabled(google_enabled)
        if not google_enabled:
            self._google_btn.setToolTip("Google Sign-In not configured")
        self._google_btn.setStyleSheet(f"""
            QPushButton {{
                color: {C.TEXT}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; font-size: 9px; padding: 6px 12px;
            }}
            QPushButton:hover {{
                border: 1px solid {HU.BRIGHT}; color: {HU.BRIGHT};
            }}
            QPushButton:disabled {{
                color: {C.TEXT_DIM}; background: {C.FILL1}; border: 1px solid {C.BORDER};
            }}
        """)
        self._google_btn.clicked.connect(self._on_google_action)
        lay.addWidget(self._google_btn)

        lay.addStretch()
        self._stack.addWidget(page)

    def _build_personal_step(self):
        """Step 2: Personal information."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        lay.addWidget(_lbl("PERSONAL INFORMATION", 9, bold=True, color=C.ACC2))
        lay.addWidget(_lbl("Help SONIC address you properly", 8, color=C.TEXT_DIM))
        lay.addSpacing(4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        lay.addWidget(sep)
        lay.addSpacing(4)

        # Full name
        lay.addWidget(_lbl("FULL NAME", 8, color=C.TEXT_DIM))
        self._personal_name = HudLineEdit()
        self._personal_name.setPlaceholderText("Your full name")
        self._personal_name.setFont(QFont("Courier New", 10))
        self._personal_name.setFixedHeight(32)
        lay.addWidget(self._personal_name)
        lay.addSpacing(6)

        # Phone
        lay.addWidget(_lbl("PHONE NUMBER", 8, color=C.TEXT_DIM))
        self._personal_phone = HudLineEdit()
        self._personal_phone.setPlaceholderText("+1 555 123 4567")
        self._personal_phone.setFont(QFont("Courier New", 10))
        self._personal_phone.setFixedHeight(32)
        lay.addWidget(self._personal_phone)
        lay.addSpacing(6)

        # Location
        lay.addWidget(_lbl("LOCATION (city, country)", 8, color=C.TEXT_DIM))
        self._personal_location = HudLineEdit()
        self._personal_location.setPlaceholderText("San Francisco, USA")
        self._personal_location.setFont(QFont("Courier New", 10))
        self._personal_location.setFixedHeight(32)
        lay.addWidget(self._personal_location)
        lay.addSpacing(6)

        # Timezone
        lay.addWidget(_lbl("TIMEZONE", 8, color=C.TEXT_DIM))
        self._personal_timezone = HudLineEdit()
        self._personal_timezone.setPlaceholderText("America/Los_Angeles")
        self._personal_timezone.setFont(QFont("Courier New", 10))
        self._personal_timezone.setFixedHeight(32)
        lay.addWidget(self._personal_timezone)
        lay.addSpacing(6)

        # Auto-detect timezone
        auto_tz_btn = HudButton("\U0001f30d  Auto-detect my timezone",
            cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        auto_tz_btn.clicked.connect(self._auto_detect_timezone)
        lay.addWidget(auto_tz_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        lay.addStretch()
        self._stack.addWidget(page)

    def _build_api_step(self):
        """Step 3: API Keys."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        lay.addWidget(_lbl("API KEYS", 9, bold=True, color=C.ACC2))
        lay.addWidget(_lbl("Add API keys for external services (optional)", 8, color=C.TEXT_DIM))
        lay.addSpacing(4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        lay.addWidget(sep)
        lay.addSpacing(4)

        # Gemini API Key
        lay.addWidget(_lbl("GEMINI API KEY", 8, color=C.TEXT_DIM))
        self._api_gemini = HudLineEdit()
        self._api_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_gemini.setPlaceholderText("AIzaSy... (from Google AI Studio)")
        self._api_gemini.setFont(QFont("Courier New", 10))
        self._api_gemini.setFixedHeight(32)
        lay.addWidget(self._api_gemini)
        lay.addSpacing(6)

        # OpenAI API Key
        lay.addWidget(_lbl("OPENAI API KEY", 8, color=C.TEXT_DIM))
        self._api_openai = HudLineEdit()
        self._api_openai.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_openai.setPlaceholderText("sk-... (from platform.openai.com)")
        self._api_openai.setFont(QFont("Courier New", 10))
        self._api_openai.setFixedHeight(32)
        lay.addWidget(self._api_openai)
        lay.addSpacing(6)

        # Other keys hint
        hint = _lbl("More keys can be added later in Settings \u2192 API Keys", 7, color=C.TEXT_DIM)
        lay.addWidget(hint)

        lay.addStretch()
        self._stack.addWidget(page)

    def _build_prefs_step(self):
        """Step 4: Preferences."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        def _lbl(txt, font_size=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", font_size,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        lay.addWidget(_lbl("PREFERENCES", 9, bold=True, color=C.ACC2))
        lay.addWidget(_lbl("Customize your SONIC experience", 8, color=C.TEXT_DIM))
        lay.addSpacing(4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};")
        lay.addWidget(sep)
        lay.addSpacing(4)

        # Theme
        lay.addWidget(_lbl("UI THEME", 8, color=C.TEXT_DIM))
        theme_row = QHBoxLayout()
        theme_row.setSpacing(8)
        self._pref_theme_dark = QPushButton("Dark")
        self._pref_theme_dark.setCheckable(True)
        self._pref_theme_dark.setChecked(True)
        self._pref_theme_dark.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pref_theme_dark.setStyleSheet(f"""
            QPushButton {{
                color: {C.PRI_DIM}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; padding: 6px 16px; font-size: 9px;
            }}
            QPushButton:checked {{
                color: {HU.BRIGHT}; background: {HU.FILL2}; border: 1px solid {HU.BRIGHT};
            }}
        """)
        self._pref_theme_dark.clicked.connect(lambda: self._set_theme("dark"))
        theme_row.addWidget(self._pref_theme_dark)

        self._pref_theme_light = QPushButton("Light")
        self._pref_theme_light.setCheckable(True)
        self._pref_theme_light.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pref_theme_light.setStyleSheet(f"""
            QPushButton {{
                color: {C.PRI_DIM}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; padding: 6px 16px; font-size: 9px;
            }}
            QPushButton:checked {{
                color: {HU.BRIGHT}; background: {HU.FILL2}; border: 1px solid {HU.BRIGHT};
            }}
        """)
        self._pref_theme_light.clicked.connect(lambda: self._set_theme("light"))
        theme_row.addWidget(self._pref_theme_light)
        theme_row.addStretch()
        lay.addLayout(theme_row)
        lay.addSpacing(12)

        # Voice
        lay.addWidget(_lbl("VOICE LANGUAGE", 8, color=C.TEXT_DIM))
        self._pref_voice = HudLineEdit()
        self._pref_voice.setPlaceholderText("en-US  (or hi-IN, es-ES, etc.)")
        self._pref_voice.setFont(QFont("Courier New", 10))
        self._pref_voice.setFixedHeight(32)
        self._pref_voice.setText("en-US")
        lay.addWidget(self._pref_voice)
        lay.addSpacing(6)

        # Assistant name
        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM))
        self._pref_assistant_name = HudLineEdit()
        self._pref_assistant_name.setPlaceholderText("SONIC")
        self._pref_assistant_name.setFont(QFont("Courier New", 10))
        self._pref_assistant_name.setFixedHeight(32)
        self._pref_assistant_name.setText("SONIC")
        lay.addWidget(self._pref_assistant_name)
        lay.addSpacing(6)

        # Your name
        lay.addWidget(_lbl("YOUR NAME (how SONIC addresses you)", 8, color=C.TEXT_DIM))
        self._pref_user_name = HudLineEdit()
        self._pref_user_name.setPlaceholderText("Captain / Sir / Your Name")
        self._pref_user_name.setFont(QFont("Courier New", 10))
        self._pref_user_name.setFixedHeight(32)
        lay.addWidget(self._pref_user_name)
        lay.addSpacing(6)

        # Language (for AI responses)
        lay.addWidget(_lbl("AI RESPONSE LANGUAGE", 8, color=C.TEXT_DIM))
        self._pref_language = HudLineEdit()
        self._pref_language.setPlaceholderText("English / Roman Urdu / Urdu / Hindi / etc.")
        self._pref_language.setFont(QFont("Courier New", 10))
        self._pref_language.setFixedHeight(32)
        lay.addWidget(self._pref_language)
        lay.addSpacing(6)

        # Custom instructions
        lay.addWidget(_lbl("CUSTOM INSTRUCTIONS (how SONIC should behave)", 8, color=C.TEXT_DIM))
        self._pref_instructions = QTextEdit()
        self._pref_instructions.setPlaceholderText("e.g. Always respond in Roman Urdu. Be concise. Use emojis sparingly.")
        self._pref_instructions.setFont(QFont("Courier New", 9))
        self._pref_instructions.setFixedHeight(60)
        self._pref_instructions.setStyleSheet(f"""
            QTextEdit {{
                color: {C.TEXT}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                border-radius: 4px; padding: 6px;
            }}
        """)
        lay.addWidget(self._pref_instructions)

        lay.addStretch()
        self._stack.addWidget(page)

    # ── Step Navigation ────────────────────────────────────────────────

    def _update_step_ui(self):
        """Update UI for current step."""
        step_names = [
            ("STEP 1 OF 4  \u25c8  ACCOUNT SETUP", "Create your SONIC account to sync across devices"),
            ("STEP 2 OF 4  \u25c8  PERSONAL INFO", "Help SONIC address you properly"),
            ("STEP 3 OF 4  \u25c8  API KEYS", "Add API keys for external services"),
            ("STEP 4 OF 4  \u25c8  PREFERENCES", "Customize your SONIC experience"),
        ]
        title, desc = step_names[self._step]
        self._progress_lbl.setText(title)
        self._step_desc.setText(desc)
        self._progress_bar.setValue(self._step + 1)

        self._stack.setCurrentIndex(self._step)
        self._back_btn.setVisible(self._step > 0)

        # Next/Finish button (hidden on step 0 which has its own action button)
        if self._step > 0:
            self._next_btn.setVisible(True)
            self._next_btn.setText("\u25b8  FINISH" if self._step == self._STEP_COUNT - 1 else "\u25b8  CONTINUE")
        else:
            self._next_btn.setVisible(False)

    def _set_theme(self, theme: str):
        """Handle theme selection in preferences step."""
        if theme == "dark":
            self._pref_theme_dark.setChecked(True)
            self._pref_theme_light.setChecked(False)
        else:
            self._pref_theme_dark.setChecked(False)
            self._pref_theme_light.setChecked(True)

    def _go_back(self):
        if self._step > 0:
            self._step -= 1
            self._update_step_ui()

    def _on_skip(self):
        self.skipped.emit()

    # ── Account Step Logic ─────────────────────────────────────────────

    def _set_account_mode(self, mode: str):
        self._account_mode = mode
        if mode == "signup":
            self._account_signup_btn.setChecked(True)
            self._account_login_btn.setChecked(False)
            self._auth_confirm_row.setVisible(True)
            self._auth_action.setText("\u25b8  CREATE ACCOUNT")
        else:
            self._account_signup_btn.setChecked(False)
            self._account_login_btn.setChecked(True)
            self._auth_confirm_row.setVisible(False)
            self._auth_action.setText("\u25b8  SIGN IN")

    def _on_account_action(self):
        # Prevent double-click / concurrent operations
        if getattr(self, '_account_operation_in_progress', False):
            return
        self._account_operation_in_progress = True

        email = self._auth_email.text().strip()
        password = self._auth_pass.text()

        if not email or not password:
            self._auth_error.setText("Email and password required.")
            self._account_operation_in_progress = False
            return

        mode = getattr(self, '_account_mode', 'signup')

        if mode == "signup":
            confirm = self._auth_confirm.text()
            if password != confirm:
                self._auth_error.setText("Passwords don't match.")
                return
            if len(password) < 6:
                self._auth_error.setText("Password must be at least 6 characters.")
                return

        self._auth_action.setEnabled(False)
        self._auth_action.setText("  CREATING ACCOUNT..." if mode == "signup" else "  SIGNING IN...")
        self._auth_error.setText("")

        def _run():
            try:
                from auth import get_auth
                auth = get_auth()
                if mode == "signup":
                    result = auth.signup(email, password)
                else:
                    result = auth.login(email, password)

                if result.get("success"):
                    uid = auth.user_id
                else:
                    uid = None

                self._account_result.emit(result, email, uid)
            except Exception as e:
                import traceback
                traceback.print_exc()
                err = str(e)
                self._account_result.emit({"success": False, "error": err}, email, None)

        import threading
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

        # Watchdog timeout - reset loading state if operation takes too long
        def _watchdog():
            if thread.is_alive():
                self._auth_action.setEnabled(True)
                self._auth_action.setText("\u25b8  CREATE ACCOUNT" if mode == "signup" else "\u25b8  SIGN IN")
                self._auth_error.setText("Operation timed out. Please try again.")
        QTimer.singleShot(30000, _watchdog)  # 30 second timeout

    def _on_account_result(self, result: dict, email: str, uid: str):
        self._account_operation_in_progress = False
        self._auth_action.setEnabled(True)
        mode = getattr(self, '_account_mode', 'signup')
        self._auth_action.setText("\u25b8  CREATE ACCOUNT" if mode == "signup" else "\u25b8  SIGN IN")
        if result.get("success") and uid:
            self._data["email"] = email
            self._data["user_id"] = uid
            self._auth_error.setText("")
            # Check if onboarding already completed — skip to finish
            try:
                from auth import get_auth
                auth = get_auth()
                if auth.is_onboarding_completed():
                    # Load existing profile data into onboarding data
                    profile = auth.get_extended_profile().get("profile", {})
                    if profile:
                        self._data["full_name"] = profile.get("full_name", "")
                        self._data["phone"] = profile.get("phone", "")
                        self._data["location"] = profile.get("location", "")
                        self._data["timezone"] = profile.get("timezone", "")
                        self._data["api_keys"] = profile.get("api_keys", {})
                        self._data["preferences"] = profile.get("preferences", {})
                    self.completed.emit(self._data)
                    return
            except Exception:
                pass
            self._next_step()
        else:
            self._auth_error.setText(result.get("error", "Failed"))

    def _on_google_action(self):
        """Handle Google sign-in from onboarding wizard."""
        if getattr(self, '_account_operation_in_progress', False):
            return
        self._account_operation_in_progress = True
        self._google_btn.setEnabled(False)
        self._google_btn.setText("  Opening browser...")
        self._auth_error.setText("")

        def _run():
            try:
                from auth import get_auth
                result = get_auth().google_login_with_server()
                if result.get("success"):
                    uid = result.get("user_id", "")
                    email = result.get("email", "")
                    self._account_result.emit(result, email, uid)
                else:
                    self._account_result.emit(result, "", None)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._account_result.emit({"success": False, "error": str(e)}, "", None)

        import threading
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    # ── Personal Step Logic ────────────────────────────────────────────

    def _auto_detect_timezone(self):
        import datetime
        try:
            tz = datetime.datetime.now().astimezone().tzname()
            if tz:
                self._personal_timezone.setText(tz)
        except Exception:
            pass

    # ── Navigation ────────────────────────────────────────────────────

    def _next_step(self):
        if not self._validate_current_step():
            return
        if self._step < self._STEP_COUNT - 1:
            self._step += 1
            self._update_step_ui()
        else:
            self._finish()

    def _validate_current_step(self) -> bool:
        """Validate current step data before allowing navigation."""
        if self._step == self._STEP_PERSONAL:
            name = self._personal_name.text().strip()
            if not name:
                self._auth_error.setText("Full name is required")
                self._personal_name.setFocus()
                return False
            tz = self._personal_timezone.text().strip()
            if not tz:
                self._auth_error.setText("Timezone is required")
                self._personal_timezone.setFocus()
                return False
        elif self._step == self._STEP_API:
            # Validate API key formats if provided
            gemini = self._api_gemini.text().strip()
            if gemini and not (gemini.startswith("AIza") or len(gemini) > 20):
                self._auth_error.setText("Invalid Gemini API key format")
                self._api_gemini.setFocus()
                return False
            openai = self._api_openai.text().strip()
            if openai and not (openai.startswith("sk-") and len(openai) > 20):
                self._auth_error.setText("Invalid OpenAI API key format")
                self._api_openai.setFocus()
                return False
        elif self._step == self._STEP_PREFS:
            # Validate voice format if provided
            voice = self._pref_voice.text().strip()
            if voice and "-" not in voice:
                self._auth_error.setText("Voice format: en-US, hi-IN, etc.")
                self._pref_voice.setFocus()
                return False
        self._auth_error.setText("")
        return True

    def _finish(self):
        """Collect all data and emit completed signal."""
        # Show loading state on the FINISH button
        self._next_btn.setEnabled(False)
        self._next_btn.setText("  PROCESSING...")

        # Collect personal info
        self._data["full_name"] = self._personal_name.text().strip()
        self._data["phone"] = self._personal_phone.text().strip()
        self._data["location"] = self._personal_location.text().strip()
        self._data["timezone"] = self._personal_timezone.text().strip()

        # Collect API keys
        api_keys = {}
        if self._api_gemini.text().strip():
            api_keys["gemini"] = self._api_gemini.text().strip()
        if self._api_openai.text().strip():
            api_keys["openai"] = self._api_openai.text().strip()
        self._data["api_keys"] = api_keys

        # Collect preferences
        self._data["preferences"] = {
            "theme": "dark" if self._pref_theme_dark.isChecked() else "light",
            "voice": self._pref_voice.text().strip() or "en-US",
            "assistant_name": self._pref_assistant_name.text().strip() or "SONIC",
            "user_name": self._pref_user_name.text().strip() or "",
            "language": self._pref_language.text().strip() or "",
            "custom_instructions": self._pref_instructions.toPlainText().strip() or "",
        }

        self.completed.emit(self._data)


# HueWheel — imported from sonic-frontend-theme (pyqt6_theme)

class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name and UI colour."""

    saved = pyqtSignal(str, str, str)   # assistant_name, user_name, ui_color
    _OW, _OH = 400, 500

    def __init__(self, assistant_name="SONIC", user_name="",
                 ui_color=DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        lay.addWidget(_lbl("⚙  CUSTOMISE ASSISTANT", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        lay.addWidget(_lbl("ASSISTANT NAME", 8, color=C.TEXT_DIM,
                            align=Qt.AlignmentFlag.AlignLeft))
        self._name_input = HudLineEdit()
        self._name_input.setText(assistant_name)
        self._name_input.setFont(QFont("Courier New", 10))
        self._name_input.setFixedHeight(32)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        lay.addWidget(_lbl("YOUR NAME  (leave blank for default sir / efendim)", 8,
                            color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        self._user_input = HudLineEdit()
        self._user_input.setText(user_name)
        self._user_input.setPlaceholderText("e.g.  Tony   (leave blank for auto)")
        self._user_input.setFont(QFont("Courier New", 10))
        self._user_input.setFixedHeight(32)
        lay.addWidget(self._user_input)

        # ── UI colour — renk çarkı ───────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        clr_hdr.addWidget(_lbl("UI COLOUR  —  drag the handle", 8,
                               color=C.TEXT_DIM, align=Qt.AlignmentFlag.AlignLeft))
        clr_hdr.addStretch()
        df_btn = HudButton("DEFAULT",
                            cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        df_btn.setFixedSize(64, 20)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — canlı önizleme; MainWindow bağlar

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = HudLineEdit()
        self._hex_input.setText(self._sel_color)
        self._hex_input.setPlaceholderText("#00d4ff   (custom hex colour)")
        self._hex_input.setFont(QFont("Courier New", 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        save_btn = HudButton("▸  APPLY CHANGES",
                              cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                              border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=9)
        save_btn.setFixedHeight(34)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = HudButton("CANCEL",
                                cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                                border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=9)
        cancel_btn.setFixedHeight(34)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── renk akışı ───────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Seçili rengi günceller; hex kutusu + çark senkron kalır, tema canlı önizlenir."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # Sürükleme sırasında: hex kutusunu güncelle, temayı henüz uygulama
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Tutamaç bırakıldı → tüm arayüzü canlı önizle
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # Önizleme uygulandıysa açılıştaki renge geri dön
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "SONIC"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR)
        self.hide()


class ProfileEditorOverlay(QWidget):
    """Floating overlay — edit profile, API keys and preferences."""

    saved = pyqtSignal(dict)  # emits all updated data
    _OW, _OH = 460, 580

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ProfileEditorOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 20, 14)
        lay.setSpacing(6)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignLeft):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        # Header
        lay.addWidget(_lbl("PROFILE & SETTINGS", 11, True, HU.BRIGHT, Qt.AlignmentFlag.AlignCenter))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        # Scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)

        # ── Personal Info ──
        cl.addWidget(_lbl("PERSONAL INFORMATION", 8, True, C.ACC2))

        cl.addWidget(_lbl("FULL NAME", 7, color=C.TEXT_DIM))
        self._name_input = HudLineEdit()
        self._name_input.setFont(QFont("Courier New", 9))
        self._name_input.setFixedHeight(28)
        cl.addWidget(self._name_input)

        cl.addWidget(_lbl("PHONE", 7, color=C.TEXT_DIM))
        self._phone_input = HudLineEdit()
        self._phone_input.setFont(QFont("Courier New", 9))
        self._phone_input.setFixedHeight(28)
        cl.addWidget(self._phone_input)

        cl.addWidget(_lbl("LOCATION", 7, color=C.TEXT_DIM))
        self._location_input = HudLineEdit()
        self._location_input.setFont(QFont("Courier New", 9))
        self._location_input.setFixedHeight(28)
        cl.addWidget(self._location_input)

        cl.addWidget(_lbl("TIMEZONE", 7, color=C.TEXT_DIM))
        self._tz_input = HudLineEdit()
        self._tz_input.setFont(QFont("Courier New", 9))
        self._tz_input.setFixedHeight(28)
        cl.addWidget(self._tz_input)

        cl.addSpacing(4)

        # ── API Keys ──
        cl.addWidget(_lbl("API KEYS", 8, True, C.ACC2))

        cl.addWidget(_lbl("GEMINI API KEY", 7, color=C.TEXT_DIM))
        self._gemini_input = HudLineEdit()
        self._gemini_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._gemini_input.setPlaceholderText("AIzaSy...")
        self._gemini_input.setFont(QFont("Courier New", 9))
        self._gemini_input.setFixedHeight(28)
        cl.addWidget(self._gemini_input)

        cl.addWidget(_lbl("OPENAI API KEY", 7, color=C.TEXT_DIM))
        self._openai_input = HudLineEdit()
        self._openai_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_input.setPlaceholderText("sk-...")
        self._openai_input.setFont(QFont("Courier New", 9))
        self._openai_input.setFixedHeight(28)
        cl.addWidget(self._openai_input)

        cl.addSpacing(4)

        # ── Preferences ──
        cl.addWidget(_lbl("PREFERENCES", 8, True, C.ACC2))

        cl.addWidget(_lbl("ASSISTANT NAME", 7, color=C.TEXT_DIM))
        self._assistant_input = HudLineEdit()
        self._assistant_input.setFont(QFont("Courier New", 9))
        self._assistant_input.setFixedHeight(28)
        cl.addWidget(self._assistant_input)

        cl.addWidget(_lbl("YOUR NAME", 7, color=C.TEXT_DIM))
        self._user_name_input = HudLineEdit()
        self._user_name_input.setFont(QFont("Courier New", 9))
        self._user_name_input.setFixedHeight(28)
        cl.addWidget(self._user_name_input)

        cl.addWidget(_lbl("VOICE LANGUAGE", 7, color=C.TEXT_DIM))
        self._voice_input = HudLineEdit()
        self._voice_input.setFont(QFont("Courier New", 9))
        self._voice_input.setFixedHeight(28)
        cl.addWidget(self._voice_input)

        cl.addWidget(_lbl("THEME", 7, color=C.TEXT_DIM))
        theme_row = QHBoxLayout()
        self._theme_dark = QPushButton("Dark")
        self._theme_dark.setCheckable(True)
        self._theme_dark.setChecked(True)
        self._theme_dark.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_dark.setStyleSheet(f"""
            QPushButton {{ color: {C.PRI_DIM}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                           border-radius: 4px; padding: 4px 12px; font-size: 8px; }}
            QPushButton:checked {{ color: {HU.BRIGHT}; background: {HU.FILL2}; border: 1px solid {HU.BRIGHT}; }}
        """)
        self._theme_dark.clicked.connect(lambda: self._set_theme("dark"))
        theme_row.addWidget(self._theme_dark)

        self._theme_light = QPushButton("Light")
        self._theme_light.setCheckable(True)
        self._theme_light.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_light.setStyleSheet(f"""
            QPushButton {{ color: {C.PRI_DIM}; background: {HU.FILL2}; border: 1px solid {C.BORDER};
                           border-radius: 4px; padding: 4px 12px; font-size: 8px; }}
            QPushButton:checked {{ color: {HU.BRIGHT}; background: {HU.FILL2}; border: 1px solid {HU.BRIGHT}; }}
        """)
        self._theme_light.clicked.connect(lambda: self._set_theme("light"))
        theme_row.addWidget(self._theme_light)
        theme_row.addStretch()
        cl.addLayout(theme_row)

        cl.addSpacing(6)

        # Error label
        self._error_lbl = _lbl("", 7, color=C.RED)
        cl.addWidget(self._error_lbl)

        cl.addStretch()
        scroll.setWidget(content)
        lay.addWidget(scroll, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        save_btn = HudButton("SAVE CHANGES",
                             cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                             border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=9)
        save_btn.setFixedHeight(32)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        cancel_btn = HudButton("CANCEL",
                               cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                               border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=9)
        cancel_btn.setFixedHeight(32)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)

        lay.addLayout(btn_row)

    def _set_theme(self, theme: str):
        if theme == "dark":
            self._theme_dark.setChecked(True)
            self._theme_light.setChecked(False)
        else:
            self._theme_dark.setChecked(False)
            self._theme_light.setChecked(True)

    def load_data(self):
        """Load current profile data from auth and config."""
        try:
            from auth import get_auth
            from memory.config_manager import load_api_keys
            auth = get_auth()

            # Personal info from profile
            if auth.is_authenticated and auth.current_user:
                result = {}
                try:
                    result = auth.get_extended_profile() or {}
                except Exception:
                    pass
                profile = result.get("profile", {})
                self._name_input.setText(profile.get("full_name", ""))
                self._phone_input.setText(profile.get("phone", ""))
                self._location_input.setText(profile.get("location", ""))
                self._tz_input.setText(profile.get("timezone", ""))
                prefs = profile.get("preferences", {})
                if isinstance(prefs, str):
                    import json
                    try: prefs = json.loads(prefs)
                    except Exception: prefs = {}
                self._assistant_input.setText(prefs.get("assistant_name", "SONIC"))
                self._user_name_input.setText(prefs.get("user_name", ""))
                self._voice_input.setText(prefs.get("voice", "en-US"))
                if prefs.get("theme") == "light":
                    self._set_theme("light")
                else:
                    self._set_theme("dark")

            # API keys from config
            api = load_api_keys()
            self._gemini_input.setText(api.get("gemini_api_key", api.get("gemini", "")))
            self._openai_input.setText(api.get("openai", ""))
        except Exception as e:
            self._error_lbl.setText(f"Load error: {e}")

    def _save(self):
        data = {
            "full_name": self._name_input.text().strip(),
            "phone": self._phone_input.text().strip(),
            "location": self._location_input.text().strip(),
            "timezone": self._tz_input.text().strip(),
            "api_keys": {},
            "preferences": {
                "assistant_name": self._assistant_input.text().strip() or "SONIC",
                "user_name": self._user_name_input.text().strip(),
                "voice": self._voice_input.text().strip() or "en-US",
                "theme": "dark" if self._theme_dark.isChecked() else "light",
            },
        }
        gemini = self._gemini_input.text().strip()
        openai = self._openai_input.text().strip()
        if gemini:
            data["api_keys"]["gemini"] = gemini
        if openai:
            data["api_keys"]["openai"] = openai

        self.saved.emit(data)
        self.hide()

    def _cancel(self):
        self.hide()


class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel("🧩  PLUGIN MANAGER")
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel("No plugins found in /plugins.")
            empty.setFont(QFont("Courier New", 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = HudButton("CLOSE",
                               cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                               border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=9)
        close_btn.setFixedHeight(30)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Courier New", 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        lbl.setToolTip(p["description"] if p["valid"] else p["error"])
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = HudButton("",
                         cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                         border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        btn.setFixedSize(72, 24)
        if not p["valid"]:
            btn.setText("BROKEN")
            btn.setEnabled(False)
            btn.set_theme(border=HU.BORDER, fill=HU.FILL, color=HU.DIM)
        else:
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: HudButton, enabled: bool):
        if enabled:
            btn.setText("ON")
            btn.set_theme(border=HU.GREEN, fill=C.GREEN_D, color=HU.GREEN)
        else:
            btn.setText("OFF")
            btn.set_theme(border=HU.BORDER, fill=HU.FILL, color=HU.DIM)

    def _toggle(self, name: str, btn: HudButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class ClipboardPanel(QWidget):
    """Floating panel shown when text is copied — offers quick Sonic actions."""

    action_requested = pyqtSignal(str)
    _W, _H = 326, 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ClipboardPanel {{
                background: rgba(0, 8, 14, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._W)
        self._clip_text = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 7)
        lay.setSpacing(4)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("◈  CLIPBOARD DETECTED")
        icon_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: {C.ACC2}; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = HudButton("✕",
                           cuts=[("tl", 3), ("tr", 3), ("bl", 3), ("br", 3)],
                           border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        x_btn.setFixedSize(16, 16)
        x_btn.clicked.connect(self.hide)
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._preview = QLabel()
        self._preview.setFont(QFont("Courier New", 8))
        self._preview.setStyleSheet(f"""
            color: {C.TEXT}; background: {C.PANEL2};
            border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 6px;
        """)
        self._preview.setWordWrap(False)
        self._preview.setFixedHeight(28)
        lay.addWidget(self._preview)

        btn_row = QHBoxLayout(); btn_row.setSpacing(4)
        for label, cmd_fmt in [
            ("TRANSLATE", "Translate this text to English: {text}"),
            ("SUMMARISE", "Summarise this: {text}"),
            ("EXPLAIN",   "Explain this: {text}"),
            ("FIX",       "Fix grammar and spelling: {text}"),
        ]:
            b = HudButton(label,
                           cuts=[("tl", 3), ("tr", 3), ("bl", 3), ("br", 3)],
                           border=HU.BORDER, fill=HU.FILL2, color=HU.DIM, font_size=7)
            b.setFixedHeight(22)
            b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.hide)
        self.hide()

    def _trigger(self, cmd_fmt: str):
        if self._clip_text:
            self.action_requested.emit(cmd_fmt.format(text=self._clip_text[:800]))
        self.hide()

    def show_clipboard(self, text: str):
        self._clip_text = text
        preview = text[:58].replace('\n', ' ')
        if len(text) > 58:
            preview += "…"
        self._preview.setText(f'"{preview}"')
        self.show(); self.raise_()
        self._dismiss_timer.start(8000)


class _ConfirmBanner(QWidget):
    """Floating confirmation banner for irreversible actions (shutdown, restart, WiFi)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            _ConfirmBanner {{
                background: rgba(0, 6, 10, 248);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(360)
        self._resolve = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        hdr = QHBoxLayout(); hdr.setSpacing(4)
        icon_lbl = QLabel("⚠  CONFIRMATION REQUIRED")
        icon_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        icon_lbl.setStyleSheet(f"color: #ff8844; background: transparent;")
        hdr.addWidget(icon_lbl); hdr.addStretch()
        x_btn = HudButton("✕",
                           cuts=[("tl", 3), ("tr", 3), ("bl", 3), ("br", 3)],
                           border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        x_btn.setFixedSize(16, 16)
        x_btn.clicked.connect(lambda: self._do_resolve(False))
        hdr.addWidget(x_btn)
        lay.addLayout(hdr)

        self._title_lbl = QLabel()
        self._title_lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        self._title_lbl.setWordWrap(True)
        lay.addWidget(self._title_lbl)

        self._detail_lbl = QLabel()
        self._detail_lbl.setFont(QFont("Courier New", 8))
        self._detail_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        self._detail_lbl.setWordWrap(True)
        lay.addWidget(self._detail_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        confirm_btn = HudButton("CONFIRM",
                                 cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                 border="#ff8844", fill="#ff8844", color="#ffffff", font_size=8)
        confirm_btn.setFixedHeight(24)
        confirm_btn.clicked.connect(lambda: self._do_resolve(True))
        btn_row.addWidget(confirm_btn)

        cancel_btn = HudButton("CANCEL",
                                cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        cancel_btn.setFixedHeight(24)
        cancel_btn.clicked.connect(lambda: self._do_resolve(False))
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._do_resolve(False))

    def show_banner(self, title: str, detail: str, resolve_cb):
        self._title_lbl.setText(title)
        self._detail_lbl.setText(detail)
        self._resolve = resolve_cb
        self.show()
        self.raise_()
        self._timer.start(90_000)

    def _do_resolve(self, accepted: bool):
        self._timer.stop()
        cb = self._resolve
        self._resolve = None
        self.hide()
        if cb:
            try:
                cb(accepted)
            except Exception:
                pass


class RemoteKeyOverlay(QWidget):
    """Floating overlay — QR code for instant phone pairing + manual key fallback."""

    closed = pyqtSignal()

    _OW, _OH = 400, 465

    def __init__(self, url: str, key: str, auto_login_url: str = "",
                 manual_url: str = "", expiry_secs: int = 600, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            RemoteKeyOverlay {{
                background: rgba(0, 4, 12, 0.95);
                border: 1px solid {C.BORDER_B};
                border-radius: 14px;
            }}
        """)
        self._expiry          = time.time() + expiry_secs
        self._on_new_key      = None
        self._auto_login_url  = auto_login_url
        self._manual_url      = manual_url or url

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 16, 24, 16)
        lay.setSpacing(5)

        def _lbl(txt, fs=9, bold=False, color=C.PRI,
                 align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt)
            w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            w.setWordWrap(True)
            return w

        lay.addWidget(_lbl("◈  REMOTE ACCESS", 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep)

        # ── QR code ───────────────────────────────────────────────────────────
        self._qr_label = QLabel()
        self._qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qr_label.setFixedSize(176, 176)
        self._qr_label.setStyleSheet(
            "background: white; border-radius: 10px; padding: 4px;"
        )
        qr_row = QHBoxLayout()
        qr_row.addStretch()
        qr_row.addWidget(self._qr_label)
        qr_row.addStretch()
        lay.addLayout(qr_row)

        self._update_qr(auto_login_url)

        lay.addWidget(_lbl("Scan with phone camera to connect instantly", 8, color=C.TEXT_DIM))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {C.BORDER}; margin: 1px 0;")
        lay.addWidget(sep2)

        lay.addWidget(_lbl("Or enter manually:", 7, color=C.TEXT_DIM,
                           align=Qt.AlignmentFlag.AlignLeft))

        self._url_lbl = QLabel(self._manual_url)
        self._url_lbl.setFont(QFont("Courier New", 8))
        self._url_lbl.setStyleSheet(f"color: {C.PRI_DIM}; background: transparent;")
        self._url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._url_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._url_lbl)

        self._key_lbl = QLabel(key)
        self._key_lbl.setFont(QFont("Courier New", 28, QFont.Weight.Bold))
        self._key_lbl.setStyleSheet(f"""
            color: {C.ACC};
            background: {C.PANEL2};
            border: 1px solid {C.BORDER_B};
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 10px;
        """)
        self._key_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._key_lbl)

        self._timer_lbl = QLabel()
        self._timer_lbl.setFont(QFont("Courier New", 8))
        self._timer_lbl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        self._timer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._timer_lbl)

        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        new_btn = HudButton("NEW KEY",
                             cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                             border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=8)
        new_btn.setFixedHeight(32)
        new_btn.clicked.connect(self._refresh_key)
        btn_row.addWidget(new_btn)

        close_btn = HudButton("DISMISS",
                               cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                               border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        close_btn.setFixedHeight(32)
        close_btn.clicked.connect(self._do_close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        self._ctimer = QTimer(self)
        self._ctimer.timeout.connect(self._tick)
        self._ctimer.start(1000)
        self._tick()

    def set_new_key_callback(self, fn) -> None:
        self._on_new_key = fn

    def _update_qr(self, url: str) -> None:
        if not url:
            self._qr_label.setText("—")
            return
        try:
            import qrcode as _qrmod
            from io import BytesIO
            qr = _qrmod.QRCode(
                box_size=5, border=2,
                error_correction=_qrmod.constants.ERROR_CORRECT_M,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            img.save(buf, format="PNG")
            px = QPixmap()
            px.loadFromData(buf.getvalue())
            self._qr_label.setPixmap(
                px.scaled(170, 170,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        except ImportError:
            self._qr_label.setText("pip install\nqrcode[pil]")
            self._qr_label.setFont(QFont("Courier New", 8))
            self._qr_label.setStyleSheet(
                "color: #888; background: white; border-radius: 10px; padding: 4px;"
            )
        except Exception:
            self._qr_label.setText(url[:28])
            self._qr_label.setFont(QFont("Courier New", 7))
            self._qr_label.setStyleSheet(
                f"color: {C.PRI}; background: white; border-radius: 10px; padding: 4px;"
            )

    def _tick(self):
        remaining = max(0, int(self._expiry - time.time()))
        m, s = divmod(remaining, 60)
        self._timer_lbl.setText(f"Key expires in  {m:02d}:{s:02d}")
        if remaining == 0:
            self._do_close()

    def mark_connected(self) -> None:
        """Call from any thread when a phone successfully connects."""
        self._ctimer.stop()
        self._key_lbl.setText("CONNECTED")
        self._key_lbl.setStyleSheet(f"""
            color: {C.GREEN};
            background: rgba(34,197,94,0.08);
            border: 2px solid rgba(34,197,94,0.4);
            border-radius: 8px;
            padding: 6px 4px;
            letter-spacing: 4px;
        """)
        self._qr_label.setText("✓")
        self._qr_label.setFont(QFont("Courier New", 54, QFont.Weight.Bold))
        self._qr_label.setStyleSheet(
            f"color: {C.GREEN}; background: {C.GREEN_D}; border-radius: 10px;"
        )
        self._timer_lbl.setText("Phone connected — SONIC ready")
        self._timer_lbl.setStyleSheet(f"color: {C.GREEN}; background: transparent;")

    def _refresh_key(self):
        if self._on_new_key:
            result = self._on_new_key()
            if result:
                url    = result[0]
                key    = result[1]
                auto   = result[2] if len(result) >= 3 else ""
                manual = result[3] if len(result) >= 4 else url
                self._manual_url     = manual or url
                self._url_lbl.setText(self._manual_url)
                self._key_lbl.setText(key)
                self._auto_login_url = auto
                self._update_qr(auto or url)
                self._expiry = time.time() + 600
                self._key_lbl.setStyleSheet(f"""
                    color: {C.ACC};
                    background: {C.PANEL2};
                    border: 1px solid {C.BORDER_B};
                    border-radius: 8px;
                    padding: 6px 4px;
                    letter-spacing: 10px;
                """)
                self._timer_lbl.setStyleSheet(
                    f"color: {C.TEXT_MED}; background: transparent;"
                )
                self._ctimer.start(1000)
                self._tick()

    def _do_close(self):
        self._ctimer.stop()
        self.hide()
        self.closed.emit()


class MainWindow(QMainWindow):
    _log_sig        = pyqtSignal(str)
    _state_sig      = pyqtSignal(str)
    _content_sig    = pyqtSignal(str, str)   # (title, text) — thread-safe content display
    _reconfig_sig   = pyqtSignal()           # trigger setup overlay from any thread
    _camera_sig     = pyqtSignal(bytes)      # show camera frame preview (small overlay)
    _cam_stream_sig = pyqtSignal(bool)       # True=start live stream, False=stop
    _cam_frame_sig  = pyqtSignal(bytes)      # live camera frame → HUD area
    _clipboard_sig  = pyqtSignal(str)        # clipboard text changed (thread-safe)
    _confirm_sig    = pyqtSignal(str, str)   # (title, detail) confirmation banner
    _confirm_hide_sig = pyqtSignal()         # hide confirmation banner
    auth_completed  = pyqtSignal()           # emitted when auth & onboarding are complete

    def __init__(self, face_path: str):
        super().__init__()
        self._face_path = face_path

        # Load customization from config
        _cfg = _read_full_config()
        self._assistant_name: str = (_cfg.get("assistant_name") or "SONIC").strip()
        _display = self._assistant_name.upper()

        # Kayıtlı UI rengini panel/stylesheet'ler kurulmadan ÖNCE uygula
        _ui_color = (_cfg.get("ui_color") or "").strip()
        if _ui_color and _ui_color.lower() != DEFAULT_UI_COLOR:
            apply_ui_accent(_ui_color)

        self.setWindowTitle(f"{_display} — SONIC")
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(_DEFAULT_W, _DEFAULT_H)

        # Set window icon for taskbar/titlebar
        _icon_path = Path(__file__).resolve().parent / "config" / "sonic.ico"
        if _icon_path.exists():
            from PyQt6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(_icon_path)))

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            (screen.width()  - _DEFAULT_W) // 2,
            (screen.height() - _DEFAULT_H) // 2,
        )

        self.on_text_command   = None
        self.on_remote_clicked = None   # callable: () -> (url, key) | None
        self.on_interrupt      = None   # callable: () -> None — stop SONIC mid-speech
        self.get_plugins       = None   # callable: () -> list[dict], set by SonicLive
        self._muted            = False
        self._current_file: str | None = None
        self._remote_overlay: RemoteKeyOverlay | None = None
        self._customize_overlay: CustomizeOverlay | None = None
        self._profile_editor_overlay: ProfileEditorOverlay | None = None

        central = QWidget()
        central.setStyleSheet(f"background: {C.BG};")
        self.setCentralWidget(central)
        self._backdrop = AmbientBackdrop(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._left_panel = self._build_left_panel()
        body.addWidget(self._left_panel, stretch=0)

        # Center column: HUD + resizable content panel via QSplitter
        self.hud = HudCanvas(face_path, _display)
        self.hud.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Live camera container — replaces HUD when camera stream is active
        _cam_cont = HudPanel(cuts=[("tl", 6), ("tr", 6), ("bl", 6), ("br", 6)],
                             border=HU.BORDER, fill="#000308", glow=False)
        _cam_v = QVBoxLayout(_cam_cont)
        _cam_v.setContentsMargins(0, 0, 0, 0)
        _cam_v.setSpacing(0)
        _cam_hdr = QHBoxLayout()
        _cam_hdr.setContentsMargins(8, 5, 8, 5)
        _cam_title = QLabel("◈  CAMERA FEED")
        _cam_title.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        _cam_title.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        _cam_hdr.addWidget(_cam_title)
        _cam_hdr.addStretch()
        _cam_x = HudButton("✕  CLOSE",
                            cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=8)
        _cam_x.setFixedSize(70, 22)
        _cam_x.clicked.connect(self.stop_camera_stream)
        _cam_hdr.addWidget(_cam_x)
        _cam_v.addLayout(_cam_hdr)
        self._cam_live_lbl = QLabel()
        self._cam_live_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cam_live_lbl.setStyleSheet("background: transparent;")
        self._cam_live_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _cam_v.addWidget(self._cam_live_lbl, stretch=1)

        # Stack: 0 = animated HUD, 1 = live camera
        self._hud_cam_stack = QStackedWidget()
        self._hud_cam_stack.addWidget(self.hud)
        self._hud_cam_stack.addWidget(_cam_cont)

        self._content_panel = self._build_content_panel()
        self._command_bar = self._build_command_bar()

        self._center_split = QSplitter(Qt.Orientation.Vertical)
        self._center_split.setStyleSheet(f"""
            QSplitter::handle {{
                background: {C.BORDER};
                height: 4px;
            }}
            QSplitter::handle:hover {{
                background: {C.PRI_DIM};
            }}
        """)
        self._center_split.addWidget(self._hud_cam_stack)
        self._center_split.addWidget(self._command_bar)
        self._center_split.addWidget(self._content_panel)
        self._center_split.setStretchFactor(0, 5)
        self._center_split.setStretchFactor(1, 0)
        self._center_split.setStretchFactor(2, 1)
        self._center_split.setCollapsible(0, False)
        self._center_split.setCollapsible(1, False)
        body.addWidget(self._center_split, stretch=5)

        self._right_panel = self._build_right_panel()
        body.addWidget(self._right_panel, stretch=0)

        root.addLayout(body, stretch=1)
        root.addWidget(self._build_footer())

        self._update_autostart_btn(self._check_autostart())
        from memory.config_manager import get_brief_enabled as _gbe
        self._update_brief_btn(_gbe())

        self._clock_tmr = QTimer(self)
        self._clock_tmr.timeout.connect(self._tick_clock)
        self._clock_tmr.start(1000)
        self._tick_clock()

        # Metrik güncelleme timer'ı
        self._metric_tmr = QTimer(self)
        self._metric_tmr.timeout.connect(self._update_metrics)
        self._metric_tmr.start(2000)
        self._update_metrics()

        # Audio visualizer timer — polls audio level from SonicLive and updates orb
        self._viz_timer = QTimer(self)
        self._viz_timer.timeout.connect(self._update_viz)
        self._viz_timer.start(33)  # ~30fps
        self._sonic_live = None  # set by SonicLive.__init__

        self._log_sig.connect(self._log.append_log)
        self._state_sig.connect(self._apply_state)
        self._content_sig.connect(self._show_content)
        self._reconfig_sig.connect(self._show_setup)
        self._camera_sig.connect(self._show_camera_frame)
        self._cam_stream_sig.connect(self._on_cam_stream)
        self._cam_frame_sig.connect(self._on_cam_frame)
        self._clipboard_sig.connect(self._show_clipboard_panel)
        self._confirm_sig.connect(self._show_confirm_banner)
        self._confirm_hide_sig.connect(self._hide_confirm_banner)
        self._cam_stop = threading.Event()

        # Camera preview overlay (child of central widget, positioned in resizeEvent)
        self._cam_preview = _CameraPreview(self.centralWidget())

        # Clipboard panel (child of central widget, bottom-center)
        self._clipboard_panel = ClipboardPanel(self.centralWidget())
        self._clipboard_panel.action_requested.connect(self._on_clipboard_action)
        QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)

        # Confirmation banner (child of central widget, top-center)
        self._confirm_banner = _ConfirmBanner(self.centralWidget())
        self._confirm_banner.hide()

        self._overlay: SetupOverlay | None = None
        self._auth_overlay: AuthOverlay | None = None
        self._auth_user_id: str = ""
        self._auth_email: str = ""
        self._ready = self._check_config()
        if self._ready:
            self._check_auth()
        else:
            self._show_setup()

        sc_mute = QShortcut(QKeySequence("F4"), self)
        sc_mute.activated.connect(self._toggle_mute)
        sc_full = QShortcut(QKeySequence("F11"), self)
        sc_full.activated.connect(self._toggle_fullscreen)
        sc_intr = QShortcut(QKeySequence("Escape"), self)
        sc_intr.activated.connect(self._do_interrupt)

    def _show_camera_frame(self, img_bytes: bytes):
        """Slot — display camera preview overlay (main thread)."""
        self._cam_preview.show_frame(img_bytes)
        cw = self.centralWidget()
        pw = _CameraPreview._W
        ph = self._cam_preview.height()
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )

    # --- Live camera stream in HUD area ------------------------------------
    def _on_cam_stream(self, start: bool) -> None:
        if start:
            self._hud_cam_stack.setCurrentIndex(1)
        else:
            self._hud_cam_stack.setCurrentIndex(0)
            self._cam_live_lbl.clear()

    def _on_cam_frame(self, data: bytes) -> None:
        px = QPixmap()
        px.loadFromData(data)
        if not px.isNull():
            w, h = self._cam_live_lbl.width(), self._cam_live_lbl.height()
            if w > 1 and h > 1:
                self._cam_live_lbl.setPixmap(
                    px.scaled(w, h,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
                )

    def start_camera_stream(self) -> None:
        self._cam_stop.clear()
        self._cam_stream_sig.emit(True)
        t = threading.Thread(target=self._cam_loop, daemon=True, name="cam-stream")
        t.start()

    def _cam_loop(self) -> None:
        try:
            import cv2
            # Reuse camera index detected by screen_processor (cached in api_keys.json)
            cam_idx = 0
            try:
                import json as _j
                cfg = _j.loads((CONFIG_DIR / "api_keys.json").read_text())
                cam_idx = int(cfg.get("camera_index", 0))
            except Exception:
                pass
            try:
                backend = cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY
            except AttributeError:
                backend = 0
            cap = cv2.VideoCapture(cam_idx, backend)
            if not cap.isOpened():
                cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return
            # warm-up frames
            for _ in range(5):
                cap.read()
            while not self._cam_stop.wait(0.033) and cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 65])
                    self._cam_frame_sig.emit(buf.tobytes())
            cap.release()
        except Exception as e:
            print(f"[Camera] Stream error: {e}")
        finally:
            self._cam_stream_sig.emit(False)

    def stop_camera_stream(self) -> None:
        self._cam_stop.set()

    # ------------------------------------------------------------------
    # Icon generation — arc-reactor style, rendered with Pillow
    # ------------------------------------------------------------------
    @staticmethod
    def _build_sonic_icon(out_path: Path) -> bool:
        """
        Render a SONIC arc-reactor icon at 4× resolution and downsample
        for crisp results at all sizes. Saves a multi-res .ico to out_path.
        Returns True on success.
        """
        try:
            import math
            import PIL.Image
            import PIL.ImageDraw
            import PIL.ImageFilter
        except ImportError:
            return False

        CYAN   = (0, 212, 255)
        DIM    = (0, 100, 140)
        DARK   = (0, 6, 10)
        GLOW   = (0, 160, 200)
        WHITE  = (220, 240, 255)

        def _render(sz: int) -> PIL.Image.Image:
            S  = sz * 4                     # draw at 4× then downscale
            img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            d   = PIL.ImageDraw.Draw(img)
            cx = cy = S // 2

            # ── filled background circle ──────────────────────────────────
            R = S // 2 - 2
            d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

            # ── outer border ring ─────────────────────────────────────────
            lw = max(2, S // 40)
            d.ellipse([cx-R, cy-R, cx+R, cy+R],
                      outline=(*CYAN, 220), width=lw)

            # ── mid decorative ring ───────────────────────────────────────
            R2 = int(R * 0.72)
            d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                      outline=(*DIM, 180), width=max(1, lw // 2))

            # ── 6 radial spokes (hex bolt) ────────────────────────────────
            R_inner = int(R * 0.30)
            R_outer = int(R * 0.62)
            spoke_w = max(1, S // 80)
            for i in range(6):
                angle = math.radians(i * 60 - 30)
                x1 = cx + int(R_inner * math.cos(angle))
                y1 = cy + int(R_inner * math.sin(angle))
                x2 = cx + int(R_outer * math.cos(angle))
                y2 = cy + int(R_outer * math.sin(angle))
                d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

            # ── 6 tick marks on outer ring ────────────────────────────────
            for i in range(6):
                angle = math.radians(i * 60)
                for dr in range(lw * 2):
                    rx = (R - lw - dr)
                    d.point(
                        [cx + int(rx * math.cos(angle)),
                         cy + int(rx * math.sin(angle))],
                        fill=(*WHITE, 220),
                    )

            # ── inner glowing ring ────────────────────────────────────────
            Ri = int(R * 0.26)
            d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                      outline=(*CYAN, 255), width=max(2, lw))

            # ── bright glow soft blur applied before core ─────────────────
            # (draw a slightly larger cyan circle on a separate layer)
            glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
            gd = PIL.ImageDraw.Draw(glow_layer)
            Rc = int(R * 0.13)
            gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                       fill=(*CYAN, 110))
            glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
            img = PIL.Image.alpha_composite(img, glow_layer)
            d   = PIL.ImageDraw.Draw(img)

            # ── core dot ──────────────────────────────────────────────────
            d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

            # ── downscale to target size ──────────────────────────────────
            return img.resize((sz, sz), PIL.Image.LANCZOS)

        try:
            sizes  = [256, 128, 64, 48, 32, 16]
            frames = [_render(s) for s in sizes]
            frames[0].save(
                out_path,
                format="ICO",
                append_images=frames[1:],
                sizes=[(s, s) for s in sizes],
            )
            return True
        except Exception as e:
            print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
            return False

    @staticmethod
    def _create_lnk_windows(lnk: str, target: str, args: str,
                             work_dir: str, icon_loc: str) -> None:
        """
        Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd.
        Tries win32com (pywin32) first; falls back to wscript.exe + VBScript.
        wscript.exe is a GUI-mode host — it never opens a console window.
        """
        # ── Option 1: pywin32 (pure Python COM, zero subprocess) ──────────
        try:
            from win32com.client import Dispatch   # type: ignore
            sh = Dispatch("WScript.Shell")
            sc = sh.CreateShortCut(lnk)
            sc.TargetPath       = target
            sc.Arguments        = f'"{args}"'
            sc.WorkingDirectory = work_dir
            sc.Description      = "S.O.N.I.C AI Assistant"
            sc.IconLocation     = icon_loc
            sc.save()
            return
        except ImportError:
            pass

        # ── Option 2: wscript.exe + VBScript (always available on Windows,
        #    GUI-mode executable — never opens a console window) ────────────
        vbs = "\n".join([
            'Set ws = CreateObject("WScript.Shell")',
            f'Set sc = ws.CreateShortcut("{lnk}")',
            f'sc.TargetPath = "{target}"',
            f'sc.Arguments = Chr(34) & "{args}" & Chr(34)',
            f'sc.WorkingDirectory = "{work_dir}"',
            'sc.Description = "S.O.N.I.C AI Assistant"',
            f'sc.IconLocation = "{icon_loc}"',
            'sc.Save',
        ])
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix=".vbs")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(vbs)
            proc = subprocess.Popen(
                ["wscript.exe", "/nologo", tmp],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
            )
            proc.wait(timeout=10)
        finally:
            try:
                os.unlink(tmp)
            except Exception:
                pass

    @staticmethod
    def _refresh_windows_icon_cache(lnk_path: str) -> None:
        """
        Force Windows to refresh the icon for a shortcut.
        Uses SHChangeNotify to signal icon change, and touches the .lnk
        file timestamp to invalidate the icon cache entry.
        """
        try:
            import ctypes
            # SHCNE_ASSOCCHANGED = 0x08000000, SHCNF_IDLIST = 0
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)
        except Exception:
            pass
        # Touch the shortcut file to bust the icon cache
        try:
            from pathlib import Path as _P
            p = _P(lnk_path)
            if p.exists():
                # Update access/modification time to force cache invalidation
                import time
                now = time.time()
                os.utime(str(p), (now, now))
        except Exception:
            pass
        # Also try refreshing via explorer.exe icon cache rebuild hint
        try:
            # Notify Explorer that the desktop icons have changed
            import subprocess
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command",
                 "_shell = New-Object -ComObject Shell.Application; "
                 "$folder = $shell.Namespace(0); "
                 "$folder.Self.InvokeVerb('refresh')"],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
        except Exception:
            pass

    @staticmethod
    def _get_desktop_dir() -> Path:
        """
        Resolve the user's REAL desktop directory instead of assuming
        ~/Desktop, which breaks when:
          • OneDrive "Known Folder Move" relocates the desktop
            (C:/Users/x/OneDrive/Desktop) — very common on Win 10/11;
          • the XDG desktop is localized on Linux (~/Masaüstü,
            ~/Schreibtisch, ~/Bureau, …).
        Falls back to ~/Desktop only as a last resort.
        """
        home = Path.home()
        _os = platform.system()

        if _os == "Windows":
            # ── 1) SHGetKnownFolderPath(FOLDERID_Desktop) — the canonical
            #       answer; follows OneDrive redirection. No dependencies. ──
            try:
                import ctypes
                from ctypes import wintypes

                class _GUID(ctypes.Structure):
                    _fields_ = [("Data1", wintypes.DWORD),
                                ("Data2", wintypes.WORD),
                                ("Data3", wintypes.WORD),
                                ("Data4", ctypes.c_ubyte * 8)]

                # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
                fid = _GUID(0xB4BFCC3A, 0xDB2C, 0x424C,
                            (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9,
                                                 0x9A, 0x87, 0xC6, 0x41))
                buf = ctypes.c_wchar_p()
                if ctypes.windll.shell32.SHGetKnownFolderPath(
                        ctypes.byref(fid), 0, None, ctypes.byref(buf)) == 0:
                    p = Path(buf.value)
                    ctypes.windll.ole32.CoTaskMemFree(buf)
                    if p.is_dir():
                        return p
            except Exception:
                pass

            # ── 2) Registry: User Shell Folders (may contain %VARS%) ──────
            try:
                import winreg
                with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion"
                        r"\Explorer\User Shell Folders") as key:
                    val, _t = winreg.QueryValueEx(key, "Desktop")
                p = Path(os.path.expandvars(val))
                if p.is_dir():
                    return p
            except Exception:
                pass

        elif _os == "Linux":
            # ── xdg-user-dir honours localized names (~/Masaüstü, …) ──────
            try:
                out = subprocess.run(["xdg-user-dir", "DESKTOP"],
                                     capture_output=True, text=True, timeout=5)
                p = Path(out.stdout.strip())
                if out.stdout.strip() and p != home and p.is_dir():
                    return p
            except Exception:
                pass
            try:
                cfg = home / ".config" / "user-dirs.dirs"
                for line in cfg.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("XDG_DESKTOP_DIR"):
                        val = line.split("=", 1)[1].strip().strip('"')
                        p = Path(val.replace("$HOME", str(home)))
                        if p != home and p.is_dir():
                            return p
            except Exception:
                pass

        # macOS: ~/Desktop is always the real path (localization is
        # display-only). Everything else lands here as a last resort.
        return home / "Desktop"

    def _create_desktop_shortcut(self):
        """
        Create or update a desktop shortcut on Windows / macOS / Linux.
        Always regenerates the icon to ensure it reflects the current design.
        Never opens a terminal, console, or PowerShell window.
        """
        import stat as _stat
        script  = Path(__file__).resolve().parent / "main.py"
        python  = Path(sys.executable)
        desktop = self._get_desktop_dir()

        # ── Icon source of truth — use existing sonic.ico ──
        ico_path = Path(__file__).resolve().parent / "config" / "sonic.ico"

        try:
            _os = platform.system()

            # ── Windows ───────────────────────────────────────────────────────
            if _os == "Windows":
                pythonw  = python.parent / "pythonw.exe"
                target   = str(pythonw if pythonw.exists() else python)
                lnk      = str(desktop / "S.O.N.I.C.lnk")
                icon_loc = str(ico_path) if ico_path.exists() else f"{target},0"
                self._create_lnk_windows(lnk, target, str(script),
                                         str(script.parent), icon_loc)
                # Refresh Windows icon cache for the shortcut
                self._refresh_windows_icon_cache(lnk)

            # ── macOS — proper .app bundle (no Terminal window) ───────────────
            elif _os == "Darwin":
                app     = desktop / "S.O.N.I.C.app"
                mac_dir = app / "Contents" / "MacOS"
                res_dir = app / "Contents" / "Resources"
                mac_dir.mkdir(parents=True, exist_ok=True)
                res_dir.mkdir(exist_ok=True)

                # Launcher executable (bash — runs as background process,
                # macOS does NOT open Terminal for executables inside .app bundles)
                launcher = mac_dir / "SONIC"
                launcher.write_text(
                    "#!/usr/bin/env bash\n"
                    f'cd "{script.parent}"\n'
                    f'exec "{python}" "{script}"\n'
                )
                launcher.chmod(launcher.stat().st_mode
                               | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)

                # Minimal Info.plist (required for .app recognition)
                (app / "Contents" / "Info.plist").write_text(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                    '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                    '<plist version="1.0"><dict>\n'
                    '  <key>CFBundleExecutable</key><string>SONIC</string>\n'
                    '  <key>CFBundleIdentifier</key>'
                    '<string>com.sonic.assistant</string>\n'
                    '  <key>CFBundleName</key><string>S.O.N.I.C</string>\n'
                    '  <key>CFBundlePackageType</key><string>APPL</string>\n'
                    '  <key>CFBundleVersion</key><string>1.0</string>\n'
                    '</dict></plist>\n'
                )

                # Optional: copy icon as .icns (skip silently if Pillow is missing)
                try:
                    import PIL.Image
                    icns = res_dir / "AppIcon.icns"
                    PIL.Image.open(ico_path).save(icns, format="ICNS")
                    # Inject icon reference into plist
                    plist = app / "Contents" / "Info.plist"
                    txt = plist.read_text()
                    plist.write_text(
                        txt.replace(
                            '</dict></plist>',
                            '  <key>CFBundleIconFile</key>'
                            '<string>AppIcon</string>\n</dict></plist>\n',
                        )
                    )
                except Exception:
                    pass  # icon is optional

            # ── Linux — .desktop file (Terminal=false, no console) ────────────
            else:
                # Always regenerate .png from current .ico
                png_path = ico_path.with_suffix(".png")
                if ico_path.exists():
                    try:
                        import PIL.Image
                        PIL.Image.open(ico_path).resize(
                            (256, 256), PIL.Image.LANCZOS
                        ).save(png_path, format="PNG")
                    except Exception:
                        png_path = ico_path  # fallback to .ico

                icon_line = f"Icon={png_path}\n" if png_path.exists() else ""
                desk = desktop / "S.O.N.I.C.desktop"
                desk.write_text(
                    "[Desktop Entry]\n"
                    "Name=S.O.N.I.C\n"
                    f"Exec={python} {script}\n"
                    f"Path={script.parent}\n"
                    "Type=Application\n"
                    "Terminal=false\n"
                    "Categories=Utility;\n"
                    + icon_line
                )
                desk.chmod(desk.stat().st_mode | 0o755)

            self._log.append_log("SYS: Desktop shortcut created.")
        except Exception as e:
            self._log.append_log(f"ERR: Shortcut failed — {e}")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cw = self.centralWidget()
        self._backdrop.setGeometry(cw.rect())
        if self._overlay and self._overlay.isVisible():
            ow, oh = 460, 390
            self._overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._remote_overlay and self._remote_overlay.isVisible():
            ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
            self._remote_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._customize_overlay and self._customize_overlay.isVisible():
            ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
            self._customize_overlay.setGeometry(
                (cw.width()  - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        if self._profile_editor_overlay and self._profile_editor_overlay.isVisible():
            ow, oh = ProfileEditorOverlay._OW, ProfileEditorOverlay._OH
            oh = min(oh, cw.height() - 16)
            self._profile_editor_overlay.setGeometry(
                (cw.width() - ow) // 2,
                (cw.height() - oh) // 2,
                ow, oh,
            )
        # Camera preview — bottom-right corner of the center/HUD area
        pw = _CameraPreview._W
        ph = self._cam_preview.height() or _CameraPreview._H
        self._cam_preview.setGeometry(
            cw.width() - _RIGHT_W - pw - 12,
            cw.height() - ph - 28,
            pw, ph,
        )
        # Clipboard panel — bottom-center
        if hasattr(self, '_clipboard_panel') and self._clipboard_panel.isVisible():
            self._position_clipboard_panel()

    def _update_metrics(self):
        snap = _metrics.snapshot()

        # CPU
        cpu = snap["cpu"]
        self._bar_cpu.set_value(cpu, f"{cpu:.0f}%")

        # MEM
        mem = snap["mem"]
        self._bar_mem.set_value(mem, f"{mem:.0f}%")

        # NET
        net = snap["net"]
        if net < 1.0:
            net_str = f"{net*1024:.0f}KB/s"
        else:
            net_str = f"{net:.1f}MB/s"
        net_pct = min(100, net * 10)  # 10 MB/s = %100
        self._bar_net.set_value(net_pct, net_str)

        # GPU
        gpu = snap["gpu"]
        if gpu >= 0:
            self._bar_gpu.set_value(gpu, f"{gpu:.0f}%")
        else:
            self._bar_gpu.set_value(0, "N/A")

        # TMP
        tmp = snap["tmp"]
        if tmp >= 0:
            tmp_pct = min(100, (tmp / 100) * 100)
            self._bar_tmp.set_value(tmp_pct, f"{tmp:.0f}°C")
        else:
            self._bar_tmp.set_value(0, "N/A")


    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet(f"""
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0a0d12, stop:0.5 #070a0f, stop:1 #050710);
            border-bottom: 1px solid {C.BORDER};
        """)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 0, 16, 0)

        def _badge(txt, color=C.TEXT_DIM):
            l = QLabel(txt)
            l.setFont(QFont("Consolas", 7))
            l.setStyleSheet(f"color: {color}; background: transparent; letter-spacing: 2px;")
            return l

        lay.addWidget(_badge("◈  S.Y.S.T.E.M"))
        lay.addStretch()

        mid = QVBoxLayout(); mid.setSpacing(1)
        _disp = self._assistant_name.upper()
        self._title_lbl = QLabel(_disp)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_lbl.setFont(QFont("Orbitron", 18, QFont.Weight.Bold))
        self._title_lbl.setStyleSheet(f"""
            color: {HU.TEXT};
            background: transparent;
            letter-spacing: 6px;
        """)
        mid.addWidget(self._title_lbl)
        _sub_text = ("Artificial Intelligence Operating System"
                     if _disp in ("SONIC", "S.O.N.I.C")
                     else "Personal AI Assistant")
        self._sub_lbl = QLabel(_sub_text)
        self._sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub_lbl.setFont(QFont("Consolas", 7))
        self._sub_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 3px;")
        mid.addWidget(self._sub_lbl)
        lay.addLayout(mid)
        lay.addStretch()

        right_col = QVBoxLayout(); right_col.setSpacing(2)
        self._clock_lbl = QLabel("00:00:00")
        self._clock_lbl.setFont(QFont("Orbitron", 13))
        self._clock_lbl.setStyleSheet(f"color: {HU.GOLD}; background: transparent;")
        self._clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._clock_lbl)
        self._date_lbl = QLabel("")
        self._date_lbl.setFont(QFont("Consolas", 7))
        self._date_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent; letter-spacing: 1px;")
        self._date_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_col.addWidget(self._date_lbl)
        lay.addLayout(right_col)
        return w

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S"))
        self._date_lbl.setText(time.strftime("%a %d %b %Y"))

    def _build_left_panel(self) -> QWidget:
        w = HudPanel(cuts=[("tl", 12), ("tr", 12), ("bl", 12), ("br", 12)],
                     border=HU.BORDER, fill=HU.FILL, glow=True, marks={"tl": "M", "br": "M"})
        w.setFixedWidth(_LEFT_W)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(9, 10, 9, 10)
        lay.setSpacing(4)

        lay.addWidget(HudHeader("◈  TELEMETRY", mark="M", color=HU.BRIGHT))
        lay.addSpacing(2)

        self._bar_cpu = SciGauge("CPU", C.PRI)
        self._bar_mem = SciGauge("MEM", C.ACC2)
        self._bar_net = SciGauge("NET", C.GREEN)
        self._bar_gpu = SciGauge("GPU", C.ACC)
        self._bar_tmp = SciGauge("TMP", C.ACC)

        for bar in [self._bar_cpu, self._bar_mem, self._bar_net,
                    self._bar_gpu, self._bar_tmp]:
            lay.addWidget(bar)

        lay.addSpacing(4)

        lay.addWidget(HudHeader("CONTROLS", mark="M"))
        lay.addSpacing(2)

        remote_btn = HudButton("◉  REMOTE",
                                cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=7)
        remote_btn.setFixedHeight(24)
        remote_btn.clicked.connect(self._open_remote)
        lay.addWidget(remote_btn)

        fs_btn = HudButton("⛶  FULLSCREEN",
                            cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        fs_btn.setFixedHeight(24)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(fs_btn)

        sc_btn = HudButton("⊞  SHORTCUT",
                            cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                            border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        sc_btn.setFixedHeight(24)
        sc_btn.clicked.connect(self._create_desktop_shortcut)
        lay.addWidget(sc_btn)

        self._autostart_btn = HudButton("◉  AUTO-START: OFF",
                                         cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                         border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        self._autostart_btn.setFixedHeight(24)
        self._autostart_btn.clicked.connect(self._toggle_autostart)
        lay.addWidget(self._autostart_btn)

        self._brief_btn = HudButton("",
                                     cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                     border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        self._brief_btn.setFixedHeight(24)
        self._brief_btn.clicked.connect(self._toggle_brief)
        lay.addWidget(self._brief_btn)

        profile_btn = HudButton("👤  PROFILE",
                                cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=7)
        profile_btn.setFixedHeight(24)
        profile_btn.clicked.connect(self._open_profile_editor)
        lay.addWidget(profile_btn)

        logout_btn = HudButton("⏻  LOGOUT",
                                cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                border=C.RED, fill=HU.FILL, color=C.RED, font_size=7)
        logout_btn.setFixedHeight(24)
        logout_btn.clicked.connect(self._do_logout)
        lay.addWidget(logout_btn)

        lay.addSpacing(4)

        # ── Security Section ──────────────────────────────────────────────
        sec_btn = HudButton("🔒  SECURITY",
                            cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                            border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=7)
        sec_btn.setFixedHeight(24)
        sec_btn.clicked.connect(self._show_security_dashboard)
        lay.addWidget(sec_btn)

        # ── Update Section ────────────────────────────────────────────────
        from version import APP_VERSION
        ver_label = QLabel(f"SONIC v{APP_VERSION}")
        ver_label.setStyleSheet("color: #00d4ff; font-size: 8px; font-weight: bold; background: transparent; border: none;")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ver_label)

        update_btn = HudButton("⬆  CHECK FOR UPDATES",
                                cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                                border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=7)
        update_btn.setFixedHeight(24)
        update_btn.clicked.connect(self._check_for_updates)
        lay.addWidget(update_btn)

        lay.addStretch()

        return w
    def _build_right_panel(self) -> QWidget:
        w = HudPanel(cuts=[("tl", 12), ("tr", 12), ("bl", 12), ("br", 12)],
                     border=HU.BORDER, fill=HU.FILL, glow=True, marks={"tr": "M", "bl": "M"})
        w.setFixedWidth(_RIGHT_W)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(4)

        lay.addWidget(HudHeader("◈  EVENT STREAM", mark=">"))
        self._log = LogWidget()
        lay.addWidget(self._log, stretch=1)

        return w


    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(4)
        self._input = HudLineEdit()
        self._input.setPlaceholderText("Command interface — type or speak…")
        self._input.setFont(QFont("Consolas", 9))
        self._input.setFixedHeight(32)
        self._input.returnPressed.connect(self._send)
        row.addWidget(self._input)

        send = HudButton("▸",
                         cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
                         border=HU.BRIGHT, fill=HU.FILL2, color=HU.BRIGHT, font_size=11)
        send.setFixedSize(32, 32)
        send.clicked.connect(self._send)
        row.addWidget(send)

        self._mute_btn = HudButton("🎙",
                                    cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
                                    border=HU.BORDER, fill=HU.FILL2, color=HU.BRIGHT, font_size=9)
        self._mute_btn.setFixedSize(32, 32)
        self._mute_btn.setToolTip("Toggle microphone")
        self._mute_btn.clicked.connect(self._toggle_mute)
        self._style_mute_btn()
        row.addWidget(self._mute_btn)

        self._interrupt_btn = HudButton("✋",
                                         cuts=[("tl", 5), ("tr", 5), ("bl", 5), ("br", 5)],
                                         border=C.RED, fill=C.RED_DIM, color=C.MUTED_C, font_size=9)
        self._interrupt_btn.setFixedSize(30, 30)
        self._interrupt_btn.setToolTip("Interrupt  [ESC]")
        self._interrupt_btn.clicked.connect(self._do_interrupt)
        row.addWidget(self._interrupt_btn)

        return row

    def _build_command_bar(self) -> QWidget:
        """Command bar — sits below the HUD orb, above the content panel."""
        w = HudPanel(cuts=[("tl", 0), ("tr", 0), ("bl", 8), ("br", 8)],
                     border=HU.BORDER, fill=HU.FILL, glow=False)
        w.setFixedHeight(68)
        outer = QVBoxLayout(w)
        outer.setContentsMargins(12, 8, 12, 4)
        outer.setSpacing(2)
        outer.addLayout(self._build_input_row())

        # Limited Time Free label
        _free_lbl = QLabel("✦  LIMITED TIME FREE  —  Full access, no credit card required")
        _free_lbl.setFont(QFont("Segoe UI", 7))
        _free_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _free_lbl.setStyleSheet(
            f"color: {C.PRI_DIM}; background: transparent; "
            f"letter-spacing: 0.5px; padding: 0px;"
        )
        outer.addWidget(_free_lbl)

        return w

    def _build_content_panel(self) -> QWidget:
        """
        Collapsible panel below the HUD — shows search results, news, briefings.
        Hidden by default; appears when show_content() is called.
        """
        w = HudPanel(cuts=[("tl", 0), ("tr", 0), ("bl", 6), ("br", 6)],
                     border=HU.BORDER, fill=HU.FILL, glow=False)
        w.setObjectName("ContentPanel")
        w.hide()

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 7, 12, 8)
        lay.setSpacing(5)

        # ── header row ───────────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setSpacing(6)

        dot = QLabel("◈")
        dot.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        dot.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        hdr.addWidget(dot)

        self._content_title_lbl = QLabel("BRIEFING")
        self._content_title_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._content_title_lbl.setStyleSheet(
            f"color: {C.PRI}; background: transparent; letter-spacing: 1px;"
        )
        hdr.addWidget(self._content_title_lbl)
        hdr.addStretch()

        self._content_ts_lbl = QLabel("")
        self._content_ts_lbl.setFont(QFont("Courier New", 7))
        self._content_ts_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        hdr.addWidget(self._content_ts_lbl)

        dismiss = HudButton("DISMISS  ✕",
                             cuts=[("tl", 4), ("tr", 4), ("bl", 4), ("br", 4)],
                             border=HU.BORDER, fill=HU.FILL, color=HU.DIM, font_size=7)
        dismiss.setFixedSize(80, 18)
        dismiss.clicked.connect(w.hide)
        hdr.addWidget(dismiss)
        lay.addLayout(hdr)

        # ── separator ─────────────────────────────────────────────────────────
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER};"); lay.addWidget(sep)

        # ── text display ──────────────────────────────────────────────────────
        self._content_display = QTextEdit()
        self._content_display.setReadOnly(True)
        self._content_display.setFont(QFont("Courier New", 8))
        self._content_display.setMinimumHeight(60)
        self._content_display.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._content_display.setStyleSheet(f"""
            QTextEdit {{
                background: {C.DARK};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 3px;
                padding: 6px 8px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG}; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B}; border-radius: 3px; min-height: 16px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0; border: none;
            }}
        """)
        lay.addWidget(self._content_display)

        return w

    def _show_content(self, title: str, text: str):
        """Slot — runs on Qt main thread. Updates and shows the content panel."""
        import time as _time
        self._content_title_lbl.setText(title.upper()[:48])
        self._content_ts_lbl.setText(_time.strftime("%H:%M:%S"))
        self._content_display.setPlainText(text)
        self._content_display.moveCursor(
            self._content_display.textCursor().MoveOperation.Start
        )
        first_show = not self._content_panel.isVisible()
        self._content_panel.show()
        if first_show:
            total = self._center_split.height()
            self._center_split.setSizes([max(total - 220, 120), 220])

    def _build_footer(self) -> QWidget:
        w = HudPanel(cuts=[("tl", 0), ("tr", 0), ("bl", 6), ("br", 6)],
                     border=HU.BORDER, fill=HU.FILL, glow=False)
        w.setFixedHeight(22)
        lay = QHBoxLayout(w); lay.setContentsMargins(14, 0, 14, 0)

        def _fl(txt, color=C.TEXT_MED):
            l = QLabel(txt); l.setFont(QFont("Courier New", 7))
            l.setStyleSheet(f"color: {color}; background: transparent;")
            return l

        lay.addWidget(_fl("[F4] Mute  ·  [F11] Fullscreen"))
        lay.addStretch()
        lay.addWidget(_fl("SONIC AI", C.PRI_DIM))
        return w

    def _on_file_selected(self, path: str):
        self._current_file = path
        p    = Path(path)
        cat  = _file_category(p)
        icon, _ = _FILE_ICONS.get(cat, _FILE_ICONS["unknown"])
        size = _fmt_size(p.stat().st_size)
        self._log.append_log(f"FILE: {p.name} ({size}) loaded")
        if self.on_text_command:
            msg = (
                f"[FILE_UPLOADED] path={path} | name={p.name} | "
                f"type={p.suffix.lstrip('.')} | size={size} | "
                f"Briefly tell the user you can see the file '{p.name}' "
                f"({size}) has been uploaded and ask what they'd like to do with it."
            )
            threading.Thread(target=self.on_text_command, args=(msg,), daemon=True).start()

    def notify_phone_connected(self) -> None:
        if self._remote_overlay and self._remote_overlay.isVisible():
            self._remote_overlay.mark_connected()

    def _open_remote(self):
        if not self.on_remote_clicked:
            self._log.append_log("SYS: Dashboard not running — remote unavailable.")
            return
        result = self.on_remote_clicked()
        if not result:
            self._log.append_log("SYS: Could not generate remote key.")
            return
        url    = result[0]
        key    = result[1]
        auto   = result[2] if len(result) >= 3 else ""
        manual = result[3] if len(result) >= 4 else url
        if self._remote_overlay:
            self._remote_overlay._do_close()
        cw  = self.centralWidget()
        ow, oh = RemoteKeyOverlay._OW, RemoteKeyOverlay._OH
        ov  = RemoteKeyOverlay(url, key, auto_login_url=auto, manual_url=manual,
                               expiry_secs=600, parent=cw)
        ov.set_new_key_callback(self.on_remote_clicked)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))
        ov.show()
        self._remote_overlay = ov
        self._log.append_log(f"SYS: Remote key generated — manual: {manual or url}")

    # ── Auto-start ──────────────────────────────────────────────────────────────

    def _check_autostart(self) -> bool:
        """Returns True if auto-start is currently registered on this OS."""
        try:
            if _OS == "Windows":
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
                try:
                    winreg.QueryValueEx(key, "SONIC_AI")
                    return True
                except FileNotFoundError:
                    return False
                finally:
                    winreg.CloseKey(key)
            elif _OS == "Darwin":
                return (Path.home() / "Library" / "LaunchAgents"
                        / "com.sonic.assistant.plist").exists()
            else:
                return (Path.home() / ".config" / "autostart" / "sonic.desktop").exists()
        except Exception:
            return False

    def _toggle_autostart(self):
        currently_on = self._check_autostart()
        try:
            script = str(Path(__file__).resolve().parent / "main.py")
            if _OS == "Windows":
                import winreg
                reg = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_ALL_ACCESS)
                if currently_on:
                    winreg.DeleteValue(reg, "SONIC_AI")
                else:
                    pythonw = Path(sys.executable).parent / "pythonw.exe"
                    exe = str(pythonw if pythonw.exists() else sys.executable)
                    winreg.SetValueEx(reg, "SONIC_AI", 0, winreg.REG_SZ,
                                      f'"{exe}" "{script}"')
                winreg.CloseKey(reg)
            elif _OS == "Darwin":
                plist_dir = Path.home() / "Library" / "LaunchAgents"
                plist_dir.mkdir(parents=True, exist_ok=True)
                plist = plist_dir / "com.sonic.assistant.plist"
                if currently_on:
                    plist.unlink(missing_ok=True)
                else:
                    plist.write_text(
                        '<?xml version="1.0" encoding="UTF-8"?>\n'
                        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                        '<plist version="1.0"><dict>\n'
                        '  <key>Label</key><string>com.sonic.assistant</string>\n'
                        '  <key>ProgramArguments</key><array>\n'
                        f'    <string>{sys.executable}</string>\n'
                        f'    <string>{script}</string>\n'
                        '  </array>\n'
                        '  <key>RunAtLoad</key><true/>\n'
                        '</dict></plist>\n'
                    )
            else:
                desk_dir = Path.home() / ".config" / "autostart"
                desk_dir.mkdir(parents=True, exist_ok=True)
                desk = desk_dir / "sonic.desktop"
                if currently_on:
                    desk.unlink(missing_ok=True)
                else:
                    desk.write_text(
                        "[Desktop Entry]\n"
                        f"Name={self._assistant_name}\n"
                        f"Exec={sys.executable} {script}\n"
                        "Type=Application\nTerminal=false\n"
                        "X-GNOME-Autostart-enabled=true\n"
                    )
            enabled = not currently_on
            self._update_autostart_btn(enabled)
            self._log.append_log(
                f"SYS: Auto-start {'enabled' if enabled else 'disabled'}.")
        except Exception as e:
            self._log.append_log(f"ERR: Auto-start failed — {e}")

    def _update_autostart_btn(self, enabled: bool):
        if not hasattr(self, '_autostart_btn'):
            return
        if enabled:
            self._autostart_btn.setText("◉  AUTO-START: ON")
            self._autostart_btn.set_theme(border=HU.GREEN, fill=C.GREEN_D, color=HU.GREEN)
        else:
            self._autostart_btn.setText("◉  AUTO-START: OFF")
            self._autostart_btn.set_theme(border=HU.BORDER, fill=HU.FILL, color=HU.DIM)

    def _toggle_brief(self):
        from memory.config_manager import get_brief_enabled, save_brief_enabled
        new_val = not get_brief_enabled()
        save_brief_enabled(new_val)
        self._update_brief_btn(new_val)

    def _update_brief_btn(self, enabled: bool):
        if not hasattr(self, '_brief_btn'):
            return
        if enabled:
            self._brief_btn.setText("☀  MORNING BRIEF: ON")
            self._brief_btn.set_theme(border=HU.GREEN, fill=C.GREEN_D, color=HU.GREEN)
        else:
            self._brief_btn.setText("☀  MORNING BRIEF: OFF")
            self._brief_btn.set_theme(border=HU.BORDER, fill=HU.FILL, color=HU.DIM)

    # ── Customization ────────────────────────────────────────────────────────────

    def _open_customize(self):
        cfg = _read_full_config()
        if self._customize_overlay:
            self._customize_overlay.hide()
        cw = self.centralWidget()
        ov = CustomizeOverlay(
            cfg.get("assistant_name", "SONIC") or "SONIC",
            cfg.get("user_name", ""),
            cfg.get("ui_color", "") or DEFAULT_UI_COLOR,
            parent=cw,
        )
        ow, oh = CustomizeOverlay._OW, CustomizeOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.on_preview = self._preview_ui_color
        ov.saved.connect(self._apply_name_update)
        ov.show()
        self._customize_overlay = ov

    def _preview_ui_color(self, hex_color: str):
        """Canlı önizleme — tüm arayüzü yeni renge boyar (config'e YAZMAZ)."""
        old = current_palette()
        if apply_ui_accent(hex_color):
            retheme_all_widgets(old, current_palette())

    def _apply_theme(self, theme: str):
        """Apply theme from onboarding preferences."""
        if theme == "light":
            apply_ui_accent("#ffffff")  # Light theme accent
        else:
            apply_ui_accent(C.PRI)  # Dark theme (default)
        retheme_all_widgets(current_palette(), current_palette())

    def _apply_name_update(self, name: str, user_name: str, ui_color: str = ""):
        """Update all name/theme-dependent UI elements and persist to config."""
        self._assistant_name = name.strip() or "SONIC"
        display = self._assistant_name.upper()
        self.setWindowTitle(f"{display} — SONIC")
        self._title_lbl.setText(display)
        if display in ("SONIC", "S.O.N.I.C"):
            self._sub_lbl.setText("Just A Rather Very Intelligent System")
        else:
            self._sub_lbl.setText("Personal AI Assistant")
        self._log._ai_name_lc = self._assistant_name.lower()
        self.hud._assistant_name = display

        color_changed = False
        if ui_color:
            old = current_palette()
            if apply_ui_accent(ui_color):
                # Tüm arayüzü (paneller, butonlar, kenarlıklar, HUD) canlı boya
                retheme_all_widgets(old, current_palette())
                color_changed = old["PRI"] != C.PRI

        try:
            data = _read_full_config()
            data["assistant_name"] = self._assistant_name
            data["user_name"] = user_name.strip()
            if ui_color:
                data["ui_color"] = ui_color.strip().lower()
            API_FILE.write_text(json.dumps(data, indent=4), encoding="utf-8")
            self._log.append_log(f"SYS: Identity updated — {display}")
            if color_changed:
                self._log.append_log(f"SYS: UI colour applied — {ui_color}")
        except Exception as e:
            self._log.append_log(f"ERR: Config save failed — {e}")

    # ── Profile editor ─────────────────────────────────────────────────────────

    def _open_profile_editor(self):
        cw = self.centralWidget()
        if self._profile_editor_overlay:
            self._profile_editor_overlay.hide()
        ov = ProfileEditorOverlay(parent=cw)
        ow, oh = ProfileEditorOverlay._OW, ProfileEditorOverlay._OH
        oh = min(oh, cw.height() - 16)
        ov.setGeometry(
            (cw.width() - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.saved.connect(self._save_profile)
        ov.load_data()
        ov.show()
        ov.raise_()
        self._profile_editor_overlay = ov

    def _save_profile(self, data: dict):
        try:
            from auth import get_auth
            auth = get_auth()

            # Save personal info to profile
            if auth.is_authenticated and auth.current_user:
                profile = {}
                try:
                    profile = auth.get_extended_profile() or {}
                except Exception:
                    pass
                new_name = data.get("full_name", profile.get("full_name", ""))
                new_phone = data.get("phone", profile.get("phone", ""))
                new_location = data.get("location", profile.get("location", ""))
                new_tz = data.get("timezone", profile.get("timezone", ""))
                prefs = profile.get("preferences", {})
                if isinstance(prefs, str):
                    import json
                    try: prefs = json.loads(prefs)
                    except Exception: prefs = {}
                prefs.update(data.get("preferences", {}))
                new_prefs = prefs
                auth.update_extended_profile(
                    full_name=new_name, phone=new_phone,
                    location=new_location, timezone=new_tz,
                    preferences=new_prefs,
                )

            # Save API keys
            api_keys = data.get("api_keys", {})
            if api_keys:
                self._save_api_keys(api_keys)

            # Apply theme if changed
            theme = data.get("preferences", {}).get("theme", "")
            if theme:
                self._apply_theme(theme)

            self._log.append_log("SYS: Profile updated successfully")
        except Exception as e:
            self._log.append_log(f"ERR: Profile save failed — {e}")

    def _do_logout(self):
        """Show confirmation then logout."""
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Logout",
            "Are you sure you want to logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from auth import get_auth
            auth = get_auth()
            uid = auth.user_id
            if uid:
                try:
                    from memory.cloud_sync import on_logout
                    on_logout(uid)
                except Exception:
                    pass
            auth.logout()
            self._auth_user_id = ""
            self._auth_email = ""
            self._log.append_log("SYS: Logged out successfully")
            self._show_auth()
        except Exception as e:
            self._log.append_log(f"ERR: Logout failed — {e}")

    def _show_security_dashboard(self):
        """Show security status in content panel."""
        try:
            from security.advanced import get_security_status, security_health_check
            status = get_security_status()
            healthy, issues = security_health_check()

            lines = ["═" * 40]
            lines.append("  🔒  SECURITY STATUS")
            lines.append("═" * 40)

            # Health
            if healthy:
                lines.append("  ✅ Status: ALL SYSTEMS SECURE")
            else:
                lines.append("  ⚠️  Status: ISSUES DETECTED")
                for issue in issues:
                    lines.append(f"     • {issue}")

            lines.append("")

            # Rate Limiter
            rate = status.get("rate_limiter", {})
            lines.append("  🛡️  RATE LIMITER")
            lines.append(f"     Active keys: {rate.get('active_keys', 0)}")
            lines.append(f"     Locked accounts: {rate.get('locked_keys', 0)}")
            lines.append(f"     Total attempts: {rate.get('total_attempts', 0)}")
            lines.append("")

            # Audit Log
            audit = status.get("audit_log", {})
            lines.append("  📋 AUDIT LOG")
            lines.append(f"     Chain valid: {'✅' if audit.get('valid') else '❌'}")
            lines.append(f"     Entries: {audit.get('entries', 0)}")
            lines.append("")

            # Intrusion Detection
            ids = status.get("intrusion_detection", {})
            lines.append("  🔍 INTRUSION DETECTION")
            lines.append(f"     Threats (24h): {ids.get('total_threats_24h', 0)}")
            lines.append(f"     Threats (1h): {ids.get('threats_last_hour', 0)}")
            lines.append(f"     Blocked: {ids.get('blocked_count', 0)}")
            lines.append("")

            # Sessions
            lines.append("  👤 SESSIONS")
            lines.append(f"     Active: {status.get('active_sessions', 0)}")
            lines.append("")

            # API Keys
            keys = status.get("api_keys", {})
            lines.append("  🔑 API KEYS")
            lines.append(f"     Active: {keys.get('active_keys', 0)}")
            lines.append(f"     Expired: {keys.get('expired_keys', 0)}")

            lines.append("═" * 40)

            self._show_content("SECURITY STATUS", "\n".join(lines))

        except Exception as e:
            self._show_content("SECURITY", f"Error loading security status: {e}")

    def _check_for_updates(self):
        """Manual update check from settings."""
        from PyQt6.QtWidgets import QMessageBox
        try:
            from updater import get_update_manager
            from version import APP_VERSION

            manager = get_update_manager()
            manifest = manager.check_for_update(force=True)

            if manifest is None:
                QMessageBox.information(
                    self, "SONIC AI",
                    f"You're up to date!\nCurrent version: v{APP_VERSION}"
                )
                return

            from updater.ui import UpdatePopup
            popup = UpdatePopup(manifest, parent=self)
            popup.show()
        except ImportError:
            QMessageBox.information(
                self, "SONIC AI",
                "Update system not available."
            )
        except Exception as e:
            QMessageBox.warning(
                self, "SONIC AI",
                f"Update check failed: {e}"
            )

    def _open_plugin_manager(self):
        plugins = self.get_plugins() if self.get_plugins else []
        cw = self.centralWidget()
        ov = PluginManagerOverlay(plugins, parent=cw)
        ov.adjustSize()
        ov.setGeometry(
            (cw.width()  - ov.width())  // 2,
            (cw.height() - ov.height()) // 2,
            ov.width(), ov.height(),
        )
        ov.show()
        ov.raise_()
        self._plugin_manager_overlay = ov   # keep a reference so it isn't GC'd

    # ── Clipboard intelligence ───────────────────────────────────────────────────

    def _on_clipboard_changed(self):
        try:
            text = QApplication.clipboard().text().strip()
            if len(text) >= 10:
                self._clipboard_sig.emit(text)
        except Exception:
            pass

    def _show_clipboard_panel(self, text: str):
        self._clipboard_panel.show_clipboard(text)
        self._position_clipboard_panel()

    def _position_clipboard_panel(self):
        cw = self.centralWidget()
        pw = ClipboardPanel._W
        ph = self._clipboard_panel.sizeHint().height() or ClipboardPanel._H
        x = (cw.width() - pw) // 2
        y = cw.height() - ph - 6
        self._clipboard_panel.setGeometry(x, y, pw, ph)
        self._clipboard_panel.raise_()

    def _on_clipboard_action(self, cmd: str):
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(cmd,), daemon=True).start()

    def _show_confirm_banner(self, title: str, detail: str):
        from core import confirm
        self._confirm_banner.show_banner(title, detail, confirm.resolve)
        cw = self.centralWidget()
        bw = 360
        bh = self._confirm_banner.sizeHint().height() or 80
        x = (cw.width() - bw) // 2
        y = 50
        self._confirm_banner.setGeometry(x, y, bw, bh)
        self._confirm_banner.raise_()

    def _hide_confirm_banner(self):
        self._confirm_banner.hide()

    # ────────────────────────────────────────────────────────────────────────────

    def _do_interrupt(self):
        if self.on_interrupt:
            self.on_interrupt()

    def _toggle_mute(self):
        self._muted = not self._muted
        self.hud.muted = self._muted
        self._style_mute_btn()
        if self._muted:
            self._apply_state("MUTED")
            self._log.append_log("SYS: Microphone muted.")
        else:
            self._apply_state("LISTENING")
            self._log.append_log("SYS: Microphone active.")

    def _style_mute_btn(self):
        if self._muted:
            self._mute_btn.setText("🔇")
            self._mute_btn.set_theme(border=C.RED, fill=C.RED_DIM, color=C.MUTED_C)
        else:
            self._mute_btn.setText("🎙")
            self._mute_btn.set_theme(border=HU.GREEN, fill=C.GREEN_D, color=HU.GREEN)

    def _send(self):
        txt = self._input.text().strip()
        if not txt: return
        self._input.clear()
        self._log.append_log(f"You: {txt}")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(txt,), daemon=True).start()

    def _apply_state(self, state: str):
        self.hud.state    = state
        self.hud.speaking = (state == "SPEAKING")
        # Connect audio pipeline if not already connected
        if self._sonic_live:
            if self.hud._viz_manager is None and self._sonic_live._viz_manager:
                self.hud._viz_manager = self._sonic_live._viz_manager
            if self.hud._sonic_live is None:
                self.hud._sonic_live = self._sonic_live
            if self._sonic_live._viz_manager:
                self._sonic_live._viz_manager.set_state(state)

    def _update_viz(self):
        """Poll audio level from SonicLive and update the orb visualizer."""
        if self._sonic_live is None:
            return
        # Ensure viz_manager is connected to orb
        if self._sonic_live._viz_manager and self.hud._viz_manager is None:
            self.hud._viz_manager = self._sonic_live._viz_manager
        # ALWAYS feed audio data to orb (legacy path — proven working)
        try:
            level = self._sonic_live._viz_level
            freq = self._sonic_live._viz_freq
        except Exception:
            return
        self.hud.audio_level = level
        self.hud.audio_freq = freq
        # Debug: print every 2 seconds
        if not hasattr(self, '_viz_dbg'):
            self._viz_dbg = 0
        self._viz_dbg += 1
        if self._viz_dbg % 60 == 1:
            print(f"[VIZ] level={level:.3f} freq={freq:.3f} smooth={self.hud._smooth_audio:.3f} peak={self.hud._peak_audio:.3f} state={self.hud.state}")

    def _check_config(self) -> bool:
        if not API_FILE.exists(): return False
        try:
            d = json.loads(API_FILE.read_text(encoding="utf-8"))
            return bool(d.get("gemini_api_key"))
        except Exception:
            return False

    def _check_auth(self):
        """Check auth — show onboarding wizard if first run, else auth overlay."""
        try:
            from auth import get_auth
            auth = get_auth()
            # Check if onboarding is completed
            if auth.is_authenticated and auth.is_onboarding_completed():
                # Already onboarded and authenticated
                self._auth_user_id = auth.user_id
                self._auth_email = auth.current_user.get("email", "") if auth.current_user else ""
                self._log.append_log(f"SYS: Authenticated as {self._auth_email}")
                self._inject_profile_to_memory(auth)
                self.auth_completed.emit()
                return
            
            # Try to restore session
            if auth.restore_session():
                # Session restored - set auth info regardless of onboarding status
                self._auth_user_id = auth.user_id
                self._auth_email = auth.current_user.get("email", "") if auth.current_user else ""
                if auth.is_onboarding_completed():
                    self._log.append_log(f"SYS: Authenticated as {self._auth_email}")
                    self._inject_profile_to_memory(auth)
                    self._ready = True
                    self.auth_completed.emit()
                    return
                # Session restored but onboarding not complete
                self._log.append_log(f"SYS: Session restored, onboarding needed for {self._auth_email}")
                self._show_onboarding()
                return

            # No session — show onboarding
            self._show_onboarding()
        except ImportError:
            pass  # auth module not available, skip

    def _inject_profile_to_memory(self, auth):
        """Inject user profile data into memory engine for AI context."""
        try:
            from memory.memory_manager import remember, set_user_id
            # Set user_id from auth
            uid = auth.user_id
            if uid:
                set_user_id(uid)
            result = auth.get_extended_profile()
            profile = result.get("profile", {})
            if not profile:
                return
            if profile.get("full_name"):
                remember("name", profile["full_name"], "identity")
            if profile.get("location"):
                remember("city", profile["location"], "identity")
            if profile.get("timezone"):
                remember("timezone", profile["timezone"], "identity")
            prefs = profile.get("preferences", {})
            if isinstance(prefs, dict):
                if prefs.get("user_name"):
                    remember("preferred_name", prefs["user_name"], "identity")
        except Exception:
            pass

    def _show_auth(self):
        ov = AuthOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 420
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.auth_success.connect(self._on_auth_success)
        ov.skip.connect(self._on_auth_skip)
        ov.show()
        self._auth_overlay = ov

    def _show_onboarding(self):
        """Show the multi-step onboarding wizard."""
        ow = OnboardingWizard(self.centralWidget())
        cw = self.centralWidget()
        ow_w, ow_h = 520, 580
        ow.setGeometry(
            (cw.width()  - ow_w) // 2,
            (cw.height() - ow_h) // 2,
            ow_w, ow_h,
        )
        ow.completed.connect(self._on_onboarding_completed)
        ow.skipped.connect(self._on_onboarding_skipped)
        ow.show()
        self._onboarding_wizard = ow

    def _on_onboarding_completed(self, data: dict):
        """Handle onboarding completion — save profile and show auth if needed."""
        try:
            from auth import get_auth
            auth = get_auth()
            
            # Validate required fields
            email = data.get("email", "").strip()
            user_id = data.get("user_id", "").strip()
            if not email or not user_id:
                raise ValueError("Missing email or user_id from onboarding data")
            
            # Update extended profile with all collected data
            profile_data = {
                "full_name": data.get("full_name", "").strip(),
                "phone": data.get("phone", "").strip(),
                "location": data.get("location", "").strip(),
                "timezone": data.get("timezone", "").strip(),
                "api_keys": data.get("api_keys", {}),
                "preferences": data.get("preferences", {}),
                "onboarding_completed": 1,
            }
            
            # Only update if we have a session
            if auth.is_authenticated:
                result = auth.update_extended_profile(**profile_data)
                if result.get("error"):
                    print(f"[ONBOARD] Profile update warning: {result['error']}")
                result = auth.mark_onboarding_completed()
                if result.get("error"):
                    print(f"[ONBOARD] Mark onboarding warning: {result['error']}")
            
            # Apply preferences
            prefs = data.get("preferences", {})
            if prefs.get("assistant_name"):
                self._assistant_name = prefs["assistant_name"]
            if prefs.get("user_name"):
                self._user_name = prefs["user_name"]
            if prefs.get("theme"):
                self._apply_theme(prefs["theme"])
            
            # Save assistant/user names to config
            assistant_name = prefs.get("assistant_name", "SONIC") or "SONIC"
            user_name = prefs.get("user_name", "") or ""
            try:
                from memory.config_manager import save_assistant_config
                save_assistant_config(assistant_name, user_name)
            except Exception as e:
                print(f"[ONBOARD] Failed to save assistant config: {e}")
            
            # Apply API keys
            api_keys = data.get("api_keys", {})
            if api_keys:
                self._save_api_keys(api_keys)
            
            # Inject profile data into memory engine for AI context
            try:
                from memory.memory_manager import remember, set_user_id
                # Set user_id from auth
                uid = auth.user_id if hasattr(auth, 'user_id') else ""
                if uid:
                    set_user_id(uid)
                if data.get("full_name"):
                    remember("name", data["full_name"], "identity")
                if data.get("location"):
                    remember("city", data["location"], "identity")
                if data.get("timezone"):
                    remember("timezone", data["timezone"], "identity")
                if user_name:
                    remember("preferred_name", user_name, "identity")
                # Save language and custom instructions
                lang = prefs.get("language", "").strip()
                if lang:
                    remember("language", lang, "identity")
                instructions = prefs.get("custom_instructions", "").strip()
                if instructions:
                    remember("custom_instructions", instructions, "preferences")
                print(f"[ONBOARD] Profile injected into memory context")
            except Exception as e:
                print(f"[ONBOARD] Memory injection failed: {e}")
            
            # Log success
            print(f"[ONBOARD] Onboarding completed for {email}")
            
            # ALWAYS close wizard — even if later steps fail
            if self._onboarding_wizard:
                self._onboarding_wizard.hide()
                self._onboarding_wizard = None
                
            # ALWAYS emit auth_completed — never require second login
            self._auth_user_id = auth.user_id if auth.is_authenticated else user_id
            self._auth_email = auth.current_user.get("email", "") if auth.is_authenticated else email
            self._ready = True
            self.auth_completed.emit()
                
        except Exception as e:
            print(f"[ONBOARD] Onboarding save error: {e}")
            import traceback
            traceback.print_exc()
            # ALWAYS close wizard on error too — don't leave user stuck
            if self._onboarding_wizard:
                self._onboarding_wizard.hide()
                self._onboarding_wizard = None
            # ALWAYS emit auth_completed — runner must never hang
            try:
                from auth import get_auth
                auth = get_auth()
                self._auth_user_id = auth.user_id if auth.is_authenticated else data.get("user_id", "")
                self._auth_email = auth.current_user.get("email", "") if auth.is_authenticated else data.get("email", "")
            except Exception:
                self._auth_user_id = data.get("user_id", "")
                self._auth_email = data.get("email", "")
            self._ready = True
            self.auth_completed.emit()

    def _on_onboarding_skipped(self):
        """User skipped onboarding — show auth overlay."""
        if self._onboarding_wizard:
            self._onboarding_wizard.hide()
            self._onboarding_wizard = None
        self._show_auth()

    def _on_auth_success(self, user_id: str, email: str):
        self._auth_user_id = user_id
        self._auth_email = email
        if self._auth_overlay:
            self._auth_overlay.hide()
            self._auth_overlay = None
        self._log.append_log(f"SYS: Authenticated as {email}")
        # Check if onboarding is already completed
        try:
            from auth import get_auth
            auth = get_auth()
            if auth.is_onboarding_completed():
                self.auth_completed.emit()
            else:
                # Show onboarding after login
                self._show_onboarding()
        except Exception:
            self.auth_completed.emit()

    def _on_auth_skip(self):
        if self._auth_overlay:
            self._auth_overlay.hide()
            self._auth_overlay = None
        self._log.append_log("SYS: Running in offline mode (no cloud sync)")
        self._ready = True
        self.auth_completed.emit()

    def _save_api_keys(self, api_keys: dict):
        """Save API keys to config file."""
        try:
            from memory.config_manager import ensure_config_dir, CONFIG_FILE
            import json
            ensure_config_dir()
            data = {}
            if CONFIG_FILE.exists():
                try:
                    data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            # Map onboarding key names to config key names
            mapped = {}
            for k, v in api_keys.items():
                if k == "gemini":
                    mapped["gemini_api_key"] = v
                else:
                    mapped[k] = v
            data.update(mapped)
            CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            self._log.append_log("SYS: API keys saved")
        except Exception as e:
            self._log.append_log(f"SYS: Failed to save API keys: {e}")

    def _show_setup(self):
        ov = SetupOverlay(self.centralWidget())
        cw = self.centralWidget()
        ow, oh = 460, 390
        ov.setGeometry(
            (cw.width()  - ow) // 2,
            (cw.height() - oh) // 2,
            ow, oh,
        )
        ov.done.connect(self._on_setup_done)
        ov.show()
        self._overlay = ov

    def _on_setup_done(self, key: str, os_name: str):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        API_FILE.write_text(
            json.dumps({"gemini_api_key": key, "os_system": os_name}, indent=4),
            encoding="utf-8",
        )
        self._ready = True
        if self._overlay:
            self._overlay.hide()
            self._overlay = None
        self._assistant_name = _read_full_config().get("assistant_name", "SONIC") or "SONIC"
        self._log.append_log(f"SYS: Initialised. OS={os_name.upper()}. {self._assistant_name} online.")
        # Transition to auth/onboarding flow so auth_completed fires
        self._check_auth()

class _RootShim:
    def __init__(self, app: QApplication):
        self._app = app
    def mainloop(self):
        self._app.exec()
    def protocol(self, *_):
        pass


class SonicUI:
    def __init__(self, face_path: str, size=None, _skip_show: bool = False):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._win = MainWindow(face_path)
        if not _skip_show:
            self._win.show()
        self.root = _RootShim(self._app)

    @property
    def auth_completed(self):
        return self._win.auth_completed

    @property
    def muted(self) -> bool:
        return self._win._muted

    @muted.setter
    def muted(self, v: bool):
        if v != self._win._muted:
            self._win._toggle_mute()

    @property
    def current_file(self) -> str | None:
        return getattr(self._win, '_current_file', None)

    @property
    def on_text_command(self):
        return self._win.on_text_command

    @on_text_command.setter
    def on_text_command(self, cb):
        self._win.on_text_command = cb

    @property
    def on_remote_clicked(self):
        return self._win.on_remote_clicked

    @on_remote_clicked.setter
    def on_remote_clicked(self, cb):
        self._win.on_remote_clicked = cb

    @property
    def on_interrupt(self):
        return self._win.on_interrupt

    @on_interrupt.setter
    def on_interrupt(self, cb):
        self._win.on_interrupt = cb

    @property
    def get_plugins(self):
        return self._win.get_plugins

    @get_plugins.setter
    def get_plugins(self, cb):
        self._win.get_plugins = cb

    def notify_phone_connected(self) -> None:
        self._win.notify_phone_connected()

    def set_state(self, state: str):
        self._win._state_sig.emit(state)

    def write_log(self, text: str):
        self._win._log_sig.emit(text)

    def wait_for_api_key(self):
        while not self._win._ready:
            time.sleep(0.1)

    def show_content(self, title: str, text: str):
        """Thread-safe: display content in the panel below the HUD."""
        self._win._content_sig.emit(title[:48], text[:4000])

    def prompt_reconfig(self):
        """Thread-safe: show the API key setup overlay (e.g. after an auth error)."""
        self._win._ready = False
        self._win._reconfig_sig.emit()

    def show_camera_frame(self, img_bytes: bytes):
        """Thread-safe: show a webcam frame in the small overlay (screen captures)."""
        self._win._camera_sig.emit(img_bytes)

    def start_camera_stream(self) -> None:
        """Thread-safe: start live camera feed in the full HUD area."""
        self._win.start_camera_stream()

    def stop_camera_stream(self) -> None:
        """Thread-safe: stop the live camera feed."""
        self._win.stop_camera_stream()

    @property
    def assistant_name(self) -> str:
        return self._win._assistant_name

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted:
            self.set_state("ONLINE")

    def set_audio_level(self, level: float):
        """Thread-safe: update orb visualizer with real-time audio level."""
        self._win.hud._audio_level = level
        # Also update viz attributes for orb animation
        if self._win._sonic_live is not None:
            self._win._sonic_live._viz_level = level
            self._win._sonic_live._viz_freq = level * 0.5  # approximate freq from level

    def debug_orb_force(self, value: float = 0.7):
        """Force orb deformation for visual testing. Call from debug console."""
        hud = getattr(getattr(self, '_win', None), 'hud', None)
        if hud and hasattr(hud, 'set_debug_force'):
            hud.set_debug_force(value)
        else:
            print("[ORB DEBUG] HudCanvas not available")

    def debug_orb_off(self):
        """Turn off forced orb deformation."""
        hud = getattr(getattr(self, '_win', None), 'hud', None)
        if hud and hasattr(hud, 'set_debug_force'):
            hud.set_debug_force(0.0)

    def show_confirm(self, title: str, detail: str):
        """Thread-safe: show confirmation banner for irreversible actions."""
        self._win._confirm_sig.emit(title, detail)

    def hide_confirm(self):
        """Thread-safe: hide the confirmation banner."""
        self._win._confirm_hide_sig.emit()