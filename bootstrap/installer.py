"""SONIC AI Bootstrapper - Dependency Installer.

Handles installation of missing dependencies.
Supports pip packages, Playwright browsers, and manual instructions.
"""
from __future__ import annotations

import os
import sys
import subprocess
import shutil
import urllib.request
import hashlib
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

from .detector import Status, DepResult


@dataclass
class InstallResult:
    success: bool
    message: str = ""
    requires_manual: bool = False
    manual_url: str = ""
    manual_instructions: str = ""


class DependencyInstaller:
    def __init__(self, progress_callback: Optional[Callable] = None):
        self._progress = progress_callback or (lambda msg, pct: None)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def install(self, dep_id: str, manifest_entry: dict) -> InstallResult:
        method = manifest_entry.get("install_method", "")
        self._progress(f"Installing {manifest_entry.get('name', dep_id)}...", 0)

        if method == "bundled":
            return InstallResult(True, "Already bundled in EXE")
        elif method == "pip_and_playwright_install":
            return self._install_playwright()
        elif method == "npm_global":
            return self._install_npm_global(manifest_entry.get("install_args", []))
        elif method == "manual":
            return InstallResult(
                False, "Manual installation required",
                requires_manual=True,
                manual_instructions=manifest_entry.get("description", ""),
                manual_url=manifest_entry.get("download_url", "")
            )
        elif method == "manual_path":
            return InstallResult(
                False, "Manual installation required",
                requires_manual=True,
                manual_url=manifest_entry.get("download_url", ""),
                manual_instructions=f"Download and add to PATH: {manifest_entry.get('name', dep_id)}"
            )
        else:
            return InstallResult(False, f"Unknown install method: {method}")

    def _install_playwright(self) -> InstallResult:
        try:
            self._progress("Installing Playwright...", 10)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                capture_output=True, text=True, timeout=120,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if result.returncode != 0:
                return InstallResult(False, f"pip install failed: {result.stderr[:200]}")

            self._progress("Downloading Chromium browser (~150 MB)...", 40)
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=600,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if result.returncode != 0:
                return InstallResult(False, f"Playwright install failed: {result.stderr[:200]}")

            self._progress("Playwright installed", 100)
            return InstallResult(True, "Playwright + Chromium installed")
        except subprocess.TimeoutExpired:
            return InstallResult(False, "Installation timed out")
        except Exception as e:
            return InstallResult(False, str(e))

    def _install_npm_global(self, args: list) -> InstallResult:
        npm_path = shutil.which("npm")
        if not npm_path:
            return InstallResult(
                False, "npm not found",
                requires_manual=True,
                manual_url="https://nodejs.org/",
                manual_instructions="Install Node.js from https://nodejs.org/ first"
            )
        try:
            self._progress("Installing via npm...", 20)
            cmd = [npm_path] + args
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            if result.returncode != 0:
                return InstallResult(False, f"npm install failed: {result.stderr[:200]}")
            self._progress("Installed", 100)
            return InstallResult(True, "Installed via npm")
        except subprocess.TimeoutExpired:
            return InstallResult(False, "Installation timed out")
        except Exception as e:
            return InstallResult(False, str(e))

    def verify_installation(self, dep_id: str) -> bool:
        from .detector import _DETECTORS
        detector_map = {
            "playwright_chromium": "check_playwright",
            "opencode": "check_opencode",
            "ffmpeg": "check_ffmpeg",
            "vlc": "check_vlc",
        }
        detect_name = detector_map.get(dep_id)
        if detect_name and detect_name in _DETECTORS:
            result = _DETECTORS[detect_name]()
            return result.status == Status.INSTALLED
        return False
