"""SONIC AI — WhatsApp Adapter (WhatsApp Web).

Uses Playwright to drive web.whatsapp.com — find contact, type message,
send. Falls back to opening WhatsApp Web in default browser when
Playwright is unavailable.

WARNING: WhatsApp Web session is user-owned. Adapter never bypasses
CAPTCHA / MFA / 2FA — pauses and asks user to scan QR if not logged in.
"""
from __future__ import annotations

import logging
import time
import webbrowser
from typing import Optional

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.whatsapp")


class WhatsAppAdapter(AppAdapter):
    name = "whatsapp"
    processes = ["chrome", "msedge", "firefox", "brave"]   # WhatsApp Web lives in a browser
    capabilities = [
        AdapterCapability.NAVIGATE, AdapterCapability.CLICK,
        AdapterCapability.TYPE, AdapterCapability.EXTRACT_TEXT,
    ]
    WA_URL = "https://web.whatsapp.com"

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()
        # All WhatsApp operations route through the BrowserAdapter (Playwright)
        try:
            from .browser import BrowserAdapter
            br = BrowserAdapter()
            # ensure we're on web.whatsapp.com
            nav_action = type(action)(
                action_type=ActionType.NAVIGATE,
                target_url=self.WA_URL,
                target_name=action.target_name,
            )
            nav_result = br.execute(nav_action, state)
            if not nav_result.success:
                # fallback: open in default browser
                webbrowser.open(self.WA_URL)
                return AdapterResult(
                    success=False,
                    error="playwright unavailable; opened WA Web in default browser — please log in",
                    method="whatsapp.webbrowser_fallback",
                )

            if action.action_type == ActionType.TYPE:
                # Send message: click contact, type into message box, press enter
                contact = action.target_name or action.parameters.get("contact", "")
                message = action.text or action.parameters.get("message", "")
                page = br._page
                if not page:
                    return AdapterResult(success=False, error="no page", method="whatsapp.no_page")
                # Search for contact
                try:
                    page.locator('div[contenteditable="true"][title="Search input textbox"]').fill(contact)
                    time.sleep(0.5)
                except Exception as exc:
                    return AdapterResult(success=False, error=f"contact search failed: {exc}",
                                          method="whatsapp.contact_fail")
                page.locator(f'span[title="{contact}"]').first.click()
                # Type message
                try:
                    box = page.locator('div[contenteditable="true"][title="Type a message"]')
                    box.fill(message)
                    box.press("Enter")
                except Exception as exc:
                    return AdapterResult(success=False, error=f"send failed: {exc}",
                                          method="whatsapp.send_fail")
                return AdapterResult(
                    success=True, method="whatsapp.send",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            if action.action_type == ActionType.CLICK:
                contact = action.target_name or action.target_text or ""
                br._page.locator(f'span[title="{contact}"]').first.click()
                return AdapterResult(
                    success=True, method="whatsapp.open_chat",
                    duration_ms=(time.time() - t0) * 1000.0,
                )

            return AdapterResult(
                success=False,
                error=f"whatsapp adapter does not implement {action.action_type.value}",
                method="whatsapp.unsupported",
            )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="whatsapp.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        return {"service": "whatsapp-web"}
