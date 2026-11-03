"""SONIC AI — Notifications.

Native Windows toast + cross-platform fallback notifications so SONIC can
interrupt the user with relevant info ("Reminding you: call mom in 5 min").

Public API:
    Notifier(app_name="SONIC AI")
    .toast(title, message, duration=5, urgency="normal")    # Windows native
    .speak(text)                                              # TTS via SAPI fallback
    .beep(kind="info")                                        # system beep
    .get_stats()
"""
from __future__ import annotations

import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class NotifyResult:
    delivered: bool
    method: str                       # "winrt"|"powershell"|"plyer"|"log"
    title: str
    message: str
    timestamp: float = 0.0
    error: str = ""


class Notifier:
    """Cross-platform desktop notifier with Windows native priority."""

    def __init__(self, app_name: str = "SONIC AI"):
        self._app_name = app_name
        self._lock = threading.Lock()
        self._stats = {"sent": 0, "spoke": 0, "beeps": 0, "failed": 0}

    # ── Public ───────────────────────────────────────────────────────────────

    def toast(self, title: str, message: str,
              duration: int = 5,
              urgency: str = "normal") -> NotifyResult:
        """Show a desktop notification. Tries WinRT → PowerShell → plyer → log."""
        ts = time.time()
        # 1. Try Windows native (PowerShell BurntToast or built-in)
        result = self._toast_powershell(title, message, duration)
        if result.delivered:
            with self._lock:
                self._stats["sent"] += 1
            return result

        # 2. Try plyer (cross-platform Python lib)
        try:
            from plyer import notification
            notification.notify(
                title=title, message=message,
                app_name=self._app_name, timeout=duration,
            )
            with self._lock:
                self._stats["sent"] += 1
            return NotifyResult(True, "plyer", title, message, ts)
        except Exception:
            pass

        # 3. Fall back to log-only
        print(f"[NOTIFY] {title}: {message}")
        with self._lock:
            self._stats["failed"] += 1
        return NotifyResult(False, "log", title, message, ts,
                           error="all notification methods failed")

    def speak(self, text: str) -> NotifyResult:
        """Speak text via TTS (Windows SAPI)."""
        ts = time.time()
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
            with self._lock:
                self._stats["spoke"] += 1
            return NotifyResult(True, "sapi", "", text, ts)
        except Exception:
            pass
        # Try PowerShell
        try:
            ps_cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10,
            )
            with self._lock:
                self._stats["spoke"] += 1
            return NotifyResult(True, "powershell-sapi", "", text, ts)
        except Exception as e:
            with self._lock:
                self._stats["failed"] += 1
            return NotifyResult(False, "none", "", text, ts, error=str(e))

    def beep(self, kind: str = "info"):
        """System beep."""
        try:
            import winsound
            freq_map = {"info": 800, "warning": 1200, "error": 400, "success": 1000}
            dur_map = {"info": 80, "warning": 120, "error": 200, "success": 80}
            winsound.Beep(freq_map.get(kind, 800), dur_map.get(kind, 80))
            with self._lock:
                self._stats["beeps"] += 1
        except Exception:
            # Fallback for non-Windows
            print("\a", end="", flush=True)
            with self._lock:
                self._stats["beeps"] += 1

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ────────────────────────────────────────────────────────────

    def _toast_powershell(self, title: str, message: str,
                            duration: int) -> NotifyResult:
        if platform.system() != "Windows":
            return NotifyResult(False, "skip", title, message)
        ts = time.time()
        try:
            # Use Windows XML for modern toast (Windows 10+)
            safe_title = title.replace("'", "''").replace('"', "''")
            safe_msg = message.replace("'", "''").replace('"', "''")
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null
            $AppId = '{{1AC14E77-02E7-4E5B-B044-8F9C8B6AAAA1}}\\WindowsPowerShell\\v1.0\\powershell.exe'

            $Template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{safe_title}</text>
      <text>{safe_msg}</text>
    </binding>
  </visual>
</toast>
"@
            $Xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $Xml.LoadXml($Template)
            $Toast = [Windows.UI.Notifications.ToastNotification]::new($Xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($AppId).Show($Toast)
            Start-Sleep -Milliseconds {duration * 1000}
            """
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=duration + 5,
            )
            return NotifyResult(True, "winrt", title, message, ts)
        except Exception as e:
            # Try fallback: msg command (deprecated but works)
            try:
                subprocess.run(
                    ["msg", "*", f"{title}: {message}"],
                    capture_output=True, text=True, timeout=5,
                )
                return NotifyResult(True, "msg", title, message, ts)
            except Exception:
                return NotifyResult(False, "powershell", title, message,
                                    ts, error=str(e))
