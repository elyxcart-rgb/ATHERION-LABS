"""
SONIC AI — Premium Design Token System

BLACK + PLATINUM + ULTRA-SUBTLE ELECTRIC CYAN

Philosophy: "Less interface. More intelligence."
70% black/graphite · 25% platinum/silver · 5% cyan accent
"""

import colorsys
from PyQt6.QtGui import QColor


# ─────────────────────────────────────────────────────────────────
#  DESIGN TOKENS — Single source of truth for entire UI
# ─────────────────────────────────────────────────────────────────

class C:
    """Core design tokens. All UI colors reference these."""

    # ── Depth scale (near-black to elevated) ──
    BG          = "#05070a"      # Void — deepest background
    PANEL       = "#0a0d12"      # Primary surface
    PANEL2      = "#0f1218"      # Secondary surface
    PANEL3      = "#151a21"      # Elevated surface
    PANEL_HOVER = "#1a2028"      # Hover lift

    # ── Metallic structure ──
    BORDER      = "#1e2530"      # Default — dark metallic
    BORDER_B    = "#2a3440"      # Bright — active/selected
    BORDER_A    = "#1a3a4a"      # Accent edge — ultra-subtle cyan tint
    BORDER_DIM  = "#141a22"      # Dim — inactive
    METALLIC    = "#4a5568"      # Platinum highlight
    METALLIC_D  = "#2a3040"      # Dark metallic

    # ── Cyan accent (intelligent status, NOT decoration) ──
    PRI         = "#00d9ff"      # Electric cyan — active state only
    PRI_DIM     = "#004d66"      # Dimmed cyan
    PRI_GHO     = "#081820"      # Ghost — selection bg
    PRI_SOFT    = "#0a2230"      # Soft — subtle active bg
    PRI_VIVID   = "#00eaff"      # Vivid — peak activity

    # ── Status (restrained, warm) ──
    ACC         = "#b87a3a"      # Warm — GPU, alerts
    ACC2        = "#a08050"      # Amber-gold — memory
    GREEN       = "#3a9a6a"      # Success — healthy
    GREEN_D     = "#1a4a30"      # Dimmed green
    RED         = "#c43a4a"      # Error — restrained
    RED_DIM     = "#2a1018"      # Dimmed red bg
    AMBER       = "#b89040"      # Warning — non-critical

    # ── Text hierarchy (platinum → graphite) ──
    TEXT        = "#c8cdd4"      # Primary — soft platinum
    TEXT_DIM    = "#4a5568"      # Dimmed — timestamps
    TEXT_MED    = "#6b7a8a"      # Medium — labels
    WHITE       = "#e0e4ea"      # Bright — emphasis
    TEXT_COLD   = "#5a6a7a"      # Cold — inactive
    TEXT_CYN    = "#6ab8d0"      # Cyan text — active labels only

    # ── Utility ──
    DARK        = "#060910"      # Darkest fill
    BAR_BG      = "#0c1018"      # Bar background
    MUTED_C     = "#aa2040"      # Mic muted
    GLASS       = "#0c1220"      # Glass surface
    GLASS_A     = "#081018"      # Glass dark

    # ── Typography ──
    FONT_SYS    = "Consolas"
    FONT_TITLE  = "Orbitron"
    FONT_BODY   = "Segoe UI"


class HU:
    """HUD panel tokens — premium angular surfaces."""
    BORDER    = "#1e2530"
    BRIGHT    = "#c8cdd4"       # PLATINUM text, NOT cyan
    GLOW      = "#081018"       # Subtle inner glow base
    FILL      = "#0a0e14"       # Panel fill
    FILL2     = "#0f141c"       # Elevated fill
    GOLD      = "#d0d4da"       # Title emphasis — platinum white
    GOLD_D    = "#6b7a8a"       # Dimmed title
    RED       = "#c43a4a"
    GREEN     = "#3a9a6a"
    TEXT      = "#c8cdd4"
    DIM       = "#4a5568"
    METALLIC  = "#4a5568"

    # ── Accent colors (used sparingly) ──
    CYAN      = "#00d9ff"       # Intelligent status
    CYAN_DIM  = "#004d66"
    CYAN_GLOW = "#081820"


_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """Shift entire palette hue to match the chosen accent color."""
    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh = acc_h - base_h
    grey = acc_s < 0.08

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """Current accent-dependent colors snapshot."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """Live full-theme swap — replace old palette colors in every widget's stylesheet."""
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception:
            pass


def qcol(h: str, a: int = 255) -> QColor:
    """Create QColor from hex, optionally with alpha."""
    c = QColor(h)
    c.setAlpha(a)
    return c
