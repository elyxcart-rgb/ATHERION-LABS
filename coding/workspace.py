from __future__ import annotations

import os
import threading
from pathlib import Path


class WorkspaceManager:
    _lock = threading.Lock()
    _active_workspaces: dict[str, str] = {}

    @classmethod
    def resolve_project_root(cls, workspace: str | None = None) -> str:
        if workspace and os.path.isdir(workspace):
            return str(Path(workspace).resolve())
        cwd = os.getcwd()
        markers = (".git", "pyproject.toml", "requirements.txt",
                    "package.json", "setup.py", "Cargo.toml")
        d = Path(cwd)
        for _ in range(5):
            if any((d / m).exists() for m in markers):
                return str(d.resolve())
            if d.parent == d:
                break
            d = d.parent
        return str(Path(cwd).resolve())

    @classmethod
    def validate_workspace(cls, path: str) -> bool:
        p = Path(path)
        if not p.exists() or not p.is_dir():
            return False
        blocked = ("C:\\Windows", "C:\\System", "C:\\Program Files",
                    "/usr", "/bin", "/etc", "/System")
        rp = str(p.resolve()).lower()
        return not any(rp.startswith(b.lower()) for b in blocked)

    @classmethod
    def acquire_workspace(cls, task_id: str, workspace: str) -> bool:
        with cls._lock:
            owner = cls._active_workspaces.get(workspace)
            if owner is None or owner == task_id:
                cls._active_workspaces[workspace] = task_id
                return True
            return False

    @classmethod
    def release_workspace(cls, task_id: str, workspace: str) -> None:
        with cls._lock:
            if cls._active_workspaces.get(workspace) == task_id:
                del cls._active_workspaces[workspace]

    @classmethod
    def gather_context(cls, project_root: str, request: str) -> list[str]:
        root = Path(project_root)
        keywords = request.lower().split()
        candidates: list[tuple[float, str]] = []
        skip = {"__pycache__", ".git", "node_modules", ".venv",
                "venv", "env", ".tox", ".mypy_cache", "dist", "build"}
        exts = {".py", ".js", ".ts", ".json", ".toml", ".yaml",
                ".yml", ".md", ".txt", ".cfg", ".ini", ".sh"}
        for f in root.rglob("*"):
            if f.is_file() and f.suffix in exts:
                if any(s in f.parts for s in skip):
                    continue
                rel = str(f.relative_to(root))
                score = 0.0
                fl = f.name.lower()
                rl = rel.lower()
                for kw in keywords:
                    if kw in fl:
                        score += 3.0
                    if kw in rl:
                        score += 1.0
                if f.name in ("main.py", "app.py", "index.js",
                              "index.ts", "server.py", "config.py"):
                    score += 0.5
                if score > 0:
                    candidates.append((score, rel))
        candidates.sort(key=lambda x: -x[0])
        return [c[1] for c in candidates[:15]]

    @classmethod
    def get_project_info(cls, project_root: str) -> dict:
        root = Path(project_root)
        info: dict = {"root": str(root), "files": 0, "languages": set()}
        for f in root.rglob("*"):
            if f.is_file():
                info["files"] += 1
                if f.suffix:
                    info["languages"].add(f.suffix)
        info["languages"] = sorted(info["languages"])
        return info
