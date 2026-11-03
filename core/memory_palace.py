"""SONIC AI — Memory Palace.

Persistent long-term semantic memory across sessions. SONIC remembers:
- Every conversation (with embeddings for semantic recall)
- User preferences (learned over time)
- Daily facts ("user's birthday is March 15")
- Project context ("user is working on Atherion Labs")
- Patterns (frequently asked questions, common workflows)

Backend: SQLite (file-based, persistent) + in-process TF-IDF similarity
(safe fallback when no embedding API is available).

Public API (kept stable):
    MemoryPalace(db_path="memory_palace.db")
    .remember(text, kind="fact", importance=0.5, tags=[...])
    .recall(query, top_k=5) -> list[Memory]
    .add_conversation(user_msg, assistant_msg)
    .learn_preference(key, value)
    .get_preference(key, default=None)
    .get_stats() -> dict
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


# ═════════════════════════════════════════════════════════════════════════════
# Memory record
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Memory:
    """One remembered item."""
    id: int = 0
    text: str = ""
    kind: str = "fact"            # fact|conversation|preference|pattern|project
    importance: float = 0.5
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 0
    score: float = 0.0            # set by recall()

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# MemoryPalace
# ═════════════════════════════════════════════════════════════════════════════

class MemoryPalace:
    """Persistent long-term semantic memory."""

    # Kinds of memories and how they decay (importance boost on recall)
    KIND_BOOST = {
        "preference": 0.3,
        "project":   0.2,
        "fact":      0.15,
        "pattern":   0.1,
        "conversation": 0.05,
    }

    def __init__(self, db_path: str | Path = "memory_palace.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    # ── Public ───────────────────────────────────────────────────────────────

    def remember(self, text: str, kind: str = "fact", importance: float = 0.5,
                 tags: Optional[list[str]] = None) -> Memory:
        """Store a memory. Returns the saved Memory object."""
        with self._lock:
            now = time.time()
            tags_json = json.dumps(tags or [])
            cur = self._conn().execute(
                "INSERT INTO memories (text, kind, importance, tags, created_at, "
                "last_accessed, access_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (text, kind, importance, tags_json, now, now, 0),
            )
            self._conn().commit()
            return Memory(
                id=cur.lastrowid,
                text=text,
                kind=kind,
                importance=importance,
                tags=tags or [],
                created_at=now,
                last_accessed=now,
            )

    def recall(self, query: str, top_k: int = 5,
               kind: Optional[str] = None,
               min_score: float = 0.05) -> list[Memory]:
        """Recall memories by semantic similarity to query.

        Uses TF-IDF cosine similarity as a safe offline fallback.
        """
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []
        with self._lock:
            rows = self._conn().execute(
                "SELECT id, text, kind, importance, tags, created_at, "
                "last_accessed, access_count FROM memories"
                + (" WHERE kind=?" if kind else ""),
                (kind,) if kind else (),
            ).fetchall()

            if not rows:
                return []

            # Build IDF from corpus
            df: Counter = Counter()
            tokenized_docs: list[list[str]] = []
            for row in rows:
                toks = self._tokenize(row[1])
                tokenized_docs.append(toks)
                for t in set(toks):
                    df[t] += 1
            N = len(rows)

            # Score each doc
            scored: list[Memory] = []
            for i, row in enumerate(rows):
                doc_tokens = tokenized_docs[i]
                score = self._tfidf_cosine(query_tokens, doc_tokens, df, N)
                # Boost by importance and recency
                age_hours = (time.time() - row[5]) / 3600
                recency = math.exp(-age_hours / (24 * 30))   # 30-day half-ish decay
                final = score * (0.5 + 0.5 * row[3]) * (0.6 + 0.4 * recency)
                if final < min_score:
                    continue
                mem = Memory(
                    id=row[0], text=row[1], kind=row[2], importance=row[3],
                    tags=json.loads(row[4] or "[]"),
                    created_at=row[5], last_accessed=row[6],
                    access_count=row[7], score=final,
                )
                scored.append(mem)

            scored.sort(key=lambda m: m.score, reverse=True)
            top = scored[:top_k]
            # Boost importance on access
            for m in top:
                boost = self.KIND_BOOST.get(m.kind, 0.1)
                new_imp = min(1.0, m.importance + boost)
                self._conn().execute(
                    "UPDATE memories SET last_accessed=?, access_count=access_count+1, "
                    "importance=? WHERE id=?",
                    (time.time(), new_imp, m.id),
                )
            self._conn().commit()
            return top

    def add_conversation(self, user_msg: str, assistant_msg: str) -> tuple[Memory, Memory]:
        """Store a paired conversation exchange."""
        u = self.remember(user_msg, kind="conversation", importance=0.4,
                          tags=["conversation", "user"])
        a = self.remember(assistant_msg, kind="conversation", importance=0.4,
                          tags=["conversation", "assistant"])
        return u, a

    def learn_preference(self, key: str, value: Any) -> Memory:
        """Learn a user preference (overwrites any existing preference for key)."""
        text = f"User prefers {key}: {value}"
        with self._lock:
            self._conn().execute(
                "DELETE FROM memories WHERE kind='preference' AND text LIKE ?",
                (f"User prefers {key}:%",),
            )
            self._conn().commit()
        return self.remember(text, kind="preference", importance=0.9,
                              tags=["preference", key])

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Recall a previously learned preference."""
        results = self.recall(f"preference {key}", top_k=1, kind="preference")
        if not results:
            return default
        # Extract value: "User prefers KEY: VALUE"
        m = re.match(rf"User prefers {re.escape(key)}:\s*(.+)", results[0].text)
        if m:
            raw = m.group(1).strip()
            # Try JSON decode
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return default

    def forget(self, memory_id: int) -> bool:
        with self._lock:
            cur = self._conn().execute("DELETE FROM memories WHERE id=?", (memory_id,))
            self._conn().commit()
            return cur.rowcount > 0

    def count(self, kind: Optional[str] = None) -> int:
        with self._lock:
            if kind:
                row = self._conn().execute(
                    "SELECT COUNT(*) FROM memories WHERE kind=?", (kind,)
                ).fetchone()
            else:
                row = self._conn().execute("SELECT COUNT(*) FROM memories").fetchone()
            return row[0]

    def get_stats(self) -> dict:
        with self._lock:
            total = self.count()
            by_kind = {}
            for row in self._conn().execute(
                "SELECT kind, COUNT(*) FROM memories GROUP BY kind"
            ).fetchall():
                by_kind[row[0]] = row[1]
            db_size = self._db_path.stat().st_size if self._db_path.exists() else 0
            return {
                "total": total,
                "by_kind": by_kind,
                "db_path": str(self._db_path),
                "db_size_bytes": db_size,
            }

    # ── Internals ────────────────────────────────────────────────────────────

    def _init_db(self):
        with self._lock:
            self._conn().execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    kind TEXT NOT NULL DEFAULT 'fact',
                    importance REAL NOT NULL DEFAULT 0.5,
                    tags TEXT DEFAULT '[]',
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_kind ON memories(kind)"
            )
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_mem_imp ON memories(importance)"
            )
            self._conn().commit()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self, "_db_conn") or self._db_conn is None:
            self._db_conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._db_conn.row_factory = sqlite3.Row
        return self._db_conn

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [w.lower() for w in re.findall(r"\w+", text) if len(w) > 1]

    @staticmethod
    def _tfidf_cosine(query_tokens: list[str], doc_tokens: list[str],
                      df: Counter, N: int) -> float:
        if not doc_tokens:
            return 0.0
        q_tf = Counter(query_tokens)
        d_tf = Counter(doc_tokens)
        # Build IDF
        idf = {}
        for term in set(query_tokens) | set(doc_tokens):
            df_t = df.get(term, 0)
            idf[term] = math.log((N + 1) / (1 + df_t)) + 1
        # Cosine similarity
        q_vec = {t: q_tf.get(t, 0) * idf[t] for t in idf}
        d_vec = {t: d_tf.get(t, 0) * idf[t] for t in idf}
        dot = sum(q_vec[t] * d_vec[t] for t in q_vec)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1e-9
        d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1e-9
        return dot / (q_norm * d_norm)
