"""SONIC AI — Updater Helper

This script is compiled into SONIC-Updater.exe and handles:
1. Waiting for SONIC to exit
2. Backing up the old version
3. Installing the new version
4. Verifying the installation
5. Launching the new SONIC
6. Rollback if anything fails

Usage:
    SONIC-Updater.exe <new_exe_path> <target_exe_path> <backup_dir>
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime


def log(msg: str) -> None:
    """Log to updater journal."""
    timestamp = datetime.now().isoformat()
    line = f"[{timestamp}] {msg}"
    print(line)

    # Append to journal
    journal_path = Path(os.environ.get("LOCALAPPDATA", "")) / "SONIC AI" / "updates" / "update_journal.jsonl"
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def wait_for_process_exit(process_name: str, timeout: int = 30) -> bool:
    """Wait for a process to exit."""
    log(f"Waiting for {process_name} to exit...")

    start = time.time()
    while time.time() - start < timeout:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
            capture_output=True, text=True
        )
        if process_name.lower() not in result.stdout.lower():
            log(f"{process_name} exited")
            return True
        time.sleep(1)

    log(f"Timeout waiting for {process_name}")
    return False


def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def backup_current(target_exe: Path, backup_dir: Path) -> bool:
    """Backup the current EXE."""
    log(f"Backing up current version...")

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_exe = backup_dir / "SONIC-AI.exe"

    try:
        if target_exe.exists():
            shutil.copy2(target_exe, backup_exe)
            log(f"Backup created: {backup_exe}")
            return True
    except Exception as e:
        log(f"Backup failed: {e}")

    return False


def install_update(new_exe: Path, target_exe: Path) -> bool:
    """Install the new EXE."""
    log(f"Installing update...")

    try:
        # Rename old EXE
        old_exe = target_exe.with_suffix(".exe.old")
        if old_exe.exists():
            old_exe.unlink(missing_ok=True)

        if target_exe.exists():
            target_exe.rename(old_exe)
            log(f"Old EXE renamed to: {old_exe.name}")

        # Copy new EXE
        shutil.copy2(new_exe, target_exe)
        log(f"New EXE installed: {target_exe}")

        return True
    except Exception as e:
        log(f"Install failed: {e}")
        return False


def verify_installation(target_exe: Path, expected_version: str) -> bool:
    """Verify the new installation."""
    log(f"Verifying installation...")

    if not target_exe.exists():
        log("EXE not found after install")
        return False

    # Check file size is reasonable (> 10MB)
    size_mb = target_exe.stat().st_size / (1024 * 1024)
    if size_mb < 10:
        log(f"EXE too small: {size_mb:.1f} MB")
        return False

    log(f"Installation verified: {size_mb:.1f} MB")
    return True


def launch_sonic(target_exe: Path) -> bool:
    """Launch the new SONIC."""
    log(f"Launching SONIC...")

    try:
        subprocess.Popen(
            [str(target_exe)],
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        log("SONIC launched")
        return True
    except Exception as e:
        log(f"Launch failed: {e}")
        return False


def rollback(target_exe: Path, backup_dir: Path) -> bool:
    """Rollback to the previous version."""
    log(f"Rolling back to previous version...")

    backup_exe = backup_dir / "SONIC-AI.exe"
    if not backup_exe.exists():
        log("No backup found for rollback")
        return False

    try:
        # Remove failed install
        if target_exe.exists():
            target_exe.unlink(missing_ok=True)

        # Restore from backup
        shutil.copy2(backup_exe, target_exe)
        log(f"Restored from backup: {backup_exe}")

        # Launch old version
        launch_sonic(target_exe)

        return True
    except Exception as e:
        log(f"Rollback failed: {e}")
        return False


def main() -> None:
    """Main updater logic."""
    log("=" * 60)
    log("SONIC AI Updater Helper started")
    log("=" * 60)

    # Parse arguments
    if len(sys.argv) < 4:
        log("Usage: SONIC-Updater.exe <new_exe_path> <target_exe_path> <backup_dir>")
        sys.exit(1)

    new_exe = Path(sys.argv[1])
    target_exe = Path(sys.argv[2])
    backup_dir = Path(sys.argv[3])

    log(f"New EXE: {new_exe}")
    log(f"Target EXE: {target_exe}")
    log(f"Backup dir: {backup_dir}")

    # Validate inputs
    if not new_exe.exists():
        log(f"New EXE not found: {new_exe}")
        sys.exit(1)

    # Step 1: Wait for SONIC to exit
    if not wait_for_process_exit("SONIC-AI.exe", timeout=30):
        log("SONIC did not exit in time")
        sys.exit(1)

    # Step 2: Backup current version
    if not backup_current(target_exe, backup_dir):
        log("Backup failed — aborting update")
        sys.exit(1)

    # Step 3: Install update
    if not install_update(new_exe, target_exe):
        log("Install failed — rolling back")
        rollback(target_exe, backup_dir)
        sys.exit(1)

    # Step 4: Verify installation
    if not verify_installation(target_exe, ""):
        log("Verification failed — rolling back")
        rollback(target_exe, backup_dir)
        sys.exit(1)

    # Step 5: Launch new SONIC
    if not launch_sonic(target_exe):
        log("Launch failed — rolling back")
        rollback(target_exe, backup_dir)
        sys.exit(1)

    log("=" * 60)
    log("Update completed successfully!")
    log("=" * 60)

    # Cleanup old EXE after successful update
    old_exe = target_exe.with_suffix(".exe.old")
    if old_exe.exists():
        try:
            old_exe.unlink(missing_ok=True)
            log("Cleaned up old EXE")
        except Exception:
            pass

    sys.exit(0)


if __name__ == "__main__":
    main()
