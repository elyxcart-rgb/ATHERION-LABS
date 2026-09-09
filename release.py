"""SONIC AI — One-Command Release Automation

Usage:
    python release.py <version>

Example:
    python release.py 1.1.0

What it does:
    1. Validates version format
    2. Updates version.py
    3. Runs tests
    4. Builds SONIC-AI.exe (PyInstaller)
    5. Builds SONIC-Updater.exe (PyInstaller)
    6. Builds installer (Inno Setup)
    7. Calculates SHA-256
    8. Creates Git tag
    9. Creates GitHub Release
    10. Uploads installer
    11. Pushes to GitHub
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
SPEC = ROOT / "sonic.spec"
VERSION_FILE = ROOT / "version.py"
ISS_FILE = ROOT / "sonic_setup.iss"
INSTALLER_DIR = ROOT / "installer_output"

# Colors
C = "\033[96m"   # cyan
G = "\033[92m"   # green
R = "\033[91m"   # red
Y = "\033[93m"   # yellow
B = "\033[1m"    # bold
X = "\033[0m"    # reset


def log(msg: str, color: str = C) -> None:
    print(f"{color}{B}[RELEASE]{X} {msg}")


def fail(msg: str) -> None:
    log(msg, R)
    sys.exit(1)


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    log(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=capture, text=True)
    if check and result.returncode != 0:
        stderr = result.stderr if capture else ""
        fail(f"Command failed ({result.returncode}): {stderr[:500]}")
    return result


def calculate_sha256(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# Steps
# ═════════════════════════════════════════════════════════════════════════════

def step_validate_version(version: str) -> None:
    log("Step 1: Validating version...")
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        fail(f"Invalid version format: {version}. Use MAJOR.MINOR.PATCH")
    log(f"  Version: {version}", G)


def step_update_version(version: str) -> None:
    log("Step 2: Updating version.py...")
    content = VERSION_FILE.read_text(encoding="utf-8")
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("APP_VERSION: str = "):
            lines[i] = f'APP_VERSION: str = "{version}"'
        elif line.startswith("BUILD_VERSION: str = "):
            lines[i] = f'BUILD_VERSION: str = "{version}+build.{int(time.time())}"'
        elif line.startswith("BUILD_DATE: str = "):
            lines[i] = f'BUILD_DATE: str = "{datetime.now().strftime("%Y-%m-%d")}"'
    VERSION_FILE.write_text("\n".join(lines), encoding="utf-8")
    log(f"  APP_VERSION = {version}", G)


def step_update_iss(version: str) -> None:
    log("Step 3: Updating sonic_setup.iss...")
    if not ISS_FILE.exists():
        log("  sonic_setup.iss not found — skipping", Y)
        return
    content = ISS_FILE.read_text(encoding="utf-8")
    content = content.replace(
        '#define MyAppVersion "',
        f'#define MyAppVersion "{version}',
    ).split('"')[0] + f'"{version}"' + content.split('#define MyAppVersion "')[-1].split('"', 1)[-1]

    # Simpler: replace the line directly
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith('#define MyAppVersion "'):
            lines[i] = f'#define MyAppVersion "{version}"'
    ISS_FILE.write_text("\n".join(lines), encoding="utf-8")
    log(f"  ISS version = {version}", G)


def step_run_tests() -> None:
    log("Step 4: Running tests...")
    result = run([sys.executable, "-m", "pytest", "tests/", "-x", "-q"], check=False, capture=True)
    if result.returncode != 0:
        log(f"  Tests failed:\n{result.stdout[-1000:]}\n{result.stderr[-500:]}", R)
        fail("Tests failed — aborting release")
    log("  All tests passed", G)


def step_build_exe() -> Path:
    log("Step 5: Building SONIC-AI.exe...")
    # Clean
    for d in (BUILD, DIST):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)

    start = time.time()
    run([
        sys.executable, "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        str(SPEC),
    ])

    exe = DIST / "SONIC-AI.exe"
    if not exe.exists():
        exe = DIST / "SONIC-AI" / "SONIC-AI.exe"
    if not exe.exists():
        fail("EXE not found after build")

    elapsed = time.time() - start
    size_mb = exe.stat().st_size / (1024 * 1024)
    log(f"  SONIC-AI.exe: {size_mb:.1f} MB ({elapsed:.0f}s)", G)
    return exe


def step_build_updater() -> Path | None:
    log("Step 6: Building SONIC-Updater.exe...")
    updater_spec = ROOT / "updater_helper.spec"
    if not updater_spec.exists():
        # Create a simple spec for the updater helper
        log("  Creating updater_helper.spec...", Y)
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

    start = time.time()
    result = run([
        sys.executable, "-m", "PyInstaller",
        "--clean", "--noconfirm",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        str(updater_spec),
    ], check=False, capture=True)

    if result.returncode != 0:
        log(f"  Updater build failed:\n{result.stderr[-500:]}", Y)
        return None

    updater = DIST / "SONIC-Updater.exe"
    if not updater.exists():
        log("  SONIC-Updater.exe not found", Y)
        return None

    elapsed = time.time() - start
    size_mb = updater.stat().st_size / (1024 * 1024)
    log(f"  SONIC-Updater.exe: {size_mb:.1f} MB ({elapsed:.0f}s)", G)
    return updater


def step_build_installer(version: str) -> Path | None:
    log("Step 7: Building installer...")
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
        log("  Inno Setup not found — skipping installer", Y)
        return None

    start = time.time()
    run([iscc, str(ISS_FILE)])

    setups = list(INSTALLER_DIR.glob("SONIC-AI-Setup-*.exe"))
    if not setups:
        log("  Installer EXE not found", Y)
        return None

    setup = setups[0]
    elapsed = time.time() - start
    size_mb = setup.stat().st_size / (1024 * 1024)
    log(f"  Installer: {setup.name} ({size_mb:.1f} MB, {elapsed:.0f}s)", G)
    return setup


def step_calculate_hash(installer: Path) -> str:
    log("Step 8: Calculating SHA-256...")
    sha256 = calculate_sha256(installer)
    log(f"  SHA-256: {sha256[:32]}...", G)
    return sha256


def step_git_tag(version: str) -> None:
    log("Step 9: Creating Git tag...")
    tag = f"v{version}"
    # Delete existing tag if any
    subprocess.run(["git", "tag", "-d", tag], capture_output=True, cwd=str(ROOT))
    subprocess.run(["gh", "release", "delete", tag, "--yes"], capture_output=True, cwd=str(ROOT))

    run(["git", "add", "version.py", "sonic_setup.iss"], check=False)
    run(["git", "commit", "-m", f"Release v{version}"], check=False)
    run(["git", "tag", "-a", tag, "-m", f"Release {version}"])
    log(f"  Tag: {tag}", G)


def step_github_release(version: str, installer: Path, sha256: str) -> bool:
    log("Step 10: Creating GitHub Release...")

    # Check gh CLI
    result = subprocess.run(["gh", "--version"], capture_output=True)
    if result.returncode != 0:
        log("  gh CLI not found — skipping GitHub release", Y)
        return False

    result = subprocess.run(["gh", "auth", "status"], capture_output=True)
    if result.returncode != 0:
        log("  gh not authenticated — skipping GitHub release", Y)
        return False

    tag = f"v{version}"
    notes = f"""## SONIC AI v{version}

### What's New
- Update system improvements
- Bug fixes and stability improvements

### Installation
1. Download `SONIC-AI-Setup.exe`
2. Run the installer
3. Follow the setup wizard

### SHA-256
`{sha256}`

### System Requirements
- Windows 10/11 (64-bit)
- 4 GB RAM minimum
- 500 MB free disk space
"""

    result = run([
        "gh", "release", "create", tag,
        "--title", f"SONIC AI v{version}",
        "--notes", notes,
        "--latest",
        str(installer),
    ], check=False, capture=True)

    if result.returncode == 0:
        log(f"  Release: https://github.com/elyxcart-rgb/ATHERION-LABS/releases/tag/{tag}", G)
        return True
    else:
        log(f"  Failed: {result.stderr[:300]}", Y)
        return False


def step_push() -> None:
    log("Step 11: Pushing to GitHub...")
    run(["git", "push", "origin", "main", "--tags"], check=False)
    log("  Pushed", G)


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    if len(sys.argv) < 2:
        print(f"\n{C}{B}SONIC AI — Release Tool{X}\n")
        print(f"Usage: {sys.argv[0]} <version>")
        print(f"Example: {sys.argv[0]} 1.1.0\n")
        sys.exit(1)

    version = sys.argv[1]

    print(f"\n{C}{B}{'='*60}")
    print(f"  SONIC AI — Release v{version}")
    print(f"{'='*60}{X}\n")

    step_validate_version(version)
    step_update_version(version)
    step_update_iss(version)
    step_run_tests()
    exe = step_build_exe()
    updater = step_build_updater()
    installer = step_build_installer(version)

    if not installer:
        fail("No installer — cannot release")

    sha256 = step_calculate_hash(installer)
    step_git_tag(version)
    step_github_release(version, installer, sha256)
    step_push()

    print(f"\n{G}{B}{'='*60}")
    print(f"  RELEASE v{version} COMPLETE!")
    print(f"{'='*60}{X}\n")
    print(f"  Release URL:")
    print(f"  https://github.com/elyxcart-rgb/ATHERION-LABS/releases/tag/v{version}\n")
    print(f"  Installer: {installer.name}")
    print(f"  SHA-256:   {sha256}\n")
    print(f"  Users will be notified automatically on next launch.\n")


if __name__ == "__main__":
    main()
