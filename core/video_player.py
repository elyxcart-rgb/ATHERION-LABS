"""SONIC AI — Universal Video Player Control.

Detect the active video player (YouTube, VLC, Windows Media Player,
browser tabs, etc.) and control it with the correct shortcut for each.

Public API:
    VideoController()
    .detect_player() -> str          # "youtube" | "vlc" | "wmp" | "browser_video" | "none"
    .play() / .pause() / .toggle()
    .next() / .previous()
    .seek(seconds) / .seek_percent(pct)
    .set_volume(0-100) / .mute() / .unmute()
    .fullscreen() / .fullscreen_exit()
    .stop()
    .control(action_name, **kwargs)  # generic action dispatcher
    .get_active_player() -> str
    .get_stats()
"""
from __future__ import annotations

import ctypes
import logging
import time
import threading
from typing import Optional

logger = logging.getLogger("sonic.videoctrl")


# ═════════════════════════════════════════════════════════════════════════════
# Player profiles — keystroke per action for each supported player
# ═════════════════════════════════════════════════════════════════════════════

PLAYER_PROFILES: dict[str, dict] = {
    "youtube": {
        "name": "YouTube (browser)",
        "detect_window": ["YouTube", "Chrome", "Edge", "Firefox"],
        "play_pause": "k",
        "next": "Shift+n",
        "previous": "Shift+p",
        "seek_forward_5": "l",
        "seek_back_5": "j",
        "volume_up": "ArrowUp",
        "volume_down": "ArrowDown",
        "mute": "m",
        "fullscreen": "f",
        "stop": None,
    },
    "vlc": {
        "name": "VLC Media Player",
        "detect_window": ["VLC media player", "VLC"],
        "play_pause": "space",
        "next": "n",
        "previous": "p",
        "seek_forward_5": None,        # VLC uses Ctrl+Right for 10s
        "seek_forward_10": "ctrl+Right",
        "seek_back_5": None,
        "seek_back_10": "ctrl+Left",
        "volume_up": "ctrl+Up",
        "volume_down": "ctrl+Down",
        "mute": "m",
        "fullscreen": "f",
        "stop": None,
    },
    "wmp": {
        "name": "Windows Media Player",
        "detect_window": ["Windows Media Player", "WMP"],
        "play_pause": "ctrl+p",
        "next": "ctrl+b",
        "previous": "ctrl+f",
        "seek_forward_5": "ctrl+Right",
        "seek_back_5": "ctrl+Left",
        "volume_up": "ctrl+Up",
        "volume_down": "ctrl+Down",
        "mute": "ctrl+m",
        "fullscreen": "alt+Enter",
        "stop": "ctrl+s",
    },
    "browser_video": {
        "name": "Generic browser video (HTML5)",
        "detect_window": ["Chrome", "Firefox", "Edge", "Opera", "Brave"],
        "play_pause": "k",           # Most HTML5 players use space or k
        "next": None,
        "previous": None,
        "seek_forward_5": "Right",
        "seek_back_5": "Left",
        "volume_up": "Up",
        "volume_down": "Down",
        "mute": "m",
        "fullscreen": "f",
        "stop": None,
    },
    "potplayer": {
        "name": "PotPlayer",
        "detect_window": ["PotPlayer"],
        "play_pause": "space",
        "next": "n",
        "previous": "p",
        "seek_forward_5": "Right",
        "seek_back_5": "Left",
        "volume_up": "Up",
        "volume_down": "Down",
        "mute": "m",
        "fullscreen": "f",
        "stop": None,
    },
    "mpv": {
        "name": "mpv",
        "detect_window": ["mpv"],
        "play_pause": "space",
        "next": "n",
        "previous": "p",
        "seek_forward_5": "Right",
        "seek_back_5": "Left",
        "volume_up": "Up",
        "volume_down": "Down",
        "mute": "m",
        "fullscreen": "f",
        "stop": None,
    },
    "foobar2000": {
        "name": "foobar2000 (video enabled)",
        "detect_window": ["foobar2000"],
        "play_pause": "space",
        "next": "b",
        "previous": "z",
        "seek_forward_5": None,
        "volume_up": "Up",
        "volume_down": "Down",
        "mute": "m",
        "fullscreen": None,
        "stop": None,
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# VideoController
# ═════════════════════════════════════════════════════════════════════════════

class VideoController:
    """Control any active video player with the right keys."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_player = "none"
        self._stats = {
            "controls": 0, "player_detections": 0,
            "by_player": {p: 0 for p in PLAYER_PROFILES},
            "by_action": {},
        }

    # ── Public ───────────────────────────────────────────────────────────────

    def detect_player(self) -> str:
        """Detect the currently foreground video player.

        Returns player key (e.g. "youtube", "vlc") or "none".
        """
        with self._lock:
            self._stats["player_detections"] += 1
        title = self._get_foreground_window_title()
        if not title:
            self._last_player = "none"
            return "none"
        title_low = title.lower()
        for key, profile in PLAYER_PROFILES.items():
            for hint in profile["detect_window"]:
                if hint.lower() in title_low:
                    with self._lock:
                        self._stats["by_player"][key] += 1
                    self._last_player = key
                    return key
        # Generic HTML5 video in any browser?
        if any(b in title_low for b in
               ("chrome", "firefox", "edge", "opera", "brave")):
            if "youtube" in title_low or "video" in title_low:
                self._last_player = "browser_video"
                return "browser_video"
        self._last_player = "none"
        return "none"

    def get_active_player(self) -> str:
        if self._last_player == "none":
            return self.detect_player()
        return self._last_player

    def play(self) -> bool:
        return self.control("play_pause")

    def pause(self) -> bool:
        return self.control("play_pause")

    def toggle(self) -> bool:
        """Toggle play/pause."""
        return self.control("play_pause")

    def next(self) -> bool:
        return self.control("next")

    def previous(self) -> bool:
        return self.control("previous")

    def seek(self, seconds: int) -> bool:
        """Seek N seconds. Negative = backward. Uses 5s/10s buttons."""
        if seconds >= 0:
            if seconds % 10 == 0 and seconds >= 10:
                # Try 10s button
                if self.control("seek_forward_10"):
                    return True
            return self.control("seek_forward_5", count=abs(seconds) // 5)
        else:
            if abs(seconds) % 10 == 0 and abs(seconds) >= 10:
                if self.control("seek_back_10"):
                    return True
            return self.control("seek_back_5", count=abs(seconds) // 5)

    def seek_percent(self, percent: float) -> bool:
        """Approximate seek via keyboard. Not exact for all players."""
        if not (0 <= percent <= 100):
            return False
        # Can't precisely seek to % via keyboard; approximate via many seeks
        secs = int(percent * 6)  # very rough
        return self.seek(secs)

    def set_volume(self, level: int) -> bool:
        """Set absolute volume 0-100 via system mixer (works for all)."""
        if not (0 <= level <= 100):
            return False
        try:
            from ctypes import wintypes
            import comtypes
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            iface = devices.Activate(IAudioEndpointVolume._iid_,
                                       CLSCTX_ALL, None)
            volume = iface.QueryInterface(IAudioEndpointVolume)
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
            return True
        except Exception as e:
            logger.debug(f"pycaw volume failed: {e}")
            return False

    def volume_up(self, steps: int = 1) -> bool:
        """Bump volume up N times."""
        return self.control("volume_up", count=steps)

    def volume_down(self, steps: int = 1) -> bool:
        return self.control("volume_down", count=steps)

    def mute(self) -> bool:
        return self.control("mute")

    def unmute(self) -> bool:
        """Some players use same key; click again to unmute."""
        return self.control("mute")

    def fullscreen(self) -> bool:
        return self.control("fullscreen")

    def fullscreen_exit(self) -> bool:
        return self.control("fullscreen")  # toggles

    def stop(self) -> bool:
        return self.control("stop")

    def control(self, action: str, count: int = 1) -> bool:
        """Generic control: 'play_pause', 'next', 'mute', etc.

        Auto-detects the active player and uses the right keystroke.
        Returns True if key was sent.
        """
        player = self.detect_player()
        if player == "none":
            return False
        profile = PLAYER_PROFILES.get(player)
        if not profile:
            return False
        key = profile.get(action)
        if key is None:
            return False
        with self._lock:
            self._stats["controls"] += 1
            self._stats["by_action"][action] = (
                self._stats["by_action"].get(action, 0) + 1
            )
        return self._send_keystroke(key, count=count)

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ────────────────────────────────────────────────────────────

    def _get_foreground_window_title(self) -> str:
        """Return the title of the foreground window."""
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return ""
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value or ""
        except Exception:
            return ""

    @staticmethod
    def _send_keystroke(key: str, count: int = 1) -> bool:
        """Send keystrokes via pyautogui or pydirectinput.

        Handles modifiers like 'ctrl+Up', 'Shift+n', etc.
        """
        if not key:
            return False
        try:
            # Try pyautogui first
            try:
                import pyautogui
                for _ in range(count):
                    # Split modifiers
                    parts = key.split("+")
                    modifiers = [p.lower() for p in parts[:-1]]
                    main_key = parts[-1]
                    # pyautogui supports combo keys via hotkey
                    pyautogui.hotkey(*modifiers, main_key)
                return True
            except Exception:
                pass

            # Fallback: send via Windows SendInput
            try:
                import ctypes
                from ctypes import wintypes

                # Parse modifiers
                parts = key.split("+")
                modifiers = [p.lower() for p in parts[:-1]]
                main_key = parts[-1]

                VK_MAP = {
                    "ctrl": 0x11, "control": 0x11,
                    "shift": 0x10, "alt": 0x12,
                    "space": 0x20,
                    "left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28,
                    "return": 0x0D, "enter": 0x0D, "escape": 0x1B, "esc": 0x1B,
                    "tab": 0x09, "backspace": 0x08,
                }
                VK_CHARS = {
                    "f": 0x46, "k": 0x4B, "m": 0x4D, "n": 0x4E,
                    "p": 0x50, "j": 0x4A, "l": 0x4C, "i": 0x49,
                    "b": 0x42, "z": 0x5A, "s": 0x53,
                }

                def vk_for(part):
                    pl = part.lower()
                    if pl in VK_MAP:
                        return VK_MAP[pl]
                    if pl in VK_CHARS:
                        return VK_CHARS[pl]
                    if len(pl) == 1 and pl.isalpha():
                        return ord(pl.upper())
                    if len(pl) == 1 and pl.isdigit():
                        return ord(pl)
                    return None

                user32 = ctypes.windll.user32

                def send_key(vk, down):
                    # Use SendInput
                    extra = ctypes.c_ulong(0)
                    scan = ctypes.c_ushort(0)
                    flags = 0x0002 if down else 0x0002  # KEYEVENTF_KEYUP always needed
                    ii = (ctypes.c_ulong * 1)(0)
                    inp = (ctypes.c_uint * 4)(vk, 0 if down else 2, scan, 0)
                    p = ctypes.pointer(inp)
                    user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp[0]) * 4)

                for _ in range(count):
                    # Press modifiers
                    for mod in modifiers:
                        mvk = vk_for(mod)
                        if mvk:
                            send_key(mvk, True)
                    # Press main key
                    cvk = vk_for(main_key)
                    if cvk:
                        send_key(cvk, True)
                        send_key(cvk, False)
                    # Release modifiers in reverse
                    for mod in reversed(modifiers):
                        mvk = vk_for(mod)
                        if mvk:
                            send_key(mvk, False)
                return True
            except Exception:
                return False
        except Exception:
            return False
