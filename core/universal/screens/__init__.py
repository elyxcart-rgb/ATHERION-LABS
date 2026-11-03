"""SONIC AI — Screen Understanding Layer.

Helpers for interpreting what's visible on screen:
  - DPI awareness
  - multi-monitor geometry
  - dialog/popup detection
  - structured scene parsing from a screenshot

Public API:
    from core.universal.screens import (
        ScreenUnderstanding, DialogDetector, DPIBridge, MultiMonitor,
    )
"""
from __future__ import annotations

from .dpi import DPIBridge, MultiMonitor
from .dialog_detector import DialogDetector, DetectedDialog
from .parser import ScreenUnderstanding, SceneSnapshot


__all__ = [
    "DPIBridge", "MultiMonitor",
    "DialogDetector", "DetectedDialog",
    "ScreenUnderstanding", "SceneSnapshot",
]
