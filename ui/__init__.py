"""SONIC AI UI package.

The main application UI lives in :mod:`ui.sonic_ui`. This package exists
so additional UI components (such as the security dashboard) can live
alongside the main module without conflicting with the top-level
``ui.py`` → ``ui/`` package resolution rules.

Every public name previously importable from the flat ``ui.py`` module
is re-exported here, so existing ``from ui import SonicUI`` style code
continues to work unchanged.
"""
from .security_dashboard import (
    SecurityMeter, ThreatIndicator, StatusDot, SecurityDashboard,
)
from .sonic_ui import (
    SonicUI,
    MainWindow,
    OnboardingWizard,
    AuthOverlay,
    CustomizeOverlay,
    ProfileEditorOverlay,
    SetupOverlay,
    PluginManagerOverlay,
    ClipboardPanel,
    RemoteKeyOverlay,
    FileDropZone,
    LogWidget,
)

__all__ = [
    # Security dashboard (was here originally)
    "SecurityMeter", "ThreatIndicator", "StatusDot", "SecurityDashboard",
    # Main UI (was a flat module, now re-exported from sonic_ui.py)
    "SonicUI",
    "MainWindow",
    "OnboardingWizard",
    "AuthOverlay",
    "CustomizeOverlay",
    "ProfileEditorOverlay",
    "SetupOverlay",
    "PluginManagerOverlay",
    "ClipboardPanel",
    "RemoteKeyOverlay",
    "FileDropZone",
    "LogWidget",
]
