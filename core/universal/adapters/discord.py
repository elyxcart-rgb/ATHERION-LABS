"""SONIC AI — Discord Adapter.

Uses Playwright to drive Discord Web. Like WhatsApp, the session is
user-owned. Adapter never bypasses authentication.
"""
from __future__ import annotations

import logging
import time
import webbrowser

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.discord")


class DiscordAdapter(AppAdapter):
    name = "discord"
    processes = ["chrome", "msedge", "firefox", "brave", "discord"]
    capabilities = [
        AdapterCapability.NAVIGATE, AdapterCapability.CLICK,
        AdapterCapability.TYPE,
    ]
    DISCORD_URL = "https://discord.com/channels/@me"

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        try:
            from .browser import BrowserAdapter
            br = BrowserAdapter()
            nav = type(action)(
                action_type=ActionType.NAVIGATE,
                target_url=self.DISCORD_URL,
            )
            nav_result = br.execute(nav, state)
            if not nav_result.success:
                webbrowser.open(self.DISCORD_URL)
                return AdapterResult(
                    success=False,
                    error="playwright unavailable; opened Discord in default browser",
                    method="discord.webbrowser_fallback",
                )

            if action.action_type == ActionType.TYPE:
                channel = action.target_name or action.parameters.get("channel", "")
                message = action.text or action.parameters.get("message", "")
                page = br._page
                if not page:
                    return AdapterResult(success=False, error="no page", method="discord.no_page")
                try:
                    page.locator(f'div[aria-label*="{channel}"]').first.click()
                    time.sleep(0.5)
                    box = page.locator('div[role="textbox"]')
                    box.fill(message)
                    box.press("Enter")
                except Exception as exc:
                    return AdapterResult(success=False, error=str(exc), method="discord.send_fail")
                return AdapterResult(
                    success=True, method="discord.send",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            return AdapterResult(
                success=False,
                error=f"discord adapter does not implement {action.action_type.value}",
                method="discord.unsupported",
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="discord.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        return {"service": "discord-web"}
