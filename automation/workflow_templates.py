"""SONIC AI — Workflow Templates.

Pre-built automation recipes the user can trigger with one command.
Each template is a self-contained Python function that runs inside the
``RealtimeEngine`` worker thread — so they get progress + logs for free.

Public surface (stable, opt-in):
    - ``list_templates()`` — enumerate available workflows
    - ``run_template(name, **kwargs)`` — submit to realtime engine
    - ``TEMPLATES`` — registry of name → callable

Templates ship today:
    1. organize_downloads       — sort Downloads by type
    2. backup_documents         — zip Documents into dated archive
    3. dedup_home               — find & summarise duplicate files
    4. screenshot_timelapse     — periodic screenshots for n hours
    5. weather_brief            — fetch weather + emit a brief
    6. github_release_watch     — poll a repo, download new assets
    7. clean_temp_files         — purge files older than N days from %TEMP%
    8. report_large_files       — list top N biggest files anywhere
"""
from __future__ import annotations

import logging
import os
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("WORKFLOW_TEMPLATES")

# Local imports are deferred to the callable body to avoid circular imports
# at module-load time and to keep the registry lean.


# ═════════════════════════════════════════════════════════════════════════════
# Template registry
# ═════════════════════════════════════════════════════════════════════════════

TEMPLATES: dict[str, dict[str, Any]] = {}


def register(name: str, description: str, *,
            category: str = "general",
            params: Optional[dict] = None):
    """Decorator to register a workflow function."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        TEMPLATES[name] = {
            "fn": fn,
            "name": name,
            "description": description,
            "category": category,
            "params": params or {},
        }
        return fn
    return deco


def list_templates() -> list[dict]:
    """Return a sorted summary of all available templates."""
    return [
        {"name": t["name"], "description": t["description"],
         "category": t["category"], "params": t["params"]}
        for t in sorted(TEMPLATES.values(), key=lambda x: x["name"])
    ]


def get_template(name: str) -> Optional[Callable[..., Any]]:
    return (TEMPLATES.get(name) or {}).get("fn")


def run_template(name: str, **kwargs) -> str:
    """Submit a template to the realtime engine. Returns the job id."""
    from automation.realtime_engine import realtime, Job
    fn = get_template(name)
    if fn is None:
        raise KeyError(f"unknown template: {name!r}")
    engine = realtime()
    # The engine auto-binds _ctx_log / _ctx_progress kwargs to log lines
    # and update progress. We pass them through to fn.
    display_name = kwargs.pop("name", name)  # prefer caller-provided override
    job_id = engine.submit(
        fn,
        job_id=kwargs.pop("job_id", None),
        name=display_name,
        metadata={"params": kwargs, "category":
                  TEMPLATES[name]["category"]},
        **kwargs,
    )
    return job_id


# ═════════════════════════════════════════════════════════════════════════════
# 1. organize_downloads
# ═════════════════════════════════════════════════════════════════════════════

@register("organize_downloads",
          "Sort Downloads folder into type folders (Images, Videos, Documents, …)",
          category="files", params={"directory": "str (default: ~/Downloads)"})
def organize_downloads(directory: str = "", **_ctx) -> dict:
    from actions.universal import organize_by_type
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    src = Path(directory).expanduser() if directory else Path.home() / "Downloads"
    log(f"Source: {src}")
    if not src.is_dir():
        raise FileNotFoundError(src)

    log("Scanning for files…")
    progress(0.1)

    result = organize_by_type(str(src), move=True, recursive=False)
    log(f"Moved {result['moved']} files into type folders")
    progress(1.0)

    # Group summary
    by_kind: dict[str, int] = {}
    for d in sorted(src.iterdir()):
        if d.is_dir():
            by_kind[d.name] = sum(1 for _ in d.iterdir() if _.is_file())
    log(f"Folders: {by_kind}")
    return {"directory": str(src), "moved": result["moved"],
            "folders": by_kind}


# ═════════════════════════════════════════════════════════════════════════════
# 2. backup_documents
# ═════════════════════════════════════════════════════════════════════════════

@register("backup_documents",
          "Zip the Documents folder into a dated archive in ~/Backups",
          category="backup",
          params={"source": "str", "dest": "str (default: ~/Backups)"})
def backup_documents(source: str = "", dest: str = "", **_ctx) -> dict:
    import zipfile
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    src = Path(source).expanduser() if source else Path.home() / "Documents"
    dst_dir = Path(dest).expanduser() if dest else Path.home() / "Backups"
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src.is_dir():
        raise FileNotFoundError(src)
    log(f"Source: {src}")
    log(f"Backup folder: {dst_dir}")

    archive_name = f"Documents-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    archive = dst_dir / archive_name
    log(f"Creating archive: {archive}")

    files = [p for p in src.rglob("*") if p.is_file()]
    total = len(files)
    log(f"Found {total} files to archive")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for i, p in enumerate(files, 1):
            try:
                zf.write(p, arcname=str(p.relative_to(src)))
            except (PermissionError, OSError) as e:
                log(f"skip {p}: {e}")
            if i % 25 == 0 or i == total:
                progress(0.05 + 0.9 * i / total)
                log(f"  {i}/{total} files")

    progress(1.0)
    log(f"Done. Archive size: {archive.stat().st_size / 1e6:.2f} MB")
    return {"archive": str(archive), "files": total,
            "size_mb": round(archive.stat().st_size / 1e6, 2)}


# ═════════════════════════════════════════════════════════════════════════════
# 3. dedup_home
# ═════════════════════════════════════════════════════════════════════════════

@register("dedup_home",
          "Scan common folders for duplicate files (SHA-256) and report",
          category="files", params={"min_size_mb": "float (default: 1)"})
def dedup_home(min_size_mb: float = 1, **_ctx) -> dict:
    from core.finder import Finder
    import time as _t
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    roots = [
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home() / "Pictures",
        Path.home() / "Desktop",
    ]
    roots = [r for r in roots if r.exists()]
    log(f"Scanning roots: {[str(r) for r in roots]}")

    f = Finder(default_roots=roots)
    progress(0.1)
    log(f"Finding duplicates (min_size={int(min_size_mb * 1024 * 1024)} bytes)…")

    # Stream progress so the dashboard shows activity
    t0 = _t.monotonic()
    sizes: dict = {}
    file_count = 0
    for r in roots:
        try:
            for p in r.rglob("*"):
                if not p.is_file():
                    continue
                file_count += 1
                if file_count % 500 == 0:
                    progress(min(0.45, file_count / 10000))
                    log(f"  scanned {file_count} files…")
                try:
                    s = p.stat().st_size
                    if s >= int(min_size_mb * 1024 * 1024):
                        sizes.setdefault(s, []).append(p)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            continue

    log(f"Scan done: {file_count} files in {_t.monotonic() - t0:.1f}s, "
        f"{sum(len(v) for v in sizes.values())} candidates > {min_size_mb} MB")
    progress(0.55)

    # Hash groups
    hash_groups: dict = {}
    for size, paths in sizes.items():
        if len(paths) > 1:
            for p in paths:
                try:
                    import hashlib as _hl
                    h = _hl.sha256()
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(64 * 1024), b""):
                            h.update(chunk)
                    hash_groups.setdefault(h.hexdigest(), []).append(p)
                except (PermissionError, OSError):
                    continue

    progress(0.95)

    groups = []
    for h, paths in hash_groups.items():
        if len(paths) > 1:
            size = paths[0].stat().st_size
            groups.append({"hash": h, "size": size, "wasted": size * (len(paths) - 1),
                          "paths": [str(p) for p in paths]})
    groups.sort(key=lambda g: g["wasted"], reverse=True)
    groups = groups[:200]

    progress(1.0)

    total_wasted = sum(g["wasted"] for g in groups)
    log(f"Found {len(groups)} duplicate groups, "
        f"wasting {total_wasted / 1e6:.2f} MB")

    return {"groups": len(groups),
            "wasted_mb": round(total_wasted / 1e6, 2),
            "biggest": [{"hash": g["hash"][:12], "size_mb": round(g["size"]/1e6, 2),
                          "paths": [Path(p).name for p in g["paths"]]}
                         for g in groups[:10]]}


# ═════════════════════════════════════════════════════════════════════════════
# 4. screenshot_timelapse
# ═════════════════════════════════════════════════════════════════════════════

@register("screenshot_timelapse",
          "Take screenshots every N seconds for M minutes into ~/Pictures/SONIC/Timelapse",
          category="monitor",
          params={"interval_seconds": "int (default: 30)",
                  "duration_minutes": "int (default: 60)"})
def screenshot_timelapse(interval_seconds: int = 30,
                         duration_minutes: int = 60, **_ctx) -> dict:
    from core.app_automator import app_automator
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    aa = app_automator()
    out_dir = Path.home() / "Pictures" / "SONIC" / "Timelapse"
    out_dir.mkdir(parents=True, exist_ok=True)

    end_time = time.time() + duration_minutes * 60
    shots = 0
    log(f"Capturing every {interval_seconds}s for {duration_minutes} min "
        f"into {out_dir}")
    while time.time() < end_time:
        path = out_dir / f"shot_{datetime.now():%Y%m%d_%H%M%S}.png"
        aa.screenshot(str(path))
        shots += 1
        progress(min(1.0, shots * interval_seconds / (duration_minutes * 60)))
        log(f"  shot #{shots}: {path.name}")
        time.sleep(interval_seconds)
    progress(1.0)
    return {"shots": shots, "directory": str(out_dir)}


# ═════════════════════════════════════════════════════════════════════════════
# 5. weather_brief
# ═════════════════════════════════════════════════════════════════════════════

@register("weather_brief",
          "Fetch weather for a city and emit a one-line brief",
          category="info",
          params={"city": "str (e.g. 'Lahore')"})
def weather_brief(city: str = "Lahore", **_ctx) -> dict:
    from actions.weather_report import weather_action
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]
    log(f"Fetching weather for {city}…")
    progress(0.3)
    result = weather_action({"city": city})
    progress(1.0)
    log(result if isinstance(result, str) else str(result))
    return {"city": city, "report": result}


# ═════════════════════════════════════════════════════════════════════════════
# 6. github_release_watch
# ═════════════════════════════════════════════════════════════════════════════

@register("github_release_watch",
          "Check a GitHub repo for new releases and download assets",
          category="web",
          params={"user": "str (e.g. 'microsoft')",
                  "repo": "str (e.g. 'vscode')",
                  "asset_filter": "str (e.g. '.exe' — leave blank for all)"})
def github_release_watch(user: str, repo: str,
                          asset_filter: str = "", **_ctx) -> dict:
    from actions.universal import github_download_latest
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    log(f"Checking {user}/{repo}…")
    progress(0.3)
    result = github_download_latest(user, repo,
                                     asset_filter=asset_filter)
    if result.get("ok"):
        log(f"Downloaded: {result['asset']} → {result['dest']}")
    else:
        log(f"No match: {result.get('error')}")
    progress(1.0)
    return result


# ═════════════════════════════════════════════════════════════════════════════
# 7. clean_temp_files
# ═════════════════════════════════════════════════════════════════════════════

@register("clean_temp_files",
          "Delete files older than N days from the system temp directory",
          category="maintenance", params={"older_than_days": "int (default: 30)"})
def clean_temp_files(older_than_days: int = 30, **_ctx) -> dict:
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    tmp = Path(os.environ.get("TEMP") or Path.home() / "AppData" / "Local" / "Temp")
    if not tmp.is_dir():
        raise FileNotFoundError(tmp)
    cutoff = time.time() - older_than_days * 86400
    log(f"Scanning {tmp} for files older than {older_than_days} days…")

    victims = []
    total_bytes = 0
    for p in tmp.rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                victims.append(p)
                total_bytes += p.stat().st_size
        except (PermissionError, OSError):
            continue
    progress(0.3)
    log(f"Found {len(victims)} old files ({total_bytes / 1e6:.2f} MB)")

    deleted = 0
    for i, p in enumerate(victims, 1):
        try:
            p.unlink()
            deleted += 1
        except (PermissionError, OSError):
            continue
        if i % 50 == 0:
            progress(0.3 + 0.6 * i / len(victims))
            log(f"  {deleted}/{i} deleted")

    progress(1.0)
    log(f"Done. Deleted {deleted} files, "
        f"freed {total_bytes / 1e6:.2f} MB")
    return {"deleted": deleted, "freed_mb": round(total_bytes / 1e6, 2),
            "directory": str(tmp)}


# ═════════════════════════════════════════════════════════════════════════════
# 8. report_large_files
# ═════════════════════════════════════════════════════════════════════════════

@register("report_large_files",
          "Find the largest N files in common folders and report them",
          category="files",
          params={"min_size_mb": "float (default: 100)",
                  "max_results": "int (default: 20)",
                  "max_scan_seconds": "int (default: 15)"})
def report_large_files(min_size_mb: float = 100,
                       max_results: int = 20,
                       max_scan_seconds: int = 15, **_ctx) -> dict:
    """Scan with a time budget so the dashboard stays responsive."""
    import time as _t
    log = _ctx["_ctx_log"]
    progress = _ctx["_ctx_progress"]

    roots = [Path.home() / "Documents",
             Path.home() / "Downloads",
             Path.home() / "Videos",
             Path.home() / "Pictures"]
    log(f"Scanning roots: {[str(r) for r in roots if r.exists()]}")
    progress(0.1)

    deadline = _t.monotonic() + max_scan_seconds
    min_bytes = int(min_size_mb * 1024 * 1024)
    found: list[tuple] = []  # (size, path)
    scanned = 0

    for r in [x for x in roots if x.exists()]:
        try:
            for p in r.rglob("*"):
                scanned += 1
                if scanned % 1000 == 0:
                    if _t.monotonic() > deadline:
                        log(f"  Time budget hit after {scanned} files "
                            f"({len(found)} candidates)")
                        break
                    progress(min(0.7, scanned / 5000))
                    log(f"  scanned {scanned} files, {len(found)} candidates")
                if not p.is_file():
                    continue
                try:
                    s = p.stat().st_size
                    if s >= min_bytes:
                        found.append((s, p))
                except (PermissionError, OSError):
                    continue
            if _t.monotonic() > deadline:
                break
        except (PermissionError, OSError):
            continue

    progress(0.85)
    log(f"Scan complete: {scanned} files inspected, "
        f"{len(found)} candidates > {min_size_mb} MB")

    found.sort(key=lambda x: x[0], reverse=True)
    progress(1.0)

    hits = found[:max_results]
    log(f"Top {len(hits)} largest files:")
    for sz, p in hits[:5]:
        log(f"  • {p.name}  ({sz / 1e6:.1f} MB)")

    return {
        "count": len(hits),
        "scanned": scanned,
        "files": [
            {"name": p.name, "path": str(p),
             "size_mb": round(sz / 1e6, 2)}
            for sz, p in hits
        ]
    }


__all__ = [
    "TEMPLATES", "list_templates", "get_template", "run_template", "register",
]
