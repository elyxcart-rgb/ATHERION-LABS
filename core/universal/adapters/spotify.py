"""SONIC AI — Spotify Adapter.

Uses the Spotify Web Player for browser-based control. For desktop, falls
back to Windows Media keys + spotipy (if installed) for richer control.

NOTE: Desktop automation uses keyboard media keys which is unreliable
without a focused Spotify window; prefer Web Player through BrowserAdapter.
"""
from __future__ import annotations

import logging
import time
import webbrowser

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.spotify")


class SpotifyAdapter(AppAdapter):
    name = "spotify"
    processes = ["spotify", "chrome", "msedge", "firefox", "brave"]
    capabilities = [
        AdapterCapability.NAVIGATE, AdapterCapability.CLICK,
        AdapterCapability.TYPE, AdapterCapability.KEYPRESS,
    ]
    WEB_URL = "https://open.spotify.com"

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        try:
            from .browser import BrowserAdapter
            br = BrowserAdapter()
            nav = type(action)(
                action_type=ActionType.NAVIGATE,
                target_url=self.WEB_URL,
            )
            nav_result = br.execute(nav, state)
            if not nav_result.success:
                webbrowser.open(self.WEB_URL)
                return AdapterResult(
                    success=False,
                    error="playwright unavailable; opened Spotify Web in default browser",
                    method="spotify.webbrowser_fallback",
                )

            if action.action_type == ActionType.TYPE:
                query = action.target_text or action.text or action.parameters.get("query", "")
                page = br._page
                if page:
                    try:
                        page.locator('input[placeholder="Search for songs, artists, albums, podcasts, & playlists"]').fill(query)
                        page.keyboard.press("Enter")
                        time.sleep(1.0)
                        page.locator('div[data-testid="tracklist-row"]').first.click()
                    except Exception as exc:
                        return AdapterResult(success=False, error=str(exc), method="spotify.search_fail")
                return AdapterResult(
                    success=True, method="spotify.search_and_play",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            if action.action_type == ActionType.KEYPRESS:
                # map common keys
                page = br._page
                if page:
                    key_map = {
                        "play": "k",
                        "pause": "k",
                        "next": "j",
                        "prev": "shift+j",
                        "mute": "m",
                    }
                    for k in action.keys:
                        page.keyboard.press(key_map.get(k.lower(), k.lower()))
                return AdapterResult(
                    success=True, method="spotify.media_key",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            return AdapterResult(
                success=False,
                error=f"spotify adapter does not implement {action.action_type.value}",
                method="spotify.unsupported",
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="spotify.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        return {"service": "spotify-web"}
