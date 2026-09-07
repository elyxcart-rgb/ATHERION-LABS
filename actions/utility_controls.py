"""SONIC AI — Utility Controls.

Enhanced system controls: volume presets, brightness presets,
display info, system info, disk space, network info, clipboard history,
scheduled tasks, environment variables, and more quick actions.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

_OS = platform.system()

if _OS == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}


# ── Volume Presets ────────────────────────────────────────────────────────────

def volume_preset(preset: str = "medium") -> dict[str, Any]:
    """Set volume to a preset level: mute, low, medium, high, max."""
    from actions.computer_settings import volume_set, volume_get

    presets = {"mute": 0, "low": 15, "medium": 50, "high": 75, "max": 100}
    level = presets.get(preset.lower(), 50)
    before = volume_get()
    volume_set(level)
    return {"ok": True, "preset": preset, "level": level, "previous": before}


def volume_get_status() -> dict[str, Any]:
    """Get current volume with status description."""
    from actions.computer_settings import volume_get, volume_mute
    vol = volume_get()
    if vol is None:
        return {"ok": False, "error": "Cannot read volume"}
    if vol == 0:
        status = "muted"
    elif vol < 25:
        status = "very low"
    elif vol < 50:
        status = "low"
    elif vol < 75:
        status = "medium"
    else:
        status = "loud"
    return {"ok": True, "volume": vol, "status": status}


# ── Brightness Presets ────────────────────────────────────────────────────────

def brightness_preset(preset: str = "medium") -> dict[str, Any]:
    """Set brightness to a preset: dim, low, medium, high, max."""
    from actions.computer_settings import brightness_set, brightness_get

    presets = {"dim": 10, "low": 25, "medium": 50, "high": 75, "max": 100}
    level = presets.get(preset.lower(), 50)
    before = brightness_get()
    brightness_set(level)
    return {"ok": True, "preset": preset, "level": level, "previous": before}


def brightness_get_status() -> dict[str, Any]:
    """Get current brightness with status description."""
    from actions.computer_settings import brightness_get
    b = brightness_get()
    if b is None:
        return {"ok": False, "error": "Cannot read brightness (desktop?)"}
    if b < 20:
        status = "very dim"
    elif b < 40:
        status = "dim"
    elif b < 60:
        status = "medium"
    elif b < 80:
        status = "bright"
    else:
        status = "very bright"
    return {"ok": True, "brightness": b, "status": status}


# ── Display Info ──────────────────────────────────────────────────────────────

def display_info() -> dict[str, Any]:
    """Get display/monitor information."""
    try:
        if _OS == "Windows":
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_VideoController | Select-Object Name, "
                 "CurrentHorizontalResolution, CurrentVerticalResolution, "
                 "CurrentRefreshRate, AdapterRAM | ConvertTo-Json"],
                capture_output=True, text=True, timeout=5, **_WIN_HIDE
            )
            if r.stdout.strip():
                data = json.loads(r.stdout)
                if isinstance(data, dict):
                    data = [data]
                displays = []
                for d in data:
                    displays.append({
                        "name": d.get("Name", "Unknown"),
                        "resolution": f"{d.get('CurrentHorizontalResolution', '?')}x{d.get('CurrentVerticalResolution', '?')}",
                        "refresh_rate": f"{d.get('CurrentRefreshRate', '?')}Hz",
                        "vram_mb": round((d.get("AdapterRAM", 0) or 0) / (1024 * 1024)),
                    })
                return {"ok": True, "displays": displays}

        elif _OS == "Linux":
            r = subprocess.run(
                ["xrandr", "--query"], capture_output=True, text=True, timeout=5
            )
            resolutions = []
            for line in r.stdout.splitlines():
                if " connected" in line:
                    parts = line.split()
                    resolutions.append({"output": parts[0], "info": " ".join(parts[1:])})
            return {"ok": True, "displays": resolutions}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Not supported"}


# ── System Info ───────────────────────────────────────────────────────────────

def system_info() -> dict[str, Any]:
    """Get comprehensive system information."""
    import psutil
    info = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "processor": platform.processor() or "Unknown",
        "cpu_count": psutil.cpu_count(),
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        "ram_used_gb": round(psutil.virtual_memory().used / (1024**3), 1),
        "ram_percent": psutil.virtual_memory().percent,
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M"),
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }

    # Disk info
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mount": part.mountpoint,
                "total_gb": round(usage.total / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "percent_used": usage.percent,
            })
        except (OSError, PermissionError):
            pass
    info["disks"] = disks

    return {"ok": True, **info}


# ── Disk Space ────────────────────────────────────────────────────────────────

def disk_space() -> dict[str, Any]:
    """Get disk space for all drives."""
    import psutil
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "drive": part.device,
                "total_gb": round(usage.total / (1024**3), 1),
                "used_gb": round(usage.used / (1024**3), 1),
                "free_gb": round(usage.free / (1024**3), 1),
                "percent": usage.percent,
                "warning": "low" if usage.percent > 90 else ("medium" if usage.percent > 75 else "ok"),
            })
        except (OSError, PermissionError):
            pass
    return {"ok": True, "disks": disks}


# ── Network Info ──────────────────────────────────────────────────────────────

def network_info() -> dict[str, Any]:
    """Get network interfaces and IP addresses."""
    import psutil
    interfaces = []
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for name, addr_list in addrs.items():
        ips = []
        mac = ""
        for addr in addr_list:
            if addr.family.name == "AF_INET":
                ips.append(addr.address)
            elif addr.family.name == "AF_LINK":
                mac = addr.address

        is_up = stats.get(name)
        interfaces.append({
            "name": name,
            "ips": ips,
            "mac": mac,
            "is_up": is_up.isup if is_up else False,
        })

    # Get public IP
    public_ip = ""
    try:
        r = subprocess.run(
            ["powershell", "-Command", "(Invoke-WebRequest -Uri 'https://api.ipify.org' -UseBasicParsing).Content"],
            capture_output=True, text=True, timeout=5, **_WIN_HIDE
        )
        public_ip = r.stdout.strip()
    except Exception:
        pass

    return {"ok": True, "interfaces": interfaces, "public_ip": public_ip}


# ── Clipboard ─────────────────────────────────────────────────────────────────

_clipboard_history: list[str] = []
_CLIPBOARD_MAX = 20

def clipboard_monitor_start() -> dict[str, Any]:
    """Start monitoring clipboard changes (stores last N entries)."""
    import threading

    def _monitor():
        last = ""
        while True:
            try:
                import pyperclip
                current = pyperclip.paste()
                if current and current != last:
                    last = current
                    if current not in _clipboard_history:
                        _clipboard_history.insert(0, current)
                        if len(_clipboard_history) > _CLIPBOARD_MAX:
                            _clipboard_history.pop()
            except Exception:
                pass
            time.sleep(1)

    t = threading.Thread(target=_monitor, daemon=True)
    t.start()
    return {"ok": True, "message": "Clipboard monitor started"}


def clipboard_history() -> dict[str, Any]:
    """Get clipboard history."""
    return {"ok": True, "entries": _clipboard_history, "count": len(_clipboard_history)}


# ── Scheduled Tasks ───────────────────────────────────────────────────────────

def list_scheduled_tasks(max_results: int = 20) -> dict[str, Any]:
    """List Windows scheduled tasks related to SONIC."""
    try:
        if _OS == "Windows":
            r = subprocess.run(
                ["schtasks", "/query", "/fo", "LIST", "/v"],
                capture_output=True, text=True, timeout=10, **_WIN_HIDE
            )
            tasks = []
            current = {}
            for line in r.stdout.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    key = key.strip()
                    val = val.strip()
                    if key == "TaskName":
                        if current:
                            tasks.append(current)
                        current = {"name": val}
                    elif current:
                        current[key.lower().replace(" ", "_")] = val
            if current:
                tasks.append(current)

            # Filter for SONIC-related or interesting tasks
            relevant = [t for t in tasks if any(k in t.get("name", "").lower() for k in ["sonic", "python", "auto"])]
            if not relevant:
                relevant = tasks[:max_results]

            return {"ok": True, "tasks": relevant[:max_results], "total": len(tasks)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Not supported"}


# ── Environment ───────────────────────────────────────────────────────────────

def get_env(key: str = "") -> dict[str, Any]:
    """Get environment variables. If key provided, get specific var."""
    if key:
        val = os.environ.get(key, "")
        return {"ok": True, "key": key, "value": val, "exists": bool(val)}

    # Show common vars
    important = ["USERPROFILE", "HOME", "TEMP", "PATH", "APPDATA",
                 "LOCALAPPDATA", "COMPUTERNAME", "OS", "PROCESSOR"]
    result = {}
    for k in important:
        v = os.environ.get(k, "")
        if k == "PATH":
            v = v[:200] + "..." if len(v) > 200 else v
        result[k] = v
    return {"ok": True, "variables": result}


# ── Quick App Launcher ────────────────────────────────────────────────────────

_COMMON_APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "settings": "ms-settings:",
    "snipping tool": "snippingtool.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "teams": "ms-teams.exe",
    "zoom": "Zoom.exe",
    "spotify": "Spotify.exe",
    "discord": "Discord.exe",
    "slack": "Slack.exe",
    "vscode": "code.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "file manager": "explorer.exe",
    "recycle bin": "shell:RecycleBinFolder",
}

def quick_launch(app: str) -> dict[str, Any]:
    """Launch a common application by friendly name."""
    app_lower = app.lower().strip()
    exe = _COMMON_APPS.get(app_lower)

    if not exe:
        # Try partial match
        for name, path in _COMMON_APPS.items():
            if app_lower in name or name in app_lower:
                exe = path
                break

    if not exe:
        return {"ok": False, "error": f"Unknown app: {app}. Known: {', '.join(_COMMON_APPS.keys())}"}

    try:
        if exe.startswith("ms-") or exe.startswith("shell:"):
            subprocess.run(["cmd", "/c", "start", exe], **_WIN_HIDE)
        else:
            subprocess.Popen([exe], **_WIN_HIDE)
        return {"ok": True, "launched": app, "command": exe}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Power / Sleep ─────────────────────────────────────────────────────────────

def sleep_computer() -> dict[str, Any]:
    """Put the computer to sleep."""
    try:
        if _OS == "Windows":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], **_WIN_HIDE)
        elif _OS == "Darwin":
            subprocess.run(["pmset", "sleepnow"], **_WIN_HIDE)
        else:
            subprocess.run(["systemctl", "suspend"], **_WIN_HIDE)
        return {"ok": True, "message": "Computer going to sleep"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def hibernate_computer() -> dict[str, Any]:
    """Hibernate the computer."""
    try:
        if _OS == "Windows":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "1,1,0"], **_WIN_HIDE)
        return {"ok": True, "message": "Computer hibernating"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def monitor_off() -> dict[str, Any]:
    """Turn off the monitor display."""
    try:
        if _OS == "Windows":
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        return {"ok": True, "message": "Monitor turned off"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
