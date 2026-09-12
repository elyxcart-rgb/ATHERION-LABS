"""SONIC AI — Location Context Service.

Main entry point for all location operations.
Integrates provider, cache, permission, and memory.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .models import Location, LocationSource, LocationConfidence, PermissionState
from .provider import LocationProvider
from .cache import LocationCache


class LocationContext:
    _instance = None

    def __init__(self):
        self._provider = LocationProvider()
        self._cache = LocationCache()
        self._permission = PermissionState.NOT_ASKED
        self._current_user_id = ""
        self._saved_city = ""
        self._auto_enabled = True
        self._override: Optional[Location] = None
        self._settings_path = Path.home() / "AppData" / "Local" / "SONIC AI" / "location_settings.json"
        self._load_settings()

    @classmethod
    def get_instance(cls) -> LocationContext:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_settings(self) -> None:
        if self._settings_path.exists():
            try:
                with open(self._settings_path, "r") as f:
                    data = json.load(f)
                self._permission = PermissionState(data.get("permission", "not_asked"))
                self._saved_city = data.get("saved_city", "")
                self._auto_enabled = data.get("auto_enabled", True)
            except Exception:
                pass

    def _save_settings(self) -> None:
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._settings_path, "w") as f:
                json.dump({
                    "permission": self._permission.value,
                    "saved_city": self._saved_city,
                    "auto_enabled": self._auto_enabled,
                }, f, indent=2)
        except Exception:
            pass

    def set_user(self, user_id: str) -> None:
        if user_id != self._current_user_id:
            self._current_user_id = user_id
            self._override = None
            self._cache._memory = None
            print(f"[LOCATION] User context set: {user_id[:8]}...")

    def clear_user(self) -> None:
        self._current_user_id = ""
        self._override = None
        self._cache._memory = None
        self._permission = PermissionState.NOT_ASKED

    def get_permission_state(self) -> PermissionState:
        return self._permission

    def request_permission(self) -> bool:
        if self._permission == PermissionState.GRANTED:
            return True
        if self._permission == PermissionState.EXPLICIT_OFF:
            return False
        self._permission = PermissionState.GRANTED
        self._save_settings()
        print("[LOCATION] Permission granted")
        return True

    def deny_permission(self) -> None:
        self._permission = PermissionState.DENIED
        self._save_settings()
        print("[LOCATION] Permission denied")

    def set_auto_enabled(self, enabled: bool) -> None:
        self._auto_enabled = enabled
        self._save_settings()

    def set_saved_city(self, city: str) -> None:
        self._saved_city = city
        self._save_settings()
        if city:
            print(f"[LOCATION] Saved city set: {city}")

    def set_override(self, city: str) -> None:
        if city:
            self._override = Location(
                city=city,
                source=LocationSource.USER_OVERRIDE,
                confidence=LocationConfidence.HIGH,
                captured_at=time.time(),
            )
            print(f"[LOCATION] Override set: {city}")

    def clear_override(self) -> None:
        self._override = None

    def get_current(self, require_fresh: bool = False) -> Optional[Location]:
        if self._override:
            return self._override

        if not self._auto_enabled or self._permission == PermissionState.DENIED:
            return self._get_fallback()

        uid = self._current_user_id
        if uid:
            cached = self._cache.get(uid)
            if cached and cached.is_fresh:
                return cached

        ip_loc = self._provider.get_ip_location()
        if ip_loc and ip_loc.city:
            if uid:
                self._cache.put(uid, ip_loc)
            return ip_loc

        return self._get_fallback()

    def _get_fallback(self) -> Optional[Location]:
        if self._saved_city:
            return Location(
                city=self._saved_city,
                source=LocationSource.PROFILE,
                confidence=LocationConfidence.LOW,
            )
        return None

    def get_city(self) -> str:
        loc = self.get_current()
        if loc and loc.city:
            return loc.city
        return ""

    def get_timezone(self) -> str:
        loc = self.get_current()
        if loc and loc.timezone:
            return loc.timezone
        return ""

    def get_country(self) -> str:
        loc = self.get_current()
        if loc and loc.country:
            return loc.country
        return ""

    def is_available(self) -> bool:
        loc = self.get_current()
        return loc is not None and loc.city != ""

    def refresh(self) -> Optional[Location]:
        if self._current_user_id:
            self._cache.clear(self._current_user_id)
        return self.get_current()

    def load_from_profile(self, profile: dict) -> None:
        loc = self._provider.get_profile_location(profile)
        if loc and loc.city and not self._saved_city:
            self._saved_city = loc.city
            self._save_settings()

    def load_from_memory(self, city: str) -> None:
        if city and not self._saved_city:
            self._saved_city = city
            self._save_settings()

    def get_status(self) -> dict:
        loc = self.get_current()
        return {
            "available": self.is_available(),
            "permission": self._permission.value,
            "auto_enabled": self._auto_enabled,
            "saved_city": self._saved_city,
            "current_location": loc.to_compact_str() if loc else "None",
            "source": loc.source.value if loc else "none",
            "confidence": loc.confidence.value if loc else "none",
            "has_override": self._override is not None,
        }
