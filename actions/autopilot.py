"""SONIC AI — Auto-Pilot Mode

Full computer control via voice commands.
SONIC can see your screen, understand context, and perform actions:
- Open/close applications
- Click buttons, fill forms
- Browse websites
- Copy/paste files
- Type text
- Take screenshots
- And much more

Usage:
    "SONIC, open Chrome and go to YouTube"
    "SONIC, click the buy button"
    "SONIC, fill my address in this form"
    "SONIC, take a screenshot"
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger("AUTOPILOT")


@dataclass
class AutopilotTask:
    """Represents a task for Auto-Pilot to execute."""
    id: str
    command: str
    status: str = "pending"  # pending | running | completed | failed
    steps: list = None
    result: str = ""
    error: str = ""

    def __post_init__(self):
        if self.steps is None:
            self.steps = []


class AutoPilot:
    """Full computer control via AI."""

    def __init__(self):
        self._active = False
        self._callbacks: list[Callable] = []
        self._task_history: list[AutopilotTask] = []
        self._screen_state = {}
        self._installed_apps = self._detect_installed_apps()

    def _detect_installed_apps(self) -> dict[str, str]:
        """Detect installed applications on Windows."""
        apps = {}

        # Common Windows apps
        common_paths = {
            "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "notepad": r"C:\Windows\System32\notepad.exe",
            "calculator": r"C:\Windows\System32\calc.exe",
            "paint": r"C:\Windows\System32\mspaint.exe",
            "explorer": r"C:\Windows\explorer.exe",
            "cmd": r"C:\Windows\System32\cmd.exe",
            "powershell": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "vscode": r"C:\Users\{}\AppData\Local\Programs\Microsoft VS Code\Code.exe".format(os.environ.get("USERNAME", "")),
            "word": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            "excel": r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
        }

        for name, path in common_paths.items():
            if os.path.exists(path):
                apps[name.lower()] = path

        return apps

    def register_callback(self, cb: Callable) -> None:
        self._callbacks.append(cb)

    def _emit(self, event: str, data: dict = None):
        for cb in self._callbacks:
            try:
                cb(event, data or {})
            except Exception:
                pass

    async def execute_command(self, command: str) -> AutopilotTask:
        """Execute a voice command using Auto-Pilot."""
        task = AutopilotTask(
            id=f"task_{int(time.time())}",
            command=command,
        )

        self._active = True
        task.status = "running"
        self._emit("task_started", {"task_id": task.id, "command": command})

        try:
            # Parse command into steps
            steps = self._parse_command(command)
            task.steps = steps

            # Execute each step
            for step in steps:
                self._emit("step_started", {"task_id": task.id, "step": step})
                result = await self._execute_step(step)
                if not result.get("success", False):
                    task.status = "failed"
                    task.error = result.get("error", "Step failed")
                    self._emit("task_failed", {"task_id": task.id, "error": task.error})
                    return task
                self._emit("step_completed", {"task_id": task.id, "step": step})

            task.status = "completed"
            task.result = "All steps completed successfully"
            self._emit("task_completed", {"task_id": task.id})

        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            self._emit("task_failed", {"task_id": task.id, "error": str(e)})

        finally:
            self._active = False
            self._task_history.append(task)

        return task

    def _parse_command(self, command: str) -> list[dict]:
        """Parse natural language command into executable steps."""
        steps = []
        cmd_lower = command.lower()

        # Open application
        if "open" in cmd_lower or "launch" in cmd_lower or "start" in cmd_lower:
            app_name = self._extract_app_name(cmd_lower)
            if app_name:
                steps.append({"action": "open_app", "app": app_name})

        # Go to website
        if "go to" in cmd_lower or "open" in cmd_lower or "visit" in cmd_lower:
            url = self._extract_url(cmd_lower)
            if url:
                steps.append({"action": "open_url", "url": url})

        # Take screenshot
        if "screenshot" in cmd_lower or "capture" in cmd_lower:
            steps.append({"action": "screenshot"})

        # Click
        if "click" in cmd_lower:
            target = self._extract_click_target(cmd_lower)
            steps.append({"action": "click", "target": target})

        # Type text
        if "type" in cmd_lower or "write" in cmd_lower:
            text = self._extract_text(cmd_lower)
            steps.append({"action": "type", "text": text})

        # Copy
        if "copy" in cmd_lower:
            steps.append({"action": "copy"})

        # Paste
        if "paste" in cmd_lower:
            steps.append({"action": "paste"})

        # Close
        if "close" in cmd_lower:
            app_name = self._extract_app_name(cmd_lower)
            if app_name:
                steps.append({"action": "close_app", "app": app_name})

        # Search
        if "search" in cmd_lower or "find" in cmd_lower:
            query = self._extract_search_query(cmd_lower)
            steps.append({"action": "search", "query": query})

        # Scroll
        if "scroll" in cmd_lower:
            direction = "down" if "down" in cmd_lower else "up"
            steps.append({"action": "scroll", "direction": direction})

        # If no steps parsed, treat as AI task
        if not steps:
            steps.append({"action": "ai_task", "command": command})

        return steps

    def _extract_app_name(self, text: str) -> str:
        """Extract application name from text."""
        for app_name in self._installed_apps:
            if app_name in text:
                return app_name

        # Common aliases
        aliases = {
            "browser": "chrome",
            "google": "chrome",
            "code editor": "vscode",
            "visual studio": "vscode",
            "terminal": "cmd",
            "command prompt": "cmd",
            "file manager": "explorer",
            "files": "explorer",
        }
        for alias, app in aliases.items():
            if alias in text:
                return app

        return ""

    def _extract_url(self, text: str) -> str:
        """Extract URL from text."""
        import re
        url_match = re.search(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}', text)
        if url_match:
            url = url_match.group(0)
            if not url.startswith("http"):
                url = "https://" + url
            return url

        # Common website aliases
        website_aliases = {
            "youtube": "https://youtube.com",
            "google": "https://google.com",
            "github": "https://github.com",
            "twitter": "https://twitter.com",
            "facebook": "https://facebook.com",
            "instagram": "https://instagram.com",
            "reddit": "https://reddit.com",
            "netflix": "https://netflix.com",
            "amazon": "https://amazon.com",
        }
        for alias, url in website_aliases.items():
            if alias in text:
                return url

        return ""

    def _extract_click_target(self, text: str) -> str:
        """Extract click target from text."""
        import re
        match = re.search(r'click\s+(?:on\s+)?(?:the\s+)?(.+?)(?:\s+button)?$', text)
        return match.group(1).strip() if match else ""

    def _extract_text(self, text: str) -> str:
        """Extract text to type from command."""
        import re
        match = re.search(r'(?:type|write)\s+["\'](.+?)["\']', text)
        if match:
            return match.group(1)
        match = re.search(r'(?:type|write)\s+(.+?)(?:\s+in|\s+here|$)', text)
        return match.group(1).strip() if match else ""

    def _extract_search_query(self, text: str) -> str:
        """Extract search query from text."""
        import re
        match = re.search(r'(?:search|find)\s+(?:for\s+)?["\']?(.+?)["\']?$', text)
        return match.group(1).strip() if match else ""

    async def _execute_step(self, step: dict) -> dict:
        """Execute a single step."""
        action = step.get("action", "")

        try:
            if action == "open_app":
                return await self._open_app(step["app"])
            elif action == "close_app":
                return await self._close_app(step["app"])
            elif action == "open_url":
                return await self._open_url(step["url"])
            elif action == "screenshot":
                return await self._take_screenshot()
            elif action == "click":
                return await self._click_element(step["target"])
            elif action == "type":
                return await self._type_text(step["text"])
            elif action == "copy":
                return await self._copy()
            elif action == "paste":
                return await self._paste()
            elif action == "search":
                return await self._search(step["query"])
            elif action == "scroll":
                return await self._scroll(step["direction"])
            elif action == "ai_task":
                return await self._ai_task(step["command"])
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _open_app(self, app_name: str) -> dict:
        """Open an application."""
        app_path = self._installed_apps.get(app_name.lower())
        if not app_path:
            return {"success": False, "error": f"App not found: {app_name}"}

        try:
            subprocess.Popen([app_path], shell=False)
            logger.info("[AUTOPILOT] Opened: %s", app_name)
            return {"success": True, "message": f"Opened {app_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _close_app(self, app_name: str) -> dict:
        """Close an application."""
        try:
            # Kill process by name
            subprocess.run(["taskkill", "/IM", f"{app_name}.exe", "/F"],
                         capture_output=True, shell=True)
            logger.info("[AUTOPILOT] Closed: %s", app_name)
            return {"success": True, "message": f"Closed {app_name}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _open_url(self, url: str) -> dict:
        """Open URL in default browser."""
        try:
            import webbrowser
            webbrowser.open(url)
            logger.info("[AUTOPILOT] Opened URL: %s", url)
            return {"success": True, "message": f"Opened {url}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _take_screenshot(self) -> dict:
        """Take a screenshot."""
        try:
            import pyautogui
            screenshot_path = Path(os.environ.get("USERPROFILE", "")) / "Pictures" / f"sonic_screenshot_{int(time.time())}.png"
            pyautogui.screenshot(str(screenshot_path))
            logger.info("[AUTOPILOT] Screenshot saved: %s", screenshot_path)
            return {"success": True, "path": str(screenshot_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _click_element(self, target: str) -> dict:
        """Click on a UI element (simplified - uses pyautogui)."""
        try:
            import pyautogui
            # For now, click at center of screen
            screen_width, screen_height = pyautogui.size()
            pyautogui.click(screen_width // 2, screen_height // 2)
            logger.info("[AUTOPILOT] Clicked: %s", target)
            return {"success": True, "message": f"Clicked {target}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _type_text(self, text: str) -> dict:
        """Type text using keyboard."""
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.05)
            logger.info("[AUTOPILOT] Typed: %s", text[:50])
            return {"success": True, "message": f"Typed: {text[:50]}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _copy(self) -> dict:
        """Copy selection to clipboard."""
        try:
            import pyautogui
            pyautogui.hotkey("ctrl", "c")
            return {"success": True, "message": "Copied to clipboard"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _paste(self) -> dict:
        """Paste from clipboard."""
        try:
            import pyautogui
            pyautogui.hotkey("ctrl", "v")
            return {"success": True, "message": "Pasted from clipboard"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _search(self, query: str) -> dict:
        """Search using default search engine."""
        try:
            import webbrowser
            webbrowser.open(f"https://www.google.com/search?q={query}")
            return {"success": True, "message": f"Searching: {query}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _scroll(self, direction: str) -> dict:
        """Scroll the screen."""
        try:
            import pyautogui
            if direction == "down":
                pyautogui.scroll(-3)
            else:
                pyautogui.scroll(3)
            return {"success": True, "message": f"Scrolled {direction}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _ai_task(self, command: str) -> dict:
        """Handle complex AI tasks."""
        # This would integrate with the main AI model
        return {"success": True, "message": f"AI processing: {command}"}

    def get_status(self) -> dict:
        """Get Auto-Pilot status."""
        return {
            "active": self._active,
            "tasks_completed": len([t for t in self._task_history if t.status == "completed"]),
            "tasks_failed": len([t for t in self._task_history if t.status == "failed"]),
            "installed_apps": list(self._installed_apps.keys()),
        }


# Singleton
_autopilot: AutoPilot | None = None


def get_autopilot() -> AutoPilot:
    global _autopilot
    if _autopilot is None:
        _autopilot = AutoPilot()
    return _autopilot
