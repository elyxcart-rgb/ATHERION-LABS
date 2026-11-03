"""SONIC AI — DPI + Multi-Monitor awareness.

Wraps ctypes calls to SetProcessDpiAwarenessContext so screen captures
return logical coordinates consistent with what user-facing automation
libraries (pyautogui, pywinauto) expect.

Public API:
    DPIBridge.enable_process_dpi_awareness() → bool
    DPIBridge.get_system_dpi() → int
    MultiMonitor.list_displays() → list[dict]
    MultiMonitor.find_display_for_point(x, y) → dict | None
"""
from __future__ import annotations

import ctypes
import logging
import sys
from dataclasses import dataclass


logger = logging.getLogger("sonic.dpi")


@dataclass
class _Display:
    index: int
    width_px: int
    height_px: int
    width_logical: int
    height_logical: int
    scale_factor: float
    x_origin: int
    y_origin: int
    is_primary: bool


class DPIBridge:
    """Wrapper around Windows DPI APIs."""

    _user32 = ctypes.windll.user32 if sys.platform == "win32" else None
    _shcore = ctypes.windll.shcore if sys.platform == "win32" else None

    @classmethod
    def enable_process_dpi_awareness(cls) -> bool:
        """Mark the process as Per-Monitor V2 DPI aware. Idempotent."""
        if not cls._user32:
            return False
        try:
            # Windows 10 1703+: SetProcessDpiAwarenessContext
            awareness = ctypes.c_int(-4)  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            res = cls._user32.SetProcessDpiAwarenessContext(awareness)
            return bool(res)
        except Exception:
            try:
                # Fallback: shcore SetProcessDpiAwareness
                if cls._shcore:
                    cls._shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
                    return True
            except Exception:
                logger.exception("DPI awareness setup failed")
        return False

    @classmethod
    def get_system_dpi(cls) -> int:
        """Return the system DPI (96 / 120 / 144 / 192 typical)."""
        if not cls._user32:
            return 96
        try:
            hdc = cls._user32.GetDC(0)
            dpi = cls._user32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            cls._user32.ReleaseDC(0, hdc)
            return int(dpi) or 96
        except Exception:
            return 96

    @classmethod
    def get_scale_factor(cls) -> float:
        dpi = cls.get_system_dpi()
        return dpi / 96.0


class MultiMonitor:
    """Enumerates connected displays."""

    @classmethod
    def list_displays(cls) -> list[dict]:
        """Return a list of displays with px + logical geometry."""
        try:
            from screeninfo import get_monitors  # type: ignore
            out = []
            for i, m in enumerate(get_monitors()):
                scale = DPIBridge.get_scale_factor()
                out.append({
                    "index": i,
                    "width_px": m.width,
                    "height_px": m.height,
                    "width_logical": int(m.width / scale),
                    "height_logical": int(m.height / scale),
                    "scale_factor": scale,
                    "x_origin": m.x,
                    "y_origin": m.y,
                    "is_primary": bool(getattr(m, "is_primary", False)),
                })
            return out
        except ImportError:
            logger.warning("screeninfo not installed; multi-monitor limited to single screen")
            try:
                import tkinter as tk  # type: ignore
                root = tk.Tk()
                w = root.winfo_screenwidth()
                h = root.winfo_screenheight()
                root.destroy()
                return [{
                    "index": 0,
                    "width_px": w,
                    "height_px": h,
                    "width_logical": w,
                    "height_logical": h,
                    "scale_factor": 1.0,
                    "x_origin": 0,
                    "y_origin": 0,
                    "is_primary": True,
                }]
            except Exception:
                return [{
                    "index": 0, "width_px": 1920, "height_px": 1080,
                    "width_logical": 1920, "height_logical": 1080,
                    "scale_factor": 1.0, "x_origin": 0, "y_origin": 0,
                    "is_primary": True,
                }]

    @classmethod
    def find_display_for_point(cls, x: int, y: int) -> dict | None:
        for d in cls.list_displays():
            if (d["x_origin"] <= x < d["x_origin"] + d["width_px"]
                    and d["y_origin"] <= y < d["y_origin"] + d["height_px"]):
                return d
        return None
