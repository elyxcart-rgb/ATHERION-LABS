import platform as _platform
import subprocess as _subprocess

# ── Console encoding ─────────────────────────────────────────────────────────
# Windows consoles default to a legacy codepage — cp1254 in Turkey, cp1251 in
# Russia, cp932 in Japan. Printing an emoji there raises UnicodeEncodeError, and
# several of these prints sit inside except handlers, so the handler itself dies
# and skips the recovery code after it. Reconfiguring to UTF-8 with a
# replacement fallback costs nothing and makes the app behave in every locale.
import sys as _sys

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(_sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass          # pythonw / redirected pipes / anything exotic — never fatal

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **                       kw)

    _subprocess.Popen = _Popen

# ── Development engine integration ────────────────────────────────────────
try:
    from coding.adapter import OpenCodeAdapter as _OpenCodeAdapter
    from coding.intent_detector import IntentDetector as _CodingIntent
except ImportError:
    _OpenCodeAdapter = None   # type: ignore[assignment,misc]
    _CodingIntent = None      # type: ignore[assignment,misc]

# ── Security system ──────────────────────────────────────────────────────
try:
    from security.advanced import (
        auth_limiter as _auth_limiter,
        audit as _audit,
        ids as _ids,
        sanitizer as _sanitizer,
        AuditEvent as _AuditEvent,
    )
    _SECURITY_OK = True
except ImportError:
    _SECURITY_OK = False

# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import re
import threading
import time
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication

import sounddevice as sd
import numpy as np
from google import genai
from google.genai import types
from ui import SonicUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    save_session_summary, pop_last_session,
    search_memory, set_trim_notifier,
    init_memory_system, set_user_id, get_user_id,
    handle_remember, handle_forget, handle_memory_query,
    extract_from_turn, build_prompt_context, consolidate_memory,
    get_memory_stats,
)

# ── Emotion & Personality Engine ─────────────────────────────────────────────
from emotion import SonicPersonality

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import _capture_camera, _capture_screen
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control

# ── New Features ──────────────────────────────────────────────────────────
from actions.squad_agent       import squad_mode
from actions.recipe_engine     import recipe_engine
from actions.hologram_mode     import hologram_mode
from actions.voice_shortcut    import voice_shortcut
from actions.smart_clipboard   import smart_clipboard
from actions.autopilot         import get_autopilot
from actions.translator        import get_translator
from actions.life_dashboard    import get_life_dashboard

# Location awareness
from location import LocationContext

# Reliability engine
from reliability.classifier import classify_error, ErrorCategory
from reliability.retry import RetryEngine
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.system_monitor    import SystemMonitor, get_system_status
from actions.proactive         import ProactiveEngine
from actions.smart_file_manager import (
    find_files, find_recent_files, find_large_files, find_duplicates,
    categorize_files, open_path, open_folder, get_folder_size, list_folder,
    disk_cleanup, clipboard_get, clipboard_set, battery_status,
    wifi_status, bluetooth_status, list_processes, kill_process,
    empty_recycle_bin,
)
from actions.utility_controls import (
    volume_preset, volume_get_status, brightness_preset, brightness_get_status,
    display_info, system_info, disk_space, network_info,
    quick_launch, sleep_computer, hibernate_computer, monitor_off,
    get_env, list_scheduled_tasks,
)
from actions.background_monitor import (
    add_monitor, remove_monitor, list_monitors, check_all as monitor_check_all,
)
from actions.web_search        import _news as _fetch_news_sync
from memory.config_manager     import (
    get_brief_enabled, get_voice, get_input_device, get_output_device,
)
from core.plugin_loader        import discover_plugins
from core                      import undo as undo_stack
from core                      import confirm as confirm_gate
from core                      import audio_devices

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

# RMS below which 16-bit PCM is treated as room silence; above _LEVEL_FULL it
# reads as a full-height waveform. Tuned so ordinary speech lands mid-range and
# the bars still move for a quiet talker — language- and device-independent.
_LEVEL_FLOOR = 60.0
_LEVEL_FULL  = 2600.0


def _pcm_level(samples) -> float:
    """Map a block of int16 PCM samples to a 0.0–1.0 loudness level for the HUD
    waveform. Returns 0.0 on empty/invalid input so it can never raise."""
    try:
        x = np.asarray(samples, dtype=np.float32)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
    except Exception:
        return 0.0
    if rms <= _LEVEL_FLOOR:
        return 0.0
    return min(1.0, (rms - _LEVEL_FLOOR) / (_LEVEL_FULL - _LEVEL_FLOOR))


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are SONIC, created by Ahmad, CEO of Atherion Labs. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web. Use for ANY question about current facts, events, prices, "
            "or topics — always prefer this over guessing. "
            "Modes: 'search' (default), 'news' (latest headlines on a topic), "
            "'research' (deep comprehensive answer), 'price' (product cost lookup), "
            "'compare' (side-by-side comparison of items)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Items to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "Comparison aspect: price | specs | reviews | features"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
            "uptime, and process count. Use when the user asks about computer performance, "
            "temperature, memory, or resource usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "weather_report",
        "description": (
            "Shows weather report for a city. "
            "If no city is provided, uses the user's current location automatically. "
            "Supports time parameter like 'today', 'tomorrow', 'this week'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {
                    "type": "STRING",
                    "description": (
                        "City name. If omitted, auto-detects from current location. "
                        "Examples: 'Faisalabad', 'Islamabad', 'Lahore'"
                    ),
                },
                "time": {
                    "type": "STRING",
                    "description": (
                        "Time period. Default: 'today'. "
                        "Examples: 'today', 'tomorrow', 'this week'"
                    ),
                },
            },
            "required": [],
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures the screen or webcam image and lets you analyze it. "
            "MUST be called when user asks what is on screen, what you see, "
            "look at camera, analyze my screen, etc. "
            "You have NO visual ability without this tool. "
            "After the image is captured it is sent directly to you — describe what you see and answer the user's question. "
            "When using camera: the live view stays open until user says close it or calls close_camera."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "close_camera",
        "description": (
            "Closes the live camera view shown on screen. "
            "Call when user says: close camera, stop camera, turn off camera, "
            "kamerayı kapat, kapat, creepy, etc."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. "
            "restart, shutdown and toggle_wifi put a confirmation on the user's screen "
            "and do NOT happen until they press it — never claim they are done. "
            "Volume, brightness and dark mode can be reversed with the `undo` tool."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                # The exact vocabulary, spelled out.
                #
                # This used to say only "The action to perform", so the model
                # usually filled `description` instead — and computer_settings
                # then made a SECOND Gemini call, inside the tool, purely to
                # translate that sentence into one of these names. Every
                # "turn the volume down" cost two model round trips.
                "action": {
                    "type": "STRING",
                    "description": (
                        "The exact action. Prefer this over `description` — pick one of: "
                        "volume_up | volume_down | volume_set | mute | "
                        "brightness_up | brightness_down | sleep_display | "
                        "pause_video | close_app | close_window | full_screen | "
                        "minimize | maximize | snap_left | snap_right | "
                        "switch_window | show_desktop | task_manager | focus_search | "
                        "refresh_page | close_tab | new_tab | next_tab | prev_tab | "
                        "go_back | go_forward | zoom_in | zoom_out | zoom_reset | "
                        "find_on_page | scroll_up | scroll_down | scroll_top | "
                        "scroll_bottom | page_up | page_down | copy | paste | cut | "
                        "undo | redo | select_all | save | enter | escape | press_key | "
                        "type_text | screenshot | lock_screen | open_settings | "
                        "file_explorer | open_run | dark_mode | toggle_wifi | "
                        "restart | shutdown"
                    ),
                },
                "description": {
                    "type": "STRING",
                    "description": (
                        "Fallback only, when no action name above fits. "
                        "Resolved locally — no extra model call."
                    ),
                },
                "value":       {"type": "STRING", "description": "Optional value: volume level 0-100, text to type, key name, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Simple open/search requests launch the user's own browser normally (their real profile "
            "and logged-in accounts); interactive actions (click, type, fill_form...) attach an "
            "automation browser. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "manage_monitor",
        "description": (
            "Add, remove, or list background monitoring topics. "
            "SONIC checks these topics once a day and alerts the user when there is a new development. "
            "Use 'add' when the user says 'monitor X', 'track X', 'follow X'. "
            "Use 'remove' when the user says 'stop monitoring X'. "
            "Use 'list' when the user asks what is being monitored. "
            "Do NOT add crypto, financial, or trading topics."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type":        "STRING",
                    "description": "add | remove | list",
                },
                "topic": {
                    "type":        "STRING",
                    "description": "Topic to monitor or stop monitoring (e.g. 'space exploration', 'AI news')",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "shutdown_sonic",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Sonic. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "recall_memory",
        "description": (
            "Look up a fact you have stored about the user but which is NOT in "
            "the memory block of your system prompt. "
            "The prompt lists the keys it did not have room for under "
            "'[ALSO REMEMBERED]' — if the user asks about anything named there, "
            "call this FIRST. "
            "Also call it before saying you do not know something personal, and "
            "when the user asks what you remember about them (leave query empty "
            "for everything). "
            "This is a local file search: it is instant and costs nothing."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": (
                        "Keyword to search for — a name, a topic, a category "
                        "(e.g. 'ayse', 'coffee', 'projects'). "
                        "Leave empty to list everything stored."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "remember",
        "description": (
            "Explicitly remember something the user tells you. "
            "Use when the user says 'remember that...', 'yaad rakh...', "
            "'don't forget...', or any explicit memory instruction. "
            "This creates a high-confidence persistent memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "content": {
                    "type": "STRING",
                    "description": "The exact thing to remember, as the user stated it."
                },
            },
            "required": ["content"]
        },
    },
    {
        "name": "forget_memory",
        "description": (
            "Forget something you were told to remember. "
            "Use when the user says 'forget that...', 'bhool jao...', "
            "'don't remember...', or wants to remove a stored memory."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "content": {
                    "type": "STRING",
                    "description": "What to forget — a keyword or description of the memory."
                },
            },
            "required": ["content"]
        },
    },
    {
        "name": "memory_query",
        "description": (
            "Show the user what you remember about them. "
            "Use when the user asks 'what do you remember?', 'kya yaad hai?', "
            "'what have you learned from me?', or similar memory queries."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "undo",
        "description": (
            "Reverse the last change YOU made to this computer — a file you "
            "moved, renamed, created or wrote, or a setting you changed such as "
            "volume, brightness, dark mode or WiFi. "
            "Call this whenever the user says undo, revert, take it back, put it "
            "back, cancel that, or tells you that you did the wrong thing, in ANY "
            "language. "
            "Use action='list' when they ask what can be undone. "
            "This only covers your own actions — it is not the Ctrl+Z of whatever "
            "application is on screen (that is computer_settings with action 'undo')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "undo (default) — reverse the last change | list — show what can be undone",
                },
            },
            "required": [],
        },
    },
    {
        "name": "coding_task",
        "description": (
            "Execute any development, creation, or file-generation task. "
            "Use this for: creating apps, websites, scripts, Excel sheets, PDF reports, "
            "Word documents, PowerPoint presentations, HTML pages, Python programs, "
            "JavaScript projects, fixing bugs, adding features, refactoring code, "
            "writing tests, debugging errors, implementing modules, analyzing code, "
            "and any programming or document-creation work. "
            "Just pass the natural language request. SONIC handles project context, "
            "workspace detection, verification, and result summary automatically. "
            "Supports Python, JavaScript, TypeScript, HTML, CSS, Excel, PDF, "
            "Word, PowerPoint, and other formats. "
            "Will auto-detect project root, gather relevant files, and verify results."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "request": {
                    "type": "STRING",
                    "description": (
                        "The natural-language task description. "
                        "Examples: 'Create a calculator app', 'Build a portfolio website', "
                        "'Make an Excel budget sheet', 'Generate a PDF report', "
                        "'Create a PowerPoint presentation', 'Fix the login bug', "
                        "'Add a settings panel', 'Write a Python script for data analysis'"
                    ),
                },
                "workspace": {
                    "type": "STRING",
                    "description": (
                        "Optional project root path. If omitted, auto-detects from "
                        "current working directory by looking for project markers "
                        "(.git, pyproject.toml, requirements.txt, package.json, etc.)"
                    ),
                },
                "timeout": {
                    "type": "INTEGER",
                    "description": (
                        "Optional timeout in seconds. Default 300 (5 min). "
                        "Use 600 for complex multi-file tasks."
                    ),
                },
            },
            "required": ["request"],
        },
    },
    # ── Smart File Manager ────────────────────────────────────────────────
    {
        "name": "smart_find",
        "description": (
            "Smart file search and management. Find files by name, type, size, date. "
            "Search for duplicates, recent files, large files. Open folders and files. "
            "Get folder sizes, list directory contents, clean disk space. "
            "Use for ANY file management request: find my photos, show large files, "
            "find duplicates, how much space is in Downloads, open Documents, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "Action to perform: "
                        "search | recent | large | duplicates | categorize | "
                        "open | folder_size | list | cleanup | recycle_bin"
                    ),
                },
                "query": {"type": "STRING", "description": "Search query (filename contains)"},
                "directory": {"type": "STRING", "description": "Directory to search in (default: home)"},
                "category": {"type": "STRING", "description": "File category: images|videos|music|documents|code|archives"},
                "extension": {"type": "STRING", "description": "File extension filter e.g. '.py'"},
                "path": {"type": "STRING", "description": "Path to open or get info about"},
                "min_size_mb": {"type": "NUMBER", "description": "Minimum file size in MB"},
                "modified_days": {"type": "INTEGER", "description": "Modified within N days"},
                "max_results": {"type": "INTEGER", "description": "Max results (default: 30)"},
                "dry_run": {"type": "BOOLEAN", "description": "Dry run for cleanup (default: true)"},
            },
            "required": ["action"],
        },
    },
    # ── System Controls (Enhanced) ────────────────────────────────────────
    {
        "name": "system_controls",
        "description": (
            "Enhanced system controls: volume presets (mute/low/medium/high/max), "
            "brightness presets, display info, battery status, WiFi status, "
            "Bluetooth status, sleep/hibernate, monitor off, disk space, "
            "network info, process list, kill process, clipboard, "
            "quick launch apps, environment variables, scheduled tasks. "
            "Use for ANY system control or status query not covered by computer_settings."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "Action: volume_preset | volume_status | brightness_preset | brightness_status | "
                        "display_info | battery | wifi | bluetooth | sleep | hibernate | monitor_off | "
                        "disk_space | network | processes | kill_process | "
                        "clipboard_get | clipboard_set | quick_launch | "
                        "system_info | env | scheduled_tasks | recycle_bin"
                    ),
                },
                "value": {"type": "STRING", "description": "Value: preset name (low/medium/high), app name, process name/PID, env key, text to clipboard"},
                "sort_by": {"type": "STRING", "description": "Sort processes by: cpu|mem"},
            },
            "required": ["action"],
        },
    },
    # ── Squad Mode (Multi-Agent Parallel Tasks) ───────────────────────────
    {
        "name": "squad_mode",
        "description": (
            "Execute multiple tasks in parallel using sub-agents. "
            "Use when the user asks for multiple things at once, like "
            "'research X, check Y, and find Z' or 'do these 3 things simultaneously'. "
            "Maximum 5 parallel tasks. Each task runs independently and results are combined."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tasks": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "List of tasks to execute in parallel (max 5)",
                },
                "context": {
                    "type": "STRING",
                    "description": "Optional context or description of the overall goal",
                },
                "timeout_per_task": {
                    "type": "INTEGER",
                    "description": "Timeout per task in seconds (default: 60)",
                },
            },
            "required": ["tasks"],
        },
    },
    # ── Recipe Engine (Automated Workflows) ──────────────────────────────
    {
        "name": "recipe_engine",
        "description": (
            "Create, manage, and execute automated multi-step workflows (recipes). "
            "Use when the user wants to save a sequence of actions to reuse later, "
            "like 'remember this as a recipe' or 'create a morning routine'. "
            "Actions: create, delete, run, list, get."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: create | delete | run | list | get",
                },
                "name": {"type": "STRING", "description": "Recipe name"},
                "description": {"type": "STRING", "description": "Recipe description"},
                "steps": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "tool_name": {"type": "STRING"},
                            "parameters": {"type": "OBJECT"},
                            "description": {"type": "STRING"},
                            "delay_after": {"type": "NUMBER"},
                        },
                    },
                    "description": "Steps to include in the recipe (for create)",
                },
                "tags": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Tags for categorizing recipes",
                },
                "variables": {
                    "type": "OBJECT",
                    "description": "Variables to pass during execution (for run)",
                },
            },
            "required": ["action"],
        },
    },
    # ── Hologram Mode (Screen Annotation) ────────────────────────────────
    {
        "name": "hologram_mode",
        "description": (
            "Draw annotations directly on the user's screen. "
            "Use to highlight UI elements, draw arrows, circle items, "
            "overlay text labels, or spotlight specific areas. "
            "Annotations auto-clear after a few seconds. "
            "Actions: annotate (draw), clear (remove all)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: annotate | clear",
                },
                "type": {
                    "type": "STRING",
                    "description": "Annotation type: arrow | circle | rectangle | text | highlight | spotlight",
                },
                "x1": {"type": "NUMBER", "description": "Start X / Center X coordinate"},
                "y1": {"type": "NUMBER", "description": "Start Y / Center Y coordinate"},
                "x2": {"type": "NUMBER", "description": "End X / Radius (for spotlight)"},
                "y2": {"type": "NUMBER", "description": "End Y coordinate"},
                "text": {"type": "STRING", "description": "Text to display (for text type)"},
                "color": {"type": "STRING", "description": "Color hex code (default: #00d4ff)"},
                "duration": {"type": "NUMBER", "description": "Auto-clear duration in seconds (default: 5)"},
                "font_size": {"type": "INTEGER", "description": "Font size for text (default: 18)"},
            },
            "required": ["action"],
        },
    },
    # ── Voice Shortcuts ──────────────────────────────────────────────────
    {
        "name": "voice_shortcut",
        "description": (
            "Create and manage custom voice shortcuts. "
            "Use when the user wants to create a shortcut like "
            "'when I say focus mode, mute volume' or 'save this as a shortcut'. "
            "Actions: add, remove, list, match."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: add | remove | list | match",
                },
                "trigger": {
                    "type": "STRING",
                    "description": "The voice phrase that triggers the shortcut",
                },
                "tool_name": {
                    "type": "STRING",
                    "description": "Tool to execute when triggered",
                },
                "parameters": {
                    "type": "OBJECT",
                    "description": "Parameters to pass to the tool",
                },
                "description": {"type": "STRING", "description": "Shortcut description"},
                "aliases": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Alternative trigger phrases",
                },
                "text": {"type": "STRING", "description": "Text to match against shortcuts (for match)"},
            },
            "required": ["action"],
        },
    },
    # ── Smart Clipboard ──────────────────────────────────────────────────
    {
        "name": "smart_clipboard",
        "description": (
            "Enhanced clipboard with history, content detection, and smart operations. "
            "Use when the user wants to search clipboard history, pin items, "
            "get clipboard stats, or work with copied content. "
            "Auto-detects content types: url, code, json, email, youtube, etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "Action: add | get_recent | search | pin | unpin | pinned | "
                        "stats | by_type | clear"
                    ),
                },
                "content": {"type": "STRING", "description": "Content to add (for add)"},
                "source": {"type": "STRING", "description": "Content source (for add)"},
                "count": {"type": "INTEGER", "description": "Number of recent items (for get_recent)"},
                "query": {"type": "STRING", "description": "Search query (for search)"},
                "index": {"type": "INTEGER", "description": "Entry index (for pin/unpin)"},
                "type": {"type": "STRING", "description": "Content type filter (for by_type)"},
            },
            "required": ["action"],
        },
    },
    # ── Auto-Pilot ───────────────────────────────────────────────────────
    {
        "name": "autopilot",
        "description": (
            "Full computer control via voice. Opens apps, clicks buttons, fills forms, "
            "browses websites, takes screenshots, types text, and more. "
            "Use when the user wants SONIC to take control and perform tasks automatically."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "Natural language command (e.g. 'open Chrome and go to YouTube')",
                },
                "action": {
                    "type": "STRING",
                    "description": "Direct action: open_app | close_app | screenshot | click | type | copy | paste | scroll",
                },
                "app": {"type": "STRING", "description": "App name (for open_app/close_app)"},
                "url": {"type": "STRING", "description": "URL (for open_url)"},
                "text": {"type": "STRING", "description": "Text to type"},
                "target": {"type": "STRING", "description": "Click target"},
            },
            "required": ["command"],
        },
    },
    # ── Universal Translator ─────────────────────────────────────────────
    {
        "name": "translator",
        "description": (
            "Real-time voice translation in 100+ languages with voice cloning. "
            "Translates text and speech between languages. "
            "Supports conversation mode, pronunciation guides, and cultural context."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "translate | translate_voice | set_languages | list_languages | clone_voice",
                },
                "text": {"type": "STRING", "description": "Text to translate"},
                "source": {"type": "STRING", "description": "Source language code (e.g. 'en')"},
                "target": {"type": "STRING", "description": "Target language code (e.g. 'ja')"},
                "voice_id": {"type": "STRING", "description": "Voice profile ID for cloning"},
            },
            "required": ["action"],
        },
    },
    # ── Life Dashboard ───────────────────────────────────────────────────
    {
        "name": "life_dashboard",
        "description": (
            "Complete life management with AI predictions. Tracks health, finances, "
            "goals, habits, relationships, and provides insights. "
            "Calculates overall life score and predicts future outcomes."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "health | finance | goals | habits | relationships | "
                        "predict | life_score | dashboard | log_health | log_expense | "
                        "add_goal | add_habit"
                    ),
                },
                "data": {"type": "OBJECT", "description": "Data to log (for log_*)"},
                "title": {"type": "STRING", "description": "Goal/habit title"},
                "category": {"type": "STRING", "description": "Category"},
                "amount": {"type": "NUMBER", "description": "Amount (for finance)"},
                "description": {"type": "STRING", "description": "Description"},
            },
            "required": ["action"],
        },
    },
]

class _ReconnectSignal(Exception):
    """Raised inside the session TaskGroup to force a clean, voluntary reconnect
    (e.g. the user picked a new voice — the voice is fixed at connect time, so
    the session must be rebuilt).

    Carries `keep_context`: True for an ordinary rebuild, where the stored
    resumption handle is replayed and the conversation continues; False when the
    new session must genuinely start clean (see the voice-change note in
    _on_voice_change)."""

    def __init__(self, keep_context: bool = True):
        super().__init__()
        self.keep_context = keep_context


def _is_reconnect_signal(exc: BaseException) -> bool:
    """True if `exc` is a _ReconnectSignal, or a(n) (Base)ExceptionGroup that
    wraps one — TaskGroup bundles child exceptions into a group."""
    if isinstance(exc, _ReconnectSignal):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_reconnect_signal(sub) for sub in exc.exceptions)
    return False


def _keep_context_of(exc: BaseException) -> bool:
    """Read `keep_context` off a reconnect signal, unwrapping the group the
    TaskGroup put it in. Defaults to True: an unexpected shape must not silently
    wipe the conversation."""
    if isinstance(exc, _ReconnectSignal):
        return getattr(exc, "keep_context", True)
    if isinstance(exc, BaseExceptionGroup):
        for sub in exc.exceptions:
            if _is_reconnect_signal(sub):
                return _keep_context_of(sub)
    return True


class SonicLive:

    def __init__(self, ui: SonicUI):
        self.ui             = ui
        self._asst_name     = "SONIC"   # updated each session from config
        self.session              = None
        self.audio_in_queue       = None
        self.out_queue            = None
        self._loop                = None
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        self._viz_manager          = None    # visualization state manager for orb
        self._viz_level            = 0.0     # real-time mic audio level (0.0-1.0)
        self._viz_freq             = 0.0     # real-time audio frequency for orb
        self.ui.on_text_command   = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui.on_interrupt      = self.interrupt
        self.ui.on_voice_change   = self._on_voice_change     # voice picker → rebuild session
        self.ui.on_audio_device_change = self._on_audio_device_change
        self._reconnect_event: asyncio.Event | None = None
        self._reconnect_keep = True   # False → next rebuild drops the resumption handle

        # ── Session resumption ─────────────────────────────────────────
        # The server issues a resumption handle every few seconds and reissues
        # it as the conversation moves on. Before this, session_resumption was
        # switched ON in the config and the update was never read, so the handle
        # was thrown away and EVERY reconnect — a dropped packet, a voice change,
        # switching microphone — started an empty session. "Unlimited sessions"
        # leaked through exactly this hole.
        #
        # Deliberately in RAM only, never written to disk. Persisting it would
        # make a fresh launch continue yesterday's conversation, which sounds
        # appealing but breaks the session-summary flow: _save_session_summary
        # runs at shutdown and the morning briefing pops it the next day. A
        # conversation that never ends never produces a summary, and the
        # "yesterday we talked about…" line silently disappears.
        self._resume_handle: str | None = None
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._session_log: list[str] = []          # conversation turns for end-of-session summary

        # ── Smart Conversation Context ──────────────────────────────────────
        # Local conversation buffer for reconnect continuity. Stores rich turn
        # data (role, text, timestamp, tools used) so that when the server
        # drops the session handle, we can inject a detailed summary into the
        # system prompt. The assistant sees exactly what was discussed and
        # continues naturally.
        self._conversation_context: list[dict] = []
        # Each entry: {"role": "user"|"assistant", "text": "...", "ts": float, "tools": [...]}
        self._max_context_turns = 30  # keep last 30 turns
        self._context_injected = False  # True if context was injected on this session

        self._enhanced_live = True  # affective dialog + proactive audio; auto-disabled if the server rejects them
        _core_names = {t["name"] for t in TOOL_DECLARATIONS}
        self._plugin_registry = discover_plugins(
            plugins_dir=Path(__file__).resolve().parent / "plugins",
            core_tool_names=_core_names,
            logger=lambda msg: print(f"[Plugins] {msg}"),
        )
        self.ui.get_plugins = self._plugin_registry.list_for_ui
        self.ui.request_say = self.plugin_say
        # Development engine integration
        self._coding_adapter = _OpenCodeAdapter() if _OpenCodeAdapter else None
        if self._coding_adapter:
            avail = "available" if self._coding_adapter.is_available else "NOT FOUND"
            print(f"[SONIC] Development engine: {avail}")

        # Location awareness
        self._location = LocationContext.get_instance()
        print(f"[SONIC] Location service: {self._location.get_status()['permission']}")

        # Emotion & Personality Engine
        self._personality = SonicPersonality()
        print(f"[Emotion] 🧠 Personality loaded: warmth={self._personality.profile.warmth}, "
              f"humor={self._personality.profile.humor}, empathy={self._personality.profile.empathy}")

    def plugin_say(self, instruction: str) -> None:
        """
        Thread-safe speech channel for plugins: lets a plugin ask SONIC to
        say something short WHILE its run() is still executing (plugins block
        their executor thread, so they can't speak through the tool response
        until they finish). The instruction is injected into the Live session
        exactly like a proactive check-in; Gemini phrases it naturally in the
        user's language. Silently a no-op when no session is connected.
        """
        loop = getattr(self, "_loop", None)
        if not loop or not self.session:
            return

        async def _say():
            try:
                await self.session.send_client_content(
                    turns={"parts": [{"text": instruction}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[PluginSay] {e}")

        try:
            asyncio.run_coroutine_threadsafe(_say(), loop)
        except Exception as e:
            print(f"[PluginSay] {e}")

    def request_reconnect(self, keep_context: bool = True, reason: str = ""):
        """Thread-safe: ask the run loop to tear down and rebuild the Live
        session. Called from the Qt thread. No-op until the async loop and
        reconnect event exist.

        `keep_context=False` drops the resumption handle so the new session
        starts empty — only for changes the server cannot apply to a resumed
        session."""
        loop = getattr(self, "_loop", None)
        ev   = self._reconnect_event
        self._reconnect_keep   = keep_context
        self._reconnect_reason = reason
        if loop and ev is not None:
            loop.call_soon_threadsafe(ev.set)

    def _on_voice_change(self):
        """Voice picker applied.

        The voice is baked into the session at connect time, so a rebuild is
        required. It is rebuilt WITHOUT the resumption handle on purpose:
        resuming restores the server's own session state, and the safe reading
        is that it restores the voice with it — which would make the picker
        appear to do nothing. Losing context here is acceptable because changing
        voice is a deliberate, rare act; losing it on a dropped packet was not."""
        self.request_reconnect(keep_context=False, reason="new voice")

    def _on_audio_device_change(self):
        """Microphone or speaker changed. Both streams are opened inside the
        session TaskGroup, so they can only be re-opened by rebuilding it —
        but the conversation is kept, which is the whole reason resumption
        landed before this feature did."""
        self.request_reconnect(keep_context=True, reason="audio device")

    async def _watch_reconnect(self):
        """Session-scoped task: when a voluntary reconnect is requested, raise a
        signal that unwinds the TaskGroup so the run loop rebuilds the session."""
        assert self._reconnect_event is not None
        await self._reconnect_event.wait()
        self._reconnect_event.clear()
        keep   = self._reconnect_keep
        reason = getattr(self, "_reconnect_reason", "") or "settings"
        self.ui.write_log(
            f"SYS: Applying {reason} — reconnecting"
            + ("..." if keep else " (starting a fresh conversation)...")
        )
        raise _ReconnectSignal(keep_context=keep)

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                "Run: pip install fastapi \"uvicorn[standard]\" cryptography"
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def interrupt(self) -> None:
        """Stop SONIC mid-speech: drain queued audio and open mic immediately."""
        self._interrupted = True
        q = self.audio_in_queue
        if q:
            drained = 0
            while True:
                try:
                    q.get_nowait()
                    drained += 1
                except Exception:
                    break
            if drained:
                print(f"[SONIC] ✋ Interrupted — {drained} audio chunks discarded")
        self.set_speaking(False)
        if self._turn_done_event:
            self._turn_done_event.clear()
        self.ui.write_log("SYS: Interrupted — listening...")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        # Load customization from config
        try:
            _cfg = json.loads(open(API_CONFIG_PATH, encoding="utf-8").read())
            self._asst_name = (_cfg.get("assistant_name") or "SONIC").strip()
            _user_name = (_cfg.get("user_name") or "").strip()
        except Exception:
            self._asst_name = "SONIC"
            _user_name = ""

        # Build memory context — new SQLite brain when user_id available, legacy JSON fallback
        uid = get_user_id()
        if uid:
            # First message of session — use empty query to get broad context
            mem_str = build_prompt_context("general session start")
        else:
            memory = load_memory()
            mem_str = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        # Identity injection — overrides any hardcoded name in prompt.txt
        _addr = (f"ADDRESS: Always call the user '{_user_name}'."
                 if _user_name
                 else "ADDRESS: Address the user with the ordinary respectful form "
                      "for a superior in the language you are currently speaking — "
                      "\"sir\" in English, its everyday equivalent in any other "
                      "language. Never an archaic or aristocratic form, and never "
                      "the form from a different language than the one you are "
                      "speaking in this sentence.")
        identity_ctx = (
            f"[IDENTITY]\n"
            f"Your name is {self._asst_name}. "
            f"Always refer to yourself as {self._asst_name}.\n"
            f"{_addr}\n\n"
        )

        parts = [time_ctx, identity_ctx]
        if mem_str:
            parts.append(mem_str)

        # Personality & emotion context
        personality_block = self._personality.get_prompt_block()
        if personality_block:
            parts.append(personality_block)

        # Location context (only when location is available)
        try:
            loc = self._location.get_current()
            if loc and loc.is_valid:
                parts.append(loc.to_context_block())
        except Exception:
            pass

        parts.append(sys_prompt)

        # ── Reconnect Context Injection ────────────────────────────────────
        # When reconnecting without a server-side handle, inject recent
        # conversation context so the assistant can pick up where it left off.
        # Uses smart selection: recent turns + turns with tools + summary.
        if self._resume_handle is None and self._conversation_context:
            ctx = self._build_reconnect_context()
            parts.append(ctx)
            self._context_injected = True
            print(f"[SONIC] 🔗 Reconnect context injected ({len(self._conversation_context)} turns buffered)")

        cfg = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS + self._plugin_registry.get_tool_declarations()}],
            # Hand back the handle captured from the last session_resumption
            # update. `handle=None` is exactly the old behaviour (ask for
            # handles, start fresh), so the first connect of a run is unchanged.
            session_resumption=types.SessionResumptionConfig(
                handle=self._resume_handle
            ),
            # Sliding-window compression: session never dies from a full context
            # window — SONIC can stay in one conversation for hours
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=get_voice()
                    )
                )
            ),
        )
        if self._enhanced_live:
            # Affective dialog: SONIC hears tone/emotion and adapts its voice.
            # Proactive audio: SONIC stays silent when speech isn't addressed
            # to it (background chatter, talking to someone else in the room).
            cfg["enable_affective_dialog"] = True
            cfg["proactivity"] = types.ProactivityConfig(proactive_audio=True)
        return types.LiveConnectConfig(**cfg)

    def _build_reconnect_context(self) -> str:
        """Build a rich context block for reconnect continuity.

        Smart selection: always include last 10 turns, plus any turns that
        used tools (they contain important state), plus a summary of what
        was discussed. The goal is to give the assistant enough context to
        continue naturally without exceeding token limits.
        """
        lines = ["\n[SESSION CONTEXT — conversation before reconnect]"]
        lines.append("The session was interrupted. Here is what was discussed:")
        lines.append("")

        turns = self._conversation_context
        if not turns:
            return ""

        # Always include last 10 turns (5 user + 5 assistant pairs)
        recent = turns[-10:]
        # Also include any turns with tool calls (important state)
        tool_turns = [t for t in turns[:-10] if t.get("tools")]

        # Combine: tool turns first (context), then recent (continuity)
        selected = tool_turns[-15:] + recent  # cap at 25 turns total
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for t in selected:
            key = (t["role"], t["text"][:50])
            if key not in seen:
                seen.add(key)
                unique.append(t)

        for turn in unique:
            role = "User" if turn["role"] == "user" else self._asst_name
            text = turn["text"]
            # Truncate very long messages
            if len(text) > 300:
                text = text[:297] + "..."
            tools_info = ""
            if turn.get("tools"):
                tools_info = f" [used: {', '.join(turn['tools'][:3])}]"
            lines.append(f"{role}: {text}{tools_info}")

        # Add summary of what was happening
        user_turns = [t for t in turns if t["role"] == "user"]
        if user_turns:
            last_topic = user_turns[-1]["text"][:100]
            lines.append(f"\n[Last topic: {last_topic}]")

        lines.append("[END CONTEXT — continue naturally from where the conversation left off]")
        return "\n".join(lines)

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[SONIC] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # Track tools used in current turn for context
        if not hasattr(self, '_last_tool_calls'):
            self._last_tool_calls = []
        self._last_tool_calls.append(name)

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            uid = get_user_id()
            if uid and key and value:
                # Save to new SQLite brain
                from memory.models import Memory, MemoryType, Importance, Confidence, _now_iso
                mem = Memory(
                    user_id=uid,
                    memory_type=MemoryType.FACT.value if category == "identity" else MemoryType.PREFERENCE.value,
                    content=f"{key}: {value}",
                    importance=Importance.HIGH.value,
                    confidence=Confidence.FACT.value,
                    tags=category,
                )
                from memory import db
                db.store_memory(mem)
                print(f"[Memory] 💾 save_memory (SQLite): {category}/{key} = {value}")
            elif key and value:
                # Fallback to legacy JSON
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory (JSON): {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."
        _tool_timeout = 30  # seconds — prevent hung tools from blocking everything

        try:
            if name == "recall_memory":
                uid = get_user_id()
                if uid:
                    # Use new SQLite brain
                    from memory import retrieval
                    results = retrieval.retrieve_context(uid, args.get("query", ""), limit=8)
                    if results:
                        lines = [f"• {r['content'][:120]} ({r['confidence']})" for r in results]
                        result = f"Yaad hai '{args.get('query', '')}':\n" + "\n".join(lines)
                    else:
                        result = f"Mujhe '{args.get('query', '')}' ke baare mein kuch yaad nahi hai."
                else:
                    result = search_memory(args.get("query", ""), limit=8)

            elif name == "remember":
                content = args.get("content", "")
                if content:
                    result = handle_remember(f"remember {content}",
                                             session_id=getattr(self, "_session_id", ""))
                else:
                    result = "Kya yaad rakhna hai?"

            elif name == "forget_memory":
                content = args.get("content", "")
                if content:
                    result = handle_forget(f"forget {content}")
                else:
                    result = "Kya bhoolna hai?"

            elif name == "memory_query":
                result = handle_memory_query()

            elif name == "undo":
                if str(args.get("action", "")).lower().strip() == "list":
                    items = undo_stack.history()
                    result = ("Things I can undo, most recent first:\n"
                              + "\n".join(f"{i+1}. {t}" for i, t in enumerate(items))
                              ) if items else "I have not changed anything I can undo yet."
                else:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(self._tool_executor, undo_stack.undo_last),
                        timeout=_tool_timeout
                    )

            elif name == "open_app":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: open_app(parameters=args, response=None, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: weather_action(
                        parameters=args, player=self.ui,
                        location_context=self._location)),
                    timeout=_tool_timeout
                )
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: browser_control(parameters=args, player=self.ui)),
                    timeout=60  # browser tasks can take longer
                )
                result = r or "Done."

            elif name == "file_controller":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: file_controller(parameters=args, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or "Done."

            elif name == "send_message":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None)),
                    timeout=_tool_timeout
                )
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: reminder(parameters=args, response=None, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: youtube_video(parameters=args, response=None, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or "Done."

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                if self._vision_busy or (_now - self._vision_last_time) < _cooldown:
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await asyncio.wait_for(
                            loop.run_in_executor(self._tool_executor, _capture_camera),
                            timeout=15
                        )
                        self.ui.start_camera_stream()
                        self._vision_cam_active = True
                        print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                        _stall = "camera"
                    else:
                        img_b, mime_t = await asyncio.wait_for(
                            loop.run_in_executor(self._tool_executor, _capture_screen),
                            timeout=15
                        )
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured. "
                        f"Immediately say ONE short natural sentence in the user's own language, "
                        f"telling them you are looking at their {_stall} right now. "
                        f"Do NOT describe or guess content — the actual image arrives in the NEXT message."
                    )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "computer_settings":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: computer_settings(parameters=args, response=None, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or "Done."

            elif name == "desktop_control":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: desktop_control(parameters=args, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or "Done."

            elif name == "code_helper":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak)),
                    timeout=60  # code tasks can take longer
                )
                result = r or "Done."

            elif name == "dev_agent":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak)),
                    timeout=120  # dev agent can take a long time
                )
                result = r or "Done."

            elif name == "web_search":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: web_search_action(parameters=args, player=self.ui)),
                    timeout=30
                )
                result = r or "Done."
                # Mirror results to the on-screen content panel
                _mode = args.get("mode", "search")
                if r and not r.startswith("No results") and not r.startswith("Search failed"):
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await asyncio.wait_for(
                    loop.run_in_executor(
                        self._tool_executor,
                        lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                    ),
                    timeout=60
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: computer_control(parameters=args, player=self.ui)),
                    timeout=_tool_timeout
                )
                result = r or "Done."

            elif name == "game_updater":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak)),
                    timeout=60
                )
                result = r or "Done."

            elif name == "flight_finder":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: flight_finder(parameters=args, player=self.ui)),
                    timeout=60
                )
                result = r or "Done."

            elif name == "system_status":
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, get_system_status),
                    timeout=10
                )
                result = str(r)

            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.wait_for(asyncio.to_thread(add_monitor, topic), timeout=10)
                elif action == "remove" and topic:
                    result = await asyncio.wait_for(asyncio.to_thread(remove_monitor, topic), timeout=10)
                elif action == "list":
                    topics = await asyncio.wait_for(asyncio.to_thread(list_monitors), timeout=10)
                    result = ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
                else:
                    result = "Specify action (add/remove/list) and a topic."

            elif name == "shutdown_sonic":
                self.ui.write_log("SYS: Shutdown requested.")
                async def _do_shutdown():
                    await self._save_session_summary()
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"parts": [{"text": "Say a brief natural goodbye to the user."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(1.5)
                    import os as _os
                    _os._exit(0)
                asyncio.create_task(_do_shutdown())

            # ── Development task ──────────────────────────────────────────
            elif name == "coding_task":
                if not self._coding_adapter:
                    result = "Development engine is not available."
                elif not self._coding_adapter.is_available:
                    result = "Development engine executable not found."
                else:
                    req = args.get("request", "")
                    ws = args.get("workspace", None)
                    tmo = args.get("timeout", 300)
                    if not req:
                        result = "coding_task requires a 'request' parameter with the task description."
                    else:
                        print(f"[SONIC] Task: {req[:100]}")
                        try:
                            coding_result = await self._coding_adapter.execute(
                                request=req,
                                workspace=ws or None,
                                user_id=get_user_id() or "default",
                                session_id=getattr(self, "_session_id", ""),
                                timeout=int(tmo) if tmo else 300,
                            )
                            result = coding_result.to_response_text()
                        except Exception as e:
                            classification = classify_error(str(e), "coding_task")
                            if classification.retryable:
                                result = f"Task temporarily unavailable. Retrying... ({classification.user_message})"
                            else:
                                result = f"Task could not be completed: {classification.user_message}"

            # ── Smart File Manager ────────────────────────────────────────
            elif name == "smart_find":
                action = args.get("action", "search").lower().strip()
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: _dispatch_smart_find(action, args)),
                    timeout=30
                )
                result = r

            # ── System Controls ───────────────────────────────────────────
            elif name == "system_controls":
                action = args.get("action", "").lower().strip()
                r = await asyncio.wait_for(
                    loop.run_in_executor(self._tool_executor, lambda: _dispatch_system_controls(action, args)),
                    timeout=15
                )
                result = r

            # ── Squad Mode (Multi-Agent Parallel Tasks) ───────────────────
            elif name == "squad_mode":
                r = await asyncio.wait_for(
                    squad_mode(parameters=args, tool_executor=self._tool_executor),
                    timeout=120
                )
                result = r

            # ── Recipe Engine (Automated Workflows) ──────────────────────
            elif name == "recipe_engine":
                r = await asyncio.wait_for(
                    recipe_engine(parameters=args, tool_executor=self._tool_executor),
                    timeout=60
                )
                result = r

            # ── Hologram Mode (Screen Annotation) ────────────────────────
            elif name == "hologram_mode":
                r = await asyncio.wait_for(
                    hologram_mode(parameters=args),
                    timeout=10
                )
                result = r

            # ── Voice Shortcuts ───────────────────────────────────────────
            elif name == "voice_shortcut":
                r = await asyncio.wait_for(
                    voice_shortcut(parameters=args, tool_executor=self._tool_executor),
                    timeout=15
                )
                result = r

            # ── Smart Clipboard ───────────────────────────────────────────
            elif name == "smart_clipboard":
                r = await asyncio.wait_for(
                    smart_clipboard(parameters=args),
                    timeout=10
                )
                result = r

            # ── Auto-Pilot ───────────────────────────────────────────────
            elif name == "autopilot":
                autopilot = get_autopilot()
                command = args.get("command", "")
                if args.get("action"):
                    # Direct action
                    action = args["action"]
                    if action == "open_app":
                        r = await autopilot._open_app(args.get("app", ""))
                    elif action == "close_app":
                        r = await autopilot._close_app(args.get("app", ""))
                    elif action == "screenshot":
                        r = await autopilot._take_screenshot()
                    elif action == "click":
                        r = await autopilot._click_element(args.get("target", ""))
                    elif action == "type":
                        r = await autopilot._type_text(args.get("text", ""))
                    elif action == "copy":
                        r = await autopilot._copy()
                    elif action == "paste":
                        r = await autopilot._paste()
                    else:
                        r = {"error": f"Unknown action: {action}"}
                    result = r.get("message", str(r))
                elif command:
                    task = await autopilot.execute_command(command)
                    result = f"Auto-Pilot: {task.result}" if task.status == "completed" else f"Auto-Pilot failed: {task.error}"
                else:
                    result = "Provide a command or action for Auto-Pilot."

            # ── Universal Translator ──────────────────────────────────────
            elif name == "translator":
                translator = get_translator()
                action = args.get("action", "translate")

                if action == "list_languages":
                    langs = translator.list_languages()
                    result = f"Supported languages ({len(langs)}): " + ", ".join(f"{l['name']} ({l['code']})" for l in langs[:20]) + "..."

                elif action == "set_languages":
                    src = args.get("source", "en")
                    tgt = args.get("target", "es")
                    if translator.set_languages(src, tgt):
                        result = f"Languages set: {src} → {tgt}"
                    else:
                        result = "Invalid language codes. Use 'list_languages' to see options."

                elif action == "translate":
                    text = args.get("text", "")
                    src = args.get("source")
                    tgt = args.get("target")
                    r = await translator.translate(text, src, tgt)
                    result = f"{r.source_text}\n→ {r.translated_text}"
                    if r.pronunciation:
                        result += f"\n[Pronunciation: {r.pronunciation}]"

                elif action == "clone_voice":
                    profile = translator.create_voice_profile("user", [])
                    translator.set_active_voice(profile.id)
                    result = f"Voice cloned! Profile ID: {profile.id}"

                else:
                    result = f"Unknown translator action: {action}"

            # ── Life Dashboard ────────────────────────────────────────────
            elif name == "life_dashboard":
                dash = get_life_dashboard()
                action = args.get("action", "dashboard")

                if action == "dashboard":
                    summary = dash.get_dashboard_summary()
                    score = summary["life_score"]
                    result = (
                        f"Life Score: {score['overall']}/100 ({score['grade']})\n"
                        f"Health: {score['health']} | Finance: {score['finance']}\n"
                        f"Goals: {score['goals']} | Habits: {score['habits']}\n"
                        f"Social: {score['social']}"
                    )

                elif action == "health":
                    insights = dash.get_health_insights()
                    result = f"Health Score: {insights['health_score']}/100\n"
                    for insight in insights["insights"]:
                        result += f"• {insight}\n"

                elif action == "finance":
                    insights = dash.get_financial_insights()
                    result = f"Balance: ${insights['balance']:,.2f}\n"
                    for insight in insights["insights"]:
                        result += f"• {insight}\n"

                elif action == "goals":
                    goals = dash.get_goals_summary()
                    result = f"Goals: {goals['active']} active, {goals['completed']} completed\n"
                    for g in goals["goals"]:
                        result += f"• {g['title']}: {g['progress']}%\n"

                elif action == "habits":
                    habits = dash.get_habits_summary()
                    result = f"Habits: {habits['completed_today']}/{habits['total']} today\n"
                    result += f"Best streak: {habits['best_streak']} days\n"

                elif action == "predict":
                    predictions = dash.predict_future()
                    result = "AI Predictions:\n"
                    for p in predictions["predictions"]:
                        result += f"• [{p['category']}] {p['prediction']}\n"

                elif action == "life_score":
                    score = dash.get_life_score()
                    result = f"Life Score: {score['overall']}/100 ({score['grade']})"

                elif action == "log_health":
                    data = args.get("data", {})
                    dash.log_health(**data)
                    result = f"Health logged: {data}"

                elif action == "log_expense":
                    amount = args.get("amount", 0)
                    cat = args.get("category", "other")
                    desc = args.get("description", "")
                    dash.log_expense(amount, cat, desc)
                    result = f"Expense logged: ${amount:,.2f} ({cat})"

                elif action == "add_goal":
                    title = args.get("title", "New Goal")
                    cat = args.get("category", "personal")
                    dash.add_goal(title, cat, "2026-12-31")
                    result = f"Goal added: {title}"

                elif action == "add_habit":
                    title = args.get("title", "New Habit")
                    cat = args.get("category", "personal")
                    dash.add_habit(title, cat)
                    result = f"Habit added: {title}"

                else:
                    result = f"Unknown dashboard action: {action}"

            else:
                if self._plugin_registry.has(name):
                    r = await loop.run_in_executor(
                        None,
                        lambda: self._plugin_registry.run(name, args, player=self.ui, session_memory=None)
                    )
                    result = r or "Done."
                else:
                    result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[SONIC] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[SONIC] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                sonic_speaking = self._is_speaking
            if not sonic_speaking and not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )
                # Feed the live mic level to the HUD so the waveform reacts to
                # the user's actual voice while listening. Purely cosmetic — any
                # failure here must never disturb the mic.
                try:
                    self.ui.set_audio_level(_pcm_level(indata))
                except Exception:
                    pass

        try:
            def _open_mic(dev):
                return sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    device=dev,
                    callback=callback,
                )

            # Which microphone. resolve() returns None for "system default" and
            # for a saved device that is no longer present — so a headset
            # unplugged since the last run falls back to the built-in mic
            # instead of raising on startup and taking the session with it.
            _mic_name = get_input_device()
            _mic_dev  = audio_devices.resolve(_mic_name, "input")
            if _mic_dev is not None:
                print(f"[SONIC] 🎤 Input device: {_mic_name}")
            try:
                _mic_stream = _open_mic(_mic_dev)
            except Exception as _e:
                # A device the picker listed but the driver will not open right
                # now — exclusive mode, a webcam already in use, a virtual mic
                # whose source went away. Chosen hardware failing must never
                # mean the assistant cannot hear at all.
                if _mic_dev is None:
                    raise
                print(f"[SONIC] ⚠️  Mic '{_mic_name}' failed: {_e} — using default")
                self.ui.write_log(
                    f"SYS: Microphone '{_mic_name}' unavailable — using system default."
                )
                _mic_stream = _open_mic(None)

            with _mic_stream:
                print("[SONIC] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[SONIC] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[SONIC] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    # ── Session resumption ───────────────────────────────────
                    # The server sends this periodically. `resumable` goes false
                    # while a turn is mid-flight — replaying a handle from that
                    # moment is what the flag exists to prevent — so only
                    # resumable handles are kept. This is three lines and it is
                    # the entire fix for "every reconnect forgets everything".
                    _sru = getattr(response, "session_resumption_update", None)
                    if _sru is not None:
                        if getattr(_sru, "resumable", False) and getattr(_sru, "new_handle", None):
                            if self._resume_handle is None:
                                print("[SONIC] 🔗 Session resumption armed")
                            self._resume_handle = _sru.new_handle

                    if response.data:
                        if self._interrupted:
                            pass  # discard: interrupted
                        else:
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Split into ~50 ms chunks so interrupt() stops audio within 50 ms
                            # (24000 Hz × 2 bytes/sample × 0.05 s = 2400 bytes per slice)
                            _audio_data = response.data
                            _SLICE = 2400
                            for _i in range(0, len(_audio_data), _SLICE):
                                self.audio_in_queue.put_nowait(_audio_data[_i : _i + _SLICE])

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._last_user_speech = time.monotonic()

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # If this turn_complete ends an interrupted response, clear the
                            # flag and skip all further processing for that turn.
                            if self._interrupted:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                continue

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                                # Track in conversation context with timestamp
                                self._conversation_context.append({
                                    "role": "user", "text": full_in,
                                    "ts": time.time(), "tools": [],
                                })
                                # Reset tool tracking for this turn
                                self._last_tool_calls = []
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                                # Track tools used in this turn
                                _tools_used = []
                                if hasattr(self, '_last_tool_calls'):
                                    _tools_used = list(self._last_tool_calls)
                                # Track in conversation context with timestamp
                                self._conversation_context.append({
                                    "role": "assistant", "text": full_out,
                                    "ts": time.time(), "tools": _tools_used,
                                })
                                # Keep only recent turns (bounded memory)
                                if len(self._conversation_context) > self._max_context_turns:
                                    self._conversation_context = self._conversation_context[-self._max_context_turns:]
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "sonic",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            out_buf = []

                            # Memory extraction: analyze completed turn for durable facts
                            if full_in and full_out and get_user_id():
                                try:
                                    extract_from_turn(full_in, full_out,
                                                     session_id=getattr(self, "_session_id", ""))
                                    # Async push to Firestore
                                    try:
                                        from memory.cloud_sync import on_memory_changed
                                        on_memory_changed(get_user_id())
                                    except Exception:
                                        pass
                                except Exception as _me:
                                    print(f"[Memory] ⚠️ extraction error: {_me}")

                            # Emotion detection: analyze user's emotional state
                            if full_in:
                                try:
                                    self._personality.process_turn(full_in, full_out)
                                except Exception as _ee:
                                    print(f"[Emotion] ⚠️ detection error: {_ee}")
                                    print(f"[Memory] ⚠️ extraction error: {_me}")

                            # Vision injection: model finished tool-response turn → now send the image
                            if self._pending_vision and self.session:
                                import base64 as _b64
                                img_b, mime_t, question, angle = self._pending_vision
                                self._pending_vision = None
                                b64 = _b64.b64encode(img_b).decode("ascii")
                                print(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")
                                await self.session.send_client_content(
                                    turns={"parts": [
                                        {"inline_data": {"mime_type": mime_t, "data": b64}},
                                        {"text": question},
                                    ]},
                                    turn_complete=True,
                                )
                                # Mark next turn_complete behaviour depending on angle
                                if self._vision_cam_active:
                                    # Camera: keep busy until SONIC finishes speaking the answer
                                    self._vision_cam_active    = False
                                    self._vision_close_pending = True
                                else:
                                    # Screen-only: no camera to close; release busy flag now
                                    self._vision_busy = False
                            elif self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[SONIC] 📞 {fc.name}")
                        # Parallelize independent tool calls for faster response
                        tasks = [self._execute_tool(fc) for fc in response.tool_call.function_calls]
                        fn_responses = await asyncio.gather(*tasks, return_exceptions=True)
                        # Convert exceptions to error responses
                        cleaned = []
                        for i, r in enumerate(fn_responses):
                            if isinstance(r, Exception):
                                cleaned.append(types.Part.from_function_response(
                                    name=response.tool_call.function_calls[i].name,
                                    response={"error": str(r)}
                                ))
                            else:
                                cleaned.append(r)
                        await self.session.send_tool_response(
                            function_responses=cleaned
                        )
        except Exception as e:
            print(f"[SONIC] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[SONIC] 🔊 Play started")

        _spk_name = get_output_device()
        _spk_dev  = audio_devices.resolve(_spk_name, "output")
        if _spk_dev is not None:
            print(f"[SONIC] 🔊 Output device: {_spk_name}")

        def _open_spk(dev):
            st = sd.RawOutputStream(
                samplerate=RECEIVE_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                device=dev,
            )
            st.start()
            return st

        try:
            stream = _open_spk(_spk_dev)
        except Exception as _e:
            # A chosen output that the host API accepts by name but refuses to
            # open (exclusive mode, wrong sample rate, device asleep) must not
            # cost the user their voice. Fall back to the default and say so.
            if _spk_dev is None:
                raise
            print(f"[SONIC] ⚠️  Output device '{_spk_name}' failed: {_e} — using default")
            self.ui.write_log(f"SYS: Speaker '{_spk_name}' unavailable — using system default.")
            stream = _open_spk(None)

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)

                # Batch all immediately-available chunks into one write to reduce
                # thread-pool round-trips (was one asyncio.to_thread per 50ms slice).
                # Cap at ~200 ms so interrupt() still stops audio within ~200 ms.
                batch = bytearray(chunk)
                while len(batch) < 9600:   # 9600 bytes ≈ 200 ms at 24 kHz / 16-bit mono
                    try:
                        batch.extend(self.audio_in_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                # Drive the HUD waveform from SONIC's own voice while speaking.
                try:
                    self.ui.set_audio_level(_pcm_level(
                        np.frombuffer(bytes(batch), dtype=np.int16)))
                except Exception:
                    pass

                try:
                    await asyncio.to_thread(stream.write, bytes(batch))
                except (RuntimeError, asyncio.CancelledError):
                    break   # executor shutting down — exit cleanly
        except Exception as e:
            print(f"[SONIC] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing optimized for speed:
          Phase 1 — instant greeting (no tools) → speech starts in <1s
          Phase 2 — news pre-fetched in a background thread while Phase 1 plays,
                    delivered as ready text (no Gemini tool-call round-trip) and
                    shown on the UI content panel. Waits for turn_complete event
                    instead of a fixed sleep so there is no unnecessary gap.
        """
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")
        time_str = datetime.now().strftime("%H:%M")

        # Start fetching news immediately — runs in parallel while phase 1 plays
        loop = asyncio.get_event_loop()
        news_future = loop.run_in_executor(self._tool_executor, _fetch_news_sync, "top world news today")

        await asyncio.sleep(0.3)
        if not self.session:
            return

        # ── Phase 1: instant greeting ─────────────────────────────────────────
        # The briefing fires before the user has said anything, so the
        # remembered language is the only signal there is. It is a starting
        # point, not a setting: the moment they reply, their language wins.
        lang_clause = (f" Speak this greeting in {lang}, then follow the "
                       f"user's own language from their first reply onward."
                       if lang else "")
        name_clause = f" Address the user as {name}." if name else ""

        # Inject last session context if available — pop removes it so it's never repeated
        last = await asyncio.to_thread(pop_last_session)
        session_clause = ""
        if last:
            try:
                _delta = (datetime.now() - datetime.strptime(last["date"], "%Y-%m-%d")).days
                _when  = "earlier today" if _delta == 0 else ("yesterday" if _delta == 1 else f"{_delta} days ago")
            except Exception:
                _when = "last time"
            session_clause = (
                f" Also briefly and naturally mention that {_when}: {last['summary']}"
            )

        p1 = (
            f"Greet the user warmly, mention it is {time_str}, and say you are fetching today's news now.{session_clause} "
            f"Keep it to 2 short sentences max. Do not call any tools.{lang_clause}{name_clause}"
        )

        # Clear the turn-done event so we can wait for Phase 1 to finish
        if self._turn_done_event:
            self._turn_done_event.clear()

        await self.session.send_client_content(
            turns={"parts": [{"text": p1}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fire as soon as Phase 1 audio is done ───────────────────
        async def _deliver_news():
            try:
                lang_str = (f" Speak in {lang} unless the user has since "
                            f"spoken another language, in which case use theirs."
                            if lang else "")

                # Wait for news fetch (already running) and Phase 1 turn-complete
                # in parallel — whichever takes longer determines the wait time
                news_done   = asyncio.wrap_future(news_future)
                turn_waited = False
                if self._turn_done_event:
                    try:
                        await asyncio.wait_for(self._turn_done_event.wait(), timeout=6.0)
                        turn_waited = True
                    except asyncio.TimeoutError:
                        pass

                # Extra buffer: turn_complete fires when Gemini finishes *generating*
                # Phase 1, but audio may still be playing.  Waiting a beat here
                # prevents Phase 2 audio from arriving while Phase 1 is mid-sentence
                # (which sounds like a "repeated first response" to the user).
                if turn_waited:
                    await asyncio.sleep(0.8)
                else:
                    await asyncio.sleep(1.0)

                try:
                    news_text = await asyncio.wait_for(news_done, timeout=8.0)
                except Exception as e:
                    self.ui.write_log(f"SYS: News fetch timed out/failed: {e!r}")
                    news_text = ""

                if not self.session:
                    return

                failed = (not news_text) or news_text.startswith(
                    ("No news found", "Search failed", "Please provide")
                )
                if not failed:
                    # Show on UI content panel immediately
                    self.ui.show_content("NEWS — top world news today", news_text)

                    p2 = (
                        f"[BRIEFING] Here are today's top news headlines:\n{news_text}\n\n"
                        "Pick ONE headline, summarise it in one sentence, then say the full list "
                        f"is displayed on screen. Do not call any tools.{lang_str}"
                    )
                else:
                    self.ui.write_log(
                        f"SYS: News unavailable — backend returned: {news_text[:120]!r}"
                    )
                    p2 = (
                        "News headlines could not be fetched right now. "
                        f"Let the user know briefly.{lang_str}"
                    )

                await self.session.send_client_content(
                    turns={"parts": [{"text": p2}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Briefing phase 2 (news) sent.")
            except Exception as e:
                print(f"[Briefing] Phase 2 error: {e}")
                self.ui.write_log(f"SYS: Briefing phase 2 failed: {e}")

        asyncio.create_task(_deliver_news())

    # ── Session memory ──────────────────────────────────────────────────────────

    async def _save_session_summary(self) -> None:
        """Summarise the current session in 1-2 sentences and save to long_term.json."""
        log = self._session_log
        if len(log) < 3:          # need at least one exchange to be worth saving
            return
        self._session_log = []    # reset immediately so the next session starts clean

        # Save conversation context for crash recovery
        self._save_conversation_context()

        memory = load_memory()
        lang_entry = memory.get("identity", {}).get("language", {})
        lang = (lang_entry.get("value", "") if isinstance(lang_entry, dict) else str(lang_entry)).strip()
        lang = lang or "English"

        convo = "\n".join(log[-40:])   # cap at last 40 turns to stay within token budget
        prompt = (
            f"Summarize this conversation in 1-2 sentences in {lang}. "
            "Focus on what the user accomplished or discussed. "
            "Output ONLY the summary text, nothing else:\n\n" + convo
        )
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=_get_api_key())
            resp   = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-flash-latest",
                contents=prompt,
            )
            summary = (resp.text or "").strip()
            if summary:
                save_session_summary(summary, lang)
        except Exception as e:
            print(f"[Memory] ⚠️ Session summary failed: {e}")

        # Run consolidation cycle (dedup, conflict resolution, decay)
        try:
            stats = consolidate_memory()
            if stats:
                print(f"[Memory] 🔄 Consolidation: {stats}")
        except Exception as e:
            print(f"[Memory] ⚠️ Consolidation error: {e}")

    # ── Conversation context persistence ─────────────────────────────────────

    def _save_conversation_context(self) -> None:
        """Save conversation context to disk for crash recovery."""
        if not self._conversation_context:
            return
        try:
            import json
            from pathlib import Path
            ctx_path = Path.home() / ".sonic" / "conversation_context.json"
            ctx_path.parent.mkdir(parents=True, exist_ok=True)
            # Save last 30 turns
            data = self._conversation_context[-30:]
            ctx_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"[Memory] 💾 Saved {len(data)} turns of conversation context")
        except Exception as e:
            print(f"[Memory] ⚠️ Failed to save context: {e}")

    def _load_conversation_context(self) -> None:
        """Load conversation context from disk (crash recovery)."""
        try:
            import json
            from pathlib import Path
            ctx_path = Path.home() / ".sonic" / "conversation_context.json"
            if ctx_path.exists():
                data = json.loads(ctx_path.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    self._conversation_context = data[-30:]
                    print(f"[Memory] 🔗 Loaded {len(self._conversation_context)} turns from previous session")
        except Exception as e:
            print(f"[Memory] ⚠️ Failed to load context: {e}")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if not alert or not self.session:
                continue
            # Don't interrupt an active conversation
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking or (time.monotonic() - self._last_user_speech) < 10:
                continue
            try:
                await self.session.send_client_content(
                    turns={"parts": [{"text": alert}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Monitor] ⚠️ Could not send alert: {e}")

    # ── Background monitor ──────────────────────────────────────────────────────

    async def _run_background_monitor(self) -> None:
        """Check user-configured topics once per day; speak alerts when new headlines appear."""
        await asyncio.sleep(300)          # wait 5 min after startup before first check
        while True:
            if self.session:
                # Don't interrupt if user spoke recently or SONIC is mid-sentence
                with self._speaking_lock:
                    speaking = self._is_speaking
                recent_speech = (time.monotonic() - self._last_user_speech) < 30
                if not speaking and not recent_speech:
                    try:
                        alerts = await asyncio.to_thread(monitor_check_all)
                        memory = load_memory()
                        lang_e = memory.get("identity", {}).get("language", {})
                        lang   = (lang_e.get("value", "") if isinstance(lang_e, dict) else str(lang_e)).strip() or "English"
                        for alert in alerts:
                            msg = (
                                f"{alert}\n\n"
                                f"Inform the user about this development naturally in {lang}. "
                                "One brief sentence only."
                            )
                            await self.session.send_client_content(
                                turns={"parts": [{"text": msg}]},
                                turn_complete=True,
                            )
                            self.ui.write_log(f"SYS: Monitor alert sent.")
                            await asyncio.sleep(6)   # gap between consecutive alerts
                    except Exception as e:
                        print(f"[Monitor] ⚠️ Background check error: {e}")
            await asyncio.sleep(1800)     # check every 30 minutes

    # ── Proactive mode ──────────────────────────────────────────────────────────

    async def _run_proactive_mode(self) -> None:
        """
        Background task: periodically checks if the user has been silent long enough,
        then hands time + memory context to Gemini so it can decide what (if anything)
        to say proactively. No hardcoded rules — Gemini makes the call.
        """
        while True:
            await asyncio.sleep(60)   # evaluate once per minute

            if not self.session:
                continue

            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory       = await asyncio.to_thread(load_memory)
                monitors     = await asyncio.to_thread(list_monitors)
                recent_turns = self._session_log[-8:] if self._session_log else []
                prompt = self._proactive.build_prompt(
                    memory       = memory,
                    monitors     = monitors or None,
                    recent_turns = recent_turns or None,
                )
                await self.session.send_client_content(
                    turns={"parts": [{"text": prompt}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Proactive check-in.")
            except Exception as e:
                print(f"[Proactive] ⚠️ {e}")

    # ── Phone audio relay ────────────────────────────────────────────────────────

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()

    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": text}]},
                        turn_complete=True,
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    print(f"[Dashboard] Dropped command (no session): {text}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._reconnect_event = asyncio.Event()

        # Dedicated executor for tool calls — larger pool so slow tools don't block audio
        import concurrent.futures
        self._tool_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=12, thread_name_prefix="sonic-tool"
        )

        # Load conversation context from previous session (crash recovery)
        self._load_conversation_context()

        # ── Wire the shared core services to the interface ───────────────────
        # The confirmation gate is useless without a way to ask, and a memory
        # trim is invisible without a way to say so. Both are bound once here
        # rather than passed down through every action signature.
        confirm_gate.bind(
            show = self.ui.show_confirm,
            hide = self.ui.hide_confirm,
            log  = self.ui.write_log,
        )
        set_trim_notifier(self.ui.write_log)

        # Tell the device picker the exact rates the streams open at, from the
        # constants that actually open them — so it can never list a device that
        # cannot be opened at them.
        audio_devices.configure(SEND_SAMPLE_RATE, RECEIVE_SAMPLE_RATE)

        # Enumerate audio devices off-thread. The settings drawer must never pay
        # for host-API enumeration on the Qt thread.
        audio_devices.prefetch()

        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            asyncio.create_task(self._dashboard.serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            self._dashboard = None

        while True:
            try:
                print("[SONIC] Connecting...")
                self.ui.set_state("THINKING")
                _resumed_with = self._resume_handle is not None
                config = self._build_config()

                # Fresh client on every reconnect — avoids stale HTTP session state
                # v1alpha carries the enhanced audio features (affective dialog,
                # proactive audio); if they get rejected we fall back to v1beta.
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1alpha" if self._enhanced_live else "v1beta"}
                )

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    # Reset transient state that must not carry over from a previous session
                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False

                    print("[SONIC] Connected.")
                    if _resumed_with:
                        # Say it plainly: the difference between "it reconnected"
                        # and "it reconnected and still knows what we were doing"
                        # is the whole point, and it is invisible otherwise.
                        self.ui.write_log("SYS: Reconnected — conversation restored.")
                    elif self._context_injected:
                        # Local context was injected — assistant has memory
                        n = len(self._conversation_context)
                        self.ui.write_log(f"SYS: Reconnected — {n} turns of context restored from memory.")
                        self._context_injected = False
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: SONIC online.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    self._reconnect_event.clear()  # ignore requests from before this session
                    tg.create_task(self._watch_reconnect())
                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_background_monitor())
                    tg.create_task(self._run_proactive_mode())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())

                    # Morning briefing — fires once per process launch (if enabled)
                    if not self._briefing_sent and get_brief_enabled():
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                # Catches both Exception and BaseExceptionGroup (Python 3.11+
                # TaskGroup raises BaseExceptionGroup when tasks are cancelled
                # externally, which `except Exception` would miss, letting the
                # exception escape the while-loop and causing asyncio.run() to
                # start shutdown — resulting in "executor after shutdown" errors).
                # Voluntary reconnect (voice change) — not an error. Rebuild the
                # session immediately with no backoff and no scary logs.
                if _is_reconnect_signal(e):
                    print("[SONIC] Voluntary reconnect requested.")
                    if not _keep_context_of(e):
                        # A deliberate clean slate (voice change) — drop the
                        # handle so the next connect really does start empty.
                        self._resume_handle = None
                    self._conn_backoff = 0
                    continue

                # A resumption handle the server will not accept — expired, or
                # belonging to a session it has since dropped. Without this, the
                # same dead handle would be replayed on every retry and the
                # assistant would never come back at all: the feature meant to
                # survive a reconnect would be the thing preventing one. Drop it
                # once and let the next attempt start clean.
                if _resumed_with and (
                    "resum" in str(e).lower()
                    or "handle" in str(e).lower()
                    or "INVALID_ARGUMENT" in str(e)
                    or "NOT_FOUND" in str(e)
                ):
                    print("[SONIC] 🔗 Resumption handle rejected — using local context fallback")
                    self.ui.write_log("SYS: Session handle expired — using local conversation memory.")
                    self._resume_handle = None
                    # NOTE: _conversation_context is NOT cleared — it will be
                    # injected into the system prompt on the next connect so
                    # the assistant can continue from where it left off.
                    self._conn_backoff = 0
                    continue

                err_str = str(e)
                print(f"[SONIC] Error ({type(e).__name__}): {e}")
                traceback.print_exc()

                # Enhanced audio features rejected by the server (preview API
                # drift) — drop them and reconnect with the plain config.
                if self._enhanced_live and (
                    "INVALID_ARGUMENT" in err_str
                    or "affective" in err_str.lower()
                    or "proactiv" in err_str.lower()
                    or "Unknown name" in err_str
                    or "unexpected keyword" in err_str
                ):
                    self._enhanced_live = False
                    self.ui.write_log(
                        "SYS: Advanced audio features unavailable — reconnecting without them."
                    )
                    continue

                # Invalid API key — stop hammering the API, prompt re-configuration
                if "API key not valid" in err_str or "1007" in err_str:
                    self.ui.write_log("ERR: API key invalid — please re-enter your key.")
                    self.ui.set_state("SLEEPING")
                    self.ui.prompt_reconfig()
                    while not self.ui._win._ready:
                        await asyncio.sleep(1)
                    print("[SONIC] New API key saved — reconnecting...")
                    _conn_backoff = 3
                    continue

                # Network / timeout errors — log clearly and back off
                is_net_err = any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                ))
                if is_net_err:
                    _conn_backoff = min(getattr(self, "_conn_backoff", 3) * 2, 60)
                    self._conn_backoff = _conn_backoff
                    self.ui.write_log(
                        f"NET: Bağlantı kurulamadı — {_conn_backoff}s sonra tekrar deneniyor. "
                        "(VPN gerekiyor olabilir)"
                    )
                else:
                    self._conn_backoff = 3
            finally:
                self.session = None
                # Only save if there was a real conversation (≥3 turns)
                if len(self._session_log) >= 3:
                    asyncio.create_task(self._save_session_summary())

            # Log session resumption status for debugging
            if self._resume_handle:
                print(f"[SONIC] 🔗 Session handle preserved for reconnect")
            elif self._conversation_context:
                print(f"[SONIC] 🔗 No handle — {len(self._conversation_context)} turns of local context will be injected on reconnect")
            else:
                print("[SONIC] 🔗 No handle, no context — fresh start")

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            delay = getattr(self, "_conn_backoff", 3)
            print(f"[SONIC] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)


# ── Smart Find dispatch ──────────────────────────────────────────────────────
def _dispatch_smart_find(action: str, args: dict) -> str:
    import json as _json
    dispatch = {
        "search": lambda: find_files(
            query=args.get("query", ""),
            directory=args.get("directory", ""),
            category=args.get("category", ""),
            extension=args.get("extension", ""),
            max_results=args.get("max_results", 30),
            min_size_mb=args.get("min_size_mb", 0),
            modified_days=args.get("modified_days", 0),
        ),
        "recent": lambda: find_recent_files(
            directory=args.get("directory", ""),
            days=args.get("modified_days", 7),
            max_results=args.get("max_results", 30),
        ),
        "large": lambda: find_large_files(
            directory=args.get("directory", ""),
            min_mb=args.get("min_size_mb", 100),
            max_results=args.get("max_results", 20),
        ),
        "duplicates": lambda: find_duplicates(
            directory=args.get("directory", ""),
            max_results=args.get("max_results", 50),
        ),
        "categorize": lambda: categorize_files(
            directory=args.get("directory", ""),
        ),
        "open": lambda: open_path(args.get("path", "")),
        "folder_size": lambda: get_folder_size(args.get("path", "")),
        "list": lambda: list_folder(
            path=args.get("path", ""),
            max_items=args.get("max_results", 30),
        ),
        "cleanup": lambda: disk_cleanup(
            dry_run=args.get("dry_run", True),
        ),
        "recycle_bin": lambda: empty_recycle_bin(),
    }
    fn = dispatch.get(action)
    if not fn:
        return f"Unknown smart_find action: {action}. Use: {', '.join(dispatch.keys())}"
    try:
        r = fn()
        return _json.dumps(r, indent=1, default=str) if isinstance(r, dict) else str(r)
    except Exception as e:
        return f"smart_find error: {e}"


# ── System Controls dispatch ─────────────────────────────────────────────────
def _dispatch_system_controls(action: str, args: dict) -> str:
    import json as _json
    value = args.get("value", "")
    dispatch = {
        "volume_preset": lambda: volume_preset(value or "medium"),
        "volume_status": lambda: volume_get_status(),
        "brightness_preset": lambda: brightness_preset(value or "medium"),
        "brightness_status": lambda: brightness_get_status(),
        "display_info": lambda: display_info(),
        "battery": lambda: battery_status(),
        "wifi": lambda: wifi_status(),
        "bluetooth": lambda: bluetooth_status(),
        "sleep": lambda: sleep_computer(),
        "hibernate": lambda: hibernate_computer(),
        "monitor_off": lambda: monitor_off(),
        "disk_space": lambda: disk_space(),
        "network": lambda: network_info(),
        "processes": lambda: list_processes(sort_by=args.get("sort_by", "cpu")),
        "kill_process": lambda: _kill_process_by_name_or_pid(value),
        "clipboard_get": lambda: clipboard_get(),
        "clipboard_set": lambda: clipboard_set(value),
        "quick_launch": lambda: quick_launch(value),
        "system_info": lambda: system_info(),
        "env": lambda: get_env(value),
        "scheduled_tasks": lambda: list_scheduled_tasks(),
        "recycle_bin": lambda: empty_recycle_bin(),
    }
    fn = dispatch.get(action)
    if not fn:
        return f"Unknown system_controls action: {action}. Use: {', '.join(dispatch.keys())}"
    try:
        r = fn()
        return _json.dumps(r, indent=1, default=str) if isinstance(r, dict) else str(r)
    except Exception as e:
        return f"system_controls error: {e}"


def _kill_process_by_name_or_pid(value: str) -> dict:
    try:
        pid = int(value)
        return kill_process(pid=pid)
    except (ValueError, TypeError):
        return kill_process(name=value)


def main():
    # ── Create QApplication first ────────────────────────────────────────
    _app = QApplication.instance() or QApplication(sys.argv)
    _app.setStyle("Fusion")
    _app.setApplicationName("SONIC AI")

    # ── Bootstrap: first-run dependency check ─────────────────────────────
    try:
        from bootstrap import Bootstrapper
        _boot = Bootstrapper()
        if _boot.needs_bootstrap():
            print("[BOOTSTRAP] First run detected — running setup...")
            _boot.show_setup_ui(_app)
            print("[BOOTSTRAP] Setup complete")
        else:
            print("[BOOTSTRAP] Previously completed — skipping")
    except Exception as e:
        print(f"[BOOTSTRAP] Skipped: {e}")

    # ── Splash screen ─────────────────────────────────────────────────────
    from splash import SonicSplash

    _splash_done = False

    def _on_splash_done():
        nonlocal _splash_done
        _splash_done = True
        _splash.close()
        _show_main_window()

    _splash = SonicSplash(on_done=_on_splash_done)

    # ── Create main window (hidden initially) ─────────────────────────────
    from PyQt6.QtWidgets import QMainWindow
    from PyQt6.QtGui import QGuiApplication, QIcon
    from pathlib import Path

    _base = Path(__file__).resolve().parent
    _frame = QMainWindow()
    _frame.setWindowTitle("SONIC AI")
    _frame.setMinimumSize(1200, 800)
    _frame.resize(1400, 900)
    _frame.setStyleSheet("background: #080c14;")

    _icon_path = _base / "config" / "sonic.ico"
    if _icon_path.exists():
        _frame.setWindowIcon(QIcon(str(_icon_path)))

    _screen = QGuiApplication.primaryScreen().availableGeometry()
    _frame.move(
        (_screen.width() - 1400) // 2,
        (_screen.height() - 900) // 2,
    )

    # ── Show splash screen ────────────────────────────────────────────────
    _splash.show()
    _splash.move(
        (_screen.width() - 480) // 2,
        (_screen.height() - 640) // 2,
    )

    def _show_main_window():
        # ── Init memory + create UI directly ──────────────────────────────
        init_memory_system()
        ui = SonicUI("face.png")
        _frame.setCentralWidget(ui._win)
        _frame.show()
        print("[SONIC] App loaded")

        # ── Startup update check (background, non-blocking) ────────────────
        try:
            from updater.startup import check_for_updates_on_startup
            check_for_updates_on_startup(ui)
        except Exception as e:
            print(f"[UPDATER] Startup check skipped: {e}")

        # ── Wire bridges ──────────────────────────────────────────────────
        def _on_auth_completed():
            try:
                from auth.core import get_auth
                auth = get_auth()
                uid = auth.user_id
                if uid:
                    set_user_id(uid)
                    print(f"[Memory] Auth completed — user_id: {uid}")
                    try:
                        from memory.memory_manager import remember, recall_memory
                        profile = auth.get_extended_profile().get("profile", {})
                        if profile.get("full_name"):
                            remember("name", profile["full_name"], "identity")
                        if profile.get("location"):
                            remember("city", profile["location"], "identity")
                            _location.set_saved_city(profile["location"])
                        _location.set_user(uid)
                        _location.load_from_profile(profile)
                        city_result = recall_memory("city")
                        if city_result and "city" in city_result.lower():
                            import re
                            match = re.search(r"city[:\s]+(\w+)", city_result, re.IGNORECASE)
                            if match:
                                _location.load_from_memory(match.group(1))
                    except Exception:
                        pass
                    try:
                        from memory.cloud_sync import on_login
                        pull_stats = on_login(uid)
                        if pull_stats:
                            print(f"[CloudSync] Pulled: {pull_stats}")
                    except Exception as e:
                        print(f"[CloudSync] Login sync error: {e}")
            except Exception as e:
                print(f"[Memory] Auth bridge error: {e}")

        ui.auth_completed.connect(_on_auth_completed)

        def _runner():
            ui.wait_for_api_key()
            try:
                from auth.core import get_auth
                auth = get_auth()
                session = auth.restore_session()
                if session and isinstance(session, dict) and session.get("user_id"):
                    uid = session["user_id"]
                    set_user_id(uid)
                    print(f"[Memory] Restored session: {session.get('email', 'unknown')}")
                    try:
                        from memory.cloud_sync import on_login
                        on_login(uid)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[Memory] No auth session: {e}")

            sonic = SonicLive(ui)
            ui._win._sonic_live = sonic
            try:
                asyncio.run(sonic.run())
            except KeyboardInterrupt:
                print("\nShutting down...")

        threading.Thread(target=_runner, daemon=True).start()

    # ── Run event loop ────────────────────────────────────────────────────
    _app.exec()

if __name__ == "__main__":
    main()