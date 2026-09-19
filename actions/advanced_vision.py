"""SONIC AI — Advanced Vision System

Enhanced screen understanding with:
- OCR text extraction from screenshots
- UI element detection (buttons, forms, links)
- Screen monitoring with change detection
- Multi-region analysis
- Visual reasoning with Gemini Vision

Usage:
    "Screen pe kya hai?" → full screen analysis
    "Is button pe click karo" → UI element detection
    "Ye text padho" → OCR extraction
    "Screen monitor karo" → continuous monitoring
"""
from __future__ import annotations

import io
import json
import time
import base64
import threading
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ADVANCED_VISION")

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

from google import genai
from google.genai import types as gtypes

# ── Config ──────────────────────────────────────────────────────────────
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def _load_api_key() -> str:
    """Load Gemini API key."""
    if _CONFIG_PATH.exists():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("gemini_api_key", "")
        except Exception:
            pass
    return ""


def _get_client() -> genai.Client | None:
    """Get Gemini API client."""
    api_key = _load_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


# ── Screen Capture ──────────────────────────────────────────────────────

def _capture_screen(region: dict = None) -> tuple[bytes, str]:
    """Capture screenshot. Returns (jpeg_bytes, mime_type)."""
    if not _MSS:
        raise RuntimeError("mss not installed")

    with mss.mss() as sct:
        monitors = sct.monitors
        target = monitors[1] if len(monitors) > 1 else monitors[0]

        if region:
            target = {
                "left": region.get("x", 0),
                "top": region.get("y", 0),
                "width": region.get("width", 1920),
                "height": region.get("height", 1080),
            }

        shot = sct.grab(target)
        png = mss.tools.to_png(shot.rgb, shot.size)

    # Compress to JPEG
    if _PIL:
        img = PIL.Image.open(io.BytesIO(png)).convert("RGB")
        img.thumbnail((1280, 720), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=82)
        return buf.getvalue(), "image/jpeg"

    return png, "image/png"


def _image_to_base64(img_bytes: bytes) -> str:
    """Convert image bytes to base64 string."""
    return base64.b64encode(img_bytes).decode("ascii")


# ── OCR Text Extraction ────────────────────────────────────────────────

def extract_text(region: dict = None) -> dict:
    """
    Extract all visible text from screen using Gemini Vision OCR.
    """
    client = _get_client()
    if not client:
        return {"error": "Gemini API not configured"}

    try:
        img_bytes, mime = _capture_screen(region)
        b64 = _image_to_base64(img_bytes)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                gtypes.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime),
                "Extract ALL visible text from this screenshot. Return the text exactly as it appears, preserving layout. Do not describe the image, just extract text."
            ],
        )

        return {
            "success": True,
            "text": response.text or "",
            "image_size": len(img_bytes),
        }

    except Exception as e:
        return {"error": f"OCR failed: {e}"}


def extract_text_region(x: int, y: int, width: int, height: int) -> dict:
    """Extract text from a specific screen region."""
    return extract_text(region={"x": x, "y": y, "width": width, "height": height})


# ── UI Element Detection ───────────────────────────────────────────────

def detect_ui_elements(region: dict = None) -> dict:
    """
    Detect clickable UI elements on screen.
    Returns list of elements with positions and types.
    """
    client = _get_client()
    if not client:
        return {"error": "Gemini API not configured"}

    try:
        img_bytes, mime = _capture_screen(region)
        b64 = _image_to_base64(img_bytes)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                gtypes.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime),
                """Analyze this screenshot and identify ALL clickable UI elements.
For each element, provide:
- type: button, link, input, checkbox, dropdown, tab, icon, menu_item
- text: visible text or label
- x: center X coordinate (approximate)
- y: center Y coordinate (approximate)
- description: brief description

Return as JSON array. Example:
[
  {"type": "button", "text": "Submit", "x": 500, "y": 300, "description": "Submit form button"},
  {"type": "link", "text": "Login", "x": 200, "y": 400, "description": "Login link"}
]

Return ONLY the JSON array, no other text."""
            ],
        )

        # Parse JSON response
        text = response.text or ""
        # Try to extract JSON from response
        import re
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            elements = json.loads(json_match.group())
            return {"success": True, "elements": elements, "count": len(elements)}
        else:
            return {"success": True, "elements": [], "raw": text}

    except Exception as e:
        return {"error": f"UI detection failed: {e}"}


def find_element(description: str, region: dict = None) -> dict:
    """
    Find a specific UI element by description.
    Returns the element's position.
    """
    client = _get_client()
    if not client:
        return {"error": "Gemini API not configured"}

    try:
        img_bytes, mime = _capture_screen(region)
        b64 = _image_to_base64(img_bytes)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                gtypes.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime),
                f"""Find the UI element described as: "{description}"

Return ONLY a JSON object with:
- found: true/false
- x: center X coordinate
- y: center Y coordinate
- type: element type
- text: visible text

Example: {{"found": true, "x": 500, "y": 300, "type": "button", "text": "Submit"}}"""
            ],
        )

        text = response.text or ""
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            element = json.loads(json_match.group())
            return element
        else:
            return {"found": False}

    except Exception as e:
        return {"error": f"Element search failed: {e}"}


# ── Screen Analysis ─────────────────────────────────────────────────────

def analyze_screen(question: str = "What is on this screen?", region: dict = None) -> dict:
    """
    Analyze screen content with a custom question.
    General-purpose screen understanding.
    """
    client = _get_client()
    if not client:
        return {"error": "Gemini API not configured"}

    try:
        img_bytes, mime = _capture_screen(region)
        b64 = _image_to_base64(img_bytes)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                gtypes.Part.from_bytes(data=base64.b64decode(b64), mime_type=mime),
                question,
            ],
        )

        return {
            "success": True,
            "answer": response.text or "",
            "image_size": len(img_bytes),
        }

    except Exception as e:
        return {"error": f"Analysis failed: {e}"}


def describe_screen() -> dict:
    """Get a detailed description of what's currently on screen."""
    return analyze_screen("Describe everything visible on this screen in detail. Include text, UI elements, layout, and any notable features.")


# ── Screen Monitoring ───────────────────────────────────────────────────

class ScreenMonitor:
    """Monitors screen for changes."""

    def __init__(self):
        self._monitoring = False
        self._last_hash = None
        self._thread = None
        self._callbacks = []
        self._interval = 2  # seconds

    def start(self, interval: int = 2, callback=None):
        """Start monitoring screen for changes."""
        if self._monitoring:
            return {"message": "Already monitoring"}

        self._monitoring = True
        self._interval = interval
        if callback:
            self._callbacks.append(callback)

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        return {"success": True, "message": f"Screen monitoring started (interval: {interval}s)"}

    def stop(self):
        """Stop monitoring."""
        self._monitoring = False
        if self._thread:
            self._thread.join(timeout=5)
        return {"success": True, "message": "Screen monitoring stopped"}

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self._monitoring:
            try:
                img_bytes, _ = _capture_screen()
                current_hash = hash(img_bytes)

                if self._last_hash is not None and current_hash != self._last_hash:
                    # Screen changed!
                    for cb in self._callbacks:
                        try:
                            cb(img_bytes)
                        except Exception:
                            pass

                self._last_hash = current_hash
                time.sleep(self._interval)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(self._interval)

    @property
    def is_monitoring(self) -> bool:
        return self._monitoring


# Global monitor instance
_monitor = ScreenMonitor()


def start_monitoring(interval: int = 2) -> dict:
    """Start screen monitoring."""
    return _monitor.start(interval)


def stop_monitoring() -> dict:
    """Stop screen monitoring."""
    return _monitor.stop()


def get_monitor_status() -> dict:
    """Get monitoring status."""
    return {
        "monitoring": _monitor.is_monitoring,
        "interval": _monitor._interval,
    }


# ── Multi-Monitor Support ──────────────────────────────────────────────

def list_monitors() -> dict:
    """List all available monitors."""
    if not _MSS:
        return {"error": "mss not installed"}

    with mss.mss() as sct:
        monitors = []
        for i, m in enumerate(sct.monitors):
            monitors.append({
                "index": i,
                "name": f"Monitor {i}" if i > 0 else "All Combined",
                "left": m["left"],
                "top": m["top"],
                "width": m["width"],
                "height": m["height"],
            })
        return {"monitors": monitors, "count": len(monitors)}


def capture_monitor(monitor_index: int = 1) -> dict:
    """Capture a specific monitor."""
    if not _MSS:
        return {"error": "mss not installed"}

    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            if monitor_index >= len(monitors):
                return {"error": f"Monitor {monitor_index} not found"}

            target = monitors[monitor_index]
            shot = sct.grab(target)
            png = mss.tools.to_png(shot.rgb, shot.size)

            # Save to temp file
            import tempfile
            tmp = Path(tempfile.gettempdir()) / f"sonic_monitor_{monitor_index}.png"
            tmp.write_bytes(png)

            return {
                "success": True,
                "monitor": monitor_index,
                "size": f"{target['width']}x{target['height']}",
                "path": str(tmp),
            }
    except Exception as e:
        return {"error": str(e)}


# ── Tool Interface ──────────────────────────────────────────────────────

def advanced_vision(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Advanced vision tool.
    OCR, UI detection, screen analysis, monitoring.
    """
    action = parameters.get("action", "analyze")

    if action == "ocr":
        region = parameters.get("region")
        result = extract_text(region)
        if result.get("success"):
            return f"Extracted Text:\n{result['text'][:2000]}"
        return f"Error: {result.get('error', 'OCR failed')}"

    elif action == "ocr_region":
        x = parameters.get("x", 0)
        y = parameters.get("y", 0)
        w = parameters.get("width", 400)
        h = parameters.get("height", 200)
        result = extract_text_region(x, y, w, h)
        if result.get("success"):
            return f"Extracted Text:\n{result['text'][:2000]}"
        return f"Error: {result.get('error', 'OCR failed')}"

    elif action == "detect_elements":
        region = parameters.get("region")
        result = detect_ui_elements(region)
        if result.get("success"):
            elements = result.get("elements", [])
            lines = [f"Found {len(elements)} UI elements:"]
            for e in elements[:20]:
                lines.append(f"  [{e.get('type', '?')}] '{e.get('text', '')}' at ({e.get('x', '?')}, {e.get('y', '?')})")
            return "\n".join(lines)
        return f"Error: {result.get('error', 'Detection failed')}"

    elif action == "find_element":
        desc = parameters.get("description", "")
        if not desc:
            return "Error: description is required"
        region = parameters.get("region")
        result = find_element(desc, region)
        if result.get("found"):
            return f"Found: '{result.get('text', desc)}' at ({result.get('x')}, {result.get('y')}) [type: {result.get('type', '?')}]"
        return f"Element not found: {desc}"

    elif action == "analyze":
        question = parameters.get("question", "What is on this screen?")
        region = parameters.get("region")
        result = analyze_screen(question, region)
        if result.get("success"):
            return result["answer"][:2000]
        return f"Error: {result.get('error', 'Analysis failed')}"

    elif action == "describe":
        result = describe_screen()
        if result.get("success"):
            return result["answer"][:2000]
        return f"Error: {result.get('error', 'Description failed')}"

    elif action == "start_monitor":
        interval = parameters.get("interval", 2)
        result = start_monitoring(interval)
        return result.get("message", "Monitor started")

    elif action == "stop_monitor":
        result = stop_monitoring()
        return result.get("message", "Monitor stopped")

    elif action == "monitor_status":
        result = get_monitor_status()
        status = "ACTIVE" if result["monitoring"] else "INACTIVE"
        return f"Monitor: {status} (interval: {result['interval']}s)"

    elif action == "list_monitors":
        result = list_monitors()
        if "monitors" in result:
            lines = [f"Monitors ({result['count']}):"]
            for m in result["monitors"]:
                lines.append(f"  [{m['index']}] {m['name']} - {m['width']}x{m['height']}")
            return "\n".join(lines)
        return f"Error: {result.get('error', 'Failed')}"

    elif action == "capture_monitor":
        idx = parameters.get("index", 1)
        result = capture_monitor(idx)
        if result.get("success"):
            return f"Captured Monitor {idx}: {result['size']} → {result['path']}"
        return f"Error: {result.get('error', 'Failed')}"

    return f"Unknown action: {action}. Use: ocr, ocr_region, detect_elements, find_element, analyze, describe, start_monitor, stop_monitor, monitor_status, list_monitors, capture_monitor"
