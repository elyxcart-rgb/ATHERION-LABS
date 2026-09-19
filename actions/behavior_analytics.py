"""SONIC AI — Behavior Analytics

Tracks and analyzes user behavior patterns:
- Screen time analysis
- Productivity scoring
- Habit tracking with AI insights
- Goal progress with predictions
- Weekly/monthly reports
- Activity timeline

Usage:
    "Mera productivity score kya hai?" → productivity analysis
    "Weekly report banao" → weekly report
    "Mujhe kya karna chahiye?" → AI recommendations
    "Activity dikhao" → activity timeline
"""
from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from collections import Counter, defaultdict

logger = logging.getLogger("BEHAVIOR_ANALYTICS")

# ── Storage ─────────────────────────────────────────────────────────────
_DATA_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "analytics"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_ACTIVITY_LOG = _DATA_DIR / "activity_log.json"
_PRODUCTIVITY_LOG = _DATA_DIR / "productivity.json"
_HABITS_FILE = _DATA_DIR / "habits.json"
_GOALS_FILE = _DATA_DIR / "goals.json"


def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ── Activity Logging ────────────────────────────────────────────────────

def log_activity(category: str, action: str, details: str = "", duration: int = 0) -> dict:
    """
    Log a user activity.

    Categories: coding, browsing, gaming, working, learning, social, creative, system
    Actions: start, stop, pause, resume, switch
    """
    log = _load_json(_ACTIVITY_LOG)
    if "activities" not in log:
        log["activities"] = []

    entry = {
        "timestamp": datetime.now().isoformat(),
        "category": category,
        "action": action,
        "details": details,
        "duration": duration,
    }

    log["activities"].append(entry)

    # Keep last 10000 entries
    if len(log["activities"]) > 10000:
        log["activities"] = log["activities"][-10000:]

    _save_json(_ACTIVITY_LOG, log)
    return {"success": True, "logged": entry}


def get_activities(hours: int = 24, category: str = "") -> list[dict]:
    """Get recent activities."""
    log = _load_json(_ACTIVITY_LOG)
    activities = log.get("activities", [])

    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    recent = [a for a in activities if a.get("timestamp", "") >= cutoff]

    if category:
        recent = [a for a in recent if a.get("category") == category]

    return recent[-100:]  # last 100


# ── Productivity Scoring ────────────────────────────────────────────────

def _calculate_productivity_score(activities: list[dict]) -> dict:
    """Calculate productivity score from activities."""
    if not activities:
        return {"score": 0, "grade": "No Data", "breakdown": {}}

    # Category weights (productive vs leisure)
    category_scores = {
        "coding": 9,
        "working": 8,
        "learning": 8,
        "creative": 7,
        "browsing": 4,
        "social": 3,
        "gaming": 2,
        "system": 5,
    }

    total_score = 0
    total_time = 0
    category_time = defaultdict(int)

    for activity in activities:
        cat = activity.get("category", "system")
        duration = activity.get("duration", 0)
        weight = category_scores.get(cat, 5)

        total_score += weight * duration
        total_time += duration
        category_time[cat] += duration

    if total_time == 0:
        return {"score": 0, "grade": "No Data", "breakdown": {}}

    avg_score = total_score / total_time

    # Convert to 0-100 scale
    score = min(100, int(avg_score * 10))

    # Grade
    if score >= 80:
        grade = "Excellent"
    elif score >= 60:
        grade = "Good"
    elif score >= 40:
        grade = "Average"
    elif score >= 20:
        grade = "Below Average"
    else:
        grade = "Needs Improvement"

    # Breakdown
    breakdown = {}
    for cat, t in category_time.items():
        pct = (t / total_time * 100) if total_time > 0 else 0
        breakdown[cat] = {
            "time_minutes": t // 60,
            "percentage": round(pct, 1),
            "productivity": category_scores.get(cat, 5),
        }

    return {
        "score": score,
        "grade": grade,
        "total_time_minutes": total_time // 60,
        "breakdown": breakdown,
    }


def get_productivity(hours: int = 24) -> dict:
    """Get productivity analysis."""
    activities = get_activities(hours=hours)
    return _calculate_productivity_score(activities)


# ── Habit Tracking ──────────────────────────────────────────────────────

def _load_habits() -> dict:
    return _load_json(_HABITS_FILE) or {"habits": []}


def _save_habits(data: dict) -> None:
    _save_json(_HABITS_FILE, data)


def add_habit(name: str, category: str = "general", target_days: int = 7) -> dict:
    """Add a new habit to track."""
    habits = _load_habits()
    habit = {
        "id": f"habit_{int(time.time())}",
        "name": name,
        "category": category,
        "target_days": target_days,
        "streak": 0,
        "best_streak": 0,
        "total_completions": 0,
        "created_at": datetime.now().isoformat(),
        "last_completed": None,
        "log": [],
    }
    habits["habits"].append(habit)
    _save_habits(habits)
    return {"success": True, "habit": habit}


def complete_habit(habit_id: str) -> dict:
    """Mark a habit as completed today."""
    habits = _load_habits()
    for habit in habits.get("habits", []):
        if habit["id"] == habit_id:
            today = datetime.now().date().isoformat()

            # Check if already completed today
            if habit.get("last_completed", "").startswith(today):
                return {"message": "Already completed today"}

            # Update streak
            habit["streak"] += 1
            habit["best_streak"] = max(habit["best_streak"], habit["streak"])
            habit["total_completions"] += 1
            habit["last_completed"] = datetime.now().isoformat()
            habit["log"].append({"date": today, "completed": True})

            _save_habits(habits)
            return {"success": True, "streak": habit["streak"], "best_streak": habit["best_streak"]}

    return {"error": "Habit not found"}


def get_habits() -> dict:
    """Get all habits with stats."""
    habits = _load_habits()
    habit_list = habits.get("habits", [])

    # Calculate stats
    total = len(habit_list)
    completed_today = 0
    best_streak = 0

    today = datetime.now().date().isoformat()
    for h in habit_list:
        if h.get("last_completed", "").startswith(today):
            completed_today += 1
        best_streak = max(best_streak, h.get("best_streak", 0))

    return {
        "total_habits": total,
        "completed_today": completed_today,
        "best_streak": best_streak,
        "habits": habit_list,
    }


# ── Goal Tracking ───────────────────────────────────────────────────────

def _load_goals() -> dict:
    return _load_json(_GOALS_FILE) or {"goals": []}


def _save_goals(data: dict) -> None:
    _save_json(_GOALS_FILE, data)


def add_goal(title: str, category: str = "personal", deadline: str = "") -> dict:
    """Add a new goal."""
    goals = _load_goals()
    goal = {
        "id": f"goal_{int(time.time())}",
        "title": title,
        "category": category,
        "progress": 0,
        "status": "active",
        "deadline": deadline or (datetime.now() + timedelta(days=30)).isoformat(),
        "created_at": datetime.now().isoformat(),
        "milestones": [],
    }
    goals["goals"].append(goal)
    _save_goals(goals)
    return {"success": True, "goal": goal}


def update_goal_progress(goal_id: str, progress: int) -> dict:
    """Update goal progress (0-100)."""
    goals = _load_goals()
    for goal in goals.get("goals", []):
        if goal["id"] == goal_id:
            goal["progress"] = min(100, max(0, progress))
            if goal["progress"] >= 100:
                goal["status"] = "completed"
            _save_goals(goals)
            return {"success": True, "progress": goal["progress"], "status": goal["status"]}
    return {"error": "Goal not found"}


def get_goals() -> dict:
    """Get all goals with stats."""
    goals = _load_goals()
    goal_list = goals.get("goals", [])

    active = [g for g in goal_list if g["status"] == "active"]
    completed = [g for g in goal_list if g["status"] == "completed"]

    # Calculate average progress
    avg_progress = 0
    if active:
        avg_progress = sum(g.get("progress", 0) for g in active) // len(active)

    return {
        "total_goals": len(goal_list),
        "active": len(active),
        "completed": len(completed),
        "average_progress": avg_progress,
        "goals": goal_list,
    }


# ── Weekly Report ───────────────────────────────────────────────────────

def generate_weekly_report() -> dict:
    """Generate a comprehensive weekly report."""
    # Get activities for last 7 days
    activities = get_activities(hours=168)  # 7 days

    # Productivity
    productivity = _calculate_productivity_score(activities)

    # Category breakdown
    category_time = defaultdict(int)
    for a in activities:
        cat = a.get("category", "unknown")
        category_time[cat] += a.get("duration", 0)

    # Daily breakdown
    daily = defaultdict(lambda: defaultdict(int))
    for a in activities:
        try:
            day = a.get("timestamp", "")[:10]
            cat = a.get("category", "unknown")
            daily[day][cat] += a.get("duration", 0)
        except Exception:
            pass

    # Habits
    habits = get_habits()

    # Goals
    goals = get_goals()

    return {
        "period": "Last 7 days",
        "productivity": productivity,
        "category_breakdown": {k: v // 60 for k, v in category_time.items()},
        "daily_breakdown": {k: dict(v) for k, v in daily.items()},
        "habits_summary": {
            "total": habits["total_habits"],
            "completed_today": habits["completed_today"],
            "best_streak": habits["best_streak"],
        },
        "goals_summary": {
            "active": goals["active"],
            "completed": goals["completed"],
            "avg_progress": goals["average_progress"],
        },
    }


# ── Tool Interface ──────────────────────────────────────────────────────

def behavior_analytics(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Behavior analytics tool.
    Tracks and analyzes user behavior patterns.
    """
    action = parameters.get("action", "productivity")

    if action == "log":
        category = parameters.get("category", "system")
        act = parameters.get("action_type", "start")
        details = parameters.get("details", "")
        duration = parameters.get("duration", 0)
        result = log_activity(category, act, details, duration)
        return f"Activity logged: {category} - {act}"

    elif action == "productivity":
        hours = parameters.get("hours", 24)
        result = get_productivity(hours)
        lines = [
            f"Productivity Score: {result['score']}/100 ({result['grade']})",
        ]
        if result.get('total_time_minutes'):
            lines.append(f"Total Time: {result['total_time_minutes']} minutes")
            lines.append("")
            lines.append("Breakdown:")
            for cat, info in result.get("breakdown", {}).items():
                lines.append(f"  {cat}: {info['time_minutes']}min ({info['percentage']}%)")
        else:
            lines.append("No activity data yet. Start logging activities!")
        return "\n".join(lines)

    elif action == "habits":
        result = get_habits()
        lines = [
            f"Habits: {result['completed_today']}/{result['total_habits']} completed today",
            f"Best Streak: {result['best_streak']} days",
            "",
            "Habits:",
        ]
        for h in result["habits"]:
            status = "[X]" if h.get("last_completed", "").startswith(datetime.now().date().isoformat()) else "[ ]"
            lines.append(f"  {status} {h['name']} (streak: {h['streak']})")
        return "\n".join(lines)

    elif action == "add_habit":
        name = parameters.get("name", "")
        if not name:
            return "Error: habit name is required"
        category = parameters.get("category", "general")
        result = add_habit(name, category)
        return f"Habit added: {name}"

    elif action == "complete_habit":
        habit_id = parameters.get("habit_id", "")
        if not habit_id:
            return "Error: habit_id is required"
        result = complete_habit(habit_id)
        if result.get("success"):
            return f"Habit completed! Streak: {result['streak']}"
        return result.get("message", result.get("error", "Failed"))

    elif action == "goals":
        result = get_goals()
        lines = [
            f"Goals: {result['active']} active, {result['completed']} completed",
            f"Average Progress: {result['average_progress']}%",
            "",
            "Active Goals:",
        ]
        for g in result["goals"]:
            if g["status"] == "active":
                lines.append(f"  [{g['progress']}%] {g['title']}")
        return "\n".join(lines)

    elif action == "add_goal":
        title = parameters.get("title", "")
        if not title:
            return "Error: goal title is required"
        category = parameters.get("category", "personal")
        deadline = parameters.get("deadline", "")
        result = add_goal(title, category, deadline)
        return f"Goal added: {title}"

    elif action == "update_goal":
        goal_id = parameters.get("goal_id", "")
        progress = parameters.get("progress", 0)
        if not goal_id:
            return "Error: goal_id is required"
        result = update_goal_progress(goal_id, progress)
        if result.get("success"):
            return f"Goal progress: {result['progress']}% ({result['status']})"
        return result.get("error", "Failed")

    elif action == "weekly_report":
        report = generate_weekly_report()
        prod = report["productivity"]
        lines = [
            "=== WEEKLY REPORT ===",
            f"Period: {report['period']}",
            "",
            f"Productivity: {prod['score']}/100 ({prod['grade']})",
            f"Total Time: {prod['total_time_minutes']} minutes",
            "",
            "Category Breakdown:",
        ]
        for cat, mins in report["category_breakdown"].items():
            lines.append(f"  {cat}: {mins}min")
        lines.append("")
        lines.append(f"Habits: {report['habits_summary']['completed_today']}/{report['habits_summary']['total']} today")
        lines.append(f"Goals: {report['goals_summary']['active']} active, {report['goals_summary']['completed']} completed")
        return "\n".join(lines)

    elif action == "activities":
        hours = parameters.get("hours", 24)
        category = parameters.get("category", "")
        activities = get_activities(hours, category)
        if not activities:
            return "No recent activities"
        lines = [f"Activities (last {hours}h):"]
        for a in activities[-20:]:
            lines.append(f"  [{a['category']}] {a['action']} - {a.get('details', '')[:50]}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: log, productivity, habits, add_habit, complete_habit, goals, add_goal, update_goal, weekly_report, activities"
