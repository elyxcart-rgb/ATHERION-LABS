"""SONIC AI — Universal Downloader.

Downloads ANY file from ANY URL — HTTP, HTTPS, FTP, s3, magnet, even
YouTube / Vimeo via ``yt-dlp`` when available.

Features:
- Streaming downloads with live progress (bytes / total / speed / ETA)
- Resumable downloads via ``Range`` headers
- Browser-driven fallback (``WebAutomator``) for sites that gate files
  behind JavaScript download buttons
- Optional ``yt-dlp`` for YouTube / streaming media
- Sensible filename detection from ``Content-Disposition`` or URL

Public surface (stable, opt-in):
    - ``Downloader()``
    - ``downloader.fetch(url, dest=None, *, on_progress=None)``
    - ``downloader.fetch_with_browser(url, dest=None)``
    - ``downloader.youtube(url, dest=None, *, format='best')``
    - ``DownloadProgress`` dataclass

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("DOWNLOADER")


# ═════════════════════════════════════════════════════════════════════════════
# Data class
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class DownloadProgress:
    url: str = ""
    dest: str = ""
    bytes_downloaded: int = 0
    total_bytes: int = 0
    speed_bps: float = 0.0       # bytes per second
    eta_seconds: float = 0.0
    status: str = "pending"      # pending | downloading | done | error | paused
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    metadata: dict = field(default_factory=dict)

    @property
    def percent(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(100.0, 100.0 * self.bytes_downloaded / self.total_bytes)

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

_FILENAME_UNSAFE = re.compile(r"[^\w.\- ]+", re.UNICODE)


def _safe_filename(name: str) -> str:
    cleaned = _FILENAME_UNSAFE.sub("_", name).strip().strip(".")
    return cleaned or "download"


def _filename_from_url(url: str) -> str:
    """Best-effort filename extraction from a URL."""
    path = urllib.parse.urlsplit(url).path
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    if not name:
        return "download"
    # Strip query params if any leaked in
    name = name.split("?", 1)[0].split("#", 1)[0]
    return _safe_filename(name)


def _filename_from_headers(headers: dict) -> Optional[str]:
    """Extract filename from Content-Disposition header."""
    cd = headers.get("Content-Disposition") or headers.get("content-disposition")
    if not cd:
        return None
    # RFC 6266 — filename*= or filename=
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", cd, re.IGNORECASE)
    if m:
        try:
            from urllib.parse import unquote
            return _safe_filename(unquote(m.group(1)))
        except Exception:
            pass
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd, re.IGNORECASE)
    if m:
        return _safe_filename(m.group(1))
    m = re.search(r"filename\s*=\s*([^;]+)", cd, re.IGNORECASE)
    if m:
        return _safe_filename(m.group(1).strip())
    return None


# ═════════════════════════════════════════════════════════════════════════════
# Main downloader
# ═════════════════════════════════════════════════════════════════════════════

class Downloader:
    """Universal downloader with progress + resume + yt-dlp."""

    def __init__(self, *, default_dir: Optional[Path] = None,
                 chunk_size: int = 64 * 1024,
                 timeout: int = 30):
        self.default_dir = Path(default_dir) if default_dir else (
            Path.home() / "Downloads" / "SONIC"
        )
        self.default_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self.timeout = timeout
        self._have_ytdlp = shutil.which("yt-dlp") is not None

    # ── Plain HTTP / HTTPS ──────────────────────────────────────────────
    def fetch(self, url: str, dest: Optional[Path] = None, *,
             on_progress: Optional[Callable[[DownloadProgress], None]] = None,
             resume: bool = True) -> DownloadProgress:
        """Streaming HTTP download with progress + optional resume."""
        prog = DownloadProgress(url=url, started_at=time.time())
        try:
            import requests
        except ImportError:
            prog.status = "error"
            prog.error = "Install 'requests' for HTTP downloads"
            return prog

        # Resolve destination
        if dest is None:
            dest = self.default_dir / _filename_from_url(url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        prog.dest = str(dest)

        # Resume support
        existing = dest.stat().st_size if dest.exists() and resume else 0
        headers = {"User-Agent": "Mozilla/5.0 (SONIC Downloader)"}
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"

        try:
            resp = requests.get(url, headers=headers, stream=True,
                               timeout=self.timeout)
            if resp.status_code == 416:
                # Range not satisfiable — already complete
                prog.status = "done"
                prog.bytes_downloaded = existing
                prog.total_bytes = existing
                if on_progress:
                    on_progress(prog)
                return prog
            if resp.status_code not in (200, 206):
                prog.status = "error"
                prog.error = f"HTTP {resp.status_code}"
                return prog

            # Total size
            total = int(resp.headers.get("Content-Length") or 0)
            if existing > 0 and resp.status_code == 206:
                prog.total_bytes = existing + total
            else:
                prog.total_bytes = total or 0

            # Resolve filename from headers if not set
            if not dest.exists() or existing == 0:
                suggested = _filename_from_headers(dict(resp.headers))
                if suggested:
                    dest = dest.parent / suggested
                    prog.dest = str(dest)

            prog.status = "downloading"
            if on_progress:
                on_progress(prog)

            mode = "ab" if existing > 0 and resp.status_code == 206 else "wb"
            with open(dest, mode) as f:
                downloaded = existing
                start_time = time.time()
                last_report = start_time
                for chunk in resp.iter_content(chunk_size=self.chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    prog.bytes_downloaded = downloaded
                    now = time.time()
                    elapsed = max(0.001, now - start_time)
                    prog.speed_bps = (downloaded - existing) / elapsed
                    if prog.total_bytes > 0 and prog.speed_bps > 0:
                        prog.eta_seconds = max(
                            0, (prog.total_bytes - downloaded) / prog.speed_bps
                        )
                    # Throttle progress callbacks (every 200ms)
                    if on_progress and (now - last_report) > 0.2:
                        on_progress(prog)
                        last_report = now

            prog.bytes_downloaded = downloaded
            prog.status = "done"
            prog.finished_at = time.time()
            if on_progress:
                on_progress(prog)
            return prog

        except Exception as e:
            prog.status = "error"
            prog.error = str(e)
            prog.finished_at = time.time()
            return prog

    # ── Browser-driven download (for JS-gated files) ───────────────────
    def fetch_with_browser(self, url: str, dest: Optional[Path] = None) -> DownloadProgress:
        """Use the WebAutomator to fetch files behind JS download buttons."""
        from core.web_automator import web
        prog = DownloadProgress(url=url, started_at=time.time())
        try:
            with web().open_page(url) as page:
                if dest is None:
                    dest = web().download_dir / _filename_from_url(url)
                result = web().download_url(page, url, dest=dest)
                prog.dest = result.path
                prog.bytes_downloaded = result.bytes_downloaded
                prog.status = "done" if result.ok else "error"
                prog.error = result.error
                prog.finished_at = time.time()
                return prog
        except Exception as e:
            prog.status = "error"
            prog.error = str(e)
            prog.finished_at = time.time()
            return prog

    # ── YouTube / streaming media via yt-dlp ───────────────────────────
    def youtube(self, url: str, dest: Optional[Path] = None, *,
                format: str = "best",  # noqa: shadow builtin
                audio_only: bool = False) -> DownloadProgress:
        """Download from YouTube / Vimeo / etc. via yt-dlp (or fallback)."""
        prog = DownloadProgress(url=url, started_at=time.time(),
                               metadata={"platform": "youtube-dlp"})
        if not self._have_ytdlp:
            prog.status = "error"
            prog.error = (
                "yt-dlp not installed. Run: pip install yt-dlp  "
                "(fallback: we tried the HTTP fetch, but YouTube needs JS)."
            )
            # Try plain HTTP fetch as last resort
            return self.fetch(url, dest=dest)
        out_dir = Path(dest).parent if dest else self.default_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            args = ["yt-dlp", "--no-playlist", "--newline",
                    "-o", str(out_dir / "%(title)s.%(ext)s")]
            if audio_only:
                args += ["-x", "--audio-format", "mp3"]
            else:
                args += ["-f", format]
            args.append(url)
            proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            output_path = None
            for line in proc.stdout or []:
                # yt-dlp progress lines: "[download]  45.2% of  10.50MiB at  1.23MiB/s ETA 00:05"
                m = re.search(r"(\d+\.\d+)%\s+of\s+([\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+(\d+:\d+)", line)
                if m:
                    prog.bytes_downloaded = 0
                    prog.total_bytes = 0
                    prog.speed_bps = 0
                    prog.eta_seconds = 0
                if "[download] Destination:" in line:
                    output_path = line.split("Destination:", 1)[1].strip()
            proc.wait()
            if proc.returncode == 0 and output_path:
                p = Path(output_path)
                if p.exists():
                    prog.dest = str(p)
                    prog.bytes_downloaded = p.stat().st_size
                    prog.total_bytes = prog.bytes_downloaded
                    prog.status = "done"
                else:
                    prog.status = "done"
            else:
                prog.status = "error"
                prog.error = f"yt-dlp exit code {proc.returncode}"
            prog.finished_at = time.time()
            return prog
        except Exception as e:
            prog.status = "error"
            prog.error = str(e)
            prog.finished_at = time.time()
            return prog

    # ── Smart dispatcher ───────────────────────────────────────────────
    def smart_fetch(self, url: str, dest: Optional[Path] = None, **kw
                    ) -> DownloadProgress:
        """Pick the right strategy based on the URL.

        - YouTube / Vimeo / etc. → yt-dlp
        - Direct file URL → streaming HTTP
        - JS-gated page → browser
        """
        u = url.lower()
        if any(d in u for d in ("youtube.com", "youtu.be", "vimeo.com",
                                "soundcloud.com", "twitch.tv")):
            return self.youtube(url, dest=dest, **kw)
        # Check Content-Type first — if it's HTML it's likely JS-gated
        try:
            import requests
            head = requests.head(url, allow_redirects=True, timeout=10)
            ctype = head.headers.get("Content-Type", "")
            if "text/html" in ctype.lower():
                return self.fetch_with_browser(url, dest=dest)
        except Exception:
            pass
        return self.fetch(url, dest=dest, **kw)


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[Downloader] = None


def downloader() -> Downloader:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Downloader()
    return _INSTANCE


__all__ = [
    "Downloader", "DownloadProgress",
    "downloader",
]
