"""SONIC AI — Universal Actions.

High-level actions that use ``core.navigator``, ``core.finder``, and
``core.content`` to perform **anything** — across files, apps, websites,
and emails.

Public surface (stable, opt-in):
    - ``find_and_open(query)``              — one-shot fuzzy find + open
    - ``smart_copy(src, dst, *, dedup=True)``
    - ``organize_by_type(directory, *, move=True)``
    - ``bulk_rename(files, pattern, replacement)``
    - ``extract_to(archive, destination)``
    - ``web_summarize(url)``                — fetch + summarize
    - ``send_email(to, subject, body)``
    - ``app_action(app, *args)``            — app-specific dispatch
    - ``clip_text(query, *sources)``        — search files + clipboard
"""
from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("UNIVERSAL_ACTIONS")

# ───────────────────────────────────────────────────────────────────────────
# find_and_open
# ───────────────────────────────────────────────────────────────────────────

def find_and_open(query: str, *, max_results: int = 5) -> dict[str, Any]:
    """Find the best file/app/web match for ``query`` and open it.

    Returns a dict describing what was opened, even on failure.
    """
    from core.navigator import navigator as _nav_factory
    from core.finder import get_finder

    nav = _nav_factory()  # singleton

    # 1. Try local files (fuzzy)
    finder = get_finder()
    local_hits = finder.fuzzy_search(query, max_results=max_results)
    if local_hits and local_hits[0].score >= 0.85:
        result = nav.open_path(local_hits[0].path)
        return {
            "ok": result.ok,
            "mode": "file",
            "matched": local_hits[0].name,
            "path": local_hits[0].path,
            "score": local_hits[0].score,
            **({"error": result.error} if not result.ok else {}),
        }

    # 2. Try app alias
    result = nav.open_app(query, silent=True)
    if result.ok:
        return {
            "ok": True, "mode": "app",
            "matched": query, "score": 1.0,
            "detail": result.detail,
        }

    # 3. Fall back to web search
    result = nav.open_search(query)
    return {
        "ok": result.ok, "mode": "web_search",
        "matched": query, "score": 0.0,
        "detail": result.detail,
        **({"error": result.error} if not result.ok else {}),
    }


# ───────────────────────────────────────────────────────────────────────────
# smart_copy
# ───────────────────────────────────────────────────────────────────────────

def smart_copy(src: str, dst: str, *, dedup: bool = True) -> dict[str, Any]:
    """Copy a file/folder, with dedup detection + conflict resolution."""
    src_path = Path(src).expanduser()
    dst_path = Path(dst).expanduser()
    if not src_path.exists():
        return {"ok": False, "error": f"Source not found: {src_path}"}

    try:
        if dst_path.exists() and dedup:
            # Compare contents by hash
            src_hash = _file_hash(src_path)
            dst_hash = _file_hash(dst_path)
            if src_hash == dst_hash:
                return {
                    "ok": True, "skipped": True,
                    "reason": "destination is identical (same hash)",
                    "src": str(src_path), "dst": str(dst_path),
                }
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
            return {"ok": True, "copied": str(src_path), "to": str(dst_path),
                    "kind": "directory"}
        shutil.copy2(src_path, dst_path)
        return {"ok": True, "copied": str(src_path), "to": str(dst_path),
                "kind": "file"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _file_hash(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                h.update(str(child.relative_to(path)).encode("utf-8"))
                with open(child, "rb") as f:
                    for chunk in iter(lambda: f.read(64 * 1024), b""):
                        h.update(chunk)
        return h.hexdigest()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ───────────────────────────────────────────────────────────────────────────
# organize_by_type
# ───────────────────────────────────────────────────────────────────────────

_TYPE_FOLDERS = {
    "Images":    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".svg", ".heic"},
    "Videos":    {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".wmv"},
    "Audio":     {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma"},
    "Documents": {".pdf", ".docx", ".doc", ".txt", ".md", ".rtf", ".odt", ".pptx", ".ppt"},
    "Spreadsheets": {".xlsx", ".xls", ".csv", ".ods"},
    "Archives":  {".zip", ".tar", ".tar.gz", ".tgz", ".rar", ".7z", ".bz2"},
    "Code":      {".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml",
                  ".java", ".cpp", ".c", ".h", ".go", ".rs", ".rb", ".php", ".sh"},
    "Executables": {".exe", ".msi", ".bat", ".cmd", ".sh", ".app", ".dmg", ".deb", ".rpm"},
}


def organize_by_type(directory: str, *, move: bool = True,
                     recursive: bool = False) -> dict[str, Any]:
    """Sort files in ``directory`` into type subfolders.

    Args:
        directory:  Source directory.
        move:       If True, move files; if False, copy.
        recursive:  If True, walk into subdirectories too.
    """
    src = Path(directory).expanduser()
    if not src.is_dir():
        return {"ok": False, "error": f"Not a directory: {src}"}

    moves: list[dict[str, str]] = []
    pattern = src.rglob("*") if recursive else src.glob("*")
    for p in pattern:
        # Skip directories themselves
        if not p.is_file():
            continue
        # Skip files already in a type folder (avoid re-organising)
        if p.parent != src:
            continue
        # Determine target type
        target_folder = None
        for folder_name, exts in _TYPE_FOLDERS.items():
            if p.suffix.lower() in exts:
                target_folder = folder_name
                break
        if target_folder is None:
            target_folder = "Other"
        dest_dir = src / target_folder
        dest = dest_dir / p.name
        try:
            dest_dir.mkdir(exist_ok=True)
            if dest.exists():
                # Add numeric suffix
                base = p.stem
                ext = p.suffix
                i = 1
                while dest.exists():
                    dest = dest_dir / f"{base}_{i}{ext}"
                    i += 1
            if move:
                shutil.move(str(p), str(dest))
            else:
                shutil.copy2(str(p), str(dest))
            moves.append({"from": str(p), "to": str(dest),
                          "kind": target_folder})
        except Exception as e:
            logger.warning(f"Failed to move {p}: {e}")

    return {"ok": True, "directory": str(src), "moved": len(moves),
            "details": moves[:50], "truncated": len(moves) > 50}


# ───────────────────────────────────────────────────────────────────────────
# bulk_rename
# ───────────────────────────────────────────────────────────────────────────

def bulk_rename(files: list[str], pattern: str, replacement: str,
                *, regex: bool = False) -> dict[str, Any]:
    """Rename multiple files using a pattern.

    If ``regex`` is False, ``pattern`` and ``replacement`` are treated as
    literal strings (but ``pattern`` may appear anywhere in the filename).

    If ``regex`` is True, ``pattern`` is compiled as a Python regex.
    """
    renamed: list[dict[str, str]] = []
    errors: list[str] = []
    for f in files:
        p = Path(f)
        if not p.exists():
            errors.append(f"Not found: {f}")
            continue
        try:
            if regex:
                new_name = re.sub(pattern, replacement, p.name)
            else:
                new_name = p.name.replace(pattern, replacement)
            if new_name == p.name:
                continue
            new_path = p.with_name(new_name)
            if new_path.exists():
                errors.append(f"Target exists: {new_path}")
                continue
            p.rename(new_path)
            renamed.append({"from": p.name, "to": new_name})
        except Exception as e:
            errors.append(f"{f}: {e}")
    return {"ok": True, "renamed": renamed, "errors": errors,
            "count": len(renamed)}


# ───────────────────────────────────────────────────────────────────────────
# extract_to  (universal archive extraction)
# ───────────────────────────────────────────────────────────────────────────

def extract_to(archive: str, destination: str = "") -> dict[str, Any]:
    """Extract any common archive format to ``destination``."""
    arc = Path(archive).expanduser()
    if not arc.exists():
        return {"ok": False, "error": f"Archive not found: {arc}"}
    dst = Path(destination).expanduser() if destination else arc.parent / (arc.stem + "_extracted")
    dst.mkdir(parents=True, exist_ok=True)
    ext = arc.suffix.lower()
    try:
        if ext == ".zip":
            import zipfile
            with zipfile.ZipFile(arc) as z:
                z.extractall(dst)
        elif ext in (".tar", ".tgz", ".tar.gz"):
            import tarfile
            mode = "r:gz" if ext in (".tgz", ".tar.gz") else "r"
            with tarfile.open(arc, mode) as t:
                t.extractall(dst)
        elif ext == ".7z":
            import py7zr
            with py7zr.SevenZipFile(arc, mode="r") as z:
                z.extractall(dst)
        elif ext == ".rar":
            import rarfile
            with rarfile.RarFile(arc) as r:
                r.extractall(dst)
        elif ext == ".bz2":
            import bz2
            out = dst / arc.stem
            with bz2.open(arc, "rb") as src, open(out, "wb") as out_f:
                shutil.copyfileobj(src, out_f)
        elif ext == ".gz" and arc.suffix == ".gz":
            import gzip
            out = dst / arc.stem
            with gzip.open(arc, "rb") as src, open(out, "wb") as out_f:
                shutil.copyfileobj(src, out_f)
        else:
            return {"ok": False, "error": f"Unsupported archive format: {ext}"}
        return {"ok": True, "archive": str(arc), "destination": str(dst)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ───────────────────────────────────────────────────────────────────────────
# web_summarize
# ───────────────────────────────────────────────────────────────────────────

def web_summarize(url: str, *, max_chars: int = 4000) -> dict[str, Any]:
    """Fetch a URL and return its main text content (no LLM summarisation).

    For LLM-based summarization, combine with `core.providers`.
    """
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_chars * 4).decode("utf-8", errors="ignore")
        title = ""
        m = re.search(r"<title[^>]*>(.*?)</title>", raw,
                      re.IGNORECASE | re.DOTALL)
        if m:
            title = m.group(1).strip()
        # Strip HTML
        text = re.sub(r"<script[^>]*>.*?</script>", " ", raw,
                      flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text,
                      flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return {
            "ok": True,
            "url": url,
            "title": title,
            "content_type": content_type,
            "text": text[:max_chars],
            "truncated": len(text) > max_chars,
            "length": len(text),
        }
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)}


# ───────────────────────────────────────────────────────────────────────────
# send_email  (universal mailto helper)
# ───────────────────────────────────────────────────────────────────────────

def send_email(to: str, subject: str = "", body: str = "",
               provider: str = "gmail") -> dict[str, Any]:
    """Open the OS default mail client (mailto:)."""
    from core.navigator import navigator as _nav_factory
    return _nav_factory().open_email(to, subject=subject, body=body,
                                    provider=provider).to_dict()


# ───────────────────────────────────────────────────────────────────────────
# app_action — dispatch helper for common app-specific commands
# ───────────────────────────────────────────────────────────────────────────

def app_action(app: str, action: str, *args: str) -> dict[str, Any]:
    """High-level wrapper: run a known action against an app.

    Supported:
        media    play|pause|next|prev|stop|volume
        browser  open-tab|new-window|history|downloads|incognito
        system   lock|sleep|shutdown|restart|recycle|empty-recycle
        file     show-hidden|toggle-hidden|extensions
    """
    app_l = app.lower()
    action_l = action.lower()

    # ── media ─────────────────────────────────────────────────────────
    if app_l in ("spotify", "vlc", "media", "player"):
        return _media_action(action_l, *args)
    # ── browser ──────────────────────────────────────────────────────
    if app_l in ("chrome", "firefox", "edge", "brave", "browser", "default browser"):
        return _browser_action(app_l, action_l, *args)
    # ── system ───────────────────────────────────────────────────────
    if app_l in ("system", "windows", "os") or action_l in (
            "lock", "sleep", "shutdown", "restart", "recycle", "empty-recycle"):
        return _system_action(action_l, *args)
    # ── file explorer ────────────────────────────────────────────────
    if app_l in ("explorer", "file explorer", "files"):
        return _explorer_action(action_l, *args)
    # ── everything else: just open the app ──────────────────────────
    from core.navigator import navigator as _nav_factory
    return _nav_factory().open_app(app).to_dict()


def _media_action(action: str, *args: str) -> dict[str, Any]:
    import pyautogui
    keys = {
        "play":  "playpause", "pause": "playpause",
        "next":  "nexttrack",  "prev": "prevtrack", "stop": "stop",
        "mute":  "volumemute",
    }
    if action in keys:
        try:
            pyautogui.press(keys[action])
            return {"ok": True, "action": action, "detail": "sent media key"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if action == "volume":
        try:
            direction = args[0] if args else "up"
            key = "volumeup" if direction == "up" else "volumedown"
            steps = int(args[1]) if len(args) > 1 else 5
            for _ in range(steps):
                pyautogui.press(key)
            return {"ok": True, "action": "volume", "direction": direction,
                    "steps": steps}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Unknown media action: {action}"}


def _browser_action(app: str, action: str, *args: str) -> dict[str, Any]:
    from core.navigator import navigator as _nav_factory
    nav = _nav_factory()
    if action == "open-tab" and args:
        return nav.open_url(args[0]).to_dict()
    if action == "new-window":
        import webbrowser
        webbrowser.open("about:blank", new=2)
        return {"ok": True, "action": "new-window"}
    if action == "incognito":
        try:
            import subprocess, sys
            commands = {
                "chrome": ["chrome.exe", "--incognito"],
                "firefox": ["firefox.exe", "-private"],
                "edge": ["msedge.exe", "--inprivate"],
                "brave": ["brave.exe", "--incognito"],
            }
            cmd = commands.get(app, commands["chrome"])
            if sys.platform == "win32":
                subprocess.Popen(cmd,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.Popen(cmd)
            return {"ok": True, "action": "incognito", "app": app}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    if action in ("history", "downloads", "extensions"):
        urls = {
            "chrome":    {"history": "chrome://history",
                          "downloads": "chrome://downloads",
                          "extensions": "chrome://extensions"},
            "firefox":   {"history": "about:history",
                          "downloads": "about:downloads",
                          "extensions": "about:addons"},
            "edge":      {"history": "edge://history",
                          "downloads": "edge://downloads",
                          "extensions": "edge://extensions"},
            "brave":     {"history": "brave://history",
                          "downloads": "brave://downloads",
                          "extensions": "brave://extensions"},
        }
        url = urls.get(app, urls["chrome"]).get(action)
        return nav.open_url(url).to_dict()
    return {"ok": False, "error": f"Unknown browser action: {action}"}


def _system_action(action: str, *args: str) -> dict[str, Any]:
    if sys.platform != "win32":
        return {"ok": False, "error": "System actions are Windows-only here"}
    try:
        if action == "lock":
            subprocess.Popen("rundll32.exe user32.dll,LockWorkStation")
        elif action == "sleep":
            subprocess.Popen("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif action == "shutdown":
            confirm = (args[0].lower() == "confirm") if args else False
            cmd = "shutdown /s /t 0"
            cmd += " /f" if confirm else ""
            subprocess.Popen(cmd.split(), creationflags=subprocess.CREATE_NO_WINDOW)
        elif action == "restart":
            subprocess.Popen("shutdown /r /t 0".split(),
                             creationflags=subprocess.CREATE_NO_WINDOW)
        elif action in ("recycle", "empty-recycle"):
            try:
                from windows_recycle import empty_recycle_bin
                empty_recycle_bin()
                return {"ok": True, "action": "empty-recycle"}
            except ImportError:
                # Fallback to PowerShell
                subprocess.Popen(
                    ["powershell", "-Command",
                     "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        else:
            return {"ok": False, "error": f"Unknown system action: {action}"}
        return {"ok": True, "action": action}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _explorer_action(action: str, *args: str) -> dict[str, Any]:
    if action == "show-hidden" or action == "toggle-hidden":
        import ctypes
        # SPI_GETSETSHOWHIDDENFILES? Easier: registry toggle.
        # Use the Folder Options dialog.
        subprocess.Popen(["explorer.exe", "shell:::{6DFD7C5C-2451-11d3-A299-00C04F8EF6AF}"])
        return {"ok": True, "action": action, "note": "Opened Folder Options dialog"}
    if action == "extensions" and args:
        ext_map = {
            "chrome": "chrome://extensions",
            "firefox": "about:addons",
            "edge":   "edge://extensions",
            "vscode": "vscode:extensions",
        }
        url = ext_map.get(args[0].lower(), ext_map["chrome"])
        from core.navigator import navigator as _nav_factory
        return _nav_factory().open_url(url).to_dict()
    return {"ok": False, "error": f"Unknown explorer action: {action}"}


# ───────────────────────────────────────────────────────────────────────────
# clip_text  — copy text from file / URL / clipboard to clipboard
# ───────────────────────────────────────────────────────────────────────────

def clip_text(query: str, *sources: str) -> dict[str, Any]:
    """Search across files + clipboard + optional URLs and put best match on clipboard."""
    candidates: list[tuple[float, str]] = []
    try:
        from core.finder import get_finder
        f = get_finder()
        for hit in f.fuzzy_search(query, max_results=5):
            if hit.score >= 0.5:
                candidates.append((hit.score, f"FILE:{hit.path}"))
        for hit in f.content_search(query, max_results=5):
            if hit.score >= 0.5 and hit.snippet:
                candidates.append((hit.score, f"FILE_SNIPPET:{hit.path}\n{hit.snippet}"))
    except Exception:
        pass

    # Web URLs as sources
    for s in sources:
        if s.startswith(("http://", "https://")):
            r = web_summarize(s, max_chars=800)
            if r.get("ok") and r.get("text"):
                # Score by query overlap
                q_words = set(query.lower().split())
                overlap = sum(1 for w in q_words if w in r["text"].lower())
                if overlap:
                    candidates.append((overlap / len(q_words), f"WEB:{s}\n{r['text']}"))

    if not candidates:
        return {"ok": False, "error": "No matches found"}

    candidates.sort(key=lambda x: x[0], reverse=True)
    text = candidates[0][1]
    try:
        import pyperclip
        pyperclip.copy(text.split(":", 1)[1].lstrip() if ":" in text else text)
    except Exception:
        pass
    return {"ok": True, "copied": text[:200] + ("…" if len(text) > 200 else ""),
            "score": candidates[0][0], "candidates": len(candidates)}


__all__ = [
    "find_and_open", "smart_copy", "organize_by_type", "bulk_rename",
    "extract_to", "web_summarize", "send_email",
    "app_action", "clip_text",
    "browse_and_download", "browse_and_scrape", "youtube_download",
    "app_perform", "macro_run", "search_youtube",
    "github_download_latest", "download_file",
]


# ═════════════════════════════════════════════════════════════════════════════
# High-level actions that wire the new core modules
# ═════════════════════════════════════════════════════════════════════════════

def download_file(url: str, dest: str = "",
                  *, on_progress=None, resume: bool = True) -> dict:
    """Universal download — picks the best strategy automatically.

    - YouTube / Vimeo → yt-dlp
    - HTML page (JS-gated) → browser
    - Direct file → streaming HTTP with resume
    """
    from core.downloader import downloader as _dl_factory
    from pathlib import Path as _P
    dl = _dl_factory()
    d = _P(dest) if dest else None
    prog = dl.smart_fetch(url, dest=d, on_progress=on_progress)
    return {
        "ok": prog.status == "done",
        "status": prog.status,
        "dest": prog.dest,
        "bytes": prog.bytes_downloaded,
        "speed_bps": prog.speed_bps,
        "eta_seconds": prog.eta_seconds,
        "error": prog.error,
        "percent": prog.percent,
    }


def browse_and_download(url: str, *, click_selector: str = "",
                        dest: str = "") -> dict:
    """Open a URL in a real browser, click ``click_selector`` if given,
    then capture whatever the browser starts downloading."""
    from core.web_automator import web
    from pathlib import Path as _P
    try:
        with web().open_page(url) as page:
            if click_selector:
                d = web().download_via_click(page, click_selector,
                                              dest=(_P(dest) if dest else None))
                return {"ok": d.ok, "path": d.path, "bytes": d.bytes_downloaded,
                        "error": d.error, "method": "click"}
            else:
                d = web().download_url(page, url, dest=(_P(dest) if dest else None))
                return {"ok": d.ok, "path": d.path, "bytes": d.bytes_downloaded,
                        "error": d.error, "method": "navigate"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def browse_and_scrape(url: str, *, selector: str = "") -> dict:
    """Open a URL and return the page text + title + links + images."""
    from core.web_automator import web
    try:
        with web().open_page(url) as page:
            r = web().scrape(page, selector=selector or None)
            return r.to_dict()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def youtube_download(url: str, *, dest: str = "",
                     audio_only: bool = False) -> dict:
    """Download a YouTube / Vimeo / etc. video (or audio-only).

    Requires ``yt-dlp`` (``pip install yt-dlp``).
    """
    from core.downloader import downloader as _dl_factory
    from pathlib import Path as _P
    prog = _dl_factory().youtube(url,
                                dest=(_P(dest) if dest else None),
                                audio_only=audio_only)
    return {
        "ok": prog.status == "done",
        "status": prog.status,
        "dest": prog.dest,
        "bytes": prog.bytes_downloaded,
        "error": prog.error,
    }


def search_youtube(query: str, *, max_videos: int = 5) -> dict:
    """Search YouTube and return the top video results.

    Uses real Chromium via Playwright so JavaScript renders.
    """
    from core.web_automator import web
    try:
        results = web().youtube_search(query, max_videos=max_videos)
        return {"ok": True, "query": query, "results": results,
                "count": len(results)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def github_download_latest(user: str, repo: str, *,
                           dest: str = "", asset_filter: str = "") -> dict:
    """Open the GitHub Releases page for ``user/repo`` and download the
    latest asset (optionally filtered by extension substring)."""
    from core.web_automator import web
    from core.downloader import downloader as _dl_factory
    from pathlib import Path as _P
    info = web().github_latest_release(user, repo)
    if not info.get("ok"):
        return info
    assets = info.get("assets", [])
    if asset_filter:
        assets = [a for a in assets if asset_filter.lower() in a["name"].lower()]
    if not assets:
        return {"ok": False, "error": "No matching assets",
                "all_assets": info.get("assets", [])}
    target = assets[0]
    out_dir = _P(dest) if dest else None
    prog = _dl_factory().fetch(target["url"], dest=out_dir)
    return {
        "ok": prog.status == "done",
        "asset": target["name"],
        "url": target["url"],
        "dest": prog.dest,
        "bytes": prog.bytes_downloaded,
        "tag": info.get("tag"),
    }


def app_perform(app_name: str, *args: str) -> dict:
    """Launch an app, focus it, optionally pass command-line args."""
    from core.navigator import navigator as _nav_factory
    from core.app_automator import app_automator
    nav = _nav_factory()
    res = nav.open_app(app_name)
    if not res.ok:
        return {"ok": False, "error": res.error}
    time.sleep(0.8)  # let it come up
    if args:
        # Try to set focus to the app and pass args via clipboard + paste
        if app_automator().focus(app_name):
            app_automator().type_at_active(" ".join(args))
            app_automator().press("enter")
    return {"ok": True, "detail": res.detail, "args": list(args)}


def macro_run(steps: list[dict]) -> dict:
    """Run a UI automation macro.

    Each step: ``{"action": "focus"|"type"|"press"|"hotkey"|"click"|"wait"|"screenshot", "args": {...}}``
    """
    from core.app_automator import app_automator
    return app_automator().run_macro(steps)
