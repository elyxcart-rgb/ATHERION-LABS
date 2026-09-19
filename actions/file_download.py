"""SONIC AI — File Download Manager

Downloads files from URLs with progress tracking, resume support, and auto-organization.

Usage:
    "Download this file: https://example.com/file.pdf"
    "Download and save to Documents"
    "Download all images from this page"
"""
from __future__ import annotations

import json
import os
import time
import logging
import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote, urlparse

logger = logging.getLogger("FILE_DOWNLOAD")

# ── Safety: restrict downloads to safe directories ──────────────────────
_DOWNLOAD_ROOTS = [
    Path.home() / "Downloads",
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Pictures",
]
_DOWNLOAD_ROOTS = [p for p in _DOWNLOAD_ROOTS if p.exists()]

# File type categories for auto-organization
_FILE_CATEGORIES = {
    "images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"},
    "videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm"},
    "audio": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "code": {".py", ".js", ".html", ".css", ".java", ".cpp", ".h", ".json", ".xml"},
    "executables": {".exe", ".msi", ".app", ".dmg"},
}


def _is_safe_path(path: Path) -> bool:
    """Check if download path is within allowed directories."""
    try:
        resolved = path.resolve()
        return any(str(resolved).startswith(str(root)) for root in _DOWNLOAD_ROOTS)
    except Exception:
        return False


def _get_category(filename: str) -> str:
    """Get file category from extension."""
    ext = Path(filename).suffix.lower()
    for category, extensions in _FILE_CATEGORIES.items():
        if ext in extensions:
            return category
    return "other"


def _extract_filename(url: str, headers: dict | None = None) -> str:
    """Extract filename from URL or Content-Disposition header."""
    # Try Content-Disposition first
    if headers:
        cd = headers.get("Content-Disposition", "")
        if "filename=" in cd:
            parts = cd.split("filename=")
            if len(parts) > 1:
                name = parts[1].strip('" ')
                if name:
                    return name

    # Parse URL
    parsed = urlparse(url)
    path = unquote(parsed.path)
    if path and "/" in path:
        filename = path.split("/")[-1]
        if filename and "." in filename:
            return filename

    return "downloaded_file"


def _format_size(bytes_size: int) -> str:
    """Format bytes to human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


def _format_speed(bytes_per_sec: float) -> str:
    """Format download speed."""
    return f"{_format_size(int(bytes_per_sec))}/s"


@dataclass
class DownloadTask:
    """Tracks a single download."""
    id: str
    url: str
    filename: str
    destination: str
    category: str
    status: str = "pending"  # pending | downloading | completed | failed | paused
    total_bytes: int = 0
    downloaded_bytes: int = 0
    speed: float = 0.0
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    content_type: str = ""
    thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def progress(self) -> float:
        if self.total_bytes > 0:
            return (self.downloaded_bytes / self.total_bytes) * 100
        return 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.filename,
            "destination": self.destination,
            "category": self.category,
            "status": self.status,
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "progress": round(self.progress, 1),
            "speed": _format_speed(self.speed) if self.speed > 0 else "",
            "error": self.error,
            "content_type": self.content_type,
        }


class DownloadManager:
    """Manages file downloads with progress tracking and organization."""

    def __init__(self):
        self._downloads: dict[str, DownloadTask] = {}
        self._download_history: list[dict] = []
        self._lock = threading.Lock()
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"dl_{self._counter}_{int(time.time())}"

    def _is_safe_url(self, url: str) -> bool:
        """Basic URL safety check."""
        url_lower = url.lower()
        if not url_lower.startswith(("http://", "https://")):
            return False
        # Block suspicious patterns
        blocked = ["file://", "ftp://", "javascript:", "data:"]
        return not any(b in url_lower for b in blocked)

    def download(
        self,
        url: str,
        destination: str | None = None,
        filename: str | None = None,
        organize: bool = True,
    ) -> dict:
        """
        Start downloading a file from URL.

        Args:
            url: The URL to download from
            destination: Directory to save to (default: ~/Downloads)
            filename: Override filename (default: auto-detect from URL)
            organize: Auto-organize by file type into subfolders

        Returns:
            Download task info
        """
        if not self._is_safe_url(url):
            return {"error": "Invalid or unsafe URL"}

        try:
            import requests
        except ImportError:
            return {"error": "requests library not installed. Run: pip install requests"}

        # Determine destination
        dest_dir = Path(destination) if destination else Path.home() / "Downloads"
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        if not _is_safe_path(dest_dir):
            return {"error": "Download path not allowed. Use ~/Downloads, ~/Documents, ~/Desktop, or ~/Pictures"}

        task_id = self._next_id()

        try:
            # HEAD request to get file info
            head = requests.head(url, timeout=10, allow_redirects=True)
            total_bytes = int(head.headers.get("Content-Length", 0))
            content_type = head.headers.get("Content-Type", "")

            # Determine filename
            if not filename:
                filename = _extract_filename(url, dict(head.headers))
            if not filename or "." not in filename:
                filename = f"download_{int(time.time())}"

            # Auto-organize
            if organize:
                category = _get_category(filename)
                if category != "other":
                    dest_dir = dest_dir / category
                    dest_dir.mkdir(exist_ok=True)
            else:
                category = "other"

            filepath = dest_dir / filename

            # Avoid overwriting — add number if exists
            counter = 1
            original_stem = filepath.stem
            while filepath.exists():
                filepath = dest_dir / f"{original_stem}_{counter}{filepath.suffix}"
                counter += 1

            task = DownloadTask(
                id=task_id,
                url=url,
                filename=filepath.name,
                destination=str(filepath),
                category=category,
                total_bytes=total_bytes,
                content_type=content_type,
            )

            with self._lock:
                self._downloads[task_id] = task

            # Start download in background thread
            thread = threading.Thread(
                target=self._do_download,
                args=(task,),
                daemon=True,
            )
            task.thread = thread
            thread.start()

            return {
                "success": True,
                "task_id": task_id,
                "filename": filepath.name,
                "destination": str(filepath),
                "category": category,
                "size": _format_size(total_bytes) if total_bytes > 0 else "unknown",
                "status": "downloading",
            }

        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to connect: {e}"}
        except Exception as e:
            return {"error": f"Download failed: {e}"}

    def _do_download(self, task: DownloadTask) -> None:
        """Execute the actual download in a background thread."""
        try:
            import requests

            task.status = "downloading"
            task.started_at = time.time()

            response = requests.get(task.url, stream=True, timeout=30)
            response.raise_for_status()

            # Update total bytes if not known
            if task.total_bytes == 0:
                task.total_bytes = int(response.headers.get("Content-Length", 0))

            downloaded = 0
            start_time = time.time()
            last_update = start_time

            with open(task.destination, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        task.downloaded_bytes = downloaded

                        # Update speed every 0.5s
                        now = time.time()
                        if now - last_update >= 0.5:
                            elapsed = now - start_time
                            if elapsed > 0:
                                task.speed = downloaded / elapsed
                            last_update = now

            task.status = "completed"
            task.completed_at = time.time()
            task.speed = 0.0

            logger.info(f"[Download] Completed: {task.filename} ({_format_size(downloaded)})")

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            task.completed_at = time.time()
            logger.error(f"[Download] Failed: {task.filename} - {e}")

    def get_status(self, task_id: str) -> dict:
        """Get status of a download."""
        task = self._downloads.get(task_id)
        if not task:
            return {"error": "Download not found"}
        return task.to_dict()

    def list_active(self) -> list[dict]:
        """List all active downloads."""
        return [t.to_dict() for t in self._downloads.values()
                if t.status in ("pending", "downloading", "paused")]

    def list_all(self) -> list[dict]:
        """List all downloads (active + completed)."""
        return [t.to_dict() for t in self._downloads.values()]

    def cancel(self, task_id: str) -> dict:
        """Cancel a download."""
        task = self._downloads.get(task_id)
        if not task:
            return {"error": "Download not found"}

        if task.status == "completed":
            return {"error": "Download already completed"}

        task.status = "failed"
        task.error = "Cancelled by user"
        task.completed_at = time.time()

        # Remove partial file
        try:
            if Path(task.destination).exists():
                Path(task.destination).unlink()
        except Exception:
            pass

        return {"success": True, "message": f"Cancelled: {task.filename}"}


# ── Singleton ───────────────────────────────────────────────────────────
_manager: DownloadManager | None = None


def get_download_manager() -> DownloadManager:
    global _manager
    if _manager is None:
        _manager = DownloadManager()
    return _manager


# ── Tool Interface ──────────────────────────────────────────────────────

def file_download(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    File download tool.
    Downloads files from URLs with progress tracking.
    """
    manager = get_download_manager()
    action = parameters.get("action", "download")

    if action == "download":
        url = parameters.get("url", "")
        if not url:
            return "Error: url is required"

        destination = parameters.get("destination", None)
        filename = parameters.get("filename", None)
        organize = parameters.get("organize", True)

        result = manager.download(url, destination, filename, organize)
        if result.get("success"):
            return (
                f"Download started: {result['filename']}\n"
                f"Size: {result['size']}\n"
                f"Destination: {result['destination']}\n"
                f"Category: {result['category']}\n"
                f"Task ID: {result['task_id']}"
            )
        return f"Download failed: {result.get('error', 'Unknown error')}"

    elif action == "status":
        task_id = parameters.get("task_id", "")
        if task_id:
            return json.dumps(manager.get_status(task_id), indent=2)
        active = manager.list_active()
        if active:
            return json.dumps(active, indent=2)
        return "No active downloads"

    elif action == "list":
        downloads = manager.list_all()
        if downloads:
            lines = ["Downloads:"]
            for d in downloads:
                status_icon = {"completed": "[OK]", "downloading": "[>>]", "failed": "[FAIL]", "pending": "[..]"}.get(d["status"], "?")
                lines.append(f"  {status_icon} {d['filename']} [{d['status']}]")
            return "\n".join(lines)
        return "No downloads yet"

    elif action == "cancel":
        task_id = parameters.get("task_id", "")
        if not task_id:
            return "Error: task_id is required"
        result = manager.cancel(task_id)
        return result.get("message", result.get("error", "Unknown"))

    return f"Unknown action: {action}. Use: download, status, list, cancel"
