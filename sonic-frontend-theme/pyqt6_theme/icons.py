"""
SONIC SVG Icon Engine — feather-style stroke icons.
Extracted from ui.py.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_ICON_PATHS: dict[str, str] = {
    "home":      '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9v11a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9"/>',
    "chat":      '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.5 0-2.9-.4-4.1-1L3 20l1.1-5.3A8.5 8.5 0 1 1 21 11.5z"/><line x1="8" y1="11" x2="16" y2="11"/><line x1="8" y1="14" x2="13" y2="14"/>',
    "mic":       '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1"/><line x1="12" y1="18" x2="12" y2="22"/>',
    "bot":       '<rect x="4" y="7" width="16" height="12" rx="2"/><line x1="12" y1="7" x2="12" y2="4"/><circle cx="9" cy="13" r=".8"/><circle cx="15" cy="13" r=".8"/>',
    "memory":    '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "sliders":   '<line x1="4" y1="6.5" x2="20" y2="6.5"/><circle cx="9.5" cy="6.5" r="2.3"/><line x1="4" y1="12.5" x2="20" y2="12.5"/><circle cx="15" cy="12.5" r="2.3"/><line x1="4" y1="18.5" x2="20" y2="18.5"/><circle cx="6.5" cy="18.5" r="2.3"/>',
    "info":      '<circle cx="12" cy="12" r="9"/><line x1="12" y1="11" x2="12" y2="16"/><path d="M12 7.8h.01"/>',
    "search":    '<circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/>',
    "code":      '<polyline points="8 6.5 2.5 12 8 17.5"/><polyline points="16 6.5 21.5 12 16 17.5"/>',
    "doc":       '<path d="M6 1.5h8.5L20 7v15H6z"/><line x1="9" y1="12" x2="15" y2="12"/><line x1="9" y1="16" x2="13" y2="16"/>',
    "image":     '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5L5 20"/>',
    "more":      '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/>',
    "attach":    '<path d="M21.4 11.6l-8.9 8.9a5.7 5.7 0 0 1-8-8l9-9a3.8 3.8 0 1 1 5.4 5.4l-9 9a1.9 1.9 0 1 1-2.7-2.7l7.9-7.9"/>',
    "bolt":      '<path d="M13 2 4.5 14H11l-1 8 8.5-12H12z"/>',
    "send":      '<path d="M22 2 11 13"/><path d="M22 2 15 22l-4-9-9-4z"/>',
    "close":     '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    "remote":    '<rect x="4.5" y="2" width="15" height="20" rx="3"/><circle cx="12" cy="17.5" r="1.6"/><line x1="12" y1="6" x2="12" y2="10"/>',
    "screen":    '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "link":      '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "refresh":   '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><polyline points="21 3 21 8 16 8"/>',
    "sun":       '<circle cx="12" cy="12" r="4"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><line x1="4.9" y1="4.9" x2="7" y2="7"/><line x1="17" y1="17" x2="19.1" y2="19.1"/><line x1="4.9" y1="19.1" x2="7" y2="17"/><line x1="17" y1="7" x2="19.1" y2="4.9"/>',
    "volume":    '<polygon points="4 9.5 8 9.5 13 4.5 13 19.5 8 14.5 4 14.5"/><line x1="16" y1="9.5" x2="20" y2="14.5"/><line x1="20" y1="9.5" x2="16" y2="14.5"/>',
    "cpu":       '<rect x="4.5" y="4.5" width="15" height="15" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 2v2.5M15 2v2.5M9 19.5V22M15 19.5V22M2 9h2.5M2 15h2.5M19.5 9H22M19.5 15H22"/>',
    "activity":  '<path d="M2 12h4l3-8 4 16 3-8h6"/>',
}

_ICON_PM_CACHE: dict[tuple, QPixmap] = {}


def svg_pixmap(name: str, color: str = "#00d4ff", px: int = 14) -> QPixmap:
    """Render an SVG icon to a QPixmap with the given color and size."""
    key = (name, color, px)
    hit = _ICON_PM_CACHE.get(key)
    if hit is not None:
        return hit
    d = _ICON_PATHS.get(name)
    pm = QPixmap()
    if d:
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'width="{px}" height="{px}">'
            f'<g fill="none" stroke="{color}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round">{d}</g></svg>'
        )
        r = QSvgRenderer()
        if r.load(bytes(svg, "utf-8")):
            pm = QPixmap(px, px)
            pm.fill(Qt.GlobalColor.transparent)
            pp = QPainter(pm)
            pp.setRenderHint(QPainter.RenderHint.Antialiasing)
            r.render(pp)
            pp.end()
    if not pm.isNull():
        _ICON_PM_CACHE[key] = pm
    return pm
