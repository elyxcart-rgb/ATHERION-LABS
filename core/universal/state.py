"""SONIC AI — Environment State Model.

Live representation of what's on screen, what's focused, what app is active,
what browser tab is open, what controls are visible.

The UniversalAgent consults this BEFORE planning, and updates it AFTER each
action. Re-observing state is the primary way SONIC knows whether the world
matches its expectations.

Public dataclasses:
    DisplayInfo        — physical/logical screen geometry + DPI
    ApplicationContext — foreground process, window title, exe path
    BrowserContext     — URL, title, tab list, active tab id
    ControlSnapshot    — a single visible interactive element
    EnvironmentState   — aggregate, the single state object passed around

The model never directly inspects the OS — it asks registered observers
(observers.py) which can be implemented via:
  - pywinauto / UIAutomation for Windows controls
  - Playwright for browser DOM
  - screen_vision snapshot + OCR as a fallback
  - psutil for process info
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# Display
# ──────────────────────────────────────────────────────────────────────
@dataclass
class DisplayInfo:
    """One physical display surface."""

    index: int = 0
    width_px: int = 0
    height_px: int = 0
    width_logical: int = 0
    height_logical: int = 0
    scale_factor: float = 1.0
    x_origin: int = 0
    y_origin: int = 0
    is_primary: bool = False

    @property
    def is_high_dpi(self) -> bool:
        return abs(self.scale_factor - 1.0) > 0.01

    def px_to_logical(self, x: int, y: int) -> tuple[int, int]:
        return int(x / self.scale_factor), int(y / self.scale_factor)

    def logical_to_px(self, x: int, y: int) -> tuple[int, int]:
        return int(x * self.scale_factor), int(y * self.scale_factor)

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Application
# ──────────────────────────────────────────────────────────────────────
class AppKind(str, Enum):
    UNKNOWN = "unknown"
    WINDOWS_APP = "windows_app"
    BROWSER = "browser"
    FILE_MANAGER = "file_manager"
    CONSOLE = "console"
    SETTINGS = "settings"
    OFFICE = "office"
    CODE_EDITOR = "code_editor"
    MEDIA = "media"
    MESSENGER = "messenger"


@dataclass
class ApplicationContext:
    """The foreground process the user / SONIC is currently inside."""

    kind: AppKind = AppKind.UNKNOWN
    name: str = ""
    process_name: str = ""
    pid: int = 0
    window_title: str = ""
    window_handle: int = 0
    exe_path: str = ""
    has_accessibility: bool = True     # UIA / DOM available?
    has_native_api: bool = False       # Office, VS Code, Photoshop, etc.
    focused_control: Optional["ControlSnapshot"] = None
    visible_controls: list["ControlSnapshot"] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d


# ──────────────────────────────────────────────────────────────────────
# Browser
# ──────────────────────────────────────────────────────────────────────
@dataclass
class BrowserTab:
    tab_id: str = ""
    title: str = ""
    url: str = ""
    is_active: bool = False
    is_loading: bool = False


@dataclass
class BrowserContext:
    """Active browser session — which page, which tab, which frame."""

    browser_name: str = ""        # "chrome" / "edge" / "firefox"
    is_incognito: bool = False
    page_url: str = ""
    page_title: str = ""
    active_tab_id: str = ""
    tabs: list[BrowserTab] = field(default_factory=list)
    page_dom_signature: str = ""   # hash of body innerHTML for change detection
    iframes: list[str] = field(default_factory=list)
    modals_open: list[str] = field(default_factory=list)

    def find_tab(self, url_substr: str) -> Optional[BrowserTab]:
        for t in self.tabs:
            if url_substr.lower() in t.url.lower():
                return t
        return None

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────
# Controls (visible interactive elements)
# ──────────────────────────────────────────────────────────────────────
class ControlRole(str, Enum):
    UNKNOWN = "unknown"
    BUTTON = "button"
    LINK = "link"
    TEXT_INPUT = "text_input"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SELECT = "select"
    MENU_ITEM = "menu_item"
    TAB = "tab"
    DIALOG = "dialog"
    IMAGE = "image"
    ICON = "icon"
    LIST_ITEM = "list_item"
    HEADING = "heading"
    TEXT_BLOCK = "text_block"
    VIDEO = "video"
    IFRAME = "iframe"


@dataclass
class ControlSnapshot:
    """A single visible interactive element on screen."""

    control_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: ControlRole = ControlRole.UNKNOWN
    name: str = ""                   # accessibility name / aria-label / text
    automation_id: str = ""          # UIA AutomationId
    text: str = ""
    placeholder: str = ""
    value: str = ""
    bounding_rect: tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h
    is_enabled: bool = True
    is_visible: bool = True
    is_focused: bool = False
    confidence: float = 1.0
    source: str = ""                 # "uia" / "dom" / "vision" / "ocr"
    parent_role: str = ""
    attributes: dict = field(default_factory=dict)

    def contains_point(self, x: int, y: int) -> bool:
        rx, ry, rw, rh = self.bounding_rect
        return rx <= x < rx + rw and ry <= y < ry + rh

    @property
    def center(self) -> tuple[int, int]:
        x, y, w, h = self.bounding_rect
        return x + w // 2, y + h // 2

    def to_dict(self) -> dict:
        d = asdict(self)
        d["role"] = self.role.value
        return d


# ──────────────────────────────────────────────────────────────────────
# Aggregate state
# ──────────────────────────────────────────────────────────────────────
@dataclass
class EnvironmentState:
    """The full live state — what SONIC believes is currently visible/active."""

    state_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    captured_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    displays: list[DisplayInfo] = field(default_factory=list)
    primary_display_idx: int = 0
    mouse_pos: tuple[int, int] = (0, 0)
    active_app: Optional[ApplicationContext] = None
    browser: Optional[BrowserContext] = None
    visible_text_regions: list[dict] = field(default_factory=list)   # OCR cache
    open_dialogs: list[str] = field(default_factory=list)
    clipboard_text: str = ""
    running_processes: list[dict] = field(default_factory=list)
    screenshot_signature: str = ""    # perceptual hash for change detection

    @property
    def primary_display(self) -> DisplayInfo:
        if self.primary_display_idx < len(self.displays):
            return self.displays[self.primary_display_idx]
        return DisplayInfo()

    @property
    def is_browser_active(self) -> bool:
        return self.active_app is not None and self.active_app.kind == AppKind.BROWSER

    def find_control_by_name(self, name: str) -> Optional[ControlSnapshot]:
        if not self.active_app:
            return None
        target = name.lower().strip()
        for c in self.active_app.visible_controls:
            if c.name.lower().strip() == target or c.text.lower().strip() == target:
                return c
        # fuzzy fallback
        for c in self.active_app.visible_controls:
            if target in c.name.lower() or target in c.text.lower():
                return c
        return None

    def to_dict(self) -> dict:
        return {
            "state_id": self.state_id,
            "captured_at_ms": self.captured_at_ms,
            "active_app": self.active_app.to_dict() if self.active_app else None,
            "browser": self.browser.to_dict() if self.browser else None,
            "open_dialogs": self.open_dialogs,
            "mouse_pos": list(self.mouse_pos),
            "displays": [d.to_dict() for d in self.displays],
            "control_count": len(self.active_app.visible_controls) if self.active_app else 0,
        }
