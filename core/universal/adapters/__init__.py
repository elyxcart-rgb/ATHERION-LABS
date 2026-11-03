"""SONIC AI — App Adapter Framework.

Pluggable per-application automation interfaces. Each adapter knows the
peculiarities of one app (or family of apps) and exposes a stable interface
that the UniversalAgent can call.

Adapters register themselves with the CapabilityRouter at T4_ADAPTER tier.

Public API:
    AppAdapter (base) — interface every adapter implements
    GenericWindowsAdapter — fallback for any Windows app
    BrowserAdapter — Playwright-based (Chrome/Edge/Firefox)
    FileManagerAdapter — Windows Explorer
    OfficeAdapter — Excel/Word/PowerPoint via COM (win32com if available)
    VSCodeAdapter — VS Code CLI + extension API
    WhatsAppAdapter — WhatsApp Web via DOM
    DiscordAdapter — Discord via DOM
    SpotifyAdapter — Spotify Web/Desktop
"""
from __future__ import annotations

from .base import AppAdapter, AdapterResult, AdapterCapability
from .generic_windows import GenericWindowsAdapter
from .browser import BrowserAdapter
from .file_manager import FileManagerAdapter
from .office import OfficeAdapter
from .vscode import VSCodeAdapter
from .whatsapp import WhatsAppAdapter
from .discord import DiscordAdapter
from .spotify import SpotifyAdapter
from .unreal import UnrealAdapter, UE_SHORTCUTS


def build_default_adapter_registry():
    """Returns a dict {process_name: AppAdapter} for known apps."""
    reg = {}
    for adapter in (GenericWindowsAdapter(),
                    BrowserAdapter(),
                    FileManagerAdapter(),
                    OfficeAdapter(),
                    VSCodeAdapter(),
                    WhatsAppAdapter(),
                    DiscordAdapter(),
                    SpotifyAdapter(),
                    UnrealAdapter()):
        for proc in adapter.handles_processes():
            reg[proc.lower()] = adapter
    return reg


__all__ = [
    "AppAdapter", "AdapterResult", "AdapterCapability",
    "GenericWindowsAdapter", "BrowserAdapter", "FileManagerAdapter",
    "OfficeAdapter", "VSCodeAdapter", "WhatsAppAdapter",
    "DiscordAdapter", "SpotifyAdapter", "UnrealAdapter",
    "UE_SHORTCUTS",
    "build_default_adapter_registry",
]
