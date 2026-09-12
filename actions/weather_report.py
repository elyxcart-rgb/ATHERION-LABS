"""SONIC AI — Weather Report Tool.

Uses LocationContext for auto-city detection.
Opens Google Weather search in browser.
"""
from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus
from typing import Optional


def weather_action(
    parameters: dict,
    player=None,
    session_memory=None,
    location_context=None,
) -> str:
    city = parameters.get("city", "").strip()
    when = parameters.get("time", "today").strip() or "today"

    if not city and location_context:
        loc = location_context.get_current()
        if loc and loc.city:
            city = loc.city
            source = loc.source.value
            print(f"[Weather] Auto-location: {city} (source: {source})")

    if not city:
        msg = "Sir, I need a city for the weather report. Where are you?"
        _log(msg, player)
        return msg

    search_query = f"weather in {city} {when}"
    url = f"https://www.google.com/search?q={quote_plus(search_query)}"

    try:
        opened = webbrowser.open(url)
        if not opened:
            raise RuntimeError("webbrowser.open returned False")
    except Exception as e:
        msg = f"Sir, I couldn't open the browser for weather: {e}"
        _log(msg, player)
        return msg

    msg = f"Showing weather for {city}, {when}."
    _log(msg, player)

    if session_memory:
        try:
            session_memory.set_last_search(query=search_query, response=msg)
        except Exception:
            pass

    return msg


def _log(message: str, player=None) -> None:
    print(f"[Weather] {message}")
    if player:
        try:
            player.write_log(f"SONIC: {message}")
        except Exception:
            pass
