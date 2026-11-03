"""SONIC AI — Universal Navigator.

A high-end launcher that can open ANY resource — apps, URLs, deep-links,
emails, files, paths, shell commands — and pick the **best** target
automatically based on intent.

Why this matters:
    - Other actions need to call ``launcher.open(...)`` rather than
      building their own ``subprocess.Popen`` incantations.
    - Provides a single mental model: ``navigator.open(target)`` and it
      just works.

Public surface (stable, opt-in):
    - ``navigator.open(target, *, mode="auto")`` — entry point
    - ``navigator.open_url(url, browser=None)``
    - ``navigator.open_app(name_or_exe)``
    - ``navigator.open_email(to, subject="", body="")``
    - ``navigator.open_path(path)``
    - ``navigator.open_search(query, engine="google")``
    - ``navigator.search_everything(query)`` — file + web + apps
    - ``NavigatorResult`` — uniform result dataclass

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

try:
    import webbrowser
except ImportError:  # pragma: no cover
    webbrowser = None


# ═════════════════════════════════════════════════════════════════════════════
# Result dataclass
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class NavigatorResult:
    ok: bool
    target: str
    mode: str                       # url | app | file | email | search | command
    detail: str = ""
    process_id: Optional[int] = None
    error: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Smart target classification
# ═════════════════════════════════════════════════════════════════════════════

_URL_RE = re.compile(r"^(https?|ftp|file)://", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
_LOCAL_PATH_HINT = re.compile(r"^([a-zA-Z]:\\|/|\\\\|\.{1,2}/|~/)")


# Common email providers → mailto URL
_EMAIL_PROVIDERS = {
    "gmail":     "https://mail.google.com/mail/?compose=new&to={to}&su={sub}&body={body}",
    "outlook":   "https://outlook.live.com/mail/0/deeplink/compose?to={to}&subject={sub}&body={body}",
    "yahoo":     "https://compose.mail.yahoo.com/?to={to}&subject={sub}&body={body}",
    "proton":    "https://mail.proton.me/compose?to={to}&subject={sub}&body={body}",
}


# Common app aliases → known executable names
_APP_ALIASES = {
    # Browsers
    "chrome":       ["chrome.exe", "google chrome"],
    "firefox":      ["firefox.exe"],
    "edge":         ["msedge.exe"],
    "brave":        ["brave.exe"],
    "safari":       ["Safari"],
    "opera":        ["opera.exe"],
    # Dev
    "vscode":       ["code.exe", "Code.exe"],
    "vs code":      ["code.exe", "Code.exe"],
    "code":         ["code.exe", "Code.exe"],
    "pycharm":      ["pycharm64.exe"],
    "intellij":     ["idea64.exe"],
    "sublime":      ["sublime_text.exe"],
    "vim":          ["vim.exe", "gvim.exe"],
    "neovim":       ["nvim.exe"],
    "git":          ["git.exe"],
    # System
    "explorer":     ["explorer.exe"],
    "file explorer": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "control panel": ["control.exe"],
    "settings":     ["ms-settings:"],
    "calculator":   ["calc.exe"],
    "notepad":      ["notepad.exe"],
    "paint":        ["mspaint.exe"],
    "terminal":     ["wt.exe", "cmd.exe", "powershell.exe"],
    "cmd":          ["cmd.exe"],
    "powershell":   ["powershell.exe"],
    # Media
    "spotify":      ["spotify.exe"],
    "vlc":          ["vlc.exe"],
    "obs":          ["obs64.exe", "obs.exe"],
    "photoshop":    ["photoshop.exe"],
    # Productivity
    "word":         ["winword.exe"],
    "excel":        ["excel.exe"],
    "powerpoint":   ["powerpnt.exe"],
    "outlook":      ["outlook.exe"],
    "onenote":      ["onenote.exe"],
    "teams":        ["ms-teams.exe"],
    "slack":        ["slack.exe"],
    "discord":      ["discord.exe"],
    "telegram":     ["telegram.exe"],
    "whatsapp":     ["whatsapp.exe"],
    "zoom":         ["zoom.exe"],
    # Other
    "steam":        ["steam.exe"],
    "epic":         ["EpicGamesLauncher.exe"],
    "notion":       ["Notion.exe"],
    "figma":        ["figma.exe"],
    "postman":      ["Postman.exe"],
}

# Search engines
_SEARCH_ENGINES = {
    "google":   "https://www.google.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "bing":     "https://www.bing.com/search?q={q}",
    "brave":    "https://search.brave.com/search?q={q}",
    "youtube":  "https://www.youtube.com/results?search_query={q}",
    "github":   "https://github.com/search?q={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={q}",
}


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _is_url(target: str) -> bool:
    return bool(_URL_RE.match(target))


def _is_email(target: str) -> bool:
    return bool(_EMAIL_RE.match(target))


def _looks_like_path(target: str) -> bool:
    """Whether the string *looks* like a filesystem path."""
    if not target:
        return False
    # Strip optional surrounding quotes
    target = target.strip().strip("'\"")
    if _LOCAL_PATH_HINT.match(target):
        return True
    # Absolute Unix-style path
    if target.startswith("/"):
        return True
    # Has path separator + extension
    if (("/" in target or "\\" in target)
            and "." in target.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]):
        return True
    return False


def _resolve_app(name: str) -> Optional[str]:
    """Resolve an app alias or executable name to a runnable path."""
    key = name.strip().lower()
    if not key:
        return None
    # Try alias list
    for alias, exe_list in _APP_ALIASES.items():
        if key == alias or key in alias:
            for exe in exe_list:
                # Check well-known locations first
                path = _find_executable(exe)
                if path:
                    return path
    # Try direct executable name
    return _find_executable(key) or _find_executable(key + ".exe")


def _find_executable(name: str) -> Optional[str]:
    """Look up an executable by name. Checks PATH, then common locations.

    Uses depth-bounded, time-bounded search to avoid scanning huge trees
    like ``C:\\Program Files`` (which has hundreds of thousands of files).
    """
    # 1. PATH lookup (instant)
    found = shutil.which(name)
    if found:
        return found

    # 2. Windows: well-known app directories (depth-2 only, time-bounded)
    if sys.platform == "win32":
        program_files = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LocalAppData", str(Path.home() / "AppData" / "Local")),
        ]
        deadline = time.monotonic() + 1.5  # hard cap 1.5 seconds
        for root_str in program_files:
            if time.monotonic() > deadline:
                break
            try:
                root_path = Path(root_str)
                if not root_path.exists():
                    continue
                # Bounded search: at most 2 levels deep
                found = _bounded_find(root_path, name, max_depth=2,
                                       deadline=deadline)
                if found:
                    return str(found)
            except (PermissionError, OSError):
                continue

    # 3. macOS / Linux: try /Applications/, /usr/bin, etc.
    if sys.platform == "darwin":
        for path in [
            f"/Applications/{name}.app",
            f"/Applications/{name.replace('.app', '')}.app",
        ]:
            if Path(path).exists():
                return path

    return None


def _bounded_find(root: Path, name: str, *, max_depth: int,
                  deadline: float) -> Optional[Path]:
    """Depth-bounded file finder with a time limit."""
    if time.monotonic() > deadline:
        return None
    # 1-level direct children first (fastest)
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            cand = child / name
            if cand.exists():
                return cand
    except (PermissionError, OSError):
        pass
    # 2-level nested children
    if max_depth < 2:
        return None
    try:
        for sub in root.iterdir():
            if time.monotonic() > deadline:
                return None
            if not sub.is_dir():
                continue
            try:
                cand = sub / name
                if cand.exists():
                    return cand
                # Try one more level deep
                for sub2 in sub.iterdir():
                    if not sub2.is_dir():
                        continue
                    cand = sub2 / name
                    if cand.exists():
                        return cand
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        pass
    return None


def _open_with_shell(path: str) -> bool:
    """Last-resort opener using the OS shell."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def _quote(s: str) -> str:
    return urllib.parse.quote(s, safe="")


# ═════════════════════════════════════════════════════════════════════════════
# Universal navigator
# ═════════════════════════════════════════════════════════════════════════════

class Navigator:
    """The single entry point for opening anything."""

    def open(self, target: str, *, mode: str = "auto") -> NavigatorResult:
        """Open anything — auto-detects what kind of target it is.

        Modes:
            auto    — figure it out from the string shape
            url     — treat as URL
            app     — treat as application name / alias
            file    — treat as filesystem path
            email   — treat as email address
            search  — treat as web search query
            command — run as shell command (only when explicitly requested)
        """
        if not target or not target.strip():
            return NavigatorResult(ok=False, target=target or "", mode="auto",
                                  error="Empty target")

        target = target.strip()
        m = mode.lower()

        # Explicit modes short-circuit classification
        if m == "url":
            return self.open_url(target)
        if m == "app":
            return self.open_app(target)
        if m == "file":
            return self.open_path(target)
        if m == "email":
            return self.open_email(target)
        if m == "search":
            return self.open_search(target)
        if m == "command":
            return self._run_command(target)

        # Auto classification
        if _is_url(target):
            return self.open_url(target)
        if _is_email(target):
            return self.open_email(target)
        if _looks_like_path(target):
            return self.open_path(target)
        # Try app resolution; if that fails, default to web search.
        app_result = self.open_app(target, silent=True)
        if app_result.ok:
            return app_result
        return self.open_search(target)

    # ── URLs ─────────────────────────────────────────────────────────────
    def open_url(self, url: str, *, browser: Optional[str] = None) -> NavigatorResult:
        if not _is_url(url):
            url = "https://" + url
        if webbrowser is None:
            return NavigatorResult(ok=False, target=url, mode="url",
                                   error="webbrowser module unavailable")
        try:
            if browser:
                try:
                    br = webbrowser.get(using=browser)
                    br.open(url)
                except webbrowser.Error:
                    webbrowser.open(url)
            else:
                webbrowser.open(url)
            return NavigatorResult(ok=True, target=url, mode="url",
                                  detail=f"Opened in browser")
        except Exception as e:
            return NavigatorResult(ok=False, target=url, mode="url", error=str(e))

    # ── Apps ─────────────────────────────────────────────────────────────
    def open_app(self, name_or_exe: str, *, silent: bool = False) -> NavigatorResult:
        """Launch an app by alias, executable name, or absolute path."""
        # 1. Try resolving as alias → exe path
        exe = _resolve_app(name_or_exe)
        if exe:
            try:
                if sys.platform == "win32":
                    flags = subprocess.CREATE_NO_WINDOW
                    pid = subprocess.Popen([exe],
                                          creationflags=flags).pid
                elif sys.platform == "darwin" and exe.endswith(".app"):
                    pid = subprocess.Popen(["open", exe]).pid
                else:
                    pid = subprocess.Popen([exe]).pid
                return NavigatorResult(ok=True, target=name_or_exe, mode="app",
                                      detail=f"Launched: {exe}", process_id=pid)
            except Exception as e:
                # Fall through to shell open
                if not silent:
                    pass

        # 2. Try as absolute path
        if Path(name_or_exe).exists():
            if _open_with_shell(name_or_exe):
                return NavigatorResult(ok=True, target=name_or_exe, mode="app",
                                      detail="Opened via shell")
            return NavigatorResult(ok=False, target=name_or_exe, mode="app",
                                   error="Path exists but could not be launched")

        # 3. Try shell open with the bare name
        if _open_with_shell(name_or_exe):
            return NavigatorResult(ok=True, target=name_or_exe, mode="app",
                                  detail="Opened via shell")

        return NavigatorResult(ok=False, target=name_or_exe, mode="app",
                               error=f"App not found: {name_or_exe!r}")

    # ── Files / folders ─────────────────────────────────────────────────
    def open_path(self, path: str) -> NavigatorResult:
        """Open a file or folder with its default OS handler."""
        p = Path(path).expanduser()
        if not p.exists():
            return NavigatorResult(ok=False, target=str(p), mode="file",
                                   error=f"Not found: {p}")
        if _open_with_shell(str(p)):
            return NavigatorResult(ok=True, target=str(p), mode="file",
                                  detail="Opened with default handler")
        return NavigatorResult(ok=False, target=str(p), mode="file",
                               error="OS handler failed")

    # ── Email ────────────────────────────────────────────────────────────
    def open_email(self, to: str, *, subject: str = "", body: str = "",
                   provider: str = "gmail") -> NavigatorResult:
        """Open the user's default mail client (mailto:)."""
        q = urllib.parse.urlencode({
            "subject": subject, "body": body,
        })
        url = f"mailto:{_quote(to)}?{q}"
        try:
            if webbrowser is not None:
                webbrowser.open(url)
            return NavigatorResult(ok=True, target=to, mode="email",
                                  detail=f"mailto: {to}")
        except Exception as e:
            return NavigatorResult(ok=False, target=to, mode="email", error=str(e))

    # ── Search ──────────────────────────────────────────────────────────
    def open_search(self, query: str, *, engine: str = "google") -> NavigatorResult:
        """Run a web search in the default browser."""
        template = _SEARCH_ENGINES.get(engine.lower())
        if not template:
            return NavigatorResult(ok=False, target=query, mode="search",
                                   error=f"Unknown engine: {engine}")
        url = template.format(q=_quote(query))
        if webbrowser is not None:
            webbrowser.open(url)
        return NavigatorResult(ok=True, target=query, mode="search",
                              detail=f"Search on {engine}: {url}")

    # ── Command runner (explicit only) ──────────────────────────────────
    def _run_command(self, command: str) -> NavigatorResult:
        """Run a shell command. Only invoked via ``open(target, mode='command')``."""
        try:
            if sys.platform == "win32":
                flags = subprocess.CREATE_NO_WINDOW
                pid = subprocess.Popen(command, shell=True,
                                       creationflags=flags).pid
            else:
                pid = subprocess.Popen(["sh", "-c", command]).pid
            return NavigatorResult(ok=True, target=command, mode="command",
                                  process_id=pid, detail="Shell command launched")
        except Exception as e:
            return NavigatorResult(ok=False, target=command, mode="command",
                                   error=str(e))

    # ── Universal search (files + web + apps) ────────────────────────────
    def search_everything(self, query: str, *, max_results: int = 20) -> dict:
        """One query → results from local files, web, and apps.

        Returns:
            {
                "query": str,
                "files":   [{name, path, score}, ...],
                "apps":    [{alias, exe, score}, ...],
                "web":     {engine: url, ...},
            }
        """
        from core.finder import finder   # local import to avoid cycles
        files = finder.fuzzy_search(query, max_results=max_results)
        web = {eng: tmpl.format(q=_quote(query))
               for eng, tmpl in _SEARCH_ENGINES.items()}

        q_lower = query.lower().strip()
        apps = []
        for alias in _APP_ALIASES:
            score = 0
            if q_lower == alias:
                score = 100
            elif q_lower in alias or alias in q_lower:
                score = 70
            elif any(tok in alias for tok in q_lower.split()):
                score = 40
            if score:
                apps.append({"alias": alias, "exe": _APP_ALIASES[alias][0],
                             "score": score})
        apps.sort(key=lambda a: a["score"], reverse=True)
        return {
            "query": query,
            "files": [f.to_dict() for f in files[:max_results]],
            "apps":  apps[:max_results],
            "web":   web,
        }


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[Navigator] = None


def navigator() -> Navigator:
    """Return the process-wide Navigator instance."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Navigator()
    return _INSTANCE


__all__ = [
    "Navigator", "NavigatorResult",
    "navigator",
]
