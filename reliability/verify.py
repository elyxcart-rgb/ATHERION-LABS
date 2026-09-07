"""SONIC AI — Operation Verifier.

Verifies file operations actually succeeded.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class VerifyResult:
    success: bool
    message: str
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


def verify_file_exists(path: str) -> VerifyResult:
    p = Path(path)
    if p.exists():
        return VerifyResult(True, f"Exists: {p.name}", {"path": str(p), "is_file": p.is_file(), "is_dir": p.is_dir()})
    return VerifyResult(False, f"Not found: {path}")


def verify_file_deleted(path: str) -> VerifyResult:
    p = Path(path)
    if not p.exists():
        return VerifyResult(True, f"Deleted: {path}")
    return VerifyResult(False, f"Still exists: {path}")


def verify_move(source: str, destination: str) -> VerifyResult:
    src = Path(source)
    dst = Path(destination)
    if not dst.exists():
        return VerifyResult(False, f"Destination not found: {destination}")
    if src.exists():
        return VerifyResult(False, f"Source still exists at original location: {source}")
    return VerifyResult(True, f"Moved: {src.name} -> {dst}")


def verify_copy(source: str, destination: str) -> VerifyResult:
    dst = Path(destination)
    if not dst.exists():
        return VerifyResult(False, f"Copy destination not found: {destination}")
    src = Path(source)
    if src.exists() and src.is_file() and dst.is_file():
        if src.stat().st_size == dst.stat().st_size:
            return VerifyResult(True, f"Copied: {dst.name} ({dst.stat().st_size} bytes)")
        return VerifyResult(False, f"Size mismatch: source={src.stat().st_size}, dest={dst.stat().st_size}")
    return VerifyResult(True, f"Copied: {dst.name}")


def verify_create(path: str) -> VerifyResult:
    p = Path(path)
    if p.exists():
        return VerifyResult(True, f"Created: {p.name}")
    return VerifyResult(False, f"Creation failed: {path}")


def verify_folder_contains(folder: str, filename: str) -> VerifyResult:
    f = Path(folder)
    if not f.exists():
        return VerifyResult(False, f"Folder not found: {folder}")
    if not f.is_dir():
        return VerifyResult(False, f"Not a folder: {folder}")
    target = f / filename
    if target.exists():
        return VerifyResult(True, f"Found {filename} in {f.name}")
    return VerifyResult(False, f"{filename} not found in {f.name}")


def verify_open(path: str) -> VerifyResult:
    p = Path(path)
    if not p.exists():
        return VerifyResult(False, f"Cannot open: not found: {path}")
    return VerifyResult(True, f"Opening: {p.name}")
