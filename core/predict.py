"""SONIC AI — Predictive Intelligence.

JARVIS-style anticipation. SONIC predicts what the user is going to say or do
NEXT — and offers completions as they type.

Two components:
  1. Predictor — autocompletes partial input based on history
  2. NextActionPredictor — predicts the next likely action after a sequence

Public API:
    Predictor(history: list[str])
    .complete(partial: str) -> list[Suggestion]
    .learn(text: str)

    NextActionPredictor(db_path=...)
    .record(action_sequence: list[str])
    .predict_next(recent_actions: list[str]) -> list[(action, confidence)]
    .get_stats()
"""
from __future__ import annotations

import sqlite3
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, asdict, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


@dataclass
class Suggestion:
    """An autocompletion suggestion."""
    text: str
    confidence: float = 0.0
    frequency: int = 0
    source: str = "history"           # history|markov|levenshtein

    def to_dict(self) -> dict:
        return asdict(self)


class Predictor:
    """Autocomplete based on user history."""

    def __init__(self, max_history: int = 5000):
        self._max = max_history
        self._history: deque[str] = deque(maxlen=max_history)
        # n-gram model
        self._bigrams: Counter = Counter()
        self._trigrams: Counter = Counter()
        self._unigrams: Counter = Counter()
        self._lock = threading.Lock()

    def learn(self, text: str):
        """Record a new text (from history or user typing)."""
        text = text.strip()
        if not text or len(text) < 2:
            return
        with self._lock:
            self._history.append(text.lower())
            tokens = text.lower().split()
            self._unigrams.update(tokens)
            for i in range(len(tokens) - 1):
                self._bigrams[(tokens[i], tokens[i + 1])] += 1
            for i in range(len(tokens) - 2):
                self._trigrams[(tokens[i], tokens[i + 1], tokens[i + 2])] += 1

    def complete(self, partial: str, n: int = 5) -> list[Suggestion]:
        """Predict completions for partial input."""
        partial = partial.strip().lower()
        if not partial:
            return []
        with self._lock:
            out: list[Suggestion] = []

            # 1. Match by prefix
            seen = set()
            for item in self._history:
                if item in seen:
                    continue
                if item.startswith(partial) and item != partial:
                    seen.add(item)
                    freq = self._history.count(item)
                    out.append(Suggestion(
                        text=item, confidence=min(1.0, freq / 10.0),
                        frequency=freq, source="history",
                    ))
                    if len(out) >= n * 2:
                        break

            # 2. Markov: use last tokens to predict next
            tokens = partial.split()
            if tokens and len(tokens) >= 2:
                key = (tokens[-2], tokens[-1])
                cont = Counter()
                for (a, b, c), cnt in self._trigrams.items():
                    if a == key[0] and b == key[1]:
                        cont[c] += cnt
                if cont:
                    top_next = cont.most_common(1)[0]
                    completion = " ".join(tokens + [top_next[0]])
                    out.append(Suggestion(
                        text=completion, confidence=min(1.0, top_next[1] / 10.0),
                        frequency=top_next[1], source="markov",
                    ))

            # 3. Fuzzy match
            if len(out) < n:
                for item in self._history:
                    if item in seen or item == partial:
                        continue
                    sim = SequenceMatcher(None, partial, item).ratio()
                    if sim > 0.6:
                        out.append(Suggestion(
                            text=item, confidence=sim * 0.5,
                            frequency=0, source="levenshtein",
                        ))
                        if len(out) >= n * 2:
                            break

            out.sort(key=lambda s: (s.confidence, s.frequency), reverse=True)
            return out[:n]


# ═════════════════════════════════════════════════════════════════════════════
# NextActionPredictor — Markov chain over action sequences
# ═════════════════════════════════════════════════════════════════════════════

class NextActionPredictor:
    """Predicts the user's next action based on recent history."""

    def __init__(self, db_path: str | Path = "action_predictor.db", order: int = 3):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._order = order
        self._lock = threading.RLock()
        self._init_db()

    # ── Public ───────────────────────────────────────────────────────────────

    def record(self, action_sequence: list[str]) -> int:
        """Record an action sequence (e.g. the user's day)."""
        if not action_sequence:
            return 0
        inserted = 0
        with self._lock:
            for i in range(len(action_sequence) - 1):
                history_key = " ".join(action_sequence[max(0, i - self._order + 1):i + 1])
                next_action = action_sequence[i + 1]
                self._conn().execute(
                    "INSERT INTO transitions (history_key, next_action, ts) "
                    "VALUES (?, ?, ?)",
                    (history_key, next_action, time.time()),
                )
                inserted += 1
            self._conn().commit()
        return inserted

    def predict_next(self, recent_actions: list[str], top_k: int = 3) -> list[tuple[str, float]]:
        """Predict next actions given recent history.

        Returns list of (action_name, confidence 0..1).
        """
        with self._lock:
            history_key = " ".join(recent_actions[-self._order:])
            if not history_key:
                return []

            rows = self._conn().execute(
                "SELECT next_action, COUNT(*) as c FROM transitions "
                "WHERE history_key=? GROUP BY next_action ORDER BY c DESC LIMIT ?",
                (history_key, top_k),
            ).fetchall()
            total = sum(r[1] for r in rows) or 1
            return [(r[0], r[1] / total) for r in rows]

    def get_stats(self) -> dict:
        with self._lock:
            transitions = self._conn().execute(
                "SELECT COUNT(*) FROM transitions"
            ).fetchone()[0]
            unique_history = self._conn().execute(
                "SELECT COUNT(DISTINCT history_key) FROM transitions"
            ).fetchone()[0]
            db_size = self._db_path.stat().st_size if self._db_path.exists() else 0
            return {
                "transitions": transitions,
                "unique_history_keys": unique_history,
                "markov_order": self._order,
                "db_size_bytes": db_size,
            }

    # ── Internals ────────────────────────────────────────────────────────────

    def _init_db(self):
        with self._lock:
            self._conn().execute("""
                CREATE TABLE IF NOT EXISTS transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    history_key TEXT NOT NULL,
                    next_action TEXT NOT NULL,
                    ts REAL NOT NULL
                )
            """)
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_tr_history ON transitions(history_key)"
            )
            self._conn().commit()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self, "_db") or self._db is None:
            self._db = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._db.row_factory = sqlite3.Row
        return self._db
