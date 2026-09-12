"""
SONIC AI — Sci-Fi Gold Theme

GOLD + BLACK + AMBER — Military sci-fi aesthetic.
Angular panels, circuit connectors, HUD-style metrics.
"""

import colorsys
from PyQt6.QtGui import QColor


class SciFiC:
    """Sci-Fi Gold design tokens."""

    # ── Depth scale ──
    BG          = "#0a0a0a"
    PANEL       = "#0f0f0f"
    PANEL2      = "#141414"
    PANEL3      = "#1a1a1a"
    PANEL_HOVER = "#222222"

    # ── Metallic structure ──
    BORDER      = "#2a2a1a"
    BORDER_B    = "#3a3a2a"
    BORDER_A    = "#4a4a2a"
    BORDER_DIM  = "#1a1a10"
    METALLIC    = "#8a7a50"
    METALLIC_D  = "#5a4a30"

    # ── Gold accent ──
    PRI         = "#ffd700"
    PRI_DIM     = "#8a7a30"
    PRI_GHO     = "#1a1a08"
    PRI_SOFT    = "#2a2a10"
    PRI_VIVID   = "#ffe44d"

    # ── Status ──
    ACC         = "#ff9500"
    ACC2        = "#ccaa00"
    GREEN       = "#44cc66"
    GREEN_D     = "#1a4420"
    RED         = "#ff4444"
    RED_DIM     = "#2a0a0a"
    AMBER       = "#ffaa00"

    # ── Text hierarchy ──
    TEXT        = "#e0d8c0"
    TEXT_DIM    = "#6a6040"
    TEXT_MED    = "#8a8060"
    WHITE       = "#fff8e0"
    TEXT_COLD   = "#7a7050"
    TEXT_CYN    = "#ffd700"

    # ── Utility ──
    DARK        = "#080808"
    BAR_BG      = "#121210"
    MUTED_C     = "#aa3030"
    GLASS       = "#141410"
    GLASS_A     = "#0c0c08"

    # ── Typography ──
    FONT_SYS    = "Consolas"
    FONT_TITLE  = "Orbitron"
    FONT_BODY   = "Segoe UI"

    # ── Sci-Fi specific ──
    CIRCUIT     = "#3a3a1a"
    CIRCUIT_GLOW = "#ffd700"
    HEX_BG      = "#0c0c08"
    GRID_COLOR  = "#1a1a10"


class SciFiHU:
    """Sci-Fi HUD panel tokens — angular, military style."""
    BORDER    = "#2a2a1a"
    BRIGHT    = "#ffd700"
    GLOW      = "#1a1a08"
    FILL      = "#0e0e0c"
    FILL2     = "#141410"
    GOLD      = "#ffd700"
    GOLD_D    = "#8a7a30"
    RED       = "#ff4444"
    GREEN     = "#44cc66"
    TEXT      = "#e0d8c0"
    DIM       = "#6a6040"
    METALLIC  = "#8a7a50"

    # ── Accent colors ──
    CYAN      = "#ffd700"
    CYAN_DIM  = "#8a7a30"
    CYAN_GLOW = "#1a1a08"


def apply_scifi_theme():
    """Apply sci-fi gold theme to C and HU classes."""
    from .theme import C, HU

    for attr in dir(SciFiC):
        if not attr.startswith("_") and hasattr(C, attr):
            setattr(C, attr, getattr(SciFiC, attr))

    for attr in dir(SciFiHU):
        if not attr.startswith("_") and hasattr(HU, attr):
            setattr(HU, attr, getattr(SciFiHU, attr))


def restore_default_theme():
    """Restore the original platinum-cyan theme."""
    from .theme import C, HU

    defaults = {
        "BG": "#05070a", "PANEL": "#0a0d12", "PANEL2": "#0f1218",
        "PANEL3": "#151a21", "PANEL_HOVER": "#1a2028",
        "BORDER": "#1e2530", "BORDER_B": "#2a3440", "BORDER_A": "#1a3a4a",
        "BORDER_DIM": "#141a22", "METALLIC": "#4a5568", "METALLIC_D": "#2a3040",
        "PRI": "#00d9ff", "PRI_DIM": "#004d66", "PRI_GHO": "#081820",
        "PRI_SOFT": "#0a2230", "PRI_VIVID": "#00eaff",
        "ACC": "#b87a3a", "ACC2": "#a08050",
        "GREEN": "#3a9a6a", "GREEN_D": "#1a4a30",
        "RED": "#c43a4a", "RED_DIM": "#2a1018", "AMBER": "#b89040",
        "TEXT": "#c8cdd4", "TEXT_DIM": "#4a5568", "TEXT_MED": "#6b7a8a",
        "WHITE": "#e0e4ea", "TEXT_COLD": "#5a6a7a", "TEXT_CYN": "#6ab8d0",
        "DARK": "#060910", "BAR_BG": "#0c1018",
        "MUTED_C": "#aa2040", "GLASS": "#0c1220", "GLASS_A": "#081018",
    }
    for k, v in defaults.items():
        setattr(C, k, v)

    hu_defaults = {
        "BORDER": "#1e2530", "BRIGHT": "#c8cdd4", "GLOW": "#081018",
        "FILL": "#0a0e14", "FILL2": "#0f141c", "GOLD": "#d0d4da",
        "GOLD_D": "#6b7a8a", "RED": "#c43a4a", "GREEN": "#3a9a6a",
        "TEXT": "#c8cdd4", "DIM": "#4a5568", "METALLIC": "#4a5568",
        "CYAN": "#00d9ff", "CYAN_DIM": "#004d66", "CYAN_GLOW": "#081820",
    }
    for k, v in hu_defaults.items():
        setattr(HU, k, v)
