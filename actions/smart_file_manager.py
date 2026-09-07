"""SONIC AI — Smart File Manager & Finder.

Intelligent file operations: search, filter, recent, large, duplicates,
type grouping, path opener, disk cleanup, and more.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

_OS = platform.system()

if _OS == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}


# ── Common directories ────────────────────────────────────────────────────────

_HOME = Path.home()
_DESKTOP = _HOME / "Desktop"
_DOWNLOADS = _HOME / "Downloads"
_DOCUMENTS = _HOME / "Documents"
_PICTURES = _HOME / "Pictures"
_MUSIC = _HOME / "Music"
_VIDEOS = _HOME / "Videos"

_QUICK_FOLDERS = {
    "desktop": _DESKTOP,
    "downloads": _DOWNLOADS,
    "documents": _DOCUMENTS,
    "pictures": _PICTURES,
    "music": _MUSIC,
    "videos": _VIDEOS,
    "home": _HOME,
}

_FILE_CATEGORIES = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".raw"},
    "videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "music": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt"},
    "code": {".py", ".js", ".ts", ".java", ".cpp", ".c", ".h", ".cs", ".go", ".rs", ".html", ".css", ".json", ".xml"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "executables": {".exe", ".msi", ".app", ".deb", ".rpm"},
}


# ── Search & Find ─────────────────────────────────────────────────────────────

def find_files(
    query: str = "",
    directory: str = "",
    category: str = "",
    extension: str = "",
    max_results: int = 50,
    min_size_mb: float = 0,
    max_size_mb: float = 0,
    modified_days: int = 0,
) -> dict[str, Any]:
    """
    Smart file search with multiple filters.

    Args:
        query: filename contains (case-insensitive)
        directory: root search path (default: user home)
        category: pre-built category: images|videos|music|documents|code|archives|executables
        extension: filter by extension e.g. ".py"
        max_results: max files to return
        min_size_mb: minimum file size in MB
        max_size_mb: maximum file size in MB (0 = no limit)
        modified_days: only files modified within N days (0 = any)
    """
    root = Path(directory) if directory else _HOME
    if not root.exists():
        return {"ok": False, "error": f"Directory not found: {directory}"}

    exts = set()
    if category and category in _FILE_CATEGORIES:
        exts = _FILE_CATEGORIES[category]
    elif extension:
        exts = {extension if extension.startswith(".") else f".{extension}"}

    min_bytes = int(min_size_mb * 1024 * 1024) if min_size_mb else 0
    max_bytes = int(max_size_mb * 1024 * 1024) if max_size_mb else 0
    cutoff = time.time() - (modified_days * 86400) if modified_days else 0

    results = []
    query_lower = (query or "").lower()

    try:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            if len(results) >= max_results:
                break

            name = f.name.lower()

            # Filters
            if query_lower and query_lower not in name:
                continue
            if exts and f.suffix.lower() not in exts:
                continue
            try:
                stat = f.stat()
            except (OSError, PermissionError):
                continue
            if min_bytes and stat.st_size < min_bytes:
                continue
            if max_bytes and stat.st_size > max_bytes:
                continue
            if cutoff and stat.st_mtime < cutoff:
                continue

            results.append({
                "name": f.name,
                "path": str(f),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "extension": f.suffix,
            })
    except PermissionError:
        pass

    return {
        "ok": True,
        "count": len(results),
        "files": results,
        "searched_in": str(root),
    }


def find_recent_files(directory: str = "", days: int = 7, max_results: int = 30) -> dict[str, Any]:
    """Find recently modified files."""
    return find_files(directory=directory, modified_days=days, max_results=max_results)


def find_large_files(directory: str = "", min_mb: float = 100, max_results: int = 20) -> dict[str, Any]:
    """Find large files above min_mb size."""
    return find_files(directory=directory, min_size_mb=min_mb, max_results=max_results)


def find_duplicates(directory: str = "", max_results: int = 50) -> dict[str, Any]:
    """Find duplicate files by content hash (first 8KB + size)."""
    root = Path(directory) if directory else _HOME
    if not root.exists():
        return {"ok": False, "error": f"Directory not found: {directory}"}

    hash_map: dict[str, list[dict]] = defaultdict(list)
    count = 0

    try:
        for f in root.rglob("*"):
            if not f.is_file() or count > 5000:
                break
            try:
                stat = f.stat()
                if stat.st_size == 0:
                    continue
                # Quick hash: size + first 8KB
                with open(f, "rb") as fh:
                    head = fh.read(8192)
                key = f"{stat.st_size}_{hashlib.md5(head).hexdigest()}"
                hash_map[key].append({
                    "name": f.name,
                    "path": str(f),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                })
                count += 1
            except (OSError, PermissionError):
                continue
    except PermissionError:
        pass

    duplicates = {
        k: v for k, v in hash_map.items() if len(v) > 1
    }

    groups = []
    for i, (key, files) in enumerate(list(duplicates.items())[:max_results]):
        groups.append({
            "group": i + 1,
            "count": len(files),
            "size_mb": files[0]["size_mb"],
            "files": files,
        })

    return {
        "ok": True,
        "duplicate_groups": len(groups),
        "total_duplicate_files": sum(g["count"] for g in groups),
        "groups": groups,
    }


def categorize_files(directory: str = "", max_depth: int = 2) -> dict[str, Any]:
    """Categorize files in a directory by type."""
    root = Path(directory) if directory else _HOME
    if not root.exists():
        return {"ok": False, "error": f"Directory not found: {directory}"}

    categories: dict[str, list[str]] = defaultdict(list)
    uncategorized = []

    depth = str(root).count(os.sep) + max_depth

    try:
        for f in root.rglob("*"):
            if not f.is_file():
                continue
            if str(f).count(os.sep) > depth:
                continue

            found = False
            for cat, exts in _FILE_CATEGORIES.items():
                if f.suffix.lower() in exts:
                    categories[cat].append(f.name)
                    found = True
                    break
            if not found:
                uncategorized.append(f.name)
    except PermissionError:
        pass

    result = {cat: len(files) for cat, files in categories.items()}
    if uncategorized:
        result["other"] = len(uncategorized)

    return {"ok": True, "directory": str(root), "categories": result}


# ── Path / Folder Opener ──────────────────────────────────────────────────────

def open_path(path: str) -> dict[str, Any]:
    """Open a file or folder in the system default application."""
    p = Path(path)
    if not p.exists():
        # Try expanding user shortcuts
        expanded = _expand_path(path)
        if expanded and expanded.exists():
            p = expanded
        else:
            return {"ok": False, "error": f"Path not found: {path}"}

    try:
        if _OS == "Windows":
            os.startfile(str(p))
        elif _OS == "Darwin":
            subprocess.run(["open", str(p)], **_WIN_HIDE)
        else:
            subprocess.run(["xdg-open", str(p)], **_WIN_HIDE)

        kind = "folder" if p.is_dir() else "file"
        return {"ok": True, "opened": str(p), "kind": kind}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def open_folder(folder: str) -> dict[str, Any]:
    """Open a folder in file explorer."""
    return open_path(folder)


def get_folder_size(directory: str) -> dict[str, Any]:
    """Get total size of a directory."""
    root = Path(directory)
    if not root.exists():
        return {"ok": False, "error": f"Directory not found: {directory}"}

    total = 0
    file_count = 0
    dir_count = 0
    try:
        for f in root.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                    file_count += 1
                except (OSError, PermissionError):
                    pass
            elif f.is_dir():
                dir_count += 1
    except PermissionError:
        pass

    return {
        "ok": True,
        "path": str(root),
        "size_mb": round(total / (1024 * 1024), 2),
        "size_gb": round(total / (1024 * 1024 * 1024), 2),
        "files": file_count,
        "folders": dir_count,
    }


def list_folder(path: str = "", max_items: int = 30) -> dict[str, Any]:
    """List contents of a folder with sizes."""
    p = Path(path) if path else _HOME
    if not p.exists():
        return {"ok": False, "error": f"Path not found: {path}"}
    if not p.is_dir():
        return {"ok": False, "error": f"Not a directory: {path}"}

    items = []
    try:
        for item in sorted(p.iterdir()):
            if len(items) >= max_items:
                break
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "kind": "folder" if item.is_dir() else "file",
                    "size_mb": round(stat.st_size / (1024 * 1024), 2) if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "extension": item.suffix if item.is_file() else "",
                })
            except (OSError, PermissionError):
                items.append({"name": item.name, "kind": "unknown"})
    except PermissionError:
        return {"ok": False, "error": "Permission denied"}

    return {"ok": True, "path": str(p), "count": len(items), "items": items}


# ── Disk Cleanup ──────────────────────────────────────────────────────────────

def disk_cleanup(dry_run: bool = True) -> dict[str, Any]:
    """
    Find and optionally clean temporary/cache files.
    dry_run=True shows what would be deleted.
    """
    temp_dirs = [
        Path(os.environ.get("TEMP", "")),
        Path(os.environ.get("TMP", "")),
        _HOME / "AppData" / "Local" / "Temp",
    ]
    # Remove duplicates
    temp_dirs = list({d for d in temp_dirs if d.exists()})

    browser_cache = [
        _HOME / "AppData" / "Local" / "Google" / "Chrome" / "User Data" / "Default" / "Cache",
        _HOME / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache",
    ]

    trashable = []
    total_size = 0

    for d in temp_dirs + browser_cache:
        if not d.exists():
            continue
        try:
            for f in d.rglob("*"):
                if f.is_file():
                    try:
                        size = f.stat().st_size
                        age_days = (time.time() - f.stat().st_mtime) / 86400
                        if age_days > 1 and size > 1024:
                            trashable.append({
                                "path": str(f),
                                "size_mb": round(size / (1024 * 1024), 2),
                                "age_days": round(age_days, 1),
                            })
                            total_size += size
                            if len(trashable) >= 200:
                                break
                    except (OSError, PermissionError):
                        continue
        except PermissionError:
            continue

    if not dry_run and trashable:
        deleted = 0
        for item in trashable:
            try:
                p = Path(item["path"])
                if p.exists():
                    p.unlink()
                    deleted += 1
            except (OSError, PermissionError):
                pass
        return {
            "ok": True,
            "deleted": deleted,
            "freed_mb": round(total_size / (1024 * 1024), 2),
            "mode": "clean",
        }

    return {
        "ok": True,
        "files_found": len(trashable),
        "total_mb": round(total_size / (1024 * 1024), 2),
        "mode": "dry_run",
        "preview": trashable[:20],
    }


# ── Clipboard ─────────────────────────────────────────────────────────────────

def clipboard_get() -> dict[str, Any]:
    """Get current clipboard content."""
    try:
        import pyperclip
        text = pyperclip.paste()
        return {"ok": True, "content": text[:5000], "length": len(text)}
    except Exception:
        # Fallback: PowerShell
        if _OS == "Windows":
            try:
                r = subprocess.run(
                    ["powershell", "-Command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=5, **_WIN_HIDE
                )
                return {"ok": True, "content": r.stdout.strip()[:5000], "length": len(r.stdout.strip())}
            except Exception:
                pass
        return {"ok": False, "error": "Clipboard not accessible"}


def clipboard_set(text: str) -> dict[str, Any]:
    """Set clipboard content."""
    try:
        import pyperclip
        pyperclip.copy(text)
        return {"ok": True, "message": f"Clipboard set ({len(text)} chars)"}
    except Exception:
        if _OS == "Windows":
            try:
                subprocess.run(
                    ["powershell", "-Command", f'Set-Clipboard -Value "{text}"'],
                    capture_output=True, timeout=5, **_WIN_HIDE
                )
                return {"ok": True, "message": "Clipboard set"}
            except Exception:
                pass
        return {"ok": False, "error": "Could not set clipboard"}


# ── Battery ───────────────────────────────────────────────────────────────────

def battery_status() -> dict[str, Any]:
    """Get laptop battery status."""
    try:
        if _OS == "Windows":
            import ctypes
            battery = ctypes.Structure()
            # Use WMI via PowerShell
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-WmiObject Win32_Battery | Select-Object EstimatedChargeRemaining, BatteryStatus, TimeToFull | ConvertTo-Json"],
                capture_output=True, text=True, timeout=5, **_WIN_HIDE
            )
            if r.stdout.strip():
                import json
                data = json.loads(r.stdout)
                charge = data.get("EstimatedChargeRemaining", -1)
                status_code = data.get("BatteryStatus", 0)
                # 1=Discharging, 2=AC, 3=Fully charged, 4=Low, 5=Critical
                status_map = {1: "discharging", 2: "charging", 3: "full", 4: "low", 5: "critical"}
                return {
                    "ok": True,
                    "percent": charge,
                    "status": status_map.get(status_code, "unknown"),
                    "plugged_in": status_code in (2, 3, 6, 7, 8, 9),
                }
        elif _OS == "Linux":
            r = subprocess.run(
                ["upower", "-i", "/org/freedesktop/UPower/devices/battery_BAT0"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if "percentage" in line:
                    pct = int(line.split(":")[1].strip().replace("%", ""))
                    return {"ok": True, "percent": pct, "status": "unknown", "plugged_in": True}
    except Exception:
        pass
    return {"ok": False, "error": "Battery status not available (desktop?)"}


# ── WiFi / Network ────────────────────────────────────────────────────────────

def wifi_status() -> dict[str, Any]:
    """Get WiFi connection status."""
    try:
        if _OS == "Windows":
            r = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5, **_WIN_HIDE
            )
            ssid = ""
            signal = ""
            connected = False
            for line in r.stdout.splitlines():
                line = line.strip()
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":", 1)[-1].strip()
                if "Signal" in line:
                    signal = line.split(":", 1)[-1].strip()
                if "State" in line and "connected" in line.lower():
                    connected = True
            return {
                "ok": True,
                "connected": connected,
                "ssid": ssid,
                "signal": signal,
            }
        elif _OS == "Linux":
            r = subprocess.run(
                ["nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"],
                capture_output=True, text=True, timeout=5
            )
            for line in r.stdout.splitlines():
                if line.startswith("yes:"):
                    parts = line.split(":")
                    return {"ok": True, "connected": True, "ssid": parts[1], "signal": f"{parts[2]}%"}
            return {"ok": True, "connected": False, "ssid": "", "signal": ""}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Bluetooth ─────────────────────────────────────────────────────────────────

def bluetooth_status() -> dict[str, Any]:
    """Get Bluetooth status."""
    try:
        if _OS == "Windows":
            r = subprocess.run(
                ["powershell", "-Command",
                 "Get-PnpDevice -Class Bluetooth | Select-Object Status, FriendlyName | ConvertTo-Json"],
                capture_output=True, text=True, timeout=5, **_WIN_HIDE
            )
            if r.stdout.strip():
                import json
                devices = json.loads(r.stdout)
                if isinstance(devices, dict):
                    devices = [devices]
                return {
                    "ok": True,
                    "devices": [{"name": d.get("FriendlyName", ""), "status": d.get("Status", "")} for d in devices],
                    "count": len(devices),
                }
    except Exception:
        pass
    return {"ok": True, "status": "available"}


# ── Process Manager ───────────────────────────────────────────────────────────

def list_processes(sort_by: str = "cpu", max_results: int = 15) -> dict[str, Any]:
    """List top processes by CPU or memory usage."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            info = p.info
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": round(info.get("cpu_percent", 0), 1),
                "mem_mb": round((info.get("memory_percent", 0) or 0) * psutil.virtual_memory().total / (100 * 1024 * 1024), 1),
                "status": info.get("status", ""),
            })

        if sort_by == "mem":
            procs.sort(key=lambda x: x["mem_mb"], reverse=True)
        else:
            procs.sort(key=lambda x: x["cpu"], reverse=True)

        return {"ok": True, "processes": procs[:max_results], "total": len(procs)}
    except ImportError:
        return {"ok": False, "error": "psutil not installed"}


def kill_process(pid: int = 0, name: str = "") -> dict[str, Any]:
    """Kill a process by PID or name."""
    try:
        import psutil
        if pid:
            p = psutil.Process(pid)
            p.kill()
            return {"ok": True, "killed": p.name(), "pid": pid}
        elif name:
            killed = []
            for p in psutil.process_iter(["pid", "name"]):
                if name.lower() in p.info["name"].lower():
                    p.kill()
                    killed.append(p.info["name"])
            return {"ok": True, "killed": killed, "count": len(killed)}
        return {"ok": False, "error": "Provide pid or name"}
    except ImportError:
        return {"ok": False, "error": "psutil not installed"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Quick Actions ─────────────────────────────────────────────────────────────

def empty_recycle_bin() -> dict[str, Any]:
    """Empty the recycle bin."""
    if _OS == "Windows":
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            bin_folder = shell.NameSpace(10)
            count = bin_folder.Items().Count
            shell.NameSpace(10).Items().InvokeVerb("delete")
            return {"ok": True, "message": f"Recycle bin emptied ({count} items)"}
        except Exception:
            try:
                subprocess.run(
                    ["powershell", "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    capture_output=True, timeout=10, **_WIN_HIDE
                )
                return {"ok": True, "message": "Recycle bin emptied"}
            except Exception as e:
                return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "Not supported on this OS"}


def take_screenshot(save_path: str = "") -> dict[str, Any]:
    """Take a screenshot and save it."""
    try:
        import pyautogui
        if not save_path:
            save_path = str(_HOME / "Pictures" / f"screenshot_{int(time.time())}.png")
        pyautogui.screenshot(save_path)
        return {"ok": True, "path": save_path}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Helper ────────────────────────────────────────────────────────────────────

def _expand_path(path: str) -> Path | None:
    """Expand shortcuts like ~, %USERPROFILE%, quick folder names."""
    p = path.strip()

    # Quick folder names
    if p.lower() in _QUICK_FOLDERS:
        return _QUICK_FOLDERS[p.lower()]

    # Environment variables
    expanded = os.path.expandvars(p)
    result = Path(expanded)

    # ~ expansion
    if str(result).startswith("~"):
        result = Path(os.path.expanduser(str(result)))

    return result if result.exists() else None
