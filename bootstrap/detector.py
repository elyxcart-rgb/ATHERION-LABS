"""SONIC AI Bootstrapper - Dependency Detector.

Detects system requirements, bundled runtimes, and optional tools.
Returns structured status for each dependency.
"""
from __future__ import annotations

import os
import sys
import shutil
import ctypes
import platform
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Status(Enum):
    INSTALLED = "installed"
    MISSING = "missing"
    OUTDATED = "outdated"
    CHECK_FAILED = "check_failed"
    NOT_APPLICABLE = "not_applicable"
    SKIPPED = "skipped"


@dataclass
class DepResult:
    id: str
    name: str
    status: Status
    version: str = ""
    message: str = ""
    requires_admin: bool = False
    download_size_mb: float = 0


@dataclass
class SystemInfo:
    os_name: str = ""
    os_version: str = ""
    os_build: int = 0
    architecture: str = ""
    python_version: str = ""
    total_ram_gb: float = 0
    free_disk_mb: float = 0
    is_64bit: bool = False
    is_admin: bool = False


def get_system_info() -> SystemInfo:
    info = SystemInfo()
    info.os_name = platform.system()
    info.os_version = platform.version()
    info.architecture = platform.machine()
    info.python_version = platform.python_version()
    info.is_64bit = sys.maxsize > 2**32
    info.is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0

    try:
        build = int(platform.version().split(".")[-1])
        info.os_build = build
    except Exception:
        info.os_build = 0

    try:
        import psutil
        mem = psutil.virtual_memory()
        info.total_ram_gb = round(mem.total / (1024**3), 1)
    except Exception:
        info.total_ram_gb = 0

    try:
        usage = shutil.disk_usage("C:\\")
        info.free_disk_mb = round(usage.free / (1024**2), 0)
    except Exception:
        info.free_disk_mb = 0

    return info


def check_vc_redist() -> DepResult:
    dlls = ["vcruntime140.dll", "msvcp140.dll"]
    found = []
    for dll in dlls:
        if ctypes.windll.kernel32.GetModuleHandleW(dll):
            found.append(dll)
    if len(found) == len(dlls):
        return DepResult("vc_redist_x64", "Visual C++ Redistributable",
                         Status.INSTALLED, message="Bundled in EXE")
    return DepResult("vc_redist_x64", "Visual C++ Redistributable",
                     Status.MISSING, message="Not found")


def check_portaudio() -> DepResult:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        if devices:
            return DepResult("portaudio", "PortAudio", Status.INSTALLED,
                             message=f"{len(devices)} audio devices found")
    except Exception as e:
        pass
    try:
        pa_lib = Path(sys.prefix) / "Lib" / "site-packages" / "_portaudio.pyd"
        if pa_lib.exists():
            return DepResult("portaudio", "PortAudio", Status.INSTALLED,
                             message="Bundled")
    except Exception:
        pass
    return DepResult("portaudio", "PortAudio", Status.MISSING,
                     message="Audio library not available")


def check_python_runtime() -> DepResult:
    ver = sys.version_info
    if ver >= (3, 11):
        return DepResult("python_runtime", "Python Runtime", Status.INSTALLED,
                         version=f"{ver.major}.{ver.minor}.{ver.micro}",
                         message="Bundled in EXE")
    return DepResult("python_runtime", "Python Runtime", Status.OUTDATED,
                     version=f"{ver.major}.{ver.minor}.{ver.micro}",
                     message="Python 3.11+ required")


def check_qt_runtime() -> DepResult:
    try:
        from PyQt6.QtCore import QT_VERSION_STR
        return DepResult("qt_runtime", "Qt6 Runtime", Status.INSTALLED,
                         version=QT_VERSION_STR, message="Bundled in EXE")
    except ImportError:
        return DepResult("qt_runtime", "Qt6 Runtime", Status.MISSING,
                         message="PyQt6 not available")


def check_microphone() -> DepResult:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for d in devices:
            if d.get("max_input_channels", 0) > 0:
                return DepResult("mic_check", "Microphone", Status.INSTALLED,
                                 message=d.get("name", "Found"))
        return DepResult("mic_check", "Microphone", Status.MISSING,
                         message="No input device found")
    except Exception as e:
        return DepResult("mic_check", "Microphone", Status.CHECK_FAILED,
                         message=str(e))


def check_speakers() -> DepResult:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        for d in devices:
            if d.get("max_output_channels", 0) > 0:
                return DepResult("speaker_check", "Speakers", Status.INSTALLED,
                                 message=d.get("name", "Found"))
        return DepResult("speaker_check", "Speakers", Status.MISSING,
                         message="No output device found")
    except Exception as e:
        return DepResult("speaker_check", "Speakers", Status.CHECK_FAILED,
                         message=str(e))


def check_internet() -> DepResult:
    import urllib.request
    try:
        req = urllib.request.Request("https://www.google.com",
                                     method="HEAD")
        urllib.request.urlopen(req, timeout=5)
        return DepResult("internet_check", "Internet", Status.INSTALLED,
                         message="Connected")
    except Exception:
        return DepResult("internet_check", "Internet", Status.MISSING,
                         message="No internet connection")


def check_disk_space() -> DepResult:
    try:
        usage = shutil.disk_usage("C:\\")
        free_mb = usage.free / (1024**2)
        if free_mb >= 300:
            return DepResult("disk_space", "Disk Space", Status.INSTALLED,
                             message=f"{free_mb:.0f} MB free")
        return DepResult("disk_space", "Disk Space", Status.MISSING,
                         message=f"Only {free_mb:.0f} MB free (300 MB required)")
    except Exception as e:
        return DepResult("disk_space", "Disk Space", Status.CHECK_FAILED,
                         message=str(e))


def check_playwright() -> DepResult:
    try:
        from playwright.sync_api import sync_playwright
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run"],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if "chromium" in result.stdout.lower() or result.returncode == 0:
                return DepResult("playwright_chromium", "Playwright Chromium",
                                 Status.INSTALLED, message="Available")
        except Exception:
            pass
        return DepResult("playwright_chromium", "Playwright Chromium",
                         Status.MISSING, message="Browser not installed",
                         download_size_mb=150)
    except ImportError:
        return DepResult("playwright_chromium", "Playwright Chromium",
                         Status.MISSING, message="Playwright not installed",
                         download_size_mb=150)


def check_ffmpeg() -> DepResult:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return DepResult("ffmpeg", "FFmpeg", Status.INSTALLED,
                         message=f"Found at {ffmpeg_path}")
    return DepResult("ffmpeg", "FFmpeg", Status.MISSING,
                     message="Not on PATH")


def check_vlc() -> DepResult:
    try:
        import vlc
        ver = vlc.libvlc_get_version().decode()
        return DepResult("vlc", "VLC Media Player", Status.INSTALLED,
                         version=ver, message="Available")
    except ImportError:
        pass
    vlc_path = shutil.which("vlc")
    if vlc_path:
        return DepResult("vlc", "VLC Media Player", Status.INSTALLED,
                         message=f"Found at {vlc_path}")
    return DepResult("vlc", "VLC Media Player", Status.MISSING,
                     message="Not installed")


def check_opencode() -> DepResult:
    oc_path = shutil.which("opencode")
    if oc_path:
        return DepResult("opencode", "OpenCode", Status.INSTALLED,
                         message=f"Found at {oc_path}")
    npm_path = shutil.which("npm")
    if npm_path:
        return DepResult("opencode", "OpenCode", Status.MISSING,
                         message="Available via npm install -g opencode")
    return DepResult("opencode", "OpenCode", Status.MISSING,
                     message="Node.js/npm not found")


_DETECTORS = {
    "check_vc_redist": check_vc_redist,
    "check_portaudio": check_portaudio,
    "check_python_runtime": check_python_runtime,
    "check_qt_runtime": check_qt_runtime,
    "check_microphone": check_microphone,
    "check_speakers": check_speakers,
    "check_internet": check_internet,
    "check_disk_space": check_disk_space,
    "check_playwright": check_playwright,
    "check_ffmpeg": check_ffmpeg,
    "check_vlc": check_vlc,
    "check_opencode": check_opencode,
}


def detect_all(manifest_path: Optional[str] = None) -> list[DepResult]:
    import json
    if manifest_path is None:
        manifest_path = str(Path(__file__).parent / "manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    results = []
    for req in manifest.get("requirements", []):
        detect_fn = _DETECTORS.get(req.get("detect_command", ""))
        if detect_fn:
            try:
                result = detect_fn()
                results.append(result)
            except Exception as e:
                results.append(DepResult(
                    id=req["id"], name=req["name"],
                    status=Status.CHECK_FAILED, message=str(e)))
        else:
            results.append(DepResult(
                id=req["id"], name=req["name"],
                status=Status.NOT_APPLICABLE,
                message="No detector available"))
    return results


def detect_required(manifest_path: Optional[str] = None) -> list[DepResult]:
    import json
    if manifest_path is None:
        manifest_path = str(Path(__file__).parent / "manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    required_ids = {r["id"] for r in manifest.get("requirements", [])
                    if r.get("required", False)}
    all_results = detect_all(manifest_path)
    return [r for r in all_results if r.id in required_ids]


def detect_optional(manifest_path: Optional[str] = None) -> list[DepResult]:
    import json
    if manifest_path is None:
        manifest_path = str(Path(__file__).parent / "manifest.json")
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    optional_ids = {r["id"] for r in manifest.get("requirements", [])
                    if not r.get("required", False)}
    all_results = detect_all(manifest_path)
    return [r for r in all_results if r.id in optional_ids]
