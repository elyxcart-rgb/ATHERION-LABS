"""SONIC AI — AI Life Dashboard

Complete life management system with AI predictions.
Tracks everything about your life and provides insights:
- Health & fitness tracking
- Financial management
- Goal tracking & habit building
- Relationship management
- Career development
- Mental health monitoring
- Time management
- AI-powered predictions and recommendations

Usage:
    "SONIC, show my life dashboard"
    "SONIC, log my workout"
    "SONIC, analyze my spending"
    "SONIC, predict my future"
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("LIFE_DASH")


@dataclass
class HealthData:
    """Health and fitness data."""
    steps: int = 0
    calories_burned: int = 0
    calories_consumed: int = 0
    water_intake_ml: int = 0
    sleep_hours: float = 0.0
    heart_rate: int = 0
    weight_kg: float = 0.0
    mood: str = "neutral"  # happy, neutral, sad, anxious, energetic
    energy_level: int = 5  # 1-10
    stress_level: int = 5  # 1-10
    exercise_minutes: int = 0
    meditation_minutes: int = 0


@dataclass
class FinanceData:
    """Financial data."""
    balance: float = 0.0
    income: float = 0.0
    expenses: float = 0.0
    savings: float = 0.0
    investments: float = 0.0
    debt: float = 0.0
    transactions: list = field(default_factory=list)
    budgets: dict = field(default_factory=dict)


@dataclass
class Goal:
    """Life goal."""
    id: str
    title: str
    category: str  # health, finance, career, personal, relationship
    target_date: str
    progress: float = 0.0  # 0-100%
    milestones: list = field(default_factory=list)
    status: str = "active"  # active, completed, paused
    created_at: float = 0.0


@dataclass
class Habit:
    """Daily habit."""
    id: str
    name: str
    category: str
    frequency: str = "daily"  # daily, weekly, monthly
    streak: int = 0
    completed_today: bool = False
    history: list = field(default_factory=list)


@dataclass
class Relationship:
    """People in your life."""
    id: str
    name: str
    relationship: str  # family, friend, colleague, partner
    last_interaction: float = 0.0
    importance: int = 5  # 1-10
    notes: str = ""
    birthdays: list = field(default_factory=list)


class LifeDashboard:
    """Complete life management with AI predictions."""

    def __init__(self):
        self._data_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "SONIC AI" / "life_data"
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._health = HealthData()
        self._finance = FinanceData()
        self._goals: list[Goal] = []
        self._habits: list[Habit] = []
        self._relationships: list[Relationship] = []
        self._journal: list[dict] = []
        self._callbacks: list[Callable] = []

        self._load_data()

    def _load_data(self):
        """Load all life data from disk."""
        try:
            health_file = self._data_dir / "health.json"
            if health_file.exists():
                data = json.loads(health_file.read_text(encoding="utf-8"))
                self._health = HealthData(**data)

            finance_file = self._data_dir / "finance.json"
            if finance_file.exists():
                data = json.loads(finance_file.read_text(encoding="utf-8"))
                self._finance = FinanceData(**data)

            goals_file = self._data_dir / "goals.json"
            if goals_file.exists():
                data = json.loads(goals_file.read_text(encoding="utf-8"))
                self._goals = [Goal(**g) for g in data]

            habits_file = self._data_dir / "habits.json"
            if habits_file.exists():
                data = json.loads(habits_file.read_text(encoding="utf-8"))
                self._habits = [Habit(**h) for h in data]

            rels_file = self._data_dir / "relationships.json"
            if rels_file.exists():
                data = json.loads(rels_file.read_text(encoding="utf-8"))
                self._relationships = [Relationship(**r) for r in data]

        except Exception as e:
            logger.warning("[LIFE_DASH] Failed to load data: %s", e)

    def _save_data(self):
        """Save all life data to disk."""
        try:
            (self._data_dir / "health.json").write_text(
                json.dumps(self._health.__dict__, indent=2), encoding="utf-8")
            (self._data_dir / "finance.json").write_text(
                json.dumps(self._finance.__dict__, indent=2), encoding="utf-8")
            (self._data_dir / "goals.json").write_text(
                json.dumps([g.__dict__ for g in self._goals], indent=2), encoding="utf-8")
            (self._data_dir / "habits.json").write_text(
                json.dumps([h.__dict__ for h in self._habits], indent=2), encoding="utf-8")
            (self._data_dir / "relationships.json").write_text(
                json.dumps([r.__dict__ for r in self._relationships], indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("[LIFE_DASH] Failed to save data: %s", e)

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    def _emit(self, event: str, data: dict = None):
        for cb in self._callbacks:
            try:
                cb(event, data or {})
            except Exception:
                pass

    # ── Health ───────────────────────────────────────────────────────────

    def log_health(self, **kwargs) -> dict:
        """Log health data."""
        for key, value in kwargs.items():
            if hasattr(self._health, key):
                setattr(self._health, key, value)
        self._save_data()
        self._emit("health_updated", kwargs)
        return {"status": "ok", "data": self._health.__dict__}

    def get_health_insights(self) -> dict:
        """Get AI health insights."""
        insights = []

        if self._health.steps < 10000:
            insights.append("You've walked {} steps today. Try to reach 10,000!".format(self._health.steps))
        if self._health.water_intake_ml < 2000:
            insights.append("Drink more water! You've had {}ml, aim for 2000ml.".format(self._health.water_intake_ml))
        if self._health.sleep_hours < 7:
            insights.append("You only slept {} hours. Aim for 7-9 hours.".format(self._health.sleep_hours))
        if self._health.stress_level > 7:
            insights.append("High stress detected. Try meditation or deep breathing.")
        if self._health.mood == "sad":
            insights.append("Feeling down? Consider talking to someone or doing something you enjoy.")

        health_score = self._calculate_health_score()

        return {
            "health_score": health_score,
            "insights": insights,
            "current": self._health.__dict__,
        }

    def _calculate_health_score(self) -> int:
        """Calculate overall health score (0-100)."""
        score = 50  # Base

        # Steps
        if self._health.steps >= 10000:
            score += 15
        elif self._health.steps >= 5000:
            score += 10
        elif self._health.steps >= 1000:
            score += 5

        # Sleep
        if 7 <= self._health.sleep_hours <= 9:
            score += 15
        elif 6 <= self._health.sleep_hours < 7:
            score += 10

        # Water
        if self._health.water_intake_ml >= 2000:
            score += 10

        # Mood
        if self._health.mood == "happy":
            score += 10
        elif self._health.mood == "energetic":
            score += 10

        # Stress (inverse)
        score += max(0, 10 - self._health.stress_level)

        return min(100, max(0, score))

    # ── Finance ──────────────────────────────────────────────────────────

    def log_expense(self, amount: float, category: str, description: str = "") -> dict:
        """Log an expense."""
        transaction = {
            "type": "expense",
            "amount": amount,
            "category": category,
            "description": description,
            "timestamp": time.time(),
        }
        self._finance.transactions.append(transaction)
        self._finance.expenses += amount
        self._save_data()
        self._emit("expense_logged", transaction)
        return {"status": "ok", "balance": self._finance.balance - amount}

    def log_income(self, amount: float, source: str, description: str = "") -> dict:
        """Log income."""
        transaction = {
            "type": "income",
            "amount": amount,
            "source": source,
            "description": description,
            "timestamp": time.time(),
        }
        self._finance.transactions.append(transaction)
        self._finance.income += amount
        self._finance.balance += amount
        self._save_data()
        self._emit("income_logged", transaction)
        return {"status": "ok", "balance": self._finance.balance}

    def get_financial_insights(self) -> dict:
        """Get AI financial insights."""
        insights = []

        # Spending analysis
        if self._finance.expenses > self._finance.income:
            insights.append("Warning: You're spending more than you earn!")
            insights.append("Consider reducing expenses or increasing income.")

        # Savings rate
        if self._finance.income > 0:
            savings_rate = ((self._finance.income - self._finance.expenses) / self._finance.income) * 100
            if savings_rate < 20:
                insights.append(f"Your savings rate is {savings_rate:.1f}%. Aim for 20%+.")
            else:
                insights.append(f"Great! Your savings rate is {savings_rate:.1f}%.")

        # Debt
        if self._finance.debt > 0:
            insights.append(f"You have ${self._finance.debt:,.2f} in debt. Consider a payoff plan.")

        # Budget alerts
        for category, budget in self._finance.budgets.items():
            spent = sum(
                t["amount"] for t in self._finance.transactions
                if t.get("category") == category and t["type"] == "expense"
            )
            if spent > budget * 0.9:
                insights.append(f"Warning: {category} spending is at {spent/budget*100:.0f}% of budget!")

        return {
            "balance": self._finance.balance,
            "income": self._finance.income,
            "expenses": self._finance.expenses,
            "insights": insights,
        }

    # ── Goals ────────────────────────────────────────────────────────────

    def add_goal(self, title: str, category: str, target_date: str) -> Goal:
        """Add a new life goal."""
        goal = Goal(
            id=f"goal_{int(time.time())}",
            title=title,
            category=category,
            target_date=target_date,
            created_at=time.time(),
        )
        self._goals.append(goal)
        self._save_data()
        return goal

    def update_goal_progress(self, goal_id: str, progress: float) -> bool:
        """Update goal progress."""
        for goal in self._goals:
            if goal.id == goal_id:
                goal.progress = min(100, max(0, progress))
                if goal.progress >= 100:
                    goal.status = "completed"
                self._save_data()
                return True
        return False

    def get_goals_summary(self) -> dict:
        """Get goals summary."""
        active = [g for g in self._goals if g.status == "active"]
        completed = [g for g in self._goals if g.status == "completed"]

        return {
            "total": len(self._goals),
            "active": len(active),
            "completed": len(completed),
            "goals": [g.__dict__ for g in self._goals],
        }

    # ── Habits ───────────────────────────────────────────────────────────

    def add_habit(self, name: str, category: str, frequency: str = "daily") -> Habit:
        """Add a new habit to track."""
        habit = Habit(
            id=f"habit_{int(time.time())}",
            name=name,
            category=category,
            frequency=frequency,
        )
        self._habits.append(habit)
        self._save_data()
        return habit

    def complete_habit(self, habit_id: str) -> bool:
        """Mark habit as completed today."""
        for habit in self._habits:
            if habit.id == habit_id:
                habit.completed_today = True
                habit.streak += 1
                habit.history.append({"date": datetime.now().isoformat(), "completed": True})
                self._save_data()
                return True
        return False

    def get_habits_summary(self) -> dict:
        """Get habits summary."""
        completed_today = sum(1 for h in self._habits if h.completed_today)
        total = len(self._habits)
        best_streak = max((h.streak for h in self._habits), default=0)

        return {
            "total": total,
            "completed_today": completed_today,
            "completion_rate": (completed_today / total * 100) if total > 0 else 0,
            "best_streak": best_streak,
            "habits": [h.__dict__ for h in self._habits],
        }

    # ── Relationships ────────────────────────────────────────────────────

    def add_relationship(self, name: str, rel_type: str, importance: int = 5) -> Relationship:
        """Add a person to track."""
        rel = Relationship(
            id=f"rel_{int(time.time())}",
            name=name,
            relationship=rel_type,
            importance=importance,
            last_interaction=time.time(),
        )
        self._relationships.append(rel)
        self._save_data()
        return rel

    def log_interaction(self, rel_id: str, notes: str = "") -> bool:
        """Log an interaction with someone."""
        for rel in self._relationships:
            if rel.id == rel_id:
                rel.last_interaction = time.time()
                if notes:
                    rel.notes += f"\n{datetime.now().strftime('%Y-%m-%d')}: {notes}"
                self._save_data()
                return True
        return False

    def get_relationship_insights(self) -> dict:
        """Get relationship insights."""
        insights = []
        now = time.time()

        for rel in self._relationships:
            days_since = (now - rel.last_interaction) / 86400
            if days_since > 30 and rel.importance >= 7:
                insights.append(f"You haven't contacted {rel.name} in {int(days_since)} days!")
            elif days_since > 7 and rel.importance >= 5:
                insights.append(f"Consider reaching out to {rel.name}.")

        return {
            "total": len(self._relationships),
            "insights": insights,
            "relationships": [r.__dict__ for r in self._relationships],
        }

    # ── AI Predictions ───────────────────────────────────────────────────

    def predict_future(self, timeframe: str = "1 year") -> dict:
        """AI predictions about your future."""
        predictions = []

        # Health prediction
        health_trend = "improving" if self._health.steps > 5000 else "needs improvement"
        predictions.append({
            "category": "health",
            "prediction": f"Health is {health_trend}. Keep it up!" if health_trend == "improving" else "Start exercising more for better health.",
            "confidence": 0.8,
        })

        # Financial prediction
        if self._finance.income > self._finance.expenses:
            savings_in_year = (self._finance.income - self._finance.expenses) * 12
            predictions.append({
                "category": "finance",
                "prediction": f"At current rate, you'll save ${savings_in_year:,.2f} in a year.",
                "confidence": 0.7,
            })
        else:
            predictions.append({
                "category": "finance",
                "prediction": "Warning: At current spending, you'll be in debt.",
                "confidence": 0.8,
            })

        # Goal prediction
        active_goals = [g for g in self._goals if g.status == "active"]
        for goal in active_goals:
            days_left = (datetime.fromisoformat(goal.target_date) - datetime.now()).days
            if days_left > 0:
                daily_progress = goal.progress / max(1, (365 - days_left))
                needed_daily = (100 - goal.progress) / max(1, days_left)
                if daily_progress >= needed_daily:
                    predictions.append({
                        "category": "goal",
                        "prediction": f"On track to complete '{goal.title}'!",
                        "confidence": 0.75,
                    })
                else:
                    predictions.append({
                        "category": "goal",
                        "prediction": f"May miss '{goal.title}' deadline. Increase effort!",
                        "confidence": 0.6,
                    })

        # Habit prediction
        completed_habits = sum(1 for h in self._habits if h.completed_today)
        total_habits = len(self._habits)
        if total_habits > 0:
            consistency = completed_habits / total_habits
            if consistency > 0.8:
                predictions.append({
                    "category": "habits",
                    "prediction": "Excellent habit consistency! You're building a strong routine.",
                    "confidence": 0.85,
                })
            else:
                predictions.append({
                    "category": "habits",
                    "prediction": "Work on consistency. Try completing more habits daily.",
                    "confidence": 0.7,
                })

        return {
            "timeframe": timeframe,
            "predictions": predictions,
            "generated_at": datetime.now().isoformat(),
        }

    def get_life_score(self) -> dict:
        """Calculate overall life score."""
        health_score = self._calculate_health_score()
        finance_score = self._calculate_finance_score()
        goals_score = self._calculate_goals_score()
        habits_score = self._calculate_habits_score()
        social_score = self._calculate_social_score()

        overall = (health_score + finance_score + goals_score + habits_score + social_score) // 5

        return {
            "overall": overall,
            "health": health_score,
            "finance": finance_score,
            "goals": goals_score,
            "habits": habits_score,
            "social": social_score,
            "grade": self._score_to_grade(overall),
        }

    def _calculate_finance_score(self) -> int:
        score = 50
        if self._finance.balance > 0:
            score += 20
        if self._finance.income > self._finance.expenses:
            score += 20
        if self._finance.debt == 0:
            score += 10
        return min(100, score)

    def _calculate_goals_score(self) -> int:
        if not self._goals:
            return 50
        completed = sum(1 for g in self._goals if g.status == "completed")
        return min(100, int((completed / len(self._goals)) * 100) + 50)

    def _calculate_habits_score(self) -> int:
        if not self._habits:
            return 50
        completed = sum(1 for h in self._habits if h.completed_today)
        return min(100, int((completed / len(self._habits)) * 100))

    def _calculate_social_score(self) -> int:
        if not self._relationships:
            return 50
        recent = sum(1 for r in self._relationships
                    if (time.time() - r.last_interaction) < 7 * 86400)
        return min(100, int((recent / len(self._relationships)) * 100) + 30)

    def _score_to_grade(self, score: int) -> str:
        if score >= 90: return "A+"
        if score >= 80: return "A"
        if score >= 70: return "B"
        if score >= 60: return "C"
        if score >= 50: return "D"
        return "F"

    def get_dashboard_summary(self) -> dict:
        """Get complete dashboard summary."""
        return {
            "life_score": self.get_life_score(),
            "health": self.get_health_insights(),
            "finance": self.get_financial_insights(),
            "goals": self.get_goals_summary(),
            "habits": self.get_habits_summary(),
            "relationships": self.get_relationship_insights(),
            "predictions": self.predict_future(),
        }


# Singleton
_dashboard: LifeDashboard | None = None


def get_life_dashboard() -> LifeDashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = LifeDashboard()
    return _dashboard
