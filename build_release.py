"""SONIC AI — Build & Release Script

Usage:
    python build_release.py <version>

Example:
    python build_release.py 1.1.0

This script:
1. Updates version.py
2. Runs PyInstaller build
3. Calculates SHA-256
4. Creates GitHub release
5. Uploads installer
6. Updates manifest

Requirements:
- Git configured with push access
- gh CLI authenticated (GitHub CLI)
- Inno Setup installed
"""
from __future__ import annotations

import hashlib
import json
import os
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
MANIFEST_FILE = ROOT / "releases" / "stable.json"
INSTALLER_DIR = ROOT / "installer_output"

# Colors
CYAN = "\033[96m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def log(msg: str, color: str = CYAN) -> None:
    print(f"{color}{BOLD}[RELEASE]{RESET} {msg}")


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command."""
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=capture, text=True
    )
    if check and result.returncode != 0:
        log(f"Command failed: {result.stderr if capture else ''}", RED)
        sys.exit(result.returncode)
    return result


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def update_version(version: str) -> None:
    """Update version.py with new version."""
    log(f"Updating version to {version}...")

    content = VERSION_FILE.read_text(encoding="utf-8")

    # Update APP_VERSION
    content = content.replace(
        'APP_VERSION: str = "',
        f'APP_VERSION: str = "{version}'
    ).split('"')[0] + f'"{version}"' + content.split('APP_VERSION: str = "')[-1].split('"', 1)[-1]

    # Simpler approach: replace the whole line
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("APP_VERSION: str = "):
            lines[i] = f'APP_VERSION: str = "{version}"'
        elif line.startswith("BUILD_VERSION: str = "):
            lines[i] = f'BUILD_VERSION: str = "{version}+build.{int(time.time())}"'
        elif line.startswith("BUILD_DATE: str = "):
            lines[i] = f'BUILD_DATE: str = "{datetime.now().strftime("%Y-%m-%d")}"'

    VERSION_FILE.write_text("\n".join(lines), encoding="utf-8")
    log(f"Version updated to {version}", GREEN)


def clean() -> None:
    """Clean previous build artifacts."""
    log("Cleaning previous builds...")
    for d in (BUILD, DIST):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


def build_exe() -> Path:
    """Build the EXE with PyInstaller."""
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

    exe = DIST / "SONIC-AI.exe"
    if not exe.exists():
        exe = DIST / "SONIC-AI" / "SONIC-AI.exe"

    if not exe.exists():
        log("ERROR: EXE not found after build!", RED)
        sys.exit(1)

    elapsed = time.time() - start
    size_mb = exe.stat().st_size / (1024 * 1024)
    log(f"EXE built: {exe} ({size_mb:.1f} MB) in {elapsed:.1f}s", GREEN)
    return exe


def build_installer(version: str) -> Path | None:
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
        log("Inno Setup not found — skipping installer", YELLOW)
        return None

    iss_script = ROOT / "sonic_setup.iss"
    if not iss_script.exists():
        log("sonic_setup.iss not found — skipping installer", YELLOW)
        return None

    log("Building installer...")
    start = time.time()

    run([iscc, str(iss_script)], check=True)

    elapsed = time.time() - start
    setup_files = list(INSTALLER_DIR.glob("SONIC-AI-Setup-*.exe"))

    if setup_files:
        setup = setup_files[0]
        size_mb = setup.stat().st_size / (1024 * 1024)
        log(f"Installer: {setup} ({size_mb:.1f} MB) in {elapsed:.1f}s", GREEN)
        return setup

    log("Installer build completed but EXE not found", YELLOW)
    return None


def create_github_release(version: str, installer_path: Path, sha256: str) -> bool:
    """Create GitHub release and upload installer."""
    log("Creating GitHub release...")

    # Check if gh CLI is available
    try:
        result = subprocess.run(["gh", "--version"], capture_output=True, check=True)
    except FileNotFoundError:
        log("GitHub CLI (gh) not found. Install it from https://cli.github.com/", RED)
        log("Or create release manually at: https://github.com/elyxcart-rgb/ATHERION-LABS/releases/new", YELLOW)
        return False

    # Check if authenticated
    try:
        result = subprocess.run(["gh", "auth", "status"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        log("GitHub CLI not authenticated. Run: gh auth login", RED)
        return False

    # Delete existing tag if it exists
    tag = f"v{version}"
    subprocess.run(["git", "tag", "-d", tag], capture_output=True)
    subprocess.run(["gh", "release", "delete", tag, "--yes"], capture_output=True)

    # Create git tag
    run(["git", "tag", "-a", tag, "-m", f"Release {version}"], check=True)
    run(["git", "push", "origin", tag, "--force"], check=True)

    # Create release with installer
    release_notes = f"""## SONIC AI v{version}

### What's New
- Update system improvements
- Bug fixes and stability improvements

### Installation
1. Download `SONIC-AI-Setup-{version}.exe`
2. Run the installer
3. Follow the setup wizard

### SHA-256
`{sha256}`

### System Requirements
- Windows 10/11 (64-bit)
- 4 GB RAM minimum
- 500 MB free disk space
"""

    cmd = [
        "gh", "release", "create", tag,
        "--title", f"SONIC AI v{version}",
        "--notes", release_notes,
        "--latest",
        str(installer_path),
    ]

    result = run(cmd, check=False, capture=True)

    if result.returncode == 0:
        log(f"Release created: https://github.com/elyxcart-rgb/ATHERION-LABS/releases/tag/{tag}", GREEN)
        return True
    else:
        log(f"Failed to create release: {result.stderr}", RED)
        return False


def update_manifest(version: str, installer_path: Path, sha256: str) -> None:
    """Update the stable.json manifest."""
    log("Updating manifest...")

    MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "schema_version": 1,
        "app": "SONIC AI",
        "channel": "stable",
        "version": version,
        "minimum_supported_version": "1.0.0",
        "release_id": f"v{version}",
        "published_at": datetime.now().isoformat(),
        "mandatory": False,
        "title": f"SONIC AI v{version}",
        "summary": f"SONIC AI version {version}",
        "installer": {
            "filename": installer_path.name,
            "url": f"https://github.com/elyxcart-rgb/ATHERION-LABS/releases/download/v{version}/{installer_path.name}",
            "size_bytes": installer_path.stat().st_size,
            "sha256": sha256,
            "signature": ""
        },
        "download_url": f"https://github.com/elyxcart-rgb/ATHERION-LABS/releases/download/v{version}/{installer_path.name}",
        "sha256": sha256,
        "size_bytes": installer_path.stat().st_size,
        "release_notes": f"SONIC AI version {version}",
        "release_date": datetime.now().strftime("%Y-%m-%d"),
    }

    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Manifest updated: {MANIFEST_FILE}", GREEN)


def push_manifest() -> None:
    """Push manifest changes to GitHub."""
    log("Pushing manifest to GitHub...")

    run(["git", "add", "releases/stable.json", "version.py"], check=True)
    run(["git", "commit", "-m", f"Release update to v{version}"], check=True)
    run(["git", "push", "origin", "main"], check=True)

    log("Manifest pushed to GitHub", GREEN)


def main() -> None:
    if len(sys.argv) < 2:
        log("Usage: python build_release.py <version>", RED)
        log("Example: python build_release.py 1.1.0", YELLOW)
        sys.exit(1)

    version = sys.argv[1]

    # Validate version format
    parts = version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        log("Invalid version format. Use: MAJOR.MINOR.PATCH (e.g., 1.1.0)", RED)
        sys.exit(1)

    log(f"{BOLD}SONIC AI — Release Build v{version}{RESET}")
    log(f"Root: {ROOT}")
    log("")

    # Step 1: Update version
    update_version(version)

    # Step 2: Clean and build
    clean()
    exe_path = build_exe()

    # Step 3: Build installer
    installer_path = build_installer(version)

    if not installer_path:
        log("No installer built. Creating portable release only.", YELLOW)
        installer_path = exe_path

    # Step 4: Calculate SHA-256
    log("Calculating SHA-256...")
    sha256 = calculate_sha256(installer_path)
    log(f"SHA-256: {sha256[:32]}...", GREEN)

    # Step 5: Create GitHub release
    if create_github_release(version, installer_path, sha256):
        # Step 6: Update manifest
        update_manifest(version, installer_path, sha256)

        # Step 7: Push manifest
        push_manifest()

        log("")
        log(f"{GREEN}{BOLD}Release v{version} complete!{RESET}")
        log(f"Release URL: https://github.com/elyxcart-rgb/ATHERION-LABS/releases/tag/v{version}")
        log(f"Manifest: {MANIFEST_FILE}")
    else:
        log("")
        log(f"{YELLOW}Release partially complete.{RESET}")
        log("Manual steps required:")
        log(f"1. Create release at: https://github.com/elyxcart-rgb/ATHERION-LABS/releases/new")
        log(f"2. Upload: {installer_path}")
        log(f"3. Tag: v{version}")
        log(f"4. Push manifest: git push origin main")


if __name__ == "__main__":
    main()
