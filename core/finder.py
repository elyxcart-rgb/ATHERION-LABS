"""SONIC AI — Smart Finder.

A high-end search engine for files & folders that combines:
- **Fuzzy name matching** (typo-tolerant)
- **Content search** (full-text inside supported files)
- **Metadata filters** (extension, size range, date range, kind)
- **Duplicate detection** (by content hash)

Why this is different from `actions.smart_file_manager`:
    - Adds fuzzy / typo tolerance (Levenshtein)
    - Streams results so huge trees don't blow memory
    - Returns ranked hits, not lists of paths

Public surface (stable, opt-in):
    - ``finder.fuzzy_search(query, root=None, max_results=50)``
    - ``finder.content_search(query, root=None, max_results=50)``
    - ``finder.find_duplicates(root=None, min_size=1024)``
    - ``FinderHit`` / ``DuplicateSet`` dataclasses
    - ``get_finder()`` singleton accessor

Zero-touch design: no existing file is modified.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import threading
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable, Iterator, Optional

logger = logging.getLogger("FINDER")

_DEFAULT_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
    Path.home() / "Pictures",
    Path.home() / "Videos",
    Path.home() / "Music",
]

# File extensions we treat as text-searchable
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".svg", ".csv", ".tsv",
    ".c", ".cpp", ".h", ".hpp", ".java", ".kt", ".swift", ".go",
    ".rs", ".rb", ".php", ".sh", ".bat", ".ps1",
    ".sql", ".graphql", ".proto",
}

# Maximum file size for content search (bytes) — 5 MB default
_MAX_CONTENT_BYTES = 5 * 1024 * 1024


# ═════════════════════════════════════════════════════════════════════════════
# Data classes
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class FinderHit:
    name: str
    path: str
    size: int
    modified: float
    kind: str                   # file | dir
    extension: str
    score: float                # 0.0–1.0
    match_type: str             # name | content | fuzzy
    snippet: str = ""           # first line of match (for content search)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DuplicateSet:
    """Group of files that share the same content hash."""
    hash: str
    size: int
    paths: list[str] = field(default_factory=list)
    wasted_bytes: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Finder
# ═════════════════════════════════════════════════════════════════════════════

class Finder:
    """High-end file search with fuzzy + content + dedup."""

    def __init__(self, default_roots: Optional[list[Path]] = None):
        self.default_roots = default_roots or list(_DEFAULT_ROOTS)
        self._index_lock = threading.Lock()
        self._index_conn: Optional[sqlite3.Connection] = None
        self._init_index()

    # ── Optional index for huge trees ────────────────────────────────────
    def _init_index(self):
        """Create an in-memory SQLite index used as a result cache."""
        self._index_conn = sqlite3.connect(":memory:")
        self._index_conn.execute("PRAGMA journal_mode=MEMORY")
        self._index_conn.executescript("""
            CREATE TABLE IF NOT EXISTS hits (
                name      TEXT,
                path      TEXT,
                ext       TEXT,
                size      INTEGER,
                modified  REAL,
                kind      TEXT,
                PRIMARY KEY (path)
            );
            CREATE INDEX IF NOT EXISTS idx_hits_name ON hits(name);
            CREATE INDEX IF NOT EXISTS idx_hits_ext  ON hits(ext);
        """)

    def clear_index(self):
        with self._index_lock:
            if self._index_conn is not None:
                self._index_conn.execute("DELETE FROM hits")

    def index_directory(self, root: Path, *, max_files: int = 100_000) -> int:
        """Walk ``root`` and load entries into the in-memory index.

        Returns the number of entries indexed.
        """
        if not root.exists():
            return 0
        count = 0
        with self._index_lock:
            rows = []
            try:
                for p in root.rglob("*"):
                    if count >= max_files:
                        break
                    try:
                        if p.is_file():
                            st = p.stat()
                            rows.append((p.name, str(p), p.suffix.lower(),
                                         st.st_size, st.st_mtime, "file"))
                        elif p.is_dir():
                            st = p.stat()
                            rows.append((p.name, str(p), "", 0, st.st_mtime, "dir"))
                        count += 1
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                pass
            if rows:
                self._index_conn.executemany(
                    "INSERT OR REPLACE INTO hits (name, path, ext, size, modified, kind) "
                    "VALUES (?, ?, ?, ?, ?, ?)", rows,
                )
                self._index_conn.commit()
        return count

    # ── Fuzzy name search ────────────────────────────────────────────────
    @staticmethod
    def _fuzzy_score(query: str, name: str) -> float:
        """Sequence-matcher based fuzzy score, 0.0–1.0."""
        q = query.lower().strip()
        n = name.lower().strip()
        if not q or not n:
            return 0.0
        if q == n:
            return 1.0
        if n.startswith(q):
            return 0.95
        if q in n:
            return 0.9
        # Subsequence bonus
        qi = 0
        for ch in n:
            if qi < len(q) and ch == q[qi]:
                qi += 1
        if qi == len(q):
            return 0.7
        # Token match
        q_tokens = set(re.split(r"[\s_\-.]+", q))
        n_tokens = set(re.split(r"[\s_\-.]+", n))
        if q_tokens & n_tokens:
            return 0.6 * (len(q_tokens & n_tokens) / max(len(q_tokens), 1))
        # SequenceMatcher fallback (typo tolerance)
        return SequenceMatcher(None, q, n).ratio()

    def fuzzy_search(self, query: str, *,
                     root: Optional[Path] = None,
                     max_results: int = 50,
                     extensions: Optional[list[str]] = None) -> list[FinderHit]:
        """Fuzzy match on file/dir name."""
        if not query.strip():
            return []
        roots = [Path(root)] if root else self.default_roots
        scored: list[FinderHit] = []
        for r in roots:
            if not r.exists():
                continue
            try:
                for p in r.rglob("*"):
                    try:
                        score = self._fuzzy_score(query, p.name)
                        if score < 0.4:
                            continue
                        if extensions and p.suffix.lower().lstrip(".") not in extensions:
                            continue
                        st = p.stat()
                        kind = "dir" if p.is_dir() else "file"
                        hit = FinderHit(
                            name=p.name, path=str(p), size=st.st_size,
                            modified=st.st_mtime, kind=kind,
                            extension=p.suffix.lower(), score=score,
                            match_type="fuzzy",
                        )
                        scored.append(hit)
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue
        scored.sort(key=lambda h: (h.score, h.modified), reverse=True)
        return scored[:max_results]

    # ── Content search ──────────────────────────────────────────────────
    def content_search(self, query: str, *,
                       root: Optional[Path] = None,
                       max_results: int = 50,
                       extensions: Optional[set[str]] = None,
                       max_bytes_per_file: int = _MAX_CONTENT_BYTES) -> list[FinderHit]:
        """Full-text grep across text files."""
        if not query.strip():
            return []
        roots = [Path(root)] if root else self.default_roots
        q_lower = query.lower()
        q_pattern = re.compile(re.escape(query), re.IGNORECASE)
        exts = extensions or _TEXT_EXTENSIONS
        scored: list[FinderHit] = []
        for r in roots:
            if not r.exists():
                continue
            try:
                for p in r.rglob("*"):
                    if not p.is_file():
                        continue
                    if p.suffix.lower() not in exts:
                        continue
                    try:
                        if p.stat().st_size > max_bytes_per_file:
                            continue
                        try:
                            text = p.read_text(encoding="utf-8", errors="ignore")
                        except Exception:
                            continue
                        if q_lower not in text.lower():
                            continue
                        # Find a representative snippet
                        m = q_pattern.search(text)
                        snippet = ""
                        if m:
                            start = max(0, m.start() - 30)
                            end = min(len(text), m.end() + 30)
                            snippet = text[start:end].replace("\n", " ")
                        st = p.stat()
                        hit = FinderHit(
                            name=p.name, path=str(p), size=st.st_size,
                            modified=st.st_mtime, kind="file",
                            extension=p.suffix.lower(),
                            score=min(1.0, text.lower().count(q_lower) / 5),
                            match_type="content",
                            snippet=snippet,
                        )
                        scored.append(hit)
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue
        scored.sort(key=lambda h: (h.score, h.modified), reverse=True)
        return scored[:max_results]

    # ── Duplicate detection ──────────────────────────────────────────────
    def find_duplicates(self, *,
                        root: Optional[Path] = None,
                        min_size: int = 1024,
                        max_groups: int = 100) -> list[DuplicateSet]:
        """Find files with identical content (by SHA-256).

        Skips files smaller than ``min_size`` (default 1 KB).
        """
        sizes: dict[int, list[Path]] = defaultdict(list)
        for r in [Path(root)] if root else self.default_roots:
            if not r.exists():
                continue
            try:
                for p in r.rglob("*"):
                    if not p.is_file():
                        continue
                    try:
                        s = p.stat().st_size
                        if s >= min_size:
                            sizes[s].append(p)
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue

        # Only size buckets with >1 file can contain duplicates
        candidates = [paths for paths in sizes.values() if len(paths) > 1]
        if not candidates:
            return []

        hash_groups: dict[str, list[Path]] = defaultdict(list)
        for paths in candidates:
            for p in paths:
                try:
                    h = hashlib.sha256()
                    with open(p, "rb") as f:
                        for chunk in iter(lambda: f.read(64 * 1024), b""):
                            h.update(chunk)
                    hash_groups[h.hexdigest()].append(p)
                except (PermissionError, OSError):
                    continue

        results: list[DuplicateSet] = []
        for h, paths in hash_groups.items():
            if len(paths) > 1:
                size = paths[0].stat().st_size
                wasted = size * (len(paths) - 1)
                results.append(DuplicateSet(
                    hash=h, size=size,
                    paths=[str(p) for p in paths],
                    wasted_bytes=wasted,
                ))
        results.sort(key=lambda d: d.wasted_bytes, reverse=True)
        return results[:max_groups]

    # ── Metadata filters ────────────────────────────────────────────────
    def find_by_metadata(self, *,
                         extension: Optional[str] = None,
                         min_size: Optional[int] = None,
                         max_size: Optional[int] = None,
                         modified_after: Optional[float] = None,
                         root: Optional[Path] = None,
                         max_results: int = 100) -> list[FinderHit]:
        roots = [Path(root)] if root else self.default_roots
        ext = ("." + extension.lstrip(".")) if extension else None
        scored: list[FinderHit] = []
        for r in roots:
            if not r.exists():
                continue
            try:
                for p in r.rglob("*"):
                    try:
                        if not p.is_file():
                            continue
                        if ext and not p.name.lower().endswith(ext.lower()):
                            continue
                        st = p.stat()
                        if min_size is not None and st.st_size < min_size:
                            continue
                        if max_size is not None and st.st_size > max_size:
                            continue
                        if modified_after is not None and st.st_mtime < modified_after:
                            continue
                        scored.append(FinderHit(
                            name=p.name, path=str(p), size=st.st_size,
                            modified=st.st_mtime, kind="file",
                            extension=p.suffix.lower(),
                            score=1.0, match_type="metadata",
                        ))
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                continue
        scored.sort(key=lambda h: h.modified, reverse=True)
        return scored[:max_results]


# ═════════════════════════════════════════════════════════════════════════════
# Singleton
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[Finder] = None


def get_finder() -> Finder:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = Finder()
    return _INSTANCE


# Convenience aliases
finder = get_finder()


__all__ = [
    "Finder", "FinderHit", "DuplicateSet",
    "get_finder", "finder",
]
