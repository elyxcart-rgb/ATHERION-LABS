"""SONIC AI — Proactive Engine.

Iron Man style: SONIC anticipates what the user needs BEFORE they ask.

How:
- Watches system state (time of day, active app, recent commands, day of week)
- Learns patterns from the user's history (e.g. "opens Spotify at 8am on weekdays")
- Surfaces context-aware suggestions ("It's 7:55 AM — your usual 8:00 Spotify?")

Output: ranked `Suggestion` objects with priority + reason + suggested action.
"""
from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from collections import Counter
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


@dataclass
class Suggestion:
    """Anticipatory suggestion from SONIC."""
    title: str
    reason: str
    action: str                     # action name to invoke
    args: dict = field(default_factory=dict)
    confidence: float = 0.0
    category: str = "general"       # routine|alert|context|maintenance|wellness
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ── Suggestion generators (pure functions of state) ────────────────────────

def _time_of_day(hour: int) -> str:
    if 5 <= hour < 11: return "morning"
    if 11 <= hour < 14: return "midday"
    if 14 <= hour < 18: return "afternoon"
    if 18 <= hour < 22: return "evening"
    return "night"


def _weekday(dow: int) -> str:
    return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][dow]


# Default routine suggestions by time-of-day
_ROUTINE_TIPS = {
    "morning": [
        Suggestion(
            title="Good morning",
            reason="Routine check-in. Want me to summarize overnight emails and news?",
            action="ask_ai",
            args={"prompt": "Summarize my overnight emails and any important news for today"},
            confidence=0.6,
            category="routine",
        ),
    ],
    "midday": [
        Suggestion(
            title="Midday focus block",
            reason="It's midday — ideal for deep work. Want me to mute notifications for 90 minutes?",
            action="run_python",
            args={"code": "import ctypes; ctypes.windll.user32.MessageBeep(0)"},
            confidence=0.4,
            category="wellness",
        ),
    ],
    "afternoon": [
        Suggestion(
            title="Afternoon stretch",
            reason="You've been at the screen for hours — consider a 5-minute break.",
            action="set_reminder",
            args={"when": "in 5 minutes", "what": "stand up and stretch"},
            confidence=0.3,
            category="wellness",
        ),
    ],
    "evening": [
        Suggestion(
            title="Evening wind-down",
            reason="Evening — want me to set Night Mode and queue tomorrow's agenda?",
            action="ask_ai",
            args={"prompt": "Set up tomorrow's agenda based on my calendar"},
            confidence=0.5,
            category="routine",
        ),
    ],
    "night": [
        Suggestion(
            title="Late-night check",
            reason="It's late. Want me to lock the screen and queue a 'wake up' reminder?",
            action="lock_computer",
            args={},
            confidence=0.4,
            category="routine",
        ),
    ],
}


class ProactiveEngine:
    """Anticipates user needs from patterns + current state."""

    def __init__(self, db_path: str | Path = "proactive_patterns.db"):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    # ── Public ───────────────────────────────────────────────────────────────

    def record_event(self, action: str, context: Optional[dict] = None):
        """Record that the user just did something. Feeds the pattern learner."""
        with self._lock:
            now = time.localtime()
            ctx = context or {}
            self._conn().execute(
                "INSERT INTO events (action, hour, weekday, dow, context_json, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (action, now.tm_hour, _weekday(now.tm_wday), now.tm_wday,
                 json.dumps(ctx), time.time()),
            )
            self._conn().commit()

    def suggest(self, context: Optional[dict] = None,
                max_suggestions: int = 3) -> list[Suggestion]:
        """Generate anticipatory suggestions based on current state + learned patterns."""
        with self._lock:
            now = time.localtime()
            hour = now.tm_hour
            dow = now.tm_wday
            weekday = _weekday(dow)
            tod = _time_of_day(hour)

            suggestions: list[Suggestion] = []

            # 1. Routine time-of-day suggestions
            for s in _ROUTINE_TIPS.get(tod, []):
                suggestions.append(Suggestion(
                    title=s.title, reason=s.reason, action=s.action,
                    args=dict(s.args), confidence=s.confidence,
                    category=s.category, timestamp=time.time(),
                ))

            # 2. Pattern-based: actions this user typically takes at this hour/weekday
            rows = self._conn().execute(
                "SELECT action, COUNT(*) as c FROM events "
                "WHERE hour=? AND weekday=? AND ts > ? "
                "GROUP BY action ORDER BY c DESC LIMIT 5",
                (hour, weekday, time.time() - 60 * 86400),  # last 60 days
            ).fetchall()
            total_at_this_time = sum(r[1] for r in rows) or 1
            for action, count in rows:
                conf = count / total_at_this_time
                if conf < 0.18 or action in (s.action for s in suggestions):
                    continue
                suggestions.append(Suggestion(
                    title=f"You usually do this around {hour}:00",
                    reason=f"You've run '{action}' about {count} times on {weekday} at this hour",
                    action=action,
                    args={},
                    confidence=conf,
                    category="pattern",
                    timestamp=time.time(),
                ))

            # 3. Context-driven: focused app
            ctx = context or {}
            focused = ctx.get("focused_app", "").lower()
            suggestions.extend(_app_suggestions(focused))

            # 4. Maintenance: any proactive suggestions from context
            if ctx.get("low_battery"):
                suggestions.append(Suggestion(
                    title="Battery low",
                    reason=f"Battery at {ctx.get('battery_pct')}%",
                    action="ask_ai",
                    args={"prompt": "Battery is low, switch to power saver mode"},
                    confidence=0.9,
                    category="alert",
                    timestamp=time.time(),
                ))
            if ctx.get("disk_low"):
                suggestions.append(Suggestion(
                    title="Disk space low",
                    reason=f"Only {ctx.get('free_gb', '?')} GB free",
                    action="cleanup_temp",
                    args={},
                    confidence=0.85,
                    category="maintenance",
                    timestamp=time.time(),
                ))

            suggestions.sort(key=lambda s: s.confidence, reverse=True)
            return suggestions[:max_suggestions]

    def get_stats(self) -> dict:
        with self._lock:
            total = self._conn().execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]
            unique = self._conn().execute(
                "SELECT COUNT(DISTINCT action) FROM events"
            ).fetchone()[0]
            db_size = self._db_path.stat().st_size if self._db_path.exists() else 0
            return {
                "events_recorded": total,
                "unique_actions": unique,
                "db_size_bytes": db_size,
            }

    def count_events(self) -> int:
        with self._lock:
            return self._conn().execute(
                "SELECT COUNT(*) FROM events"
            ).fetchone()[0]

    # ── Internals ────────────────────────────────────────────────────────────

    def _init_db(self):
        with self._lock:
            self._conn().execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    hour INTEGER NOT NULL,
                    weekday TEXT NOT NULL,
                    dow INTEGER NOT NULL,
                    context_json TEXT DEFAULT '{}',
                    ts REAL NOT NULL
                )
            """)
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_evt_action ON events(action)"
            )
            self._conn().execute(
                "CREATE INDEX IF NOT EXISTS idx_evt_hour ON events(hour, weekday)"
            )
            self._conn().commit()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self, "_db_conn") or self._db_conn is None:
            self._db_conn = sqlite3.connect(
                str(self._db_path), check_same_thread=False
            )
            self._db_conn.row_factory = sqlite3.Row
        return self._db_conn


def _app_suggestions(focused_app: str) -> list[Suggestion]:
    """Suggestions specific to the focused app."""
    if not focused_app:
        return []
    app = focused_app.lower()
    out = []
    if "code" in app or "pycharm" in app:
        out.append(Suggestion(
            title="Coding flow",
            reason="You're in a code editor — want me to enable do-not-disturb and start a focus timer?",
            action="ask_ai",
            args={"prompt": "Enable do not disturb and start a 90-minute focus timer"},
            confidence=0.4,
            category="context",
            timestamp=time.time(),
        ))
    elif "chrome" in app or "msedge" in app or "firefox" in app:
        out.append(Suggestion(
            title="Browser mode",
            reason="You're in a browser — want me to enable research mode and start clipping key sections?",
            action="summarize",
            args={"text": "auto-summary of current visible page"},
            confidence=0.35,
            category="context",
            timestamp=time.time(),
        ))
    elif "spotify" in app:
        out.append(Suggestion(
            title="Music mode",
            reason="Spotify's open — I'll keep notifications muted while you enjoy.",
            action="ask_ai",
            args={"prompt": "Mute notifications while music plays"},
            confidence=0.3,
            category="context",
            timestamp=time.time(),
        ))
    return out
