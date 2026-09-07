"""SONIC AI — Location Data Model."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LocationSource(Enum):
    IP_GEO = "ip_geo"
    PROFILE = "profile"
    USER_OVERRIDE = "user_override"
    MEMORY = "memory"
    UNKNOWN = "unknown"


class LocationConfidence(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class PermissionState(Enum):
    NOT_ASKED = "not_asked"
    GRANTED = "granted"
    DENIED = "denied"
    EXPLICIT_OFF = "explicit_off"


@dataclass
class Location:
    latitude: float = 0.0
    longitude: float = 0.0
    accuracy: float = 0.0
    city: str = ""
    region: str = ""
    country: str = ""
    country_code: str = ""
    timezone: str = ""
    source: LocationSource = LocationSource.UNKNOWN
    confidence: LocationConfidence = LocationConfidence.NONE
    captured_at: float = 0.0
    permission_state: PermissionState = PermissionState.NOT_ASKED

    @property
    def is_valid(self) -> bool:
        return bool(self.city) and self.confidence != LocationConfidence.NONE

    @property
    def is_fresh(self) -> bool:
        if self.captured_at == 0:
            return False
        age_hours = (time.time() - self.captured_at) / 3600
        return age_hours < 2

    @property
    def age_hours(self) -> float:
        if self.captured_at == 0:
            return float("inf")
        return (time.time() - self.captured_at) / 3600

    def to_compact_str(self) -> str:
        parts = []
        if self.city:
            parts.append(self.city)
        if self.region and self.region != self.city:
            parts.append(self.region)
        if self.country:
            parts.append(self.country)
        return ", ".join(parts) if parts else "Unknown"

    def to_context_block(self) -> str:
        lines = ["LOCATION CONTEXT:"]
        if self.city:
            lines.append(f"City: {self.city}")
        if self.region:
            lines.append(f"Region: {self.region}")
        if self.country:
            lines.append(f"Country: {self.country}")
        if self.timezone:
            lines.append(f"Timezone: {self.timezone}")
        lines.append(f"Source: {self.source.value}")
        lines.append(f"Confidence: {self.confidence.value}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "accuracy": self.accuracy,
            "city": self.city,
            "region": self.region,
            "country": self.country,
            "country_code": self.country_code,
            "timezone": self.timezone,
            "source": self.source.value,
            "confidence": self.confidence.value,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Location:
        return cls(
            latitude=data.get("latitude", 0.0),
            longitude=data.get("longitude", 0.0),
            accuracy=data.get("accuracy", 0.0),
            city=data.get("city", ""),
            region=data.get("region", ""),
            country=data.get("country", ""),
            country_code=data.get("country_code", ""),
            timezone=data.get("timezone", ""),
            source=LocationSource(data.get("source", "unknown")),
            confidence=LocationConfidence(data.get("confidence", "none")),
            captured_at=data.get("captured_at", 0.0),
        )
