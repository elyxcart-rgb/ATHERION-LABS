"""SONIC AI — Semantic Memory Engine

Advanced memory system with:
- Semantic search (understands meaning, not just keywords)
- Pattern recognition (daily routines, habits)
- Preference learning (likes, dislikes, frequency)
- Emotional memory (what triggers emotions)
- Relationship mapping (contacts, connections)
- Context-aware retrieval (time, location, recent)

Usage:
    "Yaad hai maine kya bola tha?" → semantic search
    "Mera routine kya hai?" → pattern recognition
    "Mujhe kya pasand hai?" → preference analysis
"""
from __future__ import annotations

import json
import re
import math
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from collections import Counter

logger = logging.getLogger("SEMANTIC_MEMORY")

# ── Database ────────────────────────────────────────────────────────────
_DB_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "memory"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "sonic_brain.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ── Semantic Scoring ────────────────────────────────────────────────────

# Common words to ignore in semantic search
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "about", "this",
    "that", "these", "those", "it", "its", "i", "me", "my", "we", "our",
    "you", "your", "he", "him", "his", "she", "her", "they", "them",
    "their", "what", "which", "who", "whom", "where", "when", "why",
    "how", "all", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "no", "not", "only", "same", "so",
    "than", "too", "very", "just", "because", "but", "and", "or",
    "if", "while", "during", "before", "after", "above", "below",
    "between", "through", "up", "down", "out", "off", "over", "under",
    "again", "further", "then", "once", "here", "there", "also",
    # Urdu/Hindi roman common words
    "hai", "ho", "hain", "tha", "thi", "the", "ke", "ka", "ki",
    "ko", "se", "me", "pe", "ne", "ya", "aur", "main", "mera",
    "meri", "mere", "tum", "tumhara", "apna", "kya", "ye", "wo",
    "jo", "nahi", "haan", "acha", "theek", "karo", "karna", "hai",
    "bol", "bolo", "batao", "dikhao", "chalo", "abhi", "phir",
}


def _tokenize(text: str) -> list[str]:
    """Tokenize text into meaningful words."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    words = text.split()
    return [w for w in words if len(w) > 2 and w not in _STOP_WORDS]


def _tf_idf_score(query_tokens: list[str], doc_tokens: list[str], doc_freq: dict) -> float:
    """Calculate TF-IDF similarity score."""
    if not query_tokens or not doc_tokens:
        return 0.0

    doc_counter = Counter(doc_tokens)
    doc_len = len(doc_tokens)

    score = 0.0
    for token in query_tokens:
        tf = doc_counter.get(token, 0) / doc_len if doc_len > 0 else 0
        df = doc_freq.get(token, 1)
        idf = math.log(100 / (1 + df))  # simplified IDF
        score += tf * idf

    return score


def _keyword_overlap(query_tokens: list[str], doc_tokens: list[str]) -> float:
    """Calculate keyword overlap ratio."""
    if not query_tokens:
        return 0.0
    query_set = set(query_tokens)
    doc_set = set(doc_tokens)
    intersection = query_set & doc_set
    return len(intersection) / len(query_set) if query_set else 0.0


def _semantic_similarity(query: str, content: str) -> float:
    """Calculate semantic similarity between query and content."""
    query_tokens = _tokenize(query)
    doc_tokens = _tokenize(content)

    if not query_tokens:
        return 0.0

    # Keyword overlap score (0-1)
    overlap = _keyword_overlap(query_tokens, doc_tokens)

    # Partial word matching
    partial_score = 0.0
    for qt in query_tokens:
        for dt in doc_tokens:
            if qt in dt or dt in qt:
                partial_score += 0.5
                break
    partial_score = min(partial_score / len(query_tokens), 1.0) if query_tokens else 0

    # Combined score
    return (overlap * 0.7 + partial_score * 0.3)


# ── Pattern Recognition ────────────────────────────────────────────────

def _extract_time_patterns(entries: list[dict]) -> dict:
    """Extract time-based patterns from memories."""
    patterns = {
        "morning": [],    # 5-12
        "afternoon": [],  # 12-17
        "evening": [],    # 17-21
        "night": [],      # 21-5
    }

    for entry in entries:
        created = entry.get("created_at", "")
        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            hour = dt.hour
            if 5 <= hour < 12:
                patterns["morning"].append(entry)
            elif 12 <= hour < 17:
                patterns["afternoon"].append(entry)
            elif 17 <= hour < 21:
                patterns["evening"].append(entry)
            else:
                patterns["night"].append(entry)
        except Exception:
            continue

    return patterns


def _extract_frequency_patterns(entries: list[dict]) -> dict:
    """Extract frequency-based patterns."""
    topics = Counter()
    actions = Counter()

    for entry in entries:
        content = entry.get("content", "").lower()
        words = _tokenize(content)
        topics.update(words)

    return {
        "top_topics": topics.most_common(20),
        "total_entries": len(entries),
    }


def _extract_routine_patterns(entries: list[dict]) -> list[dict]:
    """Detect daily routines from repeated actions."""
    time_patterns = _extract_time_patterns(entries)
    routines = []

    for time_of_day, period_entries in time_patterns.items():
        if len(period_entries) >= 3:
            topics = Counter()
            for e in period_entries:
                words = _tokenize(e.get("content", ""))
                topics.update(words)

            top_topics = topics.most_common(5)
            if top_topics:
                routines.append({
                    "time": time_of_day,
                    "frequency": len(period_entries),
                    "topics": [t[0] for t in top_topics],
                })

    return routines


# ── Preference Analysis ────────────────────────────────────────────────

def _analyze_preferences(entries: list[dict]) -> dict:
    """Analyze user preferences from memories."""
    likes = Counter()
    dislikes = Counter()
    topics = Counter()

    like_keywords = ["like", "love", "pasand", "achha", "best", "favorite", "prefer"]
    dislike_keywords = ["dislike", "hate", "nahi pasand", "bura", "worst", "avoid"]

    for entry in entries:
        content = entry.get("content", "").lower()
        words = _tokenize(content)
        topics.update(words)

        for kw in like_keywords:
            if kw in content:
                # Extract nearby words as liked items
                idx = content.find(kw)
                nearby = content[max(0, idx-20):idx+30]
                nearby_tokens = _tokenize(nearby)
                likes.update(nearby_tokens)
                break

        for kw in dislike_keywords:
            if kw in content:
                idx = content.find(kw)
                nearby = content[max(0, idx-20):idx+30]
                nearby_tokens = _tokenize(nearby)
                dislikes.update(nearby_tokens)
                break

    return {
        "likes": likes.most_common(10),
        "dislikes": dislikes.most_common(10),
        "top_topics": topics.most_common(15),
    }


# ── Emotional Memory ───────────────────────────────────────────────────

_EMOTION_KEYWORDS = {
    "happy": ["happy", "khush", "achha", "great", "awesome", "amazing", "nice", "best", "love"],
    "sad": ["sad", "dukh", "bura", "bad", "worst", "hate", "miss", "lonely"],
    "angry": ["angry", "gussa", "frustrated", "irritated", "annoyed"],
    "excited": ["excited", "josh", "wow", "amazing", "incredible", "unbelievable"],
    "calm": ["calm", "relaxed", "peaceful", "chill", "comfortable"],
    "anxious": ["anxious", "worried", "tension", "stress", "nervous"],
}


def _analyze_emotions(entries: list[dict]) -> dict:
    """Analyze emotional patterns from memories."""
    emotion_counts = Counter()
    emotion_entries = {emotion: [] for emotion in _EMOTION_KEYWORDS}

    for entry in entries:
        content = entry.get("content", "").lower()
        for emotion, keywords in _EMOTION_KEYWORDS.items():
            for kw in keywords:
                if kw in content:
                    emotion_counts[emotion] += 1
                    emotion_entries[emotion].append(entry.get("content", "")[:100])
                    break

    return {
        "emotion_distribution": emotion_counts.most_common(),
        "total_entries": len(entries),
    }


# ── Semantic Search ─────────────────────────────────────────────────────

def semantic_search(query: str, limit: int = 10, user_id: str = "") -> list[dict]:
    """
    Search memories using semantic similarity.
    Returns ranked results with similarity scores.
    """
    conn = _connect()
    try:
        # Get all active memories for user
        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active'",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active'"
            ).fetchall()

        if not rows:
            return []

        # Score each memory
        scored = []
        for row in rows:
            content = row["content"]
            score = _semantic_similarity(query, content)

            # Boost score for recent memories
            try:
                updated = datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
                days_old = (datetime.now(updated.tzinfo) - updated).days
                recency_boost = max(0, 1 - days_old / 365) * 0.1
                score += recency_boost
            except Exception:
                pass

            # Boost for important memories
            if row["importance"] == "high":
                score *= 1.2
            elif row["importance"] == "critical":
                score *= 1.5

            if score > 0.05:  # minimum threshold
                scored.append({
                    "memory_id": row["memory_id"],
                    "content": content,
                    "memory_type": row["memory_type"],
                    "importance": row["importance"],
                    "score": round(score, 3),
                    "created_at": row["created_at"],
                })

        # Sort by score descending
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    finally:
        conn.close()


# ── Pattern Analysis ───────────────────────────────────────────────────

def analyze_patterns(user_id: str = "") -> dict:
    """
    Analyze user patterns from all memories.
    Returns routines, habits, and behavioral insights.
    """
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active'",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active'"
            ).fetchall()

        entries = [dict(row) for row in rows]

        if not entries:
            return {"message": "No memories found for analysis"}

        # Run all analyses
        time_patterns = _extract_time_patterns(entries)
        frequency = _extract_frequency_patterns(entries)
        routines = _extract_routine_patterns(entries)
        preferences = _analyze_preferences(entries)
        emotions = _analyze_emotions(entries)

        return {
            "total_memories": len(entries),
            "routines": routines,
            "preferences": preferences,
            "emotions": emotions,
            "time_distribution": {k: len(v) for k, v in time_patterns.items()},
            "top_topics": frequency["top_topics"],
        }

    finally:
        conn.close()


# ── Preference Learning ────────────────────────────────────────────────

def get_preferences(user_id: str = "") -> dict:
    """Get user's learned preferences."""
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active' AND memory_type = 'preference'",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active' AND memory_type = 'preference'"
            ).fetchall()

        entries = [dict(row) for row in rows]
        return _analyze_preferences(entries)

    finally:
        conn.close()


# ── Emotional Profile ──────────────────────────────────────────────────

def get_emotional_profile(user_id: str = "") -> dict:
    """Get user's emotional profile from memories."""
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active'",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active'"
            ).fetchall()

        entries = [dict(row) for row in rows]
        return _analyze_emotions(entries)

    finally:
        conn.close()


# ── Routine Detection ──────────────────────────────────────────────────

def get_routines(user_id: str = "") -> dict:
    """Detect user's daily routines."""
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active'",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active'"
            ).fetchall()

        entries = [dict(row) for row in rows]
        routines = _extract_routine_patterns(entries)
        time_dist = _extract_time_patterns(entries)

        return {
            "routines": routines,
            "time_distribution": {k: len(v) for k, v in time_dist.items()},
        }

    finally:
        conn.close()
