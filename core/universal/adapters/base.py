"""SONIC AI — App Adapter Base Interface.

All app-specific adapters inherit from AppAdapter and implement:
  - handles_processes() — list of process names this adapter owns
  - execute(action, state) — perform action via app-specific API
  - observe() — return app-specific control snapshot
  - verify(result_spec) — check postcondition

Adapters are PURE Python — they don't depend on the CapabilityRouter or
UniversalAgent to avoid circular imports.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Optional


logger = logging.getLogger("sonic.adapter")


class AdapterCapability(str, Enum):
    CLICK = "click"
    TYPE = "type"
    KEYPRESS = "keypress"
    NAVIGATE = "navigate"
    EXTRACT_TEXT = "extract_text"
    LIST_CONTROLS = "list_controls"
    CUSTOM = "custom"


@dataclass
class AdapterResult:
    success: bool = False
    error: str = ""
    data: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    method: str = ""
    capabilities_used: list[AdapterCapability] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["capabilities_used"] = [c.value for c in self.capabilities_used]
        return d


class AppAdapter:
    """Base class for all app-specific adapters."""

    name: str = "base"
    processes: list[str] = []  # process names this adapter handles
    capabilities: list[AdapterCapability] = []

    def handles_processes(self) -> list[str]:
        return list(self.processes)

    def supports(self, capability: AdapterCapability) -> bool:
        return capability in self.capabilities

    # The four lifecycle hooks an adapter can implement
    def execute(self, action, state) -> AdapterResult:
        raise NotImplementedError

    def observe(self, state) -> dict:
        return {}

    def verify(self, spec, state) -> tuple[bool, str]:
        return True, "default_verify_pass"

    def describe(self) -> dict:
        return {
            "name": self.name,
            "processes": self.processes,
            "capabilities": [c.value for c in self.capabilities],
        }
