"""
Voice Shortcuts — Custom Voice Command System
Let users create custom voice shortcuts that trigger predefined actions.
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from datetime import datetime


@dataclass
class VoiceShortcut:
    trigger: str
    action: str
    tool_name: str
    parameters: dict = field(default_factory=dict)
    description: str = ""
    created_at: str = ""
    last_used: str = ""
    use_count: int = 0
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "trigger": self.trigger,
            "action": self.action,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "description": self.description,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "use_count": self.use_count,
            "aliases": self.aliases,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VoiceShortcut":
        return cls(**data)


class VoiceShortcutManager:
    """Manages custom voice shortcuts."""

    def __init__(self, storage_path: Path = None):
        self._storage_path = storage_path or Path.home() / ".sonic" / "shortcuts.json"
        self._shortcuts: dict[str, VoiceShortcut] = {}
        self._tool_executor: Callable = None
        self._load()

    def _load(self):
        try:
            if self._storage_path.exists():
                data = json.loads(self._storage_path.read_text(encoding="utf-8"))
                for trigger, sc_data in data.items():
                    self._shortcuts[trigger] = VoiceShortcut.from_dict(sc_data)
        except Exception:
            pass

    def _save(self):
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {trigger: sc.to_dict() for trigger, sc in self._shortcuts.items()}
            self._storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def set_tool_executor(self, executor: Callable):
        self._tool_executor = executor

    def add_shortcut(
        self,
        trigger: str,
        tool_name: str,
        parameters: dict = None,
        description: str = "",
        aliases: list[str] = None,
    ) -> VoiceShortcut:
        """Add a new voice shortcut."""
        shortcut = VoiceShortcut(
            trigger=trigger.lower().strip(),
            action=tool_name,
            tool_name=tool_name,
            parameters=parameters or {},
            description=description,
            created_at=datetime.now().isoformat(),
            aliases=aliases or [],
        )
        self._shortcuts[shortcut.trigger] = shortcut
        self._save()
        return shortcut

    def remove_shortcut(self, trigger: str) -> bool:
        if trigger.lower() in self._shortcuts:
            del self._shortcuts[trigger.lower()]
            self._save()
            return True
        return False

    def find_shortcut(self, text: str) -> Optional[VoiceShortcut]:
        """Find a shortcut matching the spoken text."""
        text_lower = text.lower().strip()

        for trigger, shortcut in self._shortcuts.items():
            if trigger in text_lower:
                return shortcut
            for alias in shortcut.aliases:
                if alias.lower() in text_lower:
                    return shortcut

        return None

    async def execute_shortcut(self, text: str, callback: Callable = None) -> str:
        """Find and execute a matching shortcut."""
        shortcut = self.find_shortcut(text)
        if not shortcut:
            return ""

        if callback:
            await callback(f"Running shortcut: {shortcut.trigger}")

        if not self._tool_executor:
            return f"Shortcut '{shortcut.trigger}' found but tool executor not available."

        try:
            if asyncio.iscoroutinefunction(self._tool_executor):
                result = await self._tool_executor(shortcut.tool_name, shortcut.parameters)
            else:
                result = await asyncio.to_thread(
                    self._tool_executor, shortcut.tool_name, shortcut.parameters
                )

            shortcut.last_used = datetime.now().isoformat()
            shortcut.use_count += 1
            self._save()

            return f"[SHORTCUT] {shortcut.trigger}: {result}"
        except Exception as e:
            return f"Shortcut '{shortcut.trigger}' failed: {e}"

    def list_shortcuts(self) -> list[dict]:
        return [
            {
                "trigger": sc.trigger,
                "tool": sc.tool_name,
                "description": sc.description,
                "uses": sc.use_count,
                "aliases": sc.aliases,
            }
            for sc in self._shortcuts.values()
        ]

    def get_predefined_shortcuts(self) -> list[dict]:
        """Return useful predefined shortcuts users might want."""
        return [
            {
                "trigger": "good morning",
                "tool_name": "computer_settings",
                "parameters": {"action": "volume_set", "value": "50"},
                "description": "Set volume to 50% and greet",
            },
            {
                "trigger": "focus mode",
                "tool_name": "computer_settings",
                "parameters": {"action": "volume_set", "value": "0"},
                "description": "Mute volume for focus",
            },
            {
                "trigger": "take a break",
                "tool_name": "open_app",
                "parameters": {"app_name": "Spotify"},
                "description": "Open Spotify for a break",
            },
            {
                "trigger": "screen time",
                "tool_name": "system_controls",
                "parameters": {"action": "display_info"},
                "description": "Show display information",
            },
            {
                "trigger": "cleanup time",
                "tool_name": "smart_find",
                "parameters": {"action": "cleanup", "dry_run": False},
                "description": "Clean up disk space",
            },
        ]


_manager: VoiceShortcutManager | None = None


def get_shortcut_manager() -> VoiceShortcutManager:
    global _manager
    if _manager is None:
        _manager = VoiceShortcutManager()
    return _manager


async def voice_shortcut(parameters: dict, **kwargs) -> str:
    """Tool handler for voice_shortcut."""
    action = parameters.get("action", "list")
    manager = get_shortcut_manager()

    if "tool_executor" in kwargs:
        manager.set_tool_executor(kwargs["tool_executor"])

    if action == "add":
        trigger = parameters.get("trigger", "")
        tool_name = parameters.get("tool_name", "")
        tool_params = parameters.get("parameters", {})
        description = parameters.get("description", "")
        aliases = parameters.get("aliases", [])

        if not trigger or not tool_name:
            return "Provide trigger and tool_name."

        sc = manager.add_shortcut(trigger, tool_name, tool_params, description, aliases)
        return f"Shortcut created: '{sc.trigger}' → {sc.tool_name}"

    elif action == "remove":
        trigger = parameters.get("trigger", "")
        if manager.remove_shortcut(trigger):
            return f"Shortcut '{trigger}' removed."
        return f"Shortcut '{trigger}' not found."

    elif action == "list":
        shortcuts = manager.list_shortcuts()
        if not shortcuts:
            predefined = manager.get_predefined_shortcuts()
            lines = ["No custom shortcuts yet. Here are some ideas:"]
            for p in predefined:
                lines.append(f'  "{p["trigger"]}" → {p["description"]}')
            return "\n".join(lines)
        lines = ["Custom Shortcuts:"]
        for sc in shortcuts:
            aliases = f" (aliases: {', '.join(sc['aliases'])})" if sc['aliases'] else ""
            lines.append(f'  "{sc["trigger"]}" → {sc["tool"]} (used {sc["uses"]}x){aliases}')
        return "\n".join(lines)

    elif action == "match":
        text = parameters.get("text", "")
        shortcut = manager.find_shortcut(text)
        if shortcut:
            return json.dumps(shortcut.to_dict())
        return "No matching shortcut found."

    return f"Unknown shortcut action: {action}. Use: add, remove, list, match"
