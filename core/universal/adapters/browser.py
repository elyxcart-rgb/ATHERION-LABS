"""SONIC AI — Browser Adapter (Chrome/Edge/Firefox).

Uses Playwright for semantic DOM/ARIA control. Falls back to webbrowser
when Playwright is not available.

Public surface:
    BrowserAdapter()
    .handles_processes()  → ["chrome", "msedge", "firefox", "brave"]
    .execute(action, state) → AdapterResult
    .observe(state) → dict
"""
from __future__ import annotations

import logging
import time
import webbrowser
from typing import Optional

from .base import AppAdapter, AdapterResult, AdapterCapability
from .actions_compat import ActionType


logger = logging.getLogger("sonic.adapter.browser")


class BrowserAdapter(AppAdapter):
    name = "browser"
    processes = ["chrome", "msedge", "firefox", "brave", "chromium",
                 "opera", "vivaldi", "msedgewebview2"]
    capabilities = [
        AdapterCapability.NAVIGATE, AdapterCapability.CLICK,
        AdapterCapability.TYPE, AdapterCapability.EXTRACT_TEXT,
        AdapterCapability.LIST_CONTROLS,
    ]

    def __init__(self):
        self._playwright = None
        self._page = None
        self._tried = False

    def _ensure_playwright(self):
        if self._tried:
            return self._playwright
        self._tried = True
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
            self._playwright = sync_playwright
        except ImportError:
            pass
        return self._playwright

    def _attach_or_launch(self) -> AdapterResult:
        pw = self._ensure_playwright()
        if pw is None:
            return AdapterResult(
                success=False,
                error="playwright not installed; install with `pip install playwright && playwright install`",
                method="browser.no_playwright",
            )
        try:
            ctx = pw().start().chromium.connect_over_cdp("http://localhost:9222")
            self._page = ctx.contexts[0].pages[0]
            return AdapterResult(success=True, method="browser.cdp_connect")
        except Exception:
            # fallback to launching a fresh chromium
            try:
                ctx = pw().start().chromium.launch(headless=False)
                self._page = ctx.new_page()
                return AdapterResult(success=True, method="browser.launch")
            except Exception as exc:
                return AdapterResult(
                    success=False, error=str(exc),
                    method="browser.launch_fail",
                )

    def execute(self, action, state) -> AdapterResult:
        t0 = time.time()

        # Navigation can fall back to webbrowser without playwright
        if action.action_type == ActionType.NAVIGATE and action.target_url:
            try:
                webbrowser.open(action.target_url)
                return AdapterResult(
                    success=True,
                    method="browser.webbrowser_open",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.NAVIGATE],
                )
            except Exception as exc:
                return AdapterResult(
                    success=False, error=str(exc),
                    method="browser.webbrowser_fail",
                )

        # All other ops need playwright
        attach = self._attach_or_launch()
        if not attach.success:
            return attach

        try:
            if action.action_type == ActionType.CLICK:
                if action.target_automation_id:
                    locator = self._page.get_by_test_id(action.target_automation_id)
                elif action.target_text:
                    locator = self._page.get_by_text(action.target_text, exact=False)
                elif action.target_name:
                    locator = self._page.get_by_role("button", name=action.target_name)
                else:
                    locator = self._page.locator(f"text={action.target_name or action.target_text}")
                locator.first.click(timeout=5000)
                return AdapterResult(
                    success=True, method="browser.playwright_click",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.CLICK],
                )
            elif action.action_type == ActionType.TYPE:
                if action.target_automation_id:
                    locator = self._page.get_by_test_id(action.target_automation_id)
                elif action.target_name:
                    locator = self._page.get_by_label(action.target_name)
                else:
                    locator = self._page.locator("input, textarea").first
                locator.fill(action.text or "")
                return AdapterResult(
                    success=True, method="browser.playwright_fill",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.TYPE],
                )
            elif action.action_type == ActionType.KEYPRESS:
                self._page.keyboard.press("+".join(action.keys))
                return AdapterResult(
                    success=True, method="browser.playwright_press",
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.KEYPRESS],
                )
            elif action.action_type == ActionType.EXTRACT_TEXT:
                txt = self._page.evaluate("() => document.body.innerText")
                return AdapterResult(
                    success=True, method="browser.extract_text",
                    data={"text": txt[:5000]},
                    duration_ms=(time.time() - t0) * 1000.0,
                    capabilities_used=[AdapterCapability.EXTRACT_TEXT],
                )
            elif action.action_type == ActionType.SCROLL:
                amt = action.scroll_amount or 500
                direction = action.scroll_direction or "down"
                delta = amt if direction == "down" else -amt if direction == "up" else 0
                if delta:
                    self._page.mouse.wheel(0, delta)
                return AdapterResult(
                    success=True, method="browser.scroll",
                    duration_ms=(time.time() - t0) * 1000.0,
                )
            else:
                return AdapterResult(
                    success=False,
                    error=f"browser adapter does not implement {action.action_type.value}",
                    method="browser.unsupported",
                )
        except Exception as exc:
            return AdapterResult(
                success=False, error=str(exc),
                method="browser.execute_fail",
                duration_ms=(time.time() - t0) * 1000.0,
            )

    def observe(self, state) -> dict:
        if not self._ensure_playwright() or self._page is None:
            return {"error": "no playwright page"}
        try:
            return {
                "url": self._page.url,
                "title": self._page.title(),
            }
        except Exception as exc:
            return {"error": str(exc)}
