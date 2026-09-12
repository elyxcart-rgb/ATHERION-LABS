"""
Smart Clipboard — Enhanced Clipboard with History & Intelligence
Tracks clipboard history, detects content types, and provides smart operations.
"""
import json
import time
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime


@dataclass
class ClipboardEntry:
    content: str
    content_type: str = "text"
    timestamp: float = 0.0
    source: str = "user"
    hash: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "content": self.content[:500],
            "content_type": self.content_type,
            "timestamp": self.timestamp,
            "source": self.source,
            "hash": self.hash,
            "metadata": self.metadata,
        }

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()
        if not self.hash:
            self.hash = hashlib.md5(self.content.encode()).hexdigest()[:12]


class SmartClipboard:
    """Manages clipboard history with smart content detection."""

    def __init__(self, storage_path: Path = None, max_history: int = 50):
        self._storage_path = storage_path or Path.home() / ".sonic" / "clipboard.json"
        self._history: list[ClipboardEntry] = []
        self._max_history = max_history
        self._pinned: list[ClipboardEntry] = []
        self._load()

    def _load(self):
        try:
            if self._storage_path.exists():
                data = json.loads(self._storage_path.read_text(encoding="utf-8"))
                self._history = [ClipboardEntry(**e) for e in data.get("history", [])]
                self._pinned = [ClipboardEntry(**e) for e in data.get("pinned", [])]
        except Exception:
            pass

    def _save(self):
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "history": [e.to_dict() for e in self._history[-self._max_history:]],
                "pinned": [e.to_dict() for e in self._pinned],
            }
            self._storage_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def detect_content_type(self, content: str) -> str:
        """Detect the type of clipboard content."""
        content = content.strip()

        if not content:
            return "empty"

        if content.startswith(("http://", "https://")):
            if any(x in content.lower() for x in ["youtube.com", "youtu.be"]):
                return "youtube_url"
            elif any(x in content.lower() for x in ["github.com"]):
                return "github_url"
            return "url"

        if any(content.endswith(ext) for ext in [".py", ".js", ".html", ".css", ".java", ".cpp", ".c"]):
            return "code_file"

        if content.startswith(("{", "[", "<")):
            try:
                json.loads(content)
                return "json"
            except Exception:
                pass

        if content.startswith(("from ", "import ", "def ", "class ", "function ", "const ")):
            return "code"

        lines = content.split("\n")
        if len(lines) > 3 and all(":" in line for line in lines[:5]):
            return "yaml_like"

        if "@" in content and "." in content:
            return "email"

        if any(c.isdigit() for c in content) and len(content) < 20:
            return "number"

        return "text"

    def add(self, content: str, source: str = "user") -> ClipboardEntry:
        """Add content to clipboard history."""
        if not content.strip():
            return None

        entry = ClipboardEntry(
            content=content,
            content_type=self.detect_content_type(content),
            source=source,
        )

        for existing in self._history:
            if existing.hash == entry.hash:
                existing.timestamp = entry.timestamp
                return entry

        self._history.append(entry)

        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        self._save()
        return entry

    def get_recent(self, count: int = 10) -> list[dict]:
        """Get recent clipboard entries."""
        return [e.to_dict() for e in self._history[-count:]]

    def search(self, query: str) -> list[dict]:
        """Search clipboard history."""
        query_lower = query.lower()
        results = [
            e.to_dict() for e in self._history
            if query_lower in e.content.lower()
        ]
        return results

    def pin(self, index: int = -1) -> bool:
        """Pin an entry from history."""
        if not self._history:
            return False
        entry = self._history[index]
        if entry not in self._pinned:
            self._pinned.append(entry)
            self._save()
        return True

    def unpin(self, index: int = 0) -> bool:
        """Unpin a pinned entry."""
        if 0 <= index < len(self._pinned):
            self._pinned.pop(index)
            self._save()
            return True
        return False

    def get_pinned(self) -> list[dict]:
        return [e.to_dict() for e in self._pinned]

    def clear_history(self):
        self._history.clear()
        self._save()

    def get_stats(self) -> dict:
        """Get clipboard statistics."""
        type_counts = {}
        for entry in self._history:
            t = entry.content_type
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_items": len(self._history),
            "pinned_items": len(self._pinned),
            "content_types": type_counts,
            "oldest": self._history[0].timestamp if self._history else 0,
            "newest": self._history[-1].timestamp if self._history else 0,
        }

    def get_by_type(self, content_type: str) -> list[dict]:
        """Get all entries of a specific type."""
        return [
            e.to_dict() for e in self._history
            if e.content_type == content_type
        ]


_instance: SmartClipboard | None = None


def get_clipboard() -> SmartClipboard:
    global _instance
    if _instance is None:
        _instance = SmartClipboard()
    return _instance


async def smart_clipboard(parameters: dict, **kwargs) -> str:
    """Tool handler for smart_clipboard."""
    action = parameters.get("action", "get_recent")
    clipboard = get_clipboard()

    if action == "add":
        content = parameters.get("content", "")
        source = parameters.get("source", "user")
        entry = clipboard.add(content, source)
        if entry:
            return f"Saved ({entry.content_type}): {content[:80]}..."
        return "Empty content not saved."

    elif action == "get_recent":
        count = parameters.get("count", 10)
        entries = clipboard.get_recent(count)
        if not entries:
            return "Clipboard history is empty."
        lines = ["Recent Clipboard:"]
        for i, e in enumerate(entries, 1):
            preview = e["content"][:60].replace("\n", " ")
            lines.append(f"  {i}. [{e['content_type']}] {preview}")
        return "\n".join(lines)

    elif action == "search":
        query = parameters.get("query", "")
        results = clipboard.search(query)
        if not results:
            return f"No matches for '{query}'."
        lines = [f"Search results for '{query}':"]
        for e in results[:10]:
            preview = e["content"][:60].replace("\n", " ")
            lines.append(f"  [{e['content_type']}] {preview}")
        return "\n".join(lines)

    elif action == "pin":
        index = parameters.get("index", -1)
        if clipboard.pin(index):
            return "Entry pinned."
        return "Could not pin entry."

    elif action == "unpin":
        index = parameters.get("index", 0)
        if clipboard.unpin(index):
            return "Entry unpinned."
        return "Could not unpin entry."

    elif action == "pinned":
        entries = clipboard.get_pinned()
        if not entries:
            return "No pinned entries."
        lines = ["Pinned Items:"]
        for i, e in enumerate(entries, 1):
            preview = e["content"][:60].replace("\n", " ")
            lines.append(f"  {i}. [{e['content_type']}] {preview}")
        return "\n".join(lines)

    elif action == "stats":
        stats = clipboard.get_stats()
        lines = ["Clipboard Stats:"]
        lines.append(f"  Total: {stats['total_items']} items")
        lines.append(f"  Pinned: {stats['pinned_items']} items")
        if stats["content_types"]:
            lines.append("  Types:")
            for t, count in stats["content_types"].items():
                lines.append(f"    {t}: {count}")
        return "\n".join(lines)

    elif action == "by_type":
        content_type = parameters.get("type", "text")
        entries = clipboard.get_by_type(content_type)
        if not entries:
            return f"No {content_type} entries found."
        lines = [f"{content_type.title()} Entries:"]
        for e in entries[:10]:
            preview = e["content"][:60].replace("\n", " ")
            lines.append(f"  {preview}")
        return "\n".join(lines)

    elif action == "clear":
        clipboard.clear_history()
        return "Clipboard history cleared."

    return f"Unknown clipboard action: {action}. Use: add, get_recent, search, pin, unpin, pinned, stats, by_type, clear"
