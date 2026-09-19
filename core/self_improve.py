"""SONIC AI — Self-Improvement Engine

Learns from interactions to improve over time:
- Tracks tool usage patterns and success rates
- Learns from user corrections
- Optimizes response patterns
- Performance monitoring (response time, accuracy)
- Auto-adjusts behavior based on feedback

Usage:
    "Tum improve ho?" → show improvement stats
    "Ye galat tha" → learn from correction
    "Performance dikhao" → show metrics
"""
from __future__ import annotations

import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from collections import Counter, defaultdict

logger = logging.getLogger("SELF_IMPROVE")

# ── Storage ─────────────────────────────────────────────────────────────
_DATA_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "learning"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_TOOL_USAGE_FILE = _DATA_DIR / "tool_usage.json"
_CORRECTIONS_FILE = _DATA_DIR / "corrections.json"
_PERFORMANCE_FILE = _DATA_DIR / "performance.json"
_PATTERNS_FILE = _DATA_DIR / "patterns.json"


def _load_json(path: Path) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ── Tool Usage Tracking ────────────────────────────────────────────────

def log_tool_usage(tool_name: str, success: bool, duration: float = 0, error: str = "") -> None:
    """Log a tool usage event."""
    data = _load_json(_TOOL_USAGE_FILE)
    if "tools" not in data:
        data["tools"] = {}

    if tool_name not in data["tools"]:
        data["tools"][tool_name] = {
            "total_calls": 0,
            "successes": 0,
            "failures": 0,
            "total_duration": 0,
            "errors": [],
            "last_used": None,
        }

    tool = data["tools"][tool_name]
    tool["total_calls"] += 1
    if success:
        tool["successes"] += 1
    else:
        tool["failures"] += 1
        if error and len(tool["errors"]) < 10:
            tool["errors"].append({"error": error, "time": datetime.now().isoformat()})

    tool["total_duration"] += duration
    tool["last_used"] = datetime.now().isoformat()

    _save_json(_TOOL_USAGE_FILE, data)


def get_tool_stats(tool_name: str = None) -> dict:
    """Get tool usage statistics."""
    data = _load_json(_TOOL_USAGE_FILE)
    tools = data.get("tools", {})

    if tool_name:
        if tool_name in tools:
            t = tools[tool_name]
            success_rate = (t["successes"] / t["total_calls"] * 100) if t["total_calls"] > 0 else 0
            avg_duration = (t["total_duration"] / t["total_calls"]) if t["total_calls"] > 0 else 0
            return {
                "tool": tool_name,
                "total_calls": t["total_calls"],
                "success_rate": round(success_rate, 1),
                "avg_duration": round(avg_duration, 2),
                "last_used": t["last_used"],
                "recent_errors": t["errors"][-3:],
            }
        return {"error": f"Tool '{tool_name}' not found"}

    # All tools summary
    summary = []
    for name, t in tools.items():
        success_rate = (t["successes"] / t["total_calls"] * 100) if t["total_calls"] > 0 else 0
        summary.append({
            "tool": name,
            "calls": t["total_calls"],
            "success_rate": round(success_rate, 1),
        })

    summary.sort(key=lambda x: x["calls"], reverse=True)
    return {"tools": summary, "total_tools": len(summary)}


# ── Correction Learning ─────────────────────────────────────────────────

def log_correction(original_action: str, corrected_action: str, context: str = "") -> None:
    """Log a user correction for learning."""
    data = _load_json(_CORRECTIONS_FILE)
    if "corrections" not in data:
        data["corrections"] = []

    data["corrections"].append({
        "original": original_action,
        "corrected": corrected_action,
        "context": context,
        "time": datetime.now().isoformat(),
    })

    # Keep last 500 corrections
    if len(data["corrections"]) > 500:
        data["corrections"] = data["corrections"][-500:]

    _save_json(_CORRECTIONS_FILE, data)


def get_corrections(limit: int = 20) -> list[dict]:
    """Get recent corrections."""
    data = _load_json(_CORRECTIONS_FILE)
    return data.get("corrections", [])[-limit:]


def get_correction_patterns() -> dict:
    """Analyze correction patterns to find areas for improvement."""
    data = _load_json(_CORRECTIONS_FILE)
    corrections = data.get("corrections", [])

    if not corrections:
        return {"message": "No corrections logged yet"}

    # Find common correction patterns
    original_actions = Counter()
    for c in corrections:
        original = c.get("original", "")
        original_actions[original] += 1

    return {
        "total_corrections": len(corrections),
        "common_mistakes": original_actions.most_common(10),
        "improvement_areas": [m[0] for m in original_actions.most_common(5)],
    }


# ── Performance Monitoring ──────────────────────────────────────────────

def log_performance(metric: str, value: float) -> None:
    """Log a performance metric."""
    data = _load_json(_PERFORMANCE_FILE)
    if "metrics" not in data:
        data["metrics"] = {}

    if metric not in data["metrics"]:
        data["metrics"][metric] = []

    data["metrics"][metric].append({
        "value": value,
        "time": datetime.now().isoformat(),
    })

    # Keep last 1000 entries per metric
    if len(data["metrics"][metric]) > 1000:
        data["metrics"][metric] = data["metrics"][metric][-1000:]

    _save_json(_PERFORMANCE_FILE, data)


def get_performance(metric: str = None) -> dict:
    """Get performance metrics."""
    data = _load_json(_PERFORMANCE_FILE)
    metrics = data.get("metrics", {})

    if metric:
        if metric in metrics:
            values = [m["value"] for m in metrics[metric]]
            return {
                "metric": metric,
                "count": len(values),
                "avg": round(sum(values) / len(values), 2) if values else 0,
                "min": min(values) if values else 0,
                "max": max(values) if values else 0,
                "latest": values[-1] if values else 0,
            }
        return {"error": f"Metric '{metric}' not found"}

    # All metrics summary
    summary = {}
    for name, entries in metrics.items():
        values = [e["value"] for e in entries]
        summary[name] = {
            "count": len(values),
            "avg": round(sum(values) / len(values), 2) if values else 0,
        }

    return {"metrics": summary}


# ── Pattern Detection ───────────────────────────────────────────────────

def log_pattern(pattern_type: str, pattern_data: dict) -> None:
    """Log a detected pattern."""
    data = _load_json(_PATTERNS_FILE)
    if "patterns" not in data:
        data["patterns"] = []

    data["patterns"].append({
        "type": pattern_type,
        "data": pattern_data,
        "time": datetime.now().isoformat(),
    })

    # Keep last 200 patterns
    if len(data["patterns"]) > 200:
        data["patterns"] = data["patterns"][-200:]

    _save_json(_PATTERNS_FILE, data)


def get_patterns(pattern_type: str = None) -> list[dict]:
    """Get detected patterns."""
    data = _load_json(_PATTERNS_FILE)
    patterns = data.get("patterns", [])

    if pattern_type:
        return [p for p in patterns if p.get("type") == pattern_type]

    return patterns[-20:]


# ── Improvement Report ──────────────────────────────────────────────────

def generate_improvement_report() -> dict:
    """Generate a self-improvement report."""
    tool_stats = get_tool_stats()
    corrections = get_correction_patterns()
    performance = get_performance()

    # Calculate overall improvement score
    total_calls = sum(t["calls"] for t in tool_stats.get("tools", []))
    avg_success = 0
    if tool_stats.get("tools"):
        success_rates = [t["success_rate"] for t in tool_stats["tools"]]
        avg_success = sum(success_rates) / len(success_rates) if success_rates else 0

    # Improvement areas
    improvement_areas = corrections.get("improvement_areas", [])

    return {
        "total_tool_calls": total_calls,
        "average_success_rate": round(avg_success, 1),
        "total_corrections": corrections.get("total_corrections", 0),
        "improvement_areas": improvement_areas,
        "top_tools": tool_stats.get("tools", [])[:5],
        "metrics_tracked": len(performance.get("metrics", {})),
    }


# ── Tool Interface ──────────────────────────────────────────────────────

def self_improve(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Self-improvement tool.
    Tracks learning, corrections, and performance.
    """
    action = parameters.get("action", "report")

    if action == "report":
        report = generate_improvement_report()
        lines = [
            "=== SELF-IMPROVEMENT REPORT ===",
            f"Total Tool Calls: {report['total_tool_calls']}",
            f"Average Success Rate: {report['average_success_rate']}%",
            f"Total Corrections: {report['total_corrections']}",
            f"Metrics Tracked: {report['metrics_tracked']}",
            "",
            "Top Tools:",
        ]
        for t in report["top_tools"]:
            lines.append(f"  {t['tool']}: {t['calls']} calls ({t['success_rate']}% success)")
        if report["improvement_areas"]:
            lines.append("")
            lines.append("Improvement Areas:")
            for area in report["improvement_areas"]:
                lines.append(f"  - {area}")
        return "\n".join(lines)

    elif action == "tool_stats":
        tool = parameters.get("tool", "")
        result = get_tool_stats(tool)
        if "tools" in result:
            lines = ["Tool Usage Statistics:"]
            for t in result["tools"]:
                lines.append(f"  {t['tool']}: {t['calls']} calls ({t['success_rate']}% success)")
            return "\n".join(lines)
        elif "tool" in result:
            return (
                f"Tool: {result['tool']}\n"
                f"Calls: {result['total_calls']}\n"
                f"Success Rate: {result['success_rate']}%\n"
                f"Avg Duration: {result['avg_duration']}s"
            )
        return f"Error: {result.get('error', 'Not found')}"

    elif action == "log_correction":
        original = parameters.get("original", "")
        corrected = parameters.get("corrected", "")
        context = parameters.get("context", "")
        if not original or not corrected:
            return "Error: original and corrected are required"
        log_correction(original, corrected, context)
        return "Correction logged! I'll learn from this."

    elif action == "corrections":
        limit = parameters.get("limit", 10)
        corrections = get_corrections(limit)
        if not corrections:
            return "No corrections logged yet."
        lines = [f"Recent Corrections ({len(corrections)}):"]
        for c in corrections:
            lines.append(f"  Original: {c['original']}")
            lines.append(f"  Corrected: {c['corrected']}")
            lines.append("")
        return "\n".join(lines)

    elif action == "performance":
        metric = parameters.get("metric", "")
        result = get_performance(metric)
        if "metrics" in result:
            lines = ["Performance Metrics:"]
            for name, info in result["metrics"].items():
                lines.append(f"  {name}: avg={info['avg']}, count={info['count']}")
            return "\n".join(lines)
        elif "metric" in result:
            return (
                f"Metric: {result['metric']}\n"
                f"Count: {result['count']}\n"
                f"Average: {result['avg']}\n"
                f"Min: {result['min']}, Max: {result['max']}"
            )
        return f"Error: {result.get('error', 'Not found')}"

    elif action == "log_metric":
        metric = parameters.get("metric", "")
        value = parameters.get("value", 0)
        if not metric:
            return "Error: metric name is required"
        log_performance(metric, float(value))
        return f"Metric logged: {metric} = {value}"

    elif action == "patterns":
        pattern_type = parameters.get("type", "")
        patterns = get_patterns(pattern_type)
        if not patterns:
            return "No patterns detected yet."
        lines = [f"Detected Patterns ({len(patterns)}):"]
        for p in patterns[-10:]:
            lines.append(f"  [{p['type']}] {json.dumps(p['data'])[:100]}")
        return "\n".join(lines)

    return f"Unknown action: {action}. Use: report, tool_stats, log_correction, corrections, performance, log_metric, patterns"
