"""SONIC AI — Knowledge Graph.

JARVIS-level contextual intelligence: SONIC maintains a graph of entities and
relationships (people, projects, files, places, concepts) and can answer
"Who works on Project X?" or "What files relate to Atherion Labs?" by
traversing relationships.

Built on SQLite with adjacency lists.

Public API:
    KnowledgeGraph(db_path="kg.db")
    .add_entity(name, kind, attrs={...})
    .add_relationship(src, rel, dst, attrs={...})
    .find_entities(name=..., kind=...)       → list[Entity]
    .get_relationships(entity_name)          → list[Relationship]
    .query(question_text)                    → list of relevant entities + rels
    .neighborhood(entity_name, depth=2)      → connected subgraph
    .get_stats()                             → counts
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


# ═════════════════════════════════════════════════════════════════════════════
# Records
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Entity:
    name: str
    kind: str                                # person|project|file|place|concept|tool
    attrs: dict = field(default_factory=dict)
    created_at: float = 0.0
    access_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Relationship:
    src: str
    rel: str                                 # works_on|related_to|located_in|owns|...
    dst: str
    attrs: dict = field(default_factory=dict)
    confidence: float = 1.0
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QueryResult:
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "relationships": [r.to_dict() for r in self.relationships],
            "explanation": self.explanation,
        }


# ═════════════════════════════════════════════════════════════════════════════
# KnowledgeGraph
# ═════════════════════════════════════════════════════════════════════════════

class KnowledgeGraph:
    """Entity + relationship store for contextual intelligence."""

    RELATIONSHIP_VERBS = {
        "works_on", "manages", "uses", "owns", "located_in",
        "related_to", "depends_on", "created", "remembers",
        "prefers", "knows", "speaks", "writes", "reads",
        "is_a", "part_of", "created_by", "maintained_by",
    }

    def __init__(self, db_path: str | Path = "knowledge_graph.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    # ── Public ───────────────────────────────────────────────────────────────

    def add_entity(self, name: str, kind: str, attrs: Optional[dict] = None) -> Entity:
        """Add or update an entity. If it exists, attrs are merged."""
        attrs = attrs or {}
        now = time.time()
        with self._lock:
            existing = self._get_entity(name)
            if existing:
                merged_attrs = {**existing.attrs, **attrs}
                self._conn().execute(
                    "UPDATE entities SET attrs=?, access_count=access_count+1 "
                    "WHERE name=?",
                    (json.dumps(merged_attrs), name),
                )
                self._conn().commit()
                return Entity(name=name, kind=existing.kind, attrs=merged_attrs,
                               created_at=existing.created_at,
                               access_count=existing.access_count + 1)
            self._conn().execute(
                "INSERT INTO entities (name, kind, attrs, created_at, access_count) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, kind, json.dumps(attrs), now, 0),
            )
            self._conn().commit()
            return Entity(name=name, kind=kind, attrs=dict(attrs), created_at=now)

    def add_relationship(self, src: str, rel: str, dst: str,
                          confidence: float = 1.0,
                          attrs: Optional[dict] = None) -> Relationship:
        """Add a directed relationship. Auto-creates entities if missing."""
        attrs = attrs or {}
        with self._lock:
            # Auto-create entities
            for ent_name in (src, dst):
                kind = "concept"
                if "@" in ent_name or ent_name.lower() in {"i", "you", "me"}:
                    kind = "person"
                self.add_entity(ent_name, kind)

            now = time.time()
            self._conn().execute(
                "INSERT OR REPLACE INTO relationships "
                "(src, rel, dst, attrs, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (src, rel.lower(), dst, json.dumps(attrs), confidence, now),
            )
            self._conn().commit()
            return Relationship(src=src, rel=rel.lower(), dst=dst,
                                attrs=dict(attrs), confidence=confidence,
                                created_at=now)

    def find_entities(self, name: Optional[str] = None,
                       kind: Optional[str] = None,
                       limit: int = 50) -> list[Entity]:
        """Find entities matching name (LIKE) or kind."""
        sql = "SELECT name, kind, attrs, created_at, access_count FROM entities WHERE 1=1"
        params: list = []
        if name:
            sql += " AND name LIKE ?"
            params.append(f"%{name}%")
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY access_count DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn().execute(sql, params).fetchall()
        return [Entity(name=r[0], kind=r[1], attrs=json.loads(r[2] or "{}"),
                        created_at=r[3], access_count=r[4]) for r in rows]

    def get_relationships(self, entity_name: str,
                          direction: str = "both") -> list[Relationship]:
        """Get all relationships involving an entity. direction: out|in|both."""
        with self._lock:
            if direction == "out":
                rows = self._conn().execute(
                    "SELECT src, rel, dst, attrs, confidence, created_at "
                    "FROM relationships WHERE src=?",
                    (entity_name,),
                ).fetchall()
            elif direction == "in":
                rows = self._conn().execute(
                    "SELECT src, rel, dst, attrs, confidence, created_at "
                    "FROM relationships WHERE dst=?",
                    (entity_name,),
                ).fetchall()
            else:
                rows = self._conn().execute(
                    "SELECT src, rel, dst, attrs, confidence, created_at "
                    "FROM relationships WHERE src=? OR dst=?",
                    (entity_name, entity_name),
                ).fetchall()
        return [Relationship(src=r[0], rel=r[1], dst=r[2],
                              attrs=json.loads(r[3] or "{}"),
                              confidence=r[4], created_at=r[5]) for r in rows]

    def query(self, question: str) -> QueryResult:
        """Answer a question by extracting entities from text + traversing graph."""
        with self._lock:
            # Tokenise the question and look up entities that match tokens
            tokens = re.findall(r"\w+", question)
            if not tokens:
                return QueryResult(explanation="empty question")

            relevant_entities: list[Entity] = []
            seen = set()
            for tok in tokens:
                if len(tok) < 3 or tok.lower() in {"what", "who", "where", "how", "the", "and", "for"}:
                    continue
                rows = self._conn().execute(
                    "SELECT name, kind, attrs, created_at, access_count FROM entities "
                    "WHERE name LIKE ? ORDER BY access_count DESC LIMIT 5",
                    (f"%{tok}%",),
                ).fetchall()
                for r in rows:
                    if r[0] not in seen:
                        seen.add(r[0])
                        relevant_entities.append(Entity(
                            name=r[0], kind=r[1], attrs=json.loads(r[2] or "{}"),
                            created_at=r[3], access_count=r[4],
                        ))

            # BFS from each relevant entity to its neighbors (depth=2)
            relevant_rels: list[Relationship] = []
            rel_seen = set()
            for ent in relevant_entities:
                rows = self._conn().execute(
                    "SELECT src, rel, dst, attrs, confidence, created_at "
                    "FROM relationships WHERE src=? OR dst=? LIMIT 20",
                    (ent.name, ent.name),
                ).fetchall()
                for r in rows:
                    rel_key = (r[0], r[1], r[2])
                    if rel_key not in rel_seen:
                        rel_seen.add(rel_key)
                        relevant_rels.append(Relationship(
                            src=r[0], rel=r[1], dst=r[2],
                            attrs=json.loads(r[3] or "{}"),
                            confidence=r[4], created_at=r[5],
                        ))

            explanation = self._compose_explanation(question, relevant_entities,
                                                    relevant_rels)
            return QueryResult(entities=relevant_entities,
                                relationships=relevant_rels,
                                explanation=explanation)

    def neighborhood(self, entity_name: str, depth: int = 2) -> dict:
        """BFS to find subgraph around entity."""
        with self._lock:
            visited: set[str] = set()
            current = {entity_name}
            all_ents: dict[str, Entity] = {}
            all_rels: list[Relationship] = []
            for _ in range(depth):
                if not current:
                    break
                next_level: set[str] = set()
                for name in current:
                    if name in visited:
                        continue
                    visited.add(name)
                    ent = self._get_entity(name)
                    if ent:
                        all_ents[name] = ent
                    for r in self.get_relationships(name, direction="both"):
                        all_rels.append(r)
                        if r.src not in visited:
                            next_level.add(r.src)
                        if r.dst not in visited:
                            next_level.add(r.dst)
                current = next_level
            # Dedup relationships
            seen = set()
            unique_rels = []
            for r in all_rels:
                key = (r.src, r.rel, r.dst)
                if key not in seen:
                    seen.add(key)
                    unique_rels.append(r)
            return {
                "entities": [e.to_dict() for e in all_ents.values()],
                "relationships": [r.to_dict() for r in unique_rels],
            }

    def learn_from_text(self, text: str) -> int:
        """Extract entities + relationships from free-form text heuristically.

        Patterns:
          "X is a Y"     → X (kind=Y)
          "X works on Y" → X --works_on--> Y
          "X uses Y"     → X --uses--> Y
          "X is in Y"    → X --located_in--> Y
          "X prefers Y"  → X --prefers--> Y
        """
        count = 0
        # Tokenize into sentences
        sentences = re.split(r"[.!?]\s+", text)
        patterns = [
            (r"(\w[\w\s]+?)\s+is\s+a\s+(\w+)", "is_a"),
            (r"(\w[\w\s]+?)\s+works?\s+on\s+([\w\s]+?)(?:\.|,|;|$)", "works_on"),
            (r"(\w[\w\s]+?)\s+uses?\s+([\w\s]+?)(?:\.|,|;|$)", "uses"),
            (r"(\w[\w\s]+?)\s+is\s+(?:in|at|located in)\s+([\w\s]+?)(?:\.|,|;|$)",
             "located_in"),
            (r"(\w[\w\s]+?)\s+prefers?\s+([\w\s]+?)(?:\.|,|;|$)", "prefers"),
            (r"(\w[\w\s]+?)\s+manages?\s+([\w\s]+?)(?:\.|,|;|$)", "manages"),
        ]
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            for pat, rel in patterns:
                m = re.search(pat, sent, re.IGNORECASE)
                if m:
                    src = m.group(1).strip().split()[-1]   # last word as entity
                    dst = m.group(2).strip().split()[0]    # first word of target
                    if len(src) >= 2 and len(dst) >= 2:
                        kind = "concept"
                        if rel == "is_a":
                            kind = m.group(2).strip().lower()
                        self.add_entity(src, kind)
                        self.add_relationship(src, rel, dst)
                        count += 1
        return count

    def get_stats(self) -> dict:
        with self._lock:
            ents = self._conn().execute(
                "SELECT COUNT(*) FROM entities"
            ).fetchone()[0]
            rels = self._conn().execute(
                "SELECT COUNT(*) FROM relationships"
            ).fetchone()[0]
            kinds = self._conn().execute(
                "SELECT kind, COUNT(*) FROM entities GROUP BY kind"
            ).fetchall()
            return {
                "entities": ents,
                "relationships": rels,
                "by_kind": {k: c for k, c in kinds},
                "db_size_bytes": self._db_path.stat().st_size if self._db_path.exists() else 0,
            }

    # ── Internals ────────────────────────────────────────────────────────────

    def _init_db(self):
        with self._lock:
            self._conn().execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    name TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    attrs TEXT DEFAULT '{}',
                    created_at REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            self._conn().execute("""
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src TEXT NOT NULL,
                    rel TEXT NOT NULL,
                    dst TEXT NOT NULL,
                    attrs TEXT DEFAULT '{}',
                    confidence REAL DEFAULT 1.0,
                    created_at REAL NOT NULL,
                    UNIQUE(src, rel, dst)
                )
            """)
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_src ON relationships(src)"
            )
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_kg_dst ON relationships(dst)"
            )
            self._conn().commit()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self, "_db") or self._db is None:
            self._db = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._db.row_factory = sqlite3.Row
        return self._db

    def _get_entity(self, name: str) -> Optional[Entity]:
        row = self._conn().execute(
            "SELECT name, kind, attrs, created_at, access_count "
            "FROM entities WHERE name=?",
            (name,),
        ).fetchone()
        if row is None:
            return None
        return Entity(
            name=row[0], kind=row[1],
            attrs=json.loads(row[2] or "{}"),
            created_at=row[3], access_count=row[4],
        )

    def _compose_explanation(self, question: str, entities: list[Entity],
                              rels: list[Relationship]) -> str:
        if not entities:
            return "No entities in the knowledge graph match this question."
        parts = []
        for e in entities[:5]:
            related = [r for r in rels if r.src == e.name or r.dst == e.name]
            if related:
                rel_summary = ", ".join(f"{r.rel}→{r.dst if r.src == e.name else r.src}"
                                          for r in related[:3])
                parts.append(f"{e.name} ({e.kind}): {rel_summary}")
            else:
                parts.append(f"{e.name} ({e.kind})")
        return "; ".join(parts) if parts else "Found entities but no relationships."
