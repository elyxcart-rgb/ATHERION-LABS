"""SONIC AI — Vector Memory (Semantic Recall).

A high-end semantic memory layer that uses **real embedding vectors** for
true meaning-based search, complementing the keyword/topic engine in
``memory.semantic``.

Why this is different:
    - Goes beyond TF-IDF keyword matching: "I love pizza" and "pepperoni is
      my favorite food" will be recalled together because the embeddings are
      close in vector space.
    - Uses Google's ``text-embedding-004`` model (768-dim) via Gemini.
    - Persists vectors in SQLite as packed float32 blobs — no extra
      infrastructure (no FAISS, no Chroma).
    - Falls back to a **hash-based pseudo-embedding** when the API is
      unavailable, so the system never breaks offline.

Public surface (stable, opt-in):
    - ``VectorMemory``            — main class
    - ``MemoryItem``              — dataclass for stored items
    - ``SearchResult``            — dataclass for search hits
    - ``get_vector_memory()``     — singleton accessor (mirrors ``memory_manager``)

Zero-touch design:
    - No existing file is modified.
    - Existing ``memory/*`` modules keep their own behaviour.
    - ``memory_manager`` can opt into vector recall by calling
      ``vm.search(...)`` alongside its own retrieval — fully additive.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import struct
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("VECTOR_MEMORY")

_DB_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "memory"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "vector_store.db"
_EMBED_DIM = 768
_EMBED_MODEL = "text-embedding-004"


# ═════════════════════════════════════════════════════════════════════════════
# Data classes
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class MemoryItem:
    """A single memory stored in the vector store."""
    id: str
    text: str
    kind: str = "fact"            # fact | preference | event | conversation | task
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5       # 0.0–1.0
    created_at: float = field(default_factory=time.time)
    source: str = "user"          # user | system | inferred
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResult:
    """A hit returned by ``VectorMemory.search``."""
    item: MemoryItem
    score: float                  # cosine similarity, 0.0–1.0
    rank: int = 0

    def to_dict(self) -> dict:
        return {"score": self.score, "rank": self.rank, **self.item.to_dict()}


# ═════════════════════════════════════════════════════════════════════════════
# Embedding backends
# ═════════════════════════════════════════════════════════════════════════════

class _EmbeddingBackend:
    """Abstract embedding source."""

    def embed(self, texts: list[str], task: str) -> list[list[float]]:
        raise NotImplementedError

    @property
    def name(self) -> str:
        return "abstract"

    @property
    def available(self) -> bool:
        return False


class _GeminiBackend(_EmbeddingBackend):
    """Real embeddings via Gemini ``text-embedding-004``."""

    def __init__(self):
        self._client = None
        self._warned = False

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        try:
            import google.generativeai as genai  # type: ignore
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                # Try loading from the project's config manager if present.
                try:
                    from memory.config_manager import load_api_keys
                    keys = load_api_keys() or {}
                    api_key = keys.get("gemini_api_key")
                except Exception:
                    pass
            if not api_key:
                raise RuntimeError("No Gemini API key configured")
            genai.configure(api_key=api_key)
            self._client = genai
            return self._client
        except Exception as e:
            if not self._warned:
                logger.debug(f"Gemini embeddings unavailable: {e}")
                self._warned = True
            return None

    @property
    def name(self) -> str:
        return f"gemini:{_EMBED_MODEL}"

    @property
    def available(self) -> bool:
        return self._ensure_client() is not None

    def embed(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        client = self._ensure_client()
        if client is None:
            raise RuntimeError("Gemini backend unavailable")
        results = []
        for text in texts:
            r = client.embed_content(
                model=f"models/{_EMBED_MODEL}",
                content=text,
                task_type=task,
            )
            emb = r.get("embedding") if isinstance(r, dict) else getattr(r, "embedding", None)
            if emb is None:
                raise RuntimeError("Embedding missing from Gemini response")
            results.append(list(emb["values"]) if isinstance(emb, dict) else list(emb))
        return results


class _HashBackend(_EmbeddingBackend):
    """Offline pseudo-embedding — deterministic, no API required.

    Uses 8-gram token hashing projected into 768-dim. Quality is lower than
    real embeddings but preserves the *same interface* so the rest of the
    pipeline doesn't break offline.
    """

    def __init__(self, dim: int = _EMBED_DIM):
        self._dim = dim

    @property
    def name(self) -> str:
        return f"hash:{self._dim}"

    @property
    def available(self) -> bool:
        return True

    def embed(self, texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
        return [_hash_embed(t, self._dim) for t in texts]


def _hash_embed(text: str, dim: int) -> list[float]:
    """Feature-hashing projector with sublinear TF weighting."""
    tokens = (text or "").lower().split()
    if not tokens:
        return [0.0] * dim

    vec = [0.0] * dim
    counts: dict[int, int] = {}
    for tok in tokens:
        h = hashlib.md5(tok.encode("utf-8")).digest()
        idx = struct.unpack("<H", h[:2])[0] % dim
        sign = 1.0 if (h[2] & 1) else -1.0
        counts[idx] = counts.get(idx, 0) + 1
        vec[idx] += sign

    # Sublinear TF
    for i, c in counts.items():
        vec[i] *= 1.0 + math.log(c)

    # L2 normalise so cosine = dot
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity for two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ═════════════════════════════════════════════════════════════════════════════
# Storage
# ═════════════════════════════════════════════════════════════════════════════

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))


_SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors (
    id          TEXT PRIMARY KEY,
    text        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    tags        TEXT NOT NULL,
    importance  REAL NOT NULL,
    created_at  REAL NOT NULL,
    source      TEXT NOT NULL,
    metadata    TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    backend     TEXT NOT NULL,
    dim         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vectors_kind     ON vectors(kind);
CREATE INDEX IF NOT EXISTS idx_vectors_created  ON vectors(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_vectors_importance ON vectors(importance DESC);
"""


# ═════════════════════════════════════════════════════════════════════════════
# VectorMemory
# ═════════════════════════════════════════════════════════════════════════════

class VectorMemory:
    """High-end semantic memory backed by Gemini embeddings + SQLite vectors."""

    def __init__(
        self,
        backend: Optional[_EmbeddingBackend] = None,
        db_path: Optional[Path] = None,
        auto_pick_backend: bool = True,
    ):
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        if backend is not None:
            self._backend = backend
        elif auto_pick_backend:
            gem = _GeminiBackend()
            self._backend = gem if gem.available else _HashBackend()
        else:
            self._backend = _HashBackend()

        logger.info(f"VectorMemory ready — backend={self._backend.name}, db={self.db_path}")

    # ── Backend helpers ──────────────────────────────────────────────────

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def is_real_embeddings(self) -> bool:
        """True when using actual neural embeddings (not the offline hash fallback)."""
        return self._backend.name.startswith("gemini:")

    def switch_backend(self, backend: _EmbeddingBackend, reindex: bool = False):
        """Swap the embedding backend. Optionally re-embed every stored item."""
        old_backend = self._backend
        self._backend = backend
        logger.info(f"Switched backend: {old_backend.name} -> {backend.name}")
        if reindex and old_backend.name != backend.name:
            self._reindex()

    def _reindex(self):
        """Re-embed everything using the current backend."""
        conn = self._connect() if False else self._conn  # we already have a connection
        rows = conn.execute("SELECT id, text FROM vectors").fetchall()
        if not rows:
            return
        texts = [r["text"] for r in rows]
        ids = [r["id"] for r in rows]
        try:
            embs = self._backend.embed(texts, task="RETRIEVAL_DOCUMENT")
        except Exception as e:
            logger.warning(f"Reindex failed: {e}")
            return
        for mid, emb in zip(ids, embs):
            conn.execute(
                "UPDATE vectors SET embedding=?, backend=?, dim=? WHERE id=?",
                (_pack(emb), self._backend.name, len(emb), mid),
            )
        conn.commit()
        logger.info(f"Reindexed {len(ids)} items with {self._backend.name}")

    # ── Write API ────────────────────────────────────────────────────────

    def add(self, item: MemoryItem | str, tags: Optional[list[str]] = None,
            kind: str = "fact", importance: float = 0.5,
            metadata: Optional[dict] = None) -> str:
        """Add or update a memory. Returns the item id."""
        if isinstance(item, str):
            item = MemoryItem(
                id=_make_id(item),
                text=item,
                tags=list(tags or []),
                kind=kind,
                importance=importance,
                metadata=dict(metadata or {}),
            )

        # If already present, refresh embedding only when text changed.
        existing = self._conn.execute(
            "SELECT text, backend, embedding FROM vectors WHERE id=?",
            (item.id,),
        ).fetchone()

        try:
            emb = self._backend.embed([item.text], task="RETRIEVAL_DOCUMENT")[0]
        except Exception as e:
            logger.warning(f"Embedding failed, falling back to hash: {e}")
            emb = _hash_embed(item.text, _EMBED_DIM)

        if existing and existing["text"] == item.text and existing["backend"] == self._backend.name:
            return item.id

        self._conn.execute(
            """INSERT OR REPLACE INTO vectors
               (id, text, kind, tags, importance, created_at, source, metadata,
                embedding, backend, dim)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.id, item.text, item.kind,
                json.dumps(item.tags, ensure_ascii=False),
                item.importance, item.created_at, item.source,
                json.dumps(item.metadata, ensure_ascii=False),
                _pack(emb), self._backend.name, len(emb),
            ),
        )
        self._conn.commit()
        return item.id

    def add_many(self, texts: Iterable[str], **kwargs) -> list[str]:
        """Batched add — much faster for bulk imports (single API call)."""
        texts = list(texts)
        if not texts:
            return []
        try:
            embs = self._backend.embed(texts, task="RETRIEVAL_DOCUMENT")
        except Exception as e:
            logger.warning(f"Batched embedding failed, using hash fallback: {e}")
            embs = [_hash_embed(t, _EMBED_DIM) for t in texts]

        ids = []
        now = time.time()
        for text, emb in zip(texts, embs):
            mid = _make_id(text)
            ids.append(mid)
            self._conn.execute(
                """INSERT OR REPLACE INTO vectors
                   (id, text, kind, tags, importance, created_at, source, metadata,
                    embedding, backend, dim)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mid, text, kwargs.get("kind", "fact"),
                    json.dumps(kwargs.get("tags", []), ensure_ascii=False),
                    kwargs.get("importance", 0.5),
                    now, kwargs.get("source", "user"),
                    json.dumps(kwargs.get("metadata", {}), ensure_ascii=False),
                    _pack(emb), self._backend.name, len(emb),
                ),
            )
        self._conn.commit()
        return ids

    def forget(self, memory_id: str) -> bool:
        """Remove a memory by id. Returns True if anything was deleted."""
        cur = self._conn.execute("DELETE FROM vectors WHERE id=?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def forget_by_text(self, text: str) -> int:
        """Remove all memories whose text contains ``text``. Returns count."""
        cur = self._conn.execute("DELETE FROM vectors WHERE text LIKE ?", (f"%{text}%",))
        self._conn.commit()
        return cur.rowcount

    # ── Read API ─────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.35,
        kind: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Semantic search ranked by cosine similarity."""
        if not query.strip():
            return []

        try:
            q_emb = self._backend.embed([query], task="RETRIEVAL_QUERY")[0]
        except Exception as e:
            logger.warning(f"Query embedding failed, using hash fallback: {e}")
            q_emb = _hash_embed(query, _EMBED_DIM)

        sql = "SELECT id, text, kind, tags, importance, created_at, source, metadata, embedding, dim FROM vectors"
        params: list = []
        clauses: list[str] = []
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if tags:
            for t in tags:
                clauses.append("tags LIKE ?")
                params.append(f'%"{t}"%')
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)

        rows = self._conn.execute(sql, params).fetchall()
        if not rows:
            return []

        scored: list[SearchResult] = []
        for r in rows:
            v = _unpack(r["embedding"])
            score = _cosine(q_emb, v)
            if score < min_score:
                continue
            item = MemoryItem(
                id=r["id"],
                text=r["text"],
                kind=r["kind"],
                tags=json.loads(r["tags"]),
                importance=r["importance"],
                created_at=r["created_at"],
                source=r["source"],
                metadata=json.loads(r["metadata"]),
            )
            scored.append(SearchResult(item=item, score=score))

        scored.sort(key=lambda x: (x.score, x.item.importance), reverse=True)
        for i, hit in enumerate(scored[:k]):
            hit.rank = i + 1
        return scored[:k]

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        row = self._conn.execute(
            "SELECT id, text, kind, tags, importance, created_at, source, metadata "
            "FROM vectors WHERE id=?",
            (memory_id,),
        ).fetchone()
        if not row:
            return None
        return MemoryItem(
            id=row["id"], text=row["text"], kind=row["kind"],
            tags=json.loads(row["tags"]), importance=row["importance"],
            created_at=row["created_at"], source=row["source"],
            metadata=json.loads(row["metadata"]),
        )

    def list_recent(self, limit: int = 20, kind: Optional[str] = None) -> list[MemoryItem]:
        sql = "SELECT id, text, kind, tags, importance, created_at, source, metadata FROM vectors"
        params: list = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [
            MemoryItem(
                id=r["id"], text=r["text"], kind=r["kind"],
                tags=json.loads(r["tags"]), importance=r["importance"],
                created_at=r["created_at"], source=r["source"],
                metadata=json.loads(r["metadata"]),
            )
            for r in self._conn.execute(sql, params).fetchall()
        ]

    # ── Maintenance ──────────────────────────────────────────────────────

    def stats(self) -> dict:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n, AVG(importance) AS avg_imp, "
            "MIN(created_at) AS oldest, MAX(created_at) AS newest "
            "FROM vectors"
        ).fetchone()
        by_kind = {
            k["kind"]: k["n"]
            for k in self._conn.execute(
                "SELECT kind, COUNT(*) AS n FROM vectors GROUP BY kind"
            ).fetchall()
        }
        return {
            "backend": self.backend_name,
            "real_embeddings": self.is_real_embeddings(),
            "count": row["n"] or 0,
            "avg_importance": round(row["avg_imp"] or 0.0, 3),
            "oldest": row["oldest"],
            "newest": row["newest"],
            "by_kind": by_kind,
        }

    def prune(self, max_age_days: int = 180, min_importance: float = 0.2) -> int:
        """Remove stale, low-importance memories. Returns count deleted."""
        cutoff = time.time() - (max_age_days * 86400)
        cur = self._conn.execute(
            "DELETE FROM vectors WHERE created_at < ? AND importance < ?",
            (cutoff, min_importance),
        )
        self._conn.commit()
        return cur.rowcount

    def clear(self) -> int:
        """Drop ALL stored memories. Returns count deleted. Use with care."""
        cur = self._conn.execute("DELETE FROM vectors")
        self._conn.commit()
        return cur.rowcount

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def _make_id(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]


# ═════════════════════════════════════════════════════════════════════════════
# Singleton accessor (mirrors memory.memory_manager pattern)
# ═════════════════════════════════════════════════════════════════════════════

_INSTANCE: Optional[VectorMemory] = None


def get_vector_memory() -> VectorMemory:
    """Return the process-wide VectorMemory instance."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = VectorMemory()
    return _INSTANCE


__all__ = [
    "VectorMemory", "MemoryItem", "SearchResult",
    "get_vector_memory",
    "_GeminiBackend", "_HashBackend",  # exposed for testing / swapping
]
