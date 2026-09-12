"""
SONIC Frontend Theme — Obsidian Silver sci-fi UI package.
PyQt6 widgets + web dashboard + config.
"""

from .theme import C, HU, apply_ui_accent, current_palette, retheme_all_widgets, qcol, DEFAULT_UI_COLOR
from .icons import svg_pixmap, _ICON_PATHS
from .widgets import (
    HudPanel, HudHeader, HudButton, HudLineEdit, HudCanvas,
    SciGauge, AmbientBackdrop, SciFrame, SciEqualizer, HueWheel,
)
from .theme_scifi import apply_scifi_theme, restore_default_theme, SciFiC, SciFiHU

__all__ = [
    "C", "HU", "qcol", "DEFAULT_UI_COLOR",
    "apply_ui_accent", "current_palette", "retheme_all_widgets",
    "svg_pixmap", "_ICON_PATHS",
    "HudPanel", "HudHeader", "HudButton", "HudLineEdit", "HudCanvas",
    "SciGauge", "AmbientBackdrop", "SciFrame", "SciEqualizer", "HueWheel",
    "apply_scifi_theme", "restore_default_theme", "SciFiC", "SciFiHU",
]
