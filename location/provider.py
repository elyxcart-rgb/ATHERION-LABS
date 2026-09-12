"""SONIC AI — Location Provider.

Uses IP-based geolocation as primary source.
Falls back to profile/memory location.
"""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Optional

from .models import Location, LocationSource, LocationConfidence


class LocationProvider:
    IP_SERVICES = [
        {
            "url": "http://ip-api.com/json/?fields=status,country,countryCode,regionName,city,lat,lon,timezone",
            "parse": lambda d: Location(
                latitude=d.get("lat", 0.0),
                longitude=d.get("lon", 0.0),
                city=d.get("city", ""),
                region=d.get("regionName", ""),
                country=d.get("country", ""),
                country_code=d.get("countryCode", ""),
                timezone=d.get("timezone", ""),
                source=LocationSource.IP_GEO,
                confidence=LocationConfidence.MEDIUM,
            ),
        },
        {
            "url": "https://ipapi.co/json/",
            "parse": lambda d: Location(
                latitude=d.get("latitude", 0.0),
                longitude=d.get("longitude", 0.0),
                city=d.get("city", ""),
                region=d.get("region", ""),
                country=d.get("country_name", ""),
                country_code=d.get("country_code", ""),
                timezone=d.get("timezone", ""),
                source=LocationSource.IP_GEO,
                confidence=LocationConfidence.MEDIUM,
            ),
        },
    ]

    def get_ip_location(self) -> Optional[Location]:
        for svc in self.IP_SERVICES:
            try:
                req = urllib.request.Request(
                    svc["url"],
                    headers={"User-Agent": "SONIC-AI/1.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    if data.get("status") == "failed":
                        continue
                    loc = svc["parse"](data)
                    if loc.city:
                        import time
                        loc.captured_at = time.time()
                        print(f"[LOCATION] IP geolocation: {loc.to_compact_str()}")
                        return loc
            except Exception as e:
                print(f"[LOCATION] IP service failed: {e}")
                continue
        return None

    def get_profile_location(self, profile: dict) -> Optional[Location]:
        loc_data = profile.get("location", "")
        tz = profile.get("timezone", "")
        if not loc_data:
            return None
        return Location(
            city=loc_data,
            timezone=tz,
            source=LocationSource.PROFILE,
            confidence=LocationConfidence.LOW,
        )

    def get_memory_location(self, memory_city: str) -> Optional[Location]:
        if not memory_city:
            return None
        return Location(
            city=memory_city,
            source=LocationSource.MEMORY,
            confidence=LocationConfidence.LOW,
        )
