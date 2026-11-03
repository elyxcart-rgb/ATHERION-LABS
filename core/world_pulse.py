"""SONIC AI — World Pulse.

Real-time ambient awareness: CPU, RAM, battery, network, weather, time-of-day.
Like JARVIS's peripheral sensors — always-on vitals SONIC can report on demand.

Public API:
    WorldPulse()
    .vitals() -> dict            # CPU/RAM/battery/network snapshot
    .weather(city=None) -> dict  # cached weather (5-min TTL)
    .heartbeat() -> dict         # compact pulse for dashboard
"""
from __future__ import annotations

import json
import os
import platform
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class WorldPulse:
    """Always-on vitals sampler for the SONIC dashboard."""

    def __init__(self, cache_dir: str | Path = "~/.sonic_brain"):
        self._cache_dir = Path(cache_dir).expanduser()
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._last_vitals: Optional[dict] = None
        self._last_vitals_t = 0.0
        self._weather_cache: Optional[dict] = None
        self._weather_t = 0.0
        self._started = time.time()

    # ── Vitals ───────────────────────────────────────────────────────────────

    def vitals(self) -> dict:
        """Return CPU/RAM/battery/network snapshot. Cached 2 seconds."""
        with self._lock:
            now = time.time()
            if self._last_vitals and now - self._last_vitals_t < 2.0:
                return self._last_vitals
            result = self._sample_vitals()
            self._last_vitals = result
            self._last_vitals_t = now
            return result

    def _sample_vitals(self) -> dict:
        result = {
            "timestamp": time.time(),
            "platform": platform.platform(),
            "uptime_s": time.time() - self._started,
        }

        # CPU
        try:
            import psutil
            result["cpu_pct"] = psutil.cpu_percent(interval=None)
            result["cpu_count"] = psutil.cpu_count(logical=True)
        except Exception:
            result["cpu_pct"] = None
            result["cpu_count"] = os.cpu_count()

        # RAM
        try:
            import psutil
            vm = psutil.virtual_memory()
            result["ram_used_mb"] = vm.used // (1024 * 1024)
            result["ram_total_mb"] = vm.total // (1024 * 1024)
            result["ram_pct"] = vm.percent
        except Exception:
            result["ram_pct"] = None

        # Battery
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt is not None:
                result["battery_pct"] = batt.percent
                result["battery_plugged"] = batt.power_plugged
        except Exception:
            result["battery_pct"] = None

        # Disk (primary)
        try:
            import shutil
            usage = shutil.disk_usage("C:\\" if os.name == "nt" else "/")
            result["disk_used_gb"] = round(usage.used / (1024**3), 1)
            result["disk_total_gb"] = round(usage.total / (1024**3), 1)
            result["disk_pct"] = round((usage.used / usage.total) * 100, 1)
        except Exception:
            result["disk_pct"] = None

        # Net I/O counters
        try:
            import psutil
            net = psutil.net_io_counters()
            result["net_sent_mb"] = round(net.bytes_sent / (1024**2), 2)
            result["net_recv_mb"] = round(net.bytes_recv / (1024**2), 2)
        except Exception:
            result["net_sent_mb"] = None
            result["net_recv_mb"] = None

        # Time of day
        now = datetime.now()
        result["local_time"] = now.strftime("%H:%M:%S")
        result["local_date"] = now.strftime("%Y-%m-%d")
        result["day_of_week"] = now.strftime("%A")

        return result

    # ── Weather ──────────────────────────────────────────────────────────────

    def weather(self, city: Optional[str] = None, ttl_seconds: float = 300.0) -> dict:
        """Cached weather lookup. Returns a fallback dict if network unavailable."""
        with self._lock:
            now = time.time()
            if self._weather_cache and now - self._weather_t < ttl_seconds:
                return self._weather_cache
            result = self._fetch_weather(city or "auto")
            self._weather_cache = result
            self._weather_t = now
            return result

    def _fetch_weather(self, city: str) -> dict:
        # Try wttr.in (no API key needed, returns JSON)
        try:
            import urllib.request
            import urllib.parse
            url = f"https://wttr.in/{urllib.parse.quote(city)}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "SONIC-AI/3.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = r.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
                current = (data.get("current_condition") or [{}])[0]
                area = (data.get("nearest_area") or [{}])[0]
                return {
                    "city": (area.get("areaName") or [{}])[0].get("value", city),
                    "country": (area.get("country") or [{}])[0].get("value", ""),
                    "temp_c": current.get("temp_C", "?"),
                    "temp_f": current.get("temp_F", "?"),
                    "description": (current.get("weatherDesc") or [{}])[0].get("value", ""),
                    "humidity": current.get("humidity", "?"),
                    "wind_kph": current.get("windspeedKmph", "?"),
                    "feels_like_c": current.get("FeelsLikeC", "?"),
                    "source": "wttr.in",
                }
        except Exception as e:
            # Fallback: synthesize a placeholder so the dashboard never breaks
            return {
                "city": city,
                "country": "",
                "temp_c": "n/a",
                "temp_f": "n/a",
                "description": "weather offline",
                "humidity": "n/a",
                "wind_kph": "n/a",
                "feels_like_c": "n/a",
                "source": "fallback",
                "error": str(e),
            }

    # ── Compact heartbeat ────────────────────────────────────────────────────

    def heartbeat(self) -> dict:
        """Tiny pulse summary for the cinematic HUD strip."""
        v = self.vitals()
        return {
            "cpu_pct": v.get("cpu_pct"),
            "ram_pct": v.get("ram_pct"),
            "battery_pct": v.get("battery_pct"),
            "local_time": v.get("local_time"),
            "uptime_s": v.get("uptime_s"),
        }
