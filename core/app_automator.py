"""SONIC AI — App Automator.

Cross-platform desktop-app automation using ``pywinauto`` (Windows) /
``pyautogui`` (any OS). Lets SONIC actually **drive** any application:
list open windows, focus, click buttons, type text, fill forms, take
screenshots of any app.

Why this is the missing piece:
    - ``core.navigator.open_app`` only *launches* an app.
    - AppAutomator *controls* it — exactly what the user means when they
      say "go to this app and do X".

Public surface (stable, opt-in):
    - ``AppAutomator()``
    - ``app.list_windows()``
    - ``app.focus(title)``
    - ``app.click_text(text, *, app=None)``
    - ``app.type_into(control, text)``
    - ``app.screenshot(path)``
    - ``app.run_macro(steps)``           — list of {"action": ..., "args": ...}

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import logging
import platform
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("APP_AUTOMATOR")


# ═════════════════════════════════════════════════════════════════════════════
# Data class
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class AppWindow:
    title: str
    pid: int = 0
    process_name: str = ""
    is_visible: bool = True
    is_active: bool = False
    geometry: dict = field(default_factory=dict)
    backend: str = ""   # win32 | uia | cocoa | x11

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# AppAutomator
# ═════════════════════════════════════════════════════════════════════════════

class AppAutomator:
    """Drive any application via UI automation + keyboard / mouse."""

    def __init__(self):
        self.is_windows = platform.system() == "Windows"
        self._pyautogui = None
        self._pywinauto_app = None
        self._ensure_deps()

    def _ensure_deps(self):
        try:
            import pyautogui
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.05
            self._pyautogui = pyautogui
        except ImportError:
            logger.warning("pyautogui not available")
        if self.is_windows:
            try:
                from pywinauto import Application
                self._pywinauto_app = Application
            except ImportError:
                logger.warning("pywinauto not available")

    # ── Window enumeration ─────────────────────────────────────────────
    def list_windows(self, *, visible_only: bool = True) -> list[AppWindow]:
        """List open windows (title, pid, geometry)."""
        windows: list[AppWindow] = []
        try:
            if self.is_windows and self._pywinauto_app is not None:
                from pywinauto import findwindows
                elements = findwindows.find_elements(visible_only=visible_only)
                for el in elements:
                    try:
                        windows.append(AppWindow(
                            title=el.name or "",
                            pid=el.process_id,
                            process_name=str(el.process) if hasattr(el, "process") else "",
                            is_visible=bool(el.visible) if hasattr(el, "visible") else True,
                            geometry={
                                "left":   getattr(el, "rectangle").left   if hasattr(el, "rectangle") else 0,
                                "top":    getattr(el, "rectangle").top    if hasattr(el, "rectangle") else 0,
                                "width":  getattr(el, "rectangle").width  if hasattr(el, "rectangle") else 0,
                                "height": getattr(el, "rectangle").height if hasattr(el, "rectangle") else 0,
                            },
                            backend="win32",
                        ))
                    except Exception:
                        continue
            else:
                # macOS / Linux fallback via pyautogui.getAllWindows()
                if self._pyautogui is not None:
                    for w in self._pyautogui.getAllWindows():
                        if visible_only and not w.visible:
                            continue
                        windows.append(AppWindow(
                            title=w.title or "",
                            geometry={
                                "left": w.left, "top": w.top,
                                "width": w.width, "height": w.height,
                            },
                            is_visible=w.visible,
                            backend="cocoa" if platform.system() == "Darwin" else "x11",
                        ))
        except Exception as e:
            logger.warning(f"list_windows failed: {e}")
        return windows

    def find_window(self, title_contains: str, *,
                    visible_only: bool = True) -> Optional[AppWindow]:
        """Find a window whose title contains ``title_contains``."""
        needle = title_contains.lower()
        for w in self.list_windows(visible_only=visible_only):
            if needle in w.title.lower():
                return w
        return None

    def focus(self, title_contains: str, *, timeout: float = 5.0) -> bool:
        """Bring the matching window to the foreground."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            w = self.find_window(title_contains)
            if w is None:
                time.sleep(0.2)
                continue
            try:
                if self.is_windows and self._pywinauto_app is not None:
                    app = self._pywinauto_app(backend="win32").connect(
                        process=w.pid
                    )
                    top = app.top_window()
                    if top.is_minimized():
                        top.restore()
                    top.set_focus()
                elif self._pyautogui is not None:
                    # Use pyautogui to find and activate by title
                    wins = self._pyautogui.getWindowsWithTitle(title_contains)
                    if wins:
                        w_handle = wins[0]
                        if w_handle.isMinimized:
                            w_handle.restore()
                        w_handle.activate()
                w.is_active = True
                return True
            except Exception as e:
                logger.warning(f"focus failed: {e}")
                time.sleep(0.2)
        return False

    # ── Interactions ────────────────────────────────────────────────────
    def click_text(self, text: str, *, app: Optional[Any] = None,
                   timeout: float = 5.0) -> bool:
        """Find a UI element with the given visible text and click it."""
        if app is None and self.is_windows and self._pywinauto_app is not None:
            # Best-effort: use the focused application
            try:
                focused = self._pywinauto_app(backend="uia").connect(
                    active_only=True, timeout=2
                )
                app = focused
            except Exception:
                pass
        if app is not None and hasattr(app, "window"):
            try:
                ctrl = app.window(title_re=f".*{re.escape(text)}.*")
                ctrl.wait("ready", timeout=int(timeout * 1000))
                ctrl.click_input()
                return True
            except Exception as e:
                logger.warning(f"click_text (UIA) failed: {e}")
        # Fallback: pyautogui
        if self._pyautogui is not None:
            try:
                # Locate on screen by text — requires image matching which we skip
                # Instead, fall back to clicking at last-known centre if available
                return False
            except Exception:
                return False
        return False

    def type_into(self, control, text: str, *, clear: bool = True) -> bool:
        """Type text into a control (pywinauto wrapper or click coords)."""
        try:
            if hasattr(control, "set_edit_text") and clear:
                control.set_edit_text("")
                control.type_keys(text, with_spaces=True, set_foreground=True)
                return True
            if hasattr(control, "type_keys"):
                control.type_keys(text, with_spaces=True, set_foreground=True)
                return True
        except Exception as e:
            logger.warning(f"type_into failed: {e}")
        return False

    def click_xy(self, x: int, y: int) -> None:
        if self._pyautogui is not None:
            self._pyautogui.click(x, y)

    def type_at_active(self, text: str, *, interval: float = 0.0) -> None:
        """Type into whichever control currently has focus."""
        if self._pyautogui is not None:
            self._pyautogui.typewrite(text, interval=interval)

    def press(self, key: str) -> None:
        if self._pyautogui is not None:
            self._pyautogui.press(key)

    def hotkey(self, *keys: str) -> None:
        if self._pyautogui is not None:
            self._pyautogui.hotkey(*keys)

    # ── Screenshots ──────────────────────────────────────────────────────
    def screenshot(self, path: str = "") -> str:
        if path == "":
            path = str(Path.home() / "Pictures" / "SONIC" /
                       f"screenshot_{int(time.time())}.png")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if self._pyautogui is not None:
            self._pyautogui.screenshot(path)
        return path

    # ── Macro runner ─────────────────────────────────────────────────────
    def run_macro(self, steps: list[dict]) -> dict:
        """Run a list of macro steps.

        Each step is ``{"action": "<name>", "args": {...}}``. Supported:
            - ``focus``        → ``{"title": "Notepad"}``
            - ``type``         → ``{"text": "hello world"}``
            - ``press``        → ``{"key": "enter"}``
            - ``hotkey``       → ``{"keys": ["ctrl", "s"]}``
            - ``click``        → ``{"x": 100, "y": 200}``  OR  ``{"text": "Save"}``
            - ``wait``         → ``{"seconds": 1.0}``
            - ``screenshot``   → ``{"path": "/tmp/snap.png"}``
        """
        results: list[dict] = []
        for i, step in enumerate(steps):
            action = step.get("action")
            args = step.get("args", {})
            try:
                if action == "focus":
                    ok = self.focus(args["title"], timeout=args.get("timeout", 5))
                    results.append({"step": i, "ok": ok, "action": action})
                elif action == "type":
                    self.type_at_active(args.get("text", ""),
                                       interval=args.get("interval", 0.0))
                    results.append({"step": i, "ok": True, "action": action})
                elif action == "press":
                    self.press(args.get("key", ""))
                    results.append({"step": i, "ok": True, "action": action})
                elif action == "hotkey":
                    self.hotkey(*args.get("keys", []))
                    results.append({"step": i, "ok": True, "action": action})
                elif action == "click":
                    if "text" in args:
                        ok = self.click_text(args["text"])
                        results.append({"step": i, "ok": ok, "action": action})
                    else:
                        self.click_xy(int(args.get("x", 0)), int(args.get("y", 0)))
                        results.append({"step": i, "ok": True, "action": action})
                elif action == "wait":
                    time.sleep(float(args.get("seconds", 0.5)))
                    results.append({"step": i, "ok": True, "action": action})
                elif action == "screenshot":
                    p = self.screenshot(args.get("path", ""))
                    results.append({"step": i, "ok": True, "action": action,
                                    "path": p})
                else:
                    results.append({"step": i, "ok": False, "action": action,
                                    "error": f"unknown action: {action}"})
            except Exception as e:
                results.append({"step": i, "ok": False, "action": action,
                                "error": str(e)})
        return {"ok": all(r.get("ok") for r in results), "results": results}


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[AppAutomator] = None


def app_automator() -> AppAutomator:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AppAutomator()
    return _INSTANCE


__all__ = [
    "AppAutomator", "AppWindow",
    "app_automator",
]
