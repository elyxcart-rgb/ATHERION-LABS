"""SONIC AI — Pattern Recognition Engine

Detects and tracks user behavior patterns:
- Daily routines (when user does what)
- Topic patterns (what user talks about)
- Mood patterns (emotional trends)
- Activity patterns (tool usage patterns)
- Predictive suggestions (what user might need)

Usage:
    "Mera routine kya hai?" → daily routine analysis
    "Main kya karta hoon?" → behavior patterns
    "Mujhe kya chahiye?" → predictive suggestions
"""
from __future__ import annotations

import json
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from collections import Counter, defaultdict

logger = logging.getLogger("PATTERN_RECOGNITION")

# ── Database ────────────────────────────────────────────────────────────
_DB_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "memory"
_DB_PATH = _DB_DIR / "sonic_brain.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


# ── Stop Words ──────────────────────────────────────────────────────────
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "about", "this", "that",
    "it", "its", "i", "me", "my", "we", "our", "you", "your",
    "hai", "ho", "hain", "tha", "thi", "ke", "ka", "ki", "ko", "se",
    "me", "pe", "ne", "ya", "aur", "main", "mera", "meri", "mere",
    "tum", "apna", "kya", "ye", "wo", "jo", "nahi", "haan", "acha",
    "theek", "karo", "karna", "bol", "bolo", "batao", "dikhao", "chalo",
}


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    import re
    text = re.sub(r'[^\w\s]', ' ', text)
    words = text.split()
    return [w for w in words if len(w) > 2 and w not in _STOP_WORDS]


# ── Daily Routine Detection ────────────────────────────────────────────

def detect_daily_routine(user_id: str = "") -> dict:
    """Detect user's daily routine from memories."""
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active' ORDER BY created_at",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active' ORDER BY created_at"
            ).fetchall()

        if not rows:
            return {"routine": [], "message": "No data yet"}

        # Group by hour of day
        hourly = defaultdict(list)
        for row in rows:
            try:
                dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                hour = dt.hour
                hourly[hour].append(row["content"])
            except Exception:
                continue

        # Detect patterns
        routine = []
        for hour in sorted(hourly.keys()):
            entries = hourly[hour]
            if len(entries) >= 2:  # Need at least 2 entries to detect pattern
                # Extract common topics
                all_words = []
                for e in entries:
                    all_words.extend(_tokenize(e))

                topics = Counter(all_words).most_common(3)
                time_label = _hour_to_label(hour)

                routine.append({
                    "hour": hour,
                    "time_label": time_label,
                    "frequency": len(entries),
                    "topics": [t[0] for t in topics],
                    "sample": entries[0][:100],
                })

        return {
            "routine": routine,
            "total_entries": len(rows),
            "hours_with_data": len(hourly),
        }

    finally:
        conn.close()


def _hour_to_label(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 17:
        return "afternoon"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "night"


# ── Topic Pattern Detection ────────────────────────────────────────────

def detect_topic_patterns(user_id: str = "", days: int = 30) -> dict:
    """Detect what topics user frequently discusses."""
    conn = _connect()
    try:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active' AND created_at > ?",
                (user_id, cutoff)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active' AND created_at > ?",
                (cutoff,)
            ).fetchall()

        if not rows:
            return {"topics": [], "message": "No recent data"}

        # Extract and count topics
        all_words = []
        for row in rows:
            all_words.extend(_tokenize(row["content"]))

        topic_counts = Counter(all_words)

        # Group into categories
        topics = []
        for word, count in topic_counts.most_common(30):
            if count >= 2:  # At least 2 mentions
                topics.append({
                    "topic": word,
                    "mentions": count,
                    "frequency": "high" if count >= 10 else "medium" if count >= 5 else "low",
                })

        return {
            "topics": topics,
            "total_entries": len(rows),
            "period_days": days,
        }

    finally:
        conn.close()


# ── Mood Pattern Detection ─────────────────────────────────────────────

_EMOTION_WORDS = {
    "positive": ["happy", "great", "awesome", "amazing", "love", "best", "good", "nice", "excellent", "perfect", "wonderful", "fantastic", "brilliant", "superb", "outstanding", "khush", "achha", "badhiya", "mast"],
    "negative": ["sad", "bad", "worst", "hate", "terrible", "awful", "horrible", "poor", "ugly", "boring", "annoying", "frustrated", "angry", "upset", "disappointed", "bura", "ganda", "bekaar"],
    "neutral": ["okay", "fine", "normal", "regular", "average", "usual", "common", "theek", "saab"],
}


def detect_mood_patterns(user_id: str = "", days: int = 30) -> dict:
    """Detect user's mood patterns over time."""
    conn = _connect()
    try:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        if user_id:
            rows = conn.execute(
                "SELECT * FROM memories WHERE user_id = ? AND status = 'active' AND created_at > ?",
                (user_id, cutoff)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM memories WHERE status = 'active' AND created_at > ?",
                (cutoff,)
            ).fetchall()

        if not rows:
            return {"mood": "neutral", "message": "No data"}

        # Analyze mood
        positive = 0
        negative = 0
        neutral = 0
        mood_timeline = []

        for row in rows:
            content = row["content"].lower()
            entry_mood = "neutral"

            for word in _EMOTION_WORDS["positive"]:
                if word in content:
                    positive += 1
                    entry_mood = "positive"
                    break

            for word in _EMOTION_WORDS["negative"]:
                if word in content:
                    negative += 1
                    entry_mood = "negative"
                    break

            if entry_mood == "neutral":
                neutral += 1

            try:
                dt = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
                mood_timeline.append({
                    "date": dt.date().isoformat(),
                    "mood": entry_mood,
                })
            except Exception:
                pass

        total = positive + negative + neutral
        if total == 0:
            return {"mood": "neutral"}

        # Overall mood
        if positive > negative * 1.5:
            overall = "positive"
        elif negative > positive * 1.5:
            overall = "negative"
        else:
            overall = "neutral"

        # Daily mood aggregation
        daily_mood = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0})
        for entry in mood_timeline:
            daily_mood[entry["date"]][entry["mood"]] += 1

        return {
            "overall_mood": overall,
            "positive_pct": round(positive / total * 100, 1),
            "negative_pct": round(negative / total * 100, 1),
            "neutral_pct": round(neutral / total * 100, 1),
            "total_entries": total,
        }

    finally:
        conn.close()


# ── Activity Pattern Detection ─────────────────────────────────────────

def detect_activity_patterns(user_id: str = "") -> dict:
    """Detect what tools/actions user uses most."""
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

        if not rows:
            return {"activities": [], "message": "No data"}

        # Extract action keywords
        action_words = Counter()
        for row in rows:
            content = row["content"].lower()
            words = _tokenize(content)
            action_words.update(words)

        # Common action categories
        categories = {
            "coding": ["code", "python", "javascript", "program", "debug", "fix", "bug", "develop"],
            "browsing": ["search", "google", "website", "browse", "open", "chrome", "firefox"],
            "file_management": ["file", "folder", "move", "copy", "delete", "organize", "download"],
            "communication": ["email", "message", "send", "chat", "call", "whatsapp", "telegram"],
            "media": ["music", "video", "youtube", "play", "watch", "listen"],
            "system": ["volume", "brightness", "wifi", "settings", "shutdown", "restart"],
        }

        activity_scores = {}
        for category, keywords in categories.items():
            score = sum(action_words.get(kw, 0) for kw in keywords)
            if score > 0:
                activity_scores[category] = score

        # Sort by score
        sorted_activities = sorted(activity_scores.items(), key=lambda x: x[1], reverse=True)

        return {
            "top_activities": [{"category": a[0], "score": a[1]} for a in sorted_activities[:5]],
            "total_entries": len(rows),
        }

    finally:
        conn.close()


# ── Predictive Suggestions ─────────────────────────────────────────────

def get_predictive_suggestions(user_id: str = "") -> dict:
    """Generate predictive suggestions based on patterns."""
    routine = detect_daily_routine(user_id)
    topics = detect_topic_patterns(user_id)
    mood = detect_mood_patterns(user_id)

    suggestions = []

    # Time-based suggestions
    current_hour = datetime.now().hour
    time_label = _hour_to_label(current_hour)

    # Find routine for current time
    for r in routine.get("routine", []):
        if r["time_label"] == time_label:
            suggestions.append({
                "type": "routine",
                "message": f"Usually you {', '.join(r['topics'][:2])} at this time",
                "confidence": "high" if r["frequency"] >= 5 else "medium",
            })

    # Topic-based suggestions
    top_topics = [t["topic"] for t in topics.get("topics", [])[:3]]
    if top_topics:
        suggestions.append({
            "type": "interest",
            "message": f"Your recent interests: {', '.join(top_topics)}",
            "confidence": "high",
        })

    # Mood-based suggestions
    if mood.get("overall_mood") == "negative":
        suggestions.append({
            "type": "mood",
            "message": "Your mood seems down. Want to listen to some music?",
            "confidence": "medium",
        })
    elif mood.get("overall_mood") == "positive":
        suggestions.append({
            "type": "mood",
            "message": "You seem happy! Great time to tackle challenging tasks.",
            "confidence": "medium",
        })

    return {
        "suggestions": suggestions,
        "current_time": time_label,
        "overall_mood": mood.get("overall_mood", "neutral"),
    }


# ── Tool Interface ──────────────────────────────────────────────────────

def pattern_recognition(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Pattern recognition tool.
    Detects and analyzes user behavior patterns.
    """
    action = parameters.get("action", "routine")
    user_id = parameters.get("user_id", "")

    if action == "routine":
        result = detect_daily_routine(user_id)
        routine = result.get("routine", [])
        if not routine:
            return "No routine detected yet. Keep using SONIC and patterns will emerge."

        lines = ["YOUR DAILY ROUTINE:"]
        for r in routine:
            lines.append(f"  {r['time_label'].title()} ({r['hour']:02d}:00): {', '.join(r['topics'][:3])}")
        lines.append(f"\nBased on {result['total_entries']} memories")
        return "\n".join(lines)

    elif action == "topics":
        days = parameters.get("days", 30)
        result = detect_topic_patterns(user_id, days)
        topics = result.get("topics", [])
        if not topics:
            return "No topic patterns detected yet."

        lines = [f"TOP TOPICS (last {days} days):"]
        for t in topics[:10]:
            lines.append(f"  {t['topic']}: {t['mentions']} mentions ({t['frequency']})")
        return "\n".join(lines)

    elif action == "mood":
        result = detect_mood_patterns(user_id)
        return (
            f"MOOD ANALYSIS:\n"
            f"Overall: {result['overall_mood'].title()}\n"
            f"Positive: {result['positive_pct']}%\n"
            f"Negative: {result['negative_pct']}%\n"
            f"Neutral: {result['neutral_pct']}%\n"
            f"Based on {result['total_entries']} entries"
        )

    elif action == "activities":
        result = detect_activity_patterns(user_id)
        activities = result.get("top_activities", [])
        if not activities:
            return "No activity patterns detected yet."

        lines = ["TOP ACTIVITIES:"]
        for a in activities:
            lines.append(f"  {a['category']}: {a['score']} mentions")
        return "\n".join(lines)

    elif action == "suggest":
        result = get_predictive_suggestions(user_id)
        suggestions = result.get("suggestions", [])
        if not suggestions:
            return "No suggestions yet. Keep using SONIC!"

        lines = ["PREDICTIVE SUGGESTIONS:"]
        for s in suggestions:
            lines.append(f"  [{s['type']}] {s['message']} (confidence: {s['confidence']})")
        return "\n".join(lines)

    elif action == "full_report":
        routine = detect_daily_routine(user_id)
        topics = detect_topic_patterns(user_id)
        mood = detect_mood_patterns(user_id)
        activities = detect_activity_patterns(user_id)
        suggestions = get_predictive_suggestions(user_id)

        lines = ["=== FULL PATTERN REPORT ==="]

        # Routine
        lines.append("\nDAILY ROUTINE:")
        for r in routine.get("routine", [])[:5]:
            lines.append(f"  {r['time_label'].title()}: {', '.join(r['topics'][:2])}")

        # Topics
        lines.append("\nTOP TOPICS:")
        for t in topics.get("topics", [])[:5]:
            lines.append(f"  {t['topic']}: {t['mentions']}x")

        # Mood
        lines.append(f"\nMOOD: {mood['overall_mood'].title()} ({mood['positive_pct']}% positive)")

        # Activities
        lines.append("\nTOP ACTIVITIES:")
        for a in activities.get("top_activities", [])[:3]:
            lines.append(f"  {a['category']}: {a['score']}")

        # Suggestions
        lines.append("\nSUGGESTIONS:")
        for s in suggestions.get("suggestions", [])[:3]:
            lines.append(f"  {s['message']}")

        return "\n".join(lines)

    return f"Unknown action: {action}. Use: routine, topics, mood, activities, suggest, full_report"
