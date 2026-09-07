"""SONIC AI — Path Resolver.

Resolves Windows known folders, normalizes paths, and handles fuzzy matching.
"""
from __future__ import annotations

import os
import re
from pathlib import Path, WindowsPath
from typing import Optional
import ctypes.wintypes


KNOWN_FOLDERS = {
    "desktop": None,
    "downloads": None,
    "documents": None,
    "pictures": None,
    "videos": None,
    "music": None,
    "appdata": None,
    "localappdata": None,
    "home": None,
}

_FOLDER_CSIDL = {
    "desktop": 0x0010,
    "downloads": 0x0037,
    "documents": 0x0005,
    "pictures": 0x0027,
    "videos": 0x000E,
    "music": 0x000D,
}


def _init_known_folders():
    try:
        user_profile = Path.home()
        KNOWN_FOLDERS["home"] = user_profile
        KNOWN_FOLDERS["desktop"] = user_profile / "Desktop"
        KNOWN_FOLDERS["downloads"] = user_profile / "Downloads"
        KNOWN_FOLDERS["documents"] = user_profile / "Documents"
        KNOWN_FOLDERS["pictures"] = user_profile / "Pictures"
        KNOWN_FOLDERS["videos"] = user_profile / "Videos"
        KNOWN_FOLDERS["music"] = user_profile / "Music"
        KNOWN_FOLDERS["appdata"] = Path(os.environ.get("APPDATA", user_profile))
        KNOWN_FOLDERS["localappdata"] = Path(os.environ.get("LOCALAPPDATA", user_profile))

        for alias in ["desktop", "downloads", "documents", "pictures", "videos", "music"]:
            if KNOWN_FOLDERS[alias].exists():
                print(f"[PATH] {alias}: {KNOWN_FOLDERS[alias]}")
    except Exception as e:
        print(f"[PATH] Known folder init failed: {e}")
        KNOWN_FOLDERS["home"] = Path.home()


_init_known_folders()


def resolve_path(user_input: str) -> Optional[Path]:
    if not user_input:
        return None

    cleaned = user_input.strip().strip('"').strip("'")
    cleaned = cleaned.replace("/", "\\")
    cleaned = re.sub(r'\\+', lambda m: '\\', cleaned)

    lower = cleaned.lower()

    for alias in ["desktop", "downloads", "documents", "pictures", "videos", "music"]:
        if lower == alias or lower == alias + "\\" or lower == alias + "/":
            if KNOWN_FOLDERS.get(alias):
                return KNOWN_FOLDERS[alias]

    for alias in ["desktop", "downloads", "documents", "pictures", "videos", "music"]:
        if lower.startswith(alias + "\\") or lower.startswith(alias + "/"):
            rest = cleaned[len(alias):].lstrip("\\/")
            if KNOWN_FOLDERS.get(alias):
                return KNOWN_FOLDERS[alias] / rest

    path = Path(cleaned)
    if path.exists():
        return path.resolve()

    if KNOWN_FOLDERS.get("home"):
        candidate = KNOWN_FOLDERS["home"] / cleaned
        if candidate.exists():
            return candidate.resolve()

    for alias in ["desktop", "downloads", "documents", "pictures", "videos"]:
        if KNOWN_FOLDERS.get(alias):
            candidate = KNOWN_FOLDERS[alias] / cleaned
            if candidate.exists():
                return candidate.resolve()

    return path


def search_files(query: str, search_dirs: Optional[list[Path]] = None, max_results: int = 10) -> list[dict]:
    results = []
    if not query:
        return results

    query_lower = query.lower()
    if search_dirs is None:
        search_dirs = []
        for alias in ["desktop", "downloads", "documents", "pictures", "videos"]:
            if KNOWN_FOLDERS.get(alias):
                search_dirs.append(KNOWN_FOLDERS[alias])

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for item in search_dir.rglob("*"):
                if len(results) >= max_results:
                    break
                if query_lower in item.name.lower():
                    item_type = "folder" if item.is_dir() else "file"
                    size = item.stat().st_size if item.is_file() else 0
                    results.append({
                        "path": str(item),
                        "name": item.name,
                        "type": item_type,
                        "size": size,
                        "parent": str(item.parent),
                        "confidence": _calc_confidence(query_lower, item.name.lower()),
                    })
        except PermissionError:
            continue

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return results


def _calc_confidence(query: str, filename: str) -> float:
    if query == filename:
        return 1.0
    if filename.startswith(query):
        return 0.9
    if query in filename:
        return 0.7
    query_words = query.split()
    if len(query_words) > 1:
        matches = sum(1 for w in query_words if w in filename)
        return 0.3 + (0.4 * matches / len(query_words))
    return 0.1


def get_known_folder(name: str) -> Optional[Path]:
    return KNOWN_FOLDERS.get(name.lower())


def normalize_path(path_str: str) -> str:
    if not path_str:
        return path_str
    cleaned = path_str.strip().strip('"').strip("'")
    cleaned = cleaned.replace("/", "\\")
    cleaned = re.sub(r'\\+', lambda m: '\\', cleaned)
    return cleaned
