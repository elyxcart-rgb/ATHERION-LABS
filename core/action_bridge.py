"""SONIC AI — Action Bridge.

PROPER version that respects SONIC's actual action convention:
    def action_name(parameters: dict, response=None, player=None, session_memory=None) -> str

Every SONIC action takes a `parameters` dict as the first argument. The
UniversalRouter extracts slot values (target, query, etc.) which must be
PACKED into a `parameters` dict before calling the action.

This module:
  - Maps routed action_name → (module_path, function_name)
  - Discovers function dynamically if hardcoded name is wrong
  - Builds the correct `parameters` dict from router args
  - Calls with the right signature
  - Returns formatted result
  - Records in proactive pattern DB
  - Provides retry + fallback chain (try multiple actions if one fails)

Public API:
    ActionBridge()
    .execute(action_name, args) -> dict              # returns full result dict
    .execute_text(action_name, args) -> str         # returns formatted string
    .get_available_actions() -> dict
    .get_missing_actions() -> dict
    .get_stats() -> dict
"""
from __future__ import annotations

import importlib
import inspect
import json
import logging
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional, Callable, Any


logger = logging.getLogger("sonic.bridge")


# ═════════════════════════════════════════════════════════════════════════════
# Action mapping — SONIC action_name → (module, function_name)
# Each function takes (parameters: dict, ...) as the SONIC standard
# ═════════════════════════════════════════════════════════════════════════════

_ACTION_MAP: dict[str, tuple[str, str]] = {
    # ── App / window control ─────────────────────────────────────────────
    "open_app":           ("actions.open_app", "open_app"),
    "close_app":          ("actions.open_app", "open_app"),
    "switch_window":      ("actions.desktop", "desktop_control"),
    "launch_app":         ("actions.open_app", "open_app"),

    # ── File system ──────────────────────────────────────────────────────
    "find_file":          ("actions.file_controller", "file_controller"),
    "open_file":          ("actions.file_controller", "file_controller"),
    "create_file":        ("actions.file_controller", "file_controller"),
    "delete_file":        ("actions.file_controller", "file_controller"),
    "move_file":          ("actions.file_controller", "file_controller"),
    "copy_file":          ("actions.file_controller", "file_controller"),
    "rename_file":        ("actions.file_controller", "file_controller"),
    "read_file":          ("actions.file_controller", "file_controller"),
    "list_files":         ("actions.file_controller", "file_controller"),
    "organize_downloads": ("actions.smart_file_manager", "organize_downloads"),
    "cleanup_temp":       ("actions.smart_file_manager", "cleanup_temp"),
    "find_duplicates":    ("actions.smart_file_manager", "find_duplicates"),
    "find_large_files":   ("actions.smart_file_manager", "find_large_files"),

    # ── Web / browser ────────────────────────────────────────────────────
    "web_search":         ("actions.web_search", "web_search"),
    "open_url":           ("actions.browser_control", "browser_control"),
    "play_youtube":       ("__yt_player__", "play"),    # NEW: use our smart player
    "play_list":          ("__yt_player__", "play_list"),
    "yt_pause":           ("__yt_player__", "pause"),
    "yt_resume":          ("__yt_player__", "resume"),
    "yt_next":            ("__yt_player__", "next"),
    "yt_previous":        ("__yt_player__", "previous"),
    "yt_seek":            ("__yt_player__", "seek"),
    "yt_fullscreen":      ("__yt_player__", "fullscreen"),
    "yt_like":            ("__yt_player__", "like"),
    "yt_subscribe":       ("__yt_player__", "subscribe"),
    "yt_autopilot":       ("__yt_player__", "autopilot"),
    "yt_skip_ad":         ("__yt_skipper__", "skip_once"),
    "video_play":         ("__video_ctrl__", "play"),
    "video_pause":        ("__video_ctrl__", "pause"),
    "video_next":         ("__video_ctrl__", "next"),
    "video_previous":     ("__video_ctrl__", "previous"),
    "video_seek":         ("__video_ctrl__", "seek"),
    "video_fullscreen":   ("__video_ctrl__", "fullscreen"),
    "video_mute":         ("__video_ctrl__", "mute"),
    "download":           ("actions.file_download", "file_download"),
    "scrape":             ("actions.universal", "web_summarize"),
    "research":           ("actions.universal", "web_summarize"),

    # ── System ───────────────────────────────────────────────────────────
    "set_volume":         ("actions.computer_settings", "computer_settings"),
    "get_volume":         ("actions.computer_settings", "computer_settings"),
    "volume_up":          ("actions.computer_settings", "computer_settings"),
    "volume_down":        ("actions.computer_settings", "computer_settings"),
    "volume_mute":        ("actions.computer_settings", "computer_settings"),
    "set_brightness":     ("actions.computer_settings", "computer_settings"),
    "lock_computer":      ("actions.computer_control", "computer_control"),
    "shutdown":           ("actions.computer_control", "computer_control"),
    "restart":            ("actions.computer_control", "computer_control"),
    "sleep":              ("actions.computer_control", "computer_control"),
    "screenshot":         ("actions.screen_processor", "screen_process"),

    # ── Productivity ─────────────────────────────────────────────────────
    "set_reminder":       ("actions.reminder", "reminder"),
    "list_reminders":     ("actions.reminder", "reminder"),
    "create_note":        ("actions.smart_clipboard", "smart_clipboard"),
    "clip_text":          ("actions.smart_clipboard", "smart_clipboard"),
    "paste_text":         ("actions.smart_clipboard", "smart_clipboard"),
    "clipboard_history":  ("actions.smart_clipboard", "smart_clipboard"),
    "translate":          ("actions.universal", "web_summarize"),
    "summarize":          ("actions.advanced_vision", "describe_screen"),

    # ── Communication ────────────────────────────────────────────────────
    "send_email":         ("actions.universal", "send_email"),
    "send_message":       ("actions.send_message", "send_message"),
    "draft_email":        ("actions.email_api", "email_api"),

    # ── AI / Code ────────────────────────────────────────────────────────
    "ask_ai":             ("actions.dev_agent", "dev_agent"),
    "generate_code":      ("actions.code_helper", "code_helper"),
    "run_python":         ("__sandbox__", "run_python"),
    "explain_code":       ("actions.code_helper", "code_helper"),

    # ── System info ──────────────────────────────────────────────────────
    "system_status":      ("actions.system_monitor", "get_system_status"),
    "weather":            ("actions.weather_report", "weather_report"),
    "time_now":           ("actions.utility_controls", "system_info"),
    "today_calendar":     ("actions.life_dashboard", "life_dashboard"),
    "disk_space":         ("actions.utility_controls", "system_info"),
    "network_info":       ("actions.utility_controls", "system_info"),
    "display_info":       ("actions.utility_controls", "system_info"),

    # ── Entertainment ────────────────────────────────────────────────────
    "play_music":         ("actions.desktop", "desktop_control"),
    "next_track":         ("__video_ctrl__", "next"),     # NEW: route through universal controller
    "pause_media":        ("__video_ctrl__", "pause"),
    "resume_media":       ("__video_ctrl__", "play"),
    "set_wallpaper":      ("actions.desktop", "desktop_control"),

    # ── Advanced ─────────────────────────────────────────────────────────
    "github_latest":      ("actions.github_api", "github_api"),
    "github_release":     ("actions.github_api", "github_api"),
    "twitter_post":       ("actions.twitter_api", "twitter_api"),
    "flight_search":      ("actions.flight_finder", "flight_finder"),
    "game_update":        ("actions.game_updater", "game_updater"),
    "task_plan":          ("actions.task_planner", "task_planner"),
    "squad_run":          ("actions.squad_agent", "squad_mode"),
    "tool_chain":         ("actions.tool_chain", "tool_chain"),
    "background_monitor": ("actions.background_monitor", "add_monitor"),
    "behavior_log":       ("actions.behavior_analytics", "log_activity"),
    "autopilot":          ("actions.autopilot", "autopilot"),
    "life_dashboard":     ("actions.life_dashboard", "life_dashboard"),
    "recipe_run":         ("actions.recipe_engine", "recipe_engine"),
    "voice_shortcut":     ("actions.voice_shortcut", "voice_shortcut"),
    "hologram_mode":      ("actions.hologram_mode", "hologram_mode"),
    "file_process":       ("actions.file_processor", "file_processor"),
}


# Players/youtube skipper are singletons, lazily created
_YT_PLAYER = None
_YT_SKIPPER = None
_VIDEO_CTRL = None

def _get_yt_player():
    global _YT_PLAYER
    if _YT_PLAYER is None:
        try:
            from core.youtube_player import YouTubePlayer
            from core.youtube_ad_skipper import YouTubeAdSkipper
            _YT_PLAYER = YouTubePlayer(ad_skipper=_YT_SKIPPER)
        except Exception as e:
            print(f"[bridge] YouTube player init failed: {e}")
            _YT_PLAYER = None
    return _YT_PLAYER

def _get_yt_skipper():
    global _YT_SKIPPER
    if _YT_SKIPPER is None:
        try:
            from core.youtube_ad_skipper import YouTubeAdSkipper
            _YT_SKIPPER = YouTubeAdSkipper()
        except Exception:
            _YT_SKIPPER = None
    return _YT_SKIPPER

def _get_video_ctrl():
    global _VIDEO_CTRL
    if _VIDEO_CTRL is None:
        try:
            from core.video_player import VideoController
            _VIDEO_CTRL = VideoController()
        except Exception:
            _VIDEO_CTRL = None
    return _VIDEO_CTRL


# Map common router args → parameters dict keys (action-specific)
# Each SONIC action expects specific keys inside its `parameters` dict.
_PARAM_MAPPING = {
    "open_app":        {"target": "app_name", "app": "app_name", "name": "app_name"},
    "close_app":       {"target": "app_name", "app": "app_name", "name": "app_name"},
    "switch_window":   {"target": "window_title", "app": "window_title"},
    "web_search":      {"query": "query", "q": "query"},
    "play_youtube":    {"query": "query", "q": "query", "video": "query"},
    "open_url":        {"url": "url", "link": "url"},
    "download":        {"url": "url", "link": "url"},
    "set_volume":      {"level": "level", "volume": "level"},
    "volume_up":       {"level": "level"},
    "volume_down":     {"level": "level"},
    "set_reminder":    {"when": "time", "what": "message", "time": "time",
                       "date": "date"},
    "send_email":      {"to": "to", "subject": "subject", "body": "body",
                       "message": "body"},
    "send_message":    {"to": "recipient", "body": "message", "message": "message"},
    "translate":       {"text": "text", "target_lang": "target_lang",
                       "lang": "target_lang"},
    "ask_ai":          {"prompt": "prompt", "query": "prompt", "question": "prompt"},
    "generate_code":   {"prompt": "prompt", "spec": "prompt"},
    "run_python":      {"code": "code"},
    "screenshot":      {"region": "region"},
    "weather":         {"city": "city"},
    "play_music":      {"target": "query", "query": "query"},
    "summarize":       {"text": "text"},
}


# Some SONIC actions need a specific "action" key (e.g. youtube expects
# action="play", screen_process expects action="screenshot"). Map the
# routed name to the action value the module expects.
_ACTION_INNER_KEY: dict[str, str] = {
    "play_youtube":    "play",
    "play_music":      "play",
    "next_track":      "next",
    "pause_media":     "pause",
    "resume_media":    "resume",
    "screenshot":      "screenshot",
    "switch_window":   "switch",
    "set_volume":      "set_volume",
    "volume_up":       "volume_up",
    "volume_down":     "volume_down",
    "volume_mute":     "volume_mute",
    "lock_computer":   "lock",
    "shutdown":        "shutdown",
    "restart":         "restart",
    "sleep":           "sleep",
    "set_wallpaper":   "set_wallpaper",
    "open_app":        "open",
    "close_app":       "close",
    "send_email":      "send_email",
    "send_message":    "send",
    "set_reminder":    "set_reminder",
    "web_search":      "search",
    "open_url":        "open_url",
    "download":        "download",
    "research":        "research",
    "scrape":          "scrape",
    "translate":       "translate",
    "summarize":       "summarize",
    "ask_ai":          "ask",
    "generate_code":   "generate",
    "run_python":      "run",
    "organize_downloads": "organize_downloads",
    "cleanup_temp":    "cleanup_temp",
    "find_file":       "find",
    "open_file":       "open",
    "weather":         "weather",
    "system_status":   "status",
    "time_now":        "time",
    "today_calendar":  "calendar",
}


# ═════════════════════════════════════════════════════════════════════════════
# ActionResult
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class ActionResult:
    """Outcome of an action execution."""
    success: bool
    action: str
    output: Any = None
    text: str = ""
    duration_ms: float = 0.0
    error: str = ""
    error_type: str = ""
    attempts: int = 1
    fallback_used: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        # Truncate output for dict repr
        if isinstance(d["output"], str) and len(d["output"]) > 500:
            d["output"] = d["output"][:500] + "…"
        return d


# ═════════════════════════════════════════════════════════════════════════════
# ActionBridge
# ═════════════════════════════════════════════════════════════════════════════

class ActionBridge:
    """Routes action names to real SONIC action functions.

    Handles the SONIC convention: every action takes `parameters: dict` as
    the first argument.
    """

    def __init__(self, project_root: Optional[Path] = None,
                 sandbox=None, llm_client=None, proactive_engine=None):
        self._project_root = project_root or Path(__file__).parent.parent
        self._sandbox = sandbox
        self._llm = llm_client
        self._proactive = proactive_engine

        self._module_cache: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._stats = {
            "executes": 0, "successes": 0, "failures": 0, "missing": 0,
            "retries": 0, "fallbacks": 0,
        }

        # Ensure project importable
        sys.path.insert(0, str(self._project_root))

    # ── Public ───────────────────────────────────────────────────────────────

    def execute(self, action_name: str, args: dict,
                retry: int = 1, fallback_actions: Optional[list[str]] = None
                ) -> ActionResult:
        """Execute the action. Returns a structured ActionResult."""
        t0 = time.time()
        with self._lock:
            self._stats["executes"] += 1

        # Build the parameter dict (action-specific keys)
        parameters = self._build_parameters(action_name, args)
        result = self._execute_one(action_name, parameters, retry=retry)

        # If failed and we have fallbacks, try them
        if not result.success and fallback_actions:
            with self._lock:
                self._stats["fallbacks"] += 1
            for fb_action in fallback_actions:
                fb_params = self._build_parameters(fb_action, args)
                fb_result = self._execute_one(fb_action, fb_params, retry=0)
                if fb_result.success:
                    result = fb_result
                    result.fallback_used = True
                    break

        # Record in proactive patterns on success
        if result.success and self._proactive is not None:
            try:
                self._proactive.record_event(action_name, context=parameters)
            except Exception:
                pass

        result.duration_ms = (time.time() - t0) * 1000
        return result

    def execute_text(self, action_name: str, args: dict) -> str:
        """Convenience: execute + return a human-readable string."""
        result = self.execute(action_name, args)
        if result.success:
            return result.text or f"{action_name} done"
        return f"{action_name} failed: {result.error}"

    def get_available_actions(self) -> dict[str, str]:
        with self._lock:
            available = {}
            for action, (mod, fn) in _ACTION_MAP.items():
                if self._get_module(mod) is not None:
                    available[action] = f"{mod}.{fn}"
            return available

    def get_missing_actions(self) -> dict[str, str]:
        with self._lock:
            missing = {}
            for action, (mod, fn) in _ACTION_MAP.items():
                if self._get_module(mod) is None:
                    missing[action] = f"{mod}.{fn}"
            return missing

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def register_action(self, action_name: str,
                         module_path: str, func_name: str):
        """Register a custom action at runtime."""
        with self._lock:
            _ACTION_MAP[action_name] = (module_path, func_name)

    # ── Internals ────────────────────────────────────────────────────────────

    def _build_parameters(self, action_name: str, args: dict) -> dict:
        """Convert router-style args into action-specific parameters dict.

        Maps router keys → action-specific keys per _PARAM_MAPPING, and
        adds the action's expected inner `action` value per _ACTION_INNER_KEY.
        """
        mapping = _PARAM_MAPPING.get(action_name, {})
        parameters: dict = {}
        for k, v in args.items():
            target_key = mapping.get(k, k)
            parameters[target_key] = v
        # Set the action's inner `action` key (what SONIC modules read)
        if action_name in _ACTION_INNER_KEY:
            parameters["action"] = _ACTION_INNER_KEY[action_name]
        elif action_name and "action" not in parameters:
            parameters["action"] = action_name
        # Add utterance text as fallback if no other content
        if "text" in args and "text" not in parameters and "query" not in parameters:
            parameters["text"] = args["text"]

        # Action-specific parameter fixes:
        if action_name == "set_reminder":
            # Reminder needs date + time separately, parsed
            when = parameters.get("time") or parameters.get("when") or ""
            parameters["date"], parameters["time"] = self._parse_datetime(when)
            # If no message, use text or default
            if not parameters.get("message"):
                parameters["message"] = args.get("what") or args.get("text") or "Reminder"

        elif action_name == "screenshot":
            # screen_process needs a 'text' question — default if missing
            if not parameters.get("text") and not parameters.get("user_text"):
                parameters["text"] = "What do you see on the screen? Describe briefly."
            parameters.setdefault("angle", "screen")

        elif action_name in ("set_volume", "volume_up", "volume_down"):
            # computer_settings wants action + value (not "set_volume" inner)
            if action_name == "set_volume":
                parameters["action"] = "volume_set"
            elif action_name == "volume_up":
                parameters["action"] = "volume_up"
            elif action_name == "volume_down":
                parameters["action"] = "volume_down"
            # Coerce value to int
            raw = parameters.get("value") or parameters.get("level") or 50
            try:
                parameters["value"] = max(0, min(100, int(raw)))
            except Exception:
                parameters["value"] = 50

        elif action_name == "open_app":
            # computer_settings.open_app path may want action="open"
            parameters["action"] = "open"

        elif action_name == "close_app":
            parameters["action"] = "close"

        elif action_name == "ask_ai":
            # dev_agent expects action="ask"
            parameters["action"] = "ask"

        elif action_name == "play_music":
            # desktop_control expects action="play"
            parameters["action"] = "play"

        return parameters

    def _parse_datetime(self, text: str) -> tuple[str, str]:
        """Parse '5pm', '5:00 pm', '17:30', 'in 2 hours', 'tomorrow 8am' → (date, time).

        Returns today's date in YYYY-MM-DD and the time in HH:MM.
        """
        import re
        from datetime import datetime, timedelta
        now = datetime.now()
        text = (text or "").strip().lower()
        if not text:
            return now.strftime("%Y-%m-%d"), "12:00"

        # Try explicit HH:MM with am/pm
        m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
        if m:
            h = int(m.group(1))
            mins = int(m.group(2) or 0)
            ampm = m.group(3)
            if ampm == "pm" and h < 12:
                h += 12
            elif ampm == "am" and h == 12:
                h = 0
            # If "5pm" with no minutes, default :00
            date = now.strftime("%Y-%m-%d")
            if h < now.hour or (h == now.hour and mins <= now.minute):
                # Time already passed today — schedule for tomorrow
                date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            return date, f"{h:02d}:{mins:02d}"

        # "in N minutes/hours"
        m = re.search(r"in\s+(\d+)\s+(minute|hour|min|hr)", text)
        if m:
            n = int(m.group(1))
            unit = m.group(2)
            delta_min = n * (60 if unit.startswith("h") else 1)
            target = now + timedelta(minutes=delta_min)
            return target.strftime("%Y-%m-%d"), target.strftime("%H:%M")

        # "tomorrow"
        if "tomorrow" in text:
            target_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text.replace("tomorrow", ""))
            if m:
                h = int(m.group(1))
                mins = int(m.group(2) or 0)
                ampm = m.group(3)
                if ampm == "pm" and h < 12:
                    h += 12
                return target_date, f"{h:02d}:{mins:02d}"
            return target_date, "09:00"

        # Default: today, +1 hour
        target = now + timedelta(hours=1)
        return target.strftime("%Y-%m-%d"), target.strftime("%H:%M")

    def _execute_one(self, action_name: str, parameters: dict,
                      retry: int = 1) -> ActionResult:
        """Execute one action with retry."""
        # Special case: sandbox
        if action_name == "run_python":
            return self._exec_sandbox(parameters, retry)

        # Special case: ask_ai → use LLM if available
        if action_name == "ask_ai" and self._llm is not None:
            return self._exec_llm(parameters)

        # Special: YouTube player
        if action_name.startswith("yt_") or action_name == "play_list":
            return self._exec_yt_player(action_name, parameters)

        # Special: YouTube skipper
        if action_name == "yt_skip_ad":
            return self._exec_yt_skipper(parameters)

        # Special: Universal video controller
        if action_name.startswith("video_"):
            return self._exec_video_ctrl(action_name, parameters)

        # Find module + function
        if action_name not in _ACTION_MAP:
            with self._lock:
                self._stats["missing"] += 1
            return ActionResult(
                success=False, action=action_name,
                error=f"Unknown action: {action_name}",
                error_type="UnknownAction",
            )

        module_path, func_name = _ACTION_MAP[action_name]
        mod = self._get_module(module_path)
        if mod is None:
            with self._lock:
                self._stats["missing"] += 1
            return ActionResult(
                success=False, action=action_name,
                error=f"Module not loadable: {module_path}",
                error_type="ModuleMissing",
            )

        fn = getattr(mod, func_name, None)
        if fn is None or not callable(fn):
            fn = self._discover_function(mod, func_name, parameters)
        if fn is None:
            with self._lock:
                self._stats["missing"] += 1
            return ActionResult(
                success=False, action=action_name,
                error=f"Function not found: {func_name} in {module_path}",
                error_type="FunctionMissing",
            )

        # Try execution with retry
        last_error = ""
        attempts = 0
        for attempt in range(retry + 1):
            attempts += 1
            try:
                output = self._call_with_parameters(fn, parameters)
                with self._lock:
                    self._stats["successes"] += 1
                text = self._extract_text(output)
                return ActionResult(
                    success=True, action=action_name,
                    output=output, text=text,
                    attempts=attempts,
                )
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                if attempt < retry:
                    with self._lock:
                        self._stats["retries"] += 1
                    time.sleep(0.2 * (attempt + 1))

        with self._lock:
            self._stats["failures"] += 1
        return ActionResult(
            success=False, action=action_name,
            error=last_error, error_type="ExecutionError",
            attempts=attempts,
        )

    def _call_with_parameters(self, fn, parameters: dict) -> Any:
        """Call the action with the parameters dict, respecting its signature."""
        try:
            sig = inspect.signature(fn)
        except (ValueError, TypeError):
            sig = None

        # All SONIC actions take `parameters` as first arg
        # If signature has it, call with positional parameters
        if sig is not None:
            param_names = list(sig.parameters.keys())
            if "parameters" in param_names:
                # Build kwargs for remaining params (response, player, etc.)
                kwargs = {}
                for pn in param_names[1:]:
                    if pn in ("response", "player", "session_memory", "speak"):
                        continue  # skip optional SONIC context args
                    if pn in parameters:
                        kwargs[pn] = parameters[pn]
                # Call with parameters as first positional, others as kwargs
                return fn(parameters, **kwargs) if kwargs else fn(parameters)

        # Fallback: try with parameters as kwarg
        try:
            return fn(parameters=parameters)
        except TypeError:
            pass

        # Last resort: try with no args (might be a getter)
        try:
            return fn()
        except Exception:
            pass

        # Final: try unpacking parameters
        return fn(**parameters)

    def _exec_sandbox(self, parameters: dict, retry: int) -> ActionResult:
        if self._sandbox is None:
            from core.code_sandbox import CodeSandbox
            self._sandbox = CodeSandbox()
        code = parameters.get("code", "")
        if not code:
            return ActionResult(
                success=False, action="run_python",
                error="No code provided",
                error_type="MissingParameter",
            )
        r = self._sandbox.run(code)
        text = r.summary()
        return ActionResult(
            success=r.success, action="run_python",
            output={"stdout": r.stdout, "stderr": r.stderr,
                    "duration_ms": r.duration_ms},
            text=text,
            attempts=1,
        )

    def _exec_llm(self, parameters: dict) -> ActionResult:
        prompt = parameters.get("prompt", parameters.get("query", ""))
        try:
            response = self._llm(prompt)
            return ActionResult(
                success=True, action="ask_ai",
                output=response, text=response.strip(),
            )
        except Exception as e:
            return ActionResult(
                success=False, action="ask_ai",
                error=str(e), error_type="LLMError",
            )

    def _exec_yt_player(self, action_name: str, parameters: dict) -> ActionResult:
        """Execute YouTube player action via YouTubePlayer singleton."""
        player = _get_yt_player()
        if player is None:
            return ActionResult(
                success=False, action=action_name,
                error="YouTube player not available (Playwright/browser missing?)",
                error_type="PlayerUnavailable",
            )

        try:
            if action_name == "play_youtube":
                url_or_query = parameters.get("url") or parameters.get("query")
                if not url_or_query:
                    # Default search
                    url_or_query = parameters.get("text", "YouTube")
                ok = player.play(url_or_query)
                return ActionResult(
                    success=ok, action=action_name,
                    text=("Playing: " + url_or_query) if ok else "Failed to start playback",
                )
            elif action_name == "play_list":
                urls = parameters.get("urls") or parameters.get("list", [])
                if isinstance(urls, str):
                    urls = [urls]
                if not urls:
                    return ActionResult(
                        success=False, action=action_name,
                        error="play_list needs a 'urls' parameter (list of URLs)",
                        error_type="MissingParameter",
                    )
                ok = player.play_list(urls)
                return ActionResult(
                    success=ok, action=action_name,
                    text=f"Played {len(urls)} videos" if ok else "List playback failed",
                )
            elif action_name == "yt_pause":
                return ActionResult(
                    success=player.pause(), action=action_name,
                    text="Paused" if player.pause() else "Pause failed",
                )
            elif action_name == "yt_resume":
                return ActionResult(
                    success=player.resume(), action=action_name,
                    text="Resumed" if player.resume() else "Resume failed",
                )
            elif action_name == "yt_next":
                return ActionResult(
                    success=player.next(), action=action_name,
                    text="Skipped to next" if player.next() else "Next failed",
                )
            elif action_name == "yt_previous":
                return ActionResult(
                    success=player.previous(), action=action_name,
                    text="Previous" if player.previous() else "Previous failed",
                )
            elif action_name == "yt_seek":
                secs = parameters.get("seconds", 0)
                return ActionResult(
                    success=player.seek(int(secs)), action=action_name,
                    text=f"Seeked {secs}s",
                )
            elif action_name == "yt_fullscreen":
                return ActionResult(
                    success=player.fullscreen(), action=action_name,
                    text="Toggled fullscreen",
                )
            elif action_name == "yt_like":
                return ActionResult(
                    success=player.like(), action=action_name,
                    text="Liked",
                )
            elif action_name == "yt_subscribe":
                return ActionResult(
                    success=player.subscribe(), action=action_name,
                    text="Subscribed",
                )
            elif action_name == "yt_autopilot":
                url = parameters.get("url") or parameters.get("query", "")
                max_v = int(parameters.get("max_videos", 10))
                return ActionResult(
                    success=player.autopilot(url, max_v), action=action_name,
                    text=f"Autopilot started ({max_v} videos)",
                )
        except Exception as e:
            return ActionResult(
                success=False, action=action_name,
                error=str(e), error_type="YTPlayerError",
            )
        return ActionResult(
            success=False, action=action_name, error="unknown action",
        )

    def _exec_yt_skipper(self, parameters: dict) -> ActionResult:
        """Skip current YouTube ad once."""
        skipper = _get_yt_skipper()
        if skipper is None:
            return ActionResult(
                success=False, action="yt_skip_ad",
                error="Ad skipper unavailable",
                error_type="SkipperUnavailable",
            )
        try:
            ok = skipper.skip_once()
            return ActionResult(
                success=ok, action="yt_skip_ad",
                text=("Ad skipped" if ok else "No ad to skip"),
                output=skipper.get_stats(),
            )
        except Exception as e:
            return ActionResult(
                success=False, action="yt_skip_ad",
                error=str(e), error_type="SkipperError",
            )

    def _exec_video_ctrl(self, action_name: str, parameters: dict) -> ActionResult:
        """Universal video controller."""
        ctrl = _get_video_ctrl()
        if ctrl is None:
            return ActionResult(
                success=False, action=action_name,
                error="Video controller unavailable",
                error_type="CtrlUnavailable",
            )
        try:
            if action_name == "video_play":
                ok = ctrl.play()
            elif action_name == "video_pause":
                ok = ctrl.pause()
            elif action_name == "video_next":
                ok = ctrl.next()
            elif action_name == "video_previous":
                ok = ctrl.previous()
            elif action_name == "video_seek":
                secs = parameters.get("seconds", 0)
                ok = ctrl.seek(int(secs))
            elif action_name == "video_fullscreen":
                ok = ctrl.fullscreen()
            elif action_name == "video_mute":
                ok = ctrl.mute()
            else:
                ok = False
            player = ctrl.get_active_player()
            return ActionResult(
                success=ok, action=action_name,
                output={"active_player": player, "action": action_name},
                text=f"{action_name} → {player}: {'ok' if ok else 'failed'}",
            )
        except Exception as e:
            return ActionResult(
                success=False, action=action_name,
                error=str(e), error_type="VideoCtrlError",
            )

    def _extract_text(self, output: Any) -> str:
        """Best-effort text extraction from action output."""
        if output is None:
            return ""
        if isinstance(output, str):
            return output.strip()
        if isinstance(output, dict):
            # Try common keys
            for key in ("response", "result", "output", "message",
                        "text", "summary", "answer"):
                if key in output and isinstance(output[key], str):
                    return output[key].strip()
            # Fallback to compact JSON
            try:
                return json.dumps(output, default=str)[:500]
            except Exception:
                return str(output)[:200]
        if isinstance(output, (list, tuple)):
            return ", ".join(str(x) for x in output[:5])
        return str(output)[:200].strip()

    def _get_module(self, module_path: str):
        if module_path in self._module_cache:
            return self._module_cache[module_path]
        try:
            mod = importlib.import_module(module_path)
            self._module_cache[module_path] = mod
            return mod
        except Exception as e:
            logger.debug(f"Module import failed: {module_path}: {e}")
            self._module_cache[module_path] = None
            return None

    def _discover_function(self, mod, name: str, parameters: dict
                            ) -> Optional[Callable]:
        """Find a callable in module matching the action name."""
        # Direct lookups with synonyms
        synonyms = {
            "open_app":       ["open_app", "open", "launch", "launch_app"],
            "close_app":      ["close_app", "close", "quit", "kill_app"],
            "switch_window":  ["switch_to_window", "focus_window", "switch_window"],
            "web_search":     ["web_search", "search", "search_web"],
            "weather":        ["weather_report", "weather", "get_weather"],
            "reminder":       ["reminder", "set_reminder"],
            "send_email":     ["send_email", "email_send", "mail"],
            "send_message":   ["send_message", "send_msg", "message_send"],
            "ask_ai":         ["dev_agent", "ask_ai", "ask"],
            "screenshot":     ["screen_process", "screenshot", "take_screenshot"],
            "system_status":  ["get_system_status", "system_status", "status"],
            "translate":      ["translate", "translator", "translate_text"],
        }
        candidates = synonyms.get(name, [name])
        for c in candidates:
            fn = getattr(mod, c, None)
            if callable(fn):
                return fn
        # Scan module for any callable matching
        for attr_name, obj in vars(mod).items():
            if callable(obj) and not attr_name.startswith("_"):
                if getattr(obj, "__module__", "") == mod.__name__:
                    # Check name similarity
                    if attr_name.lower().replace("_", "") == name.lower().replace("_", ""):
                        return obj
        return None
