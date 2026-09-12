"""SONIC AI — Location Cache.

Caches location to avoid repeated IP lookups.
Persists to disk per-user.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .models import Location


class LocationCache:
    FRESHNESS_HOURS = 2

    def __init__(self, cache_dir: Optional[str] = None):
        if cache_dir is None:
            cache_dir = str(Path.home() / "AppData" / "Local" / "SONIC AI")
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory: Optional[Location] = None

    def _cache_path(self, user_id: str) -> Path:
        safe_id = user_id.replace("/", "_").replace("\\", "_")
        return self._dir / f"location_{safe_id}.json"

    def get(self, user_id: str) -> Optional[Location]:
        if self._memory and self._memory.is_fresh:
            return self._memory
        path = self._cache_path(user_id)
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            loc = Location.from_dict(data)
            self._memory = loc
            if loc.is_fresh:
                print(f"[LOCATION] Cache hit: {loc.to_compact_str()} ({loc.age_hours:.1f}h old)")
                return loc
            else:
                print(f"[LOCATION] Cache stale: {loc.to_compact_str()} ({loc.age_hours:.1f}h old)")
                return None
        except Exception:
            return None

    def put(self, user_id: str, location: Location) -> None:
        self._memory = location
        path = self._cache_path(user_id)
        try:
            with open(path, "w") as f:
                json.dump(location.to_dict(), f, indent=2)
            print(f"[LOCATION] Cached: {location.to_compact_str()}")
        except Exception as e:
            print(f"[LOCATION] Cache write failed: {e}")

    def clear(self, user_id: str) -> None:
        self._memory = None
        path = self._cache_path(user_id)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass

    def clear_all(self) -> None:
        self._memory = None
        for f in self._dir.glob("location_*.json"):
            try:
                f.unlink()
            except Exception:
                pass
