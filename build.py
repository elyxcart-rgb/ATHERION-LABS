"""SONIC AI — Production Build Script.

Usage:
    python build.py

Builds the SONIC AI desktop application as a Windows EXE.
Output: dist/SONIC-AI/SONIC-AI.exe
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "sonic.spec"

# Colors for output
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(msg: str, color: str = CYAN) -> None:
    print(f"{color}{BOLD}[BUILD]{RESET} {msg}")


def run(cmd: list[str], check: bool = True) -> int:
    """Run a command and return the exit code."""
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if check and result.returncode != 0:
        log(f"Command failed with code {result.returncode}", RED)
        sys.exit(result.returncode)
    return result.returncode


def clean() -> None:
    """Clean previous build artifacts."""
    log("Cleaning previous builds...")
    for d in (BUILD, DIST):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    for f in ROOT.glob("*.spec.bak"):
        f.unlink(missing_ok=True)


def check_prerequisites() -> None:
    """Verify build tools are available."""
    log("Checking prerequisites...")

    # Check PyInstaller
    try:
        import PyInstaller
        log(f"  PyInstaller {PyInstaller.__version__}")
    except ImportError:
        log("  PyInstaller not found. Installing...", YELLOW)
        run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Check key dependencies
    for mod in ["PyQt6", "psutil", "google.genai", "sounddevice"]:
        try:
            __import__(mod)
            log(f"  {mod} OK")
        except ImportError:
            log(f"  WARNING: {mod} not installed", YELLOW)


def build() -> None:
    """Run PyInstaller build."""
    log("Building SONIC AI EXE...")
    start = time.time()

    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        str(SPEC),
    ], check=True)

    elapsed = time.time() - start
    log(f"Build completed in {elapsed:.1f}s", GREEN)


def verify() -> None:
    """Verify the build output exists."""
    exe = DIST / "SONIC-AI.exe"
    if not exe.exists():
        # Try subdirectory layout
        exe = DIST / "SONIC-AI" / "SONIC-AI.exe"
    if not exe.exists():
        log("ERROR: EXE not found after build!", RED)
        sys.exit(1)

    size_mb = exe.stat().st_size / (1024 * 1024)
    log(f"Output: {exe}", GREEN)
    log(f"Size: {size_mb:.1f} MB", GREEN)

    # Check critical files are bundled
    data_dir = DIST / "SONIC-AI"
    required = ["config/sonic.ico", "config/api_keys.json", "core/prompt.txt"]
    for r in required:
        p = data_dir / r
        if p.exists():
            log(f"  OK: {r}")
        else:
            log(f"  MISSING: {r}", RED)


def build_updater() -> None:
    """Build SONIC-Updater.exe from updater_helper.py."""
    updater_spec = ROOT / "updater_helper.spec"

    # Create spec if it doesn't exist
    if not updater_spec.exists():
        spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ['updater_helper.py'],
    pathex=[{repr(str(ROOT))}],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SONIC-Updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='config/sonic.ico',
)
"""
        updater_spec.write_text(spec_content, encoding="utf-8")

    log("Building SONIC-Updater.exe...")
    start = time.time()

    run([
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        str(updater_spec),
    ], check=True)

    updater_exe = DIST / "SONIC-Updater.exe"
    if updater_exe.exists():
        size_mb = updater_exe.stat().st_size / (1024 * 1024)
        log(f"SONIC-Updater.exe: {size_mb:.1f} MB", GREEN)
    else:
        log("SONIC-Updater.exe not found after build", YELLOW)

    elapsed = time.time() - start
    log(f"Updater build completed in {elapsed:.1f}s", GREEN)


def build_installer() -> None:
    """Build Inno Setup installer."""
    iscc_paths = [
        r"C:\Users\94\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    iscc = None
    for p in iscc_paths:
        if os.path.exists(p):
            iscc = p
            break

    if not iscc:
        log("Inno Setup not found — skipping installer build", YELLOW)
        return

    iss_script = ROOT / "sonic_setup.iss"
    if not iss_script.exists():
        log("sonic_setup.iss not found — skipping installer build", YELLOW)
        return

    log("Building installer...")
    start = time.time()

    run([iscc, str(iss_script)], check=True)

    elapsed = time.time() - start
    installer_dir = ROOT / "installer_output"
    setup_files = list(installer_dir.glob("SONIC-AI-Setup-*.exe"))
    if setup_files:
        setup = setup_files[0]
        size_mb = setup.stat().st_size / (1024 * 1024)
        log(f"Installer: {setup}", GREEN)
        log(f"Installer size: {size_mb:.1f} MB", GREEN)
    else:
        log("Installer build completed but EXE not found", YELLOW)

    log(f"Installer build completed in {elapsed:.1f}s", GREEN)


def main() -> None:
    log(f"{BOLD}SONIC AI — Production Build{RESET}")
    log(f"Root: {ROOT}")
    log("")

    clean()
    check_prerequisites()
    build()
    verify()
    build_updater()
    build_installer()

    log("")
    log(f"{GREEN}{BOLD}Build successful!{RESET}")
    log(f"Portable EXE: {DIST / 'SONIC-AI.exe'}")
    installer_dir = ROOT / "installer_output"
    setup_files = list(installer_dir.glob("SONIC-AI-Setup-*.exe"))
    if setup_files:
        log(f"Setup Installer: {setup_files[0]}")
    log("")
    log("To test: dist\\SONIC-AI.exe")


if __name__ == "__main__":
    main()
