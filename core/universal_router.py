"""SONIC AI — Universal Natural Language Router.

Reads any user utterance ("open chrome", "play lofi music",
"remind me at 5pm to call mom", "translate this to spanish") and routes it
to the right action among SONIC's 45+ existing action modules.

Strategy (in order):
  1. Direct intent match via keyword table (fast, offline, zero-LLM cost)
  2. Regex/pattern extraction (times, file paths, languages, etc.)
  3. Optional LLM fallback for ambiguous phrasing

The router never breaks the action contract: it returns a JSON-serialisable
`Route` with `action`, `args`, `confidence`, `explanation`.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Optional


# ═════════════════════════════════════════════════════════════════════════════
# Route
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class Route:
    """Result of routing a user utterance to an action."""
    action: str                          # e.g. "open_app"
    args: dict = field(default_factory=dict)
    confidence: float = 0.0
    explanation: str = ""                # human-readable reasoning
    source: str = "keyword"              # keyword|regex|llm|fallback
    raw_utterance: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Intent catalogue — maps verb phrases → action modules + arg extractors
# ═════════════════════════════════════════════════════════════════════════════

# Each entry: (canonical_action, [keyword_phrases], required_arg_keys, optional_arg_keys)
_INTENTS: list[dict] = [
    # ── App / window control ─────────────────────────────────────────────────
    {"action": "open_app",            "phrases": ["open", "launch", "start", "run"],
     "args": {"target": r".*"}, "examples": ["open chrome", "launch spotify"]},
    {"action": "close_app",           "phrases": ["close", "quit", "exit", "kill"],
     "args": {"target": r".*"}},
    {"action": "switch_window",       "phrases": ["switch to", "focus", "go to", "show"],
     "args": {"target": r".*"}},

    # ── File system ──────────────────────────────────────────────────────────
    {"action": "find_file",           "phrases": ["find file", "locate", "where is", "search for file"],
     "args": {"pattern": r".*"}},
    {"action": "open_file",           "phrases": ["open file", "show file"],
     "args": {"path": r".*"}},
    {"action": "organize_downloads",  "phrases": ["organize downloads", "tidy downloads", "sort downloads"]},
    {"action": "cleanup_temp",        "phrases": ["clean temp", "clean cache", "free space", "clear junk"]},

    # ── Web / browser ────────────────────────────────────────────────────────
    {"action": "web_search",          "phrases": ["search for", "google", "look up", "search web"],
     "args": {"query": r".*"}},
    {"action": "open_url",            "phrases": ["go to", "navigate to", "browse", "open url"],
     "args": {"url": r".*"}},
    {"action": "play_youtube",        "phrases": ["play", "youtube", "watch"],
     "args": {"query": r".*"}},
    {"action": "download",            "phrases": ["download", "fetch"],
     "args": {"url": r".*"}},

    # ── System ───────────────────────────────────────────────────────────────
    {"action": "set_volume",          "phrases": ["volume", "louder", "quieter", "mute", "unmute"],
     "args": {"level": r"\d+"}},
    {"action": "screenshot",          "phrases": ["screenshot", "snap screen", "capture screen"]},
    {"action": "lock_computer",       "phrases": ["lock", "lock pc", "lock computer"]},
    {"action": "shutdown",            "phrases": ["shutdown", "shut down", "power off"]},
    {"action": "restart",             "phrases": ["restart", "reboot"]},
    {"action": "sleep",               "phrases": ["sleep", "hibernate"]},

    # ── Productivity ─────────────────────────────────────────────────────────
    {"action": "set_reminder",        "phrases": ["remind me", "reminder", "alert me"],
     "args": {"when": r".*", "what": r".*"}},
    {"action": "create_note",         "phrases": ["note", "write down", "jot down"],
     "args": {"content": r".*"}},
    {"action": "translate",           "phrases": ["translate", "convert to", "in spanish", "in french",
                                                  "in urdu", "in hindi", "in arabic"],
     "args": {"text": r".*", "target_lang": r".*"}},
    {"action": "summarize",           "phrases": ["summarize", "summary", "tldr", "brief me"]},

    # ── Communication ────────────────────────────────────────────────────────
    {"action": "send_email",          "phrases": ["send email", "email", "mail to"],
     "args": {"to": r".*", "subject": r".*", "body": r".*"}},
    {"action": "send_message",        "phrases": ["send message", "message", "text", "whatsapp"],
     "args": {"to": r".*", "body": r".*"}},

    # ── AI / Universe ────────────────────────────────────────────────────────
    {"action": "ask_ai",              "phrases": ["ask", "tell me", "explain", "what is", "who is",
                                                  "how does", "why"],
     "args": {"prompt": r".*"}},
    {"action": "generate_code",       "phrases": ["write code", "generate code", "code me", "script"],
     "args": {"prompt": r".*"}},
    {"action": "run_python",          "phrases": ["run python", "execute python", "evaluate"],
     "args": {"code": r".*"}},
    {"action": "research",            "phrases": ["research", "deep dive", "investigate"],
     "args": {"topic": r".*"}},

    # ── System info ──────────────────────────────────────────────────────────
    {"action": "system_status",       "phrases": ["system status", "how's the pc", "pc health",
                                                  "battery", "cpu usage"]},
    {"action": "weather",             "phrases": ["weather", "temperature", "forecast"]},
    {"action": "time_now",            "phrases": ["what time", "current time", "tell me the time"]},
    {"action": "today_calendar",      "phrases": ["today's schedule", "my calendar", "my meetings"]},

    # ── Entertainment ────────────────────────────────────────────────────────
    {"action": "play_music",          "phrases": ["play music", "play song", "play the song"]},
    {"action": "next_track",          "phrases": ["next song", "next track", "skip"]},
    {"action": "pause_media",         "phrases": ["pause", "stop music"]},
    {"action": "resume_media",        "phrases": ["resume", "continue"]},

    # ── YouTube + Video (universal) ───────────────────────────────────────────
    {"action": "yt_next",             "phrases": ["next video", "next on youtube",
                                                 "skip video", "play next",
                                                 "skip to next", "play the next"]},
    {"action": "yt_previous",         "phrases": ["previous video", "go back",
                                                 "back video", "previous on youtube"]},
    {"action": "yt_pause",            "phrases": ["pause youtube", "pause the youtube",
                                                 "pause video", "pause the video",
                                                 "pause this video"]},
    {"action": "yt_resume",           "phrases": ["resume youtube", "play the youtube",
                                                 "resume video", "play the video"]},
    {"action": "yt_skip_ad",          "phrases": ["skip ad", "skip youtube ad",
                                                 "skip the ad", "skip this ad",
                                                 "skip advertisement"]},
    {"action": "yt_like",             "phrases": ["like this", "like video",
                                                 "like this video", "thumbs up"]},
    {"action": "yt_subscribe",        "phrases": ["subscribe", "subscribe to channel",
                                                 "subscribe to this"]},
    {"action": "yt_fullscreen",       "phrases": ["fullscreen", "go fullscreen",
                                                 "make fullscreen", "full screen"]},
    {"action": "yt_seek",             "phrases": ["seek", "skip ahead", "jump ahead",
                                                 "skip in video", "fast forward"]},
    {"action": "play_youtube",        "phrases": ["play youtube", "open youtube",
                                                 "youtube", "watch youtube"]},
    {"action": "video_play",          "phrases": ["play video", "resume video"]},
    {"action": "video_pause",         "phrases": ["pause video", "pause the video",
                                                 "pause the player"]},
    {"action": "video_mute",          "phrases": ["mute video", "mute the video"]},

    # ── Files & clipboard ────────────────────────────────────────────────────
    {"action": "clip_text",           "phrases": ["copy text", "clip the text"]},
    {"action": "paste_text",          "phrases": ["paste"]},
    {"action": "open_clipboard",      "phrases": ["clipboard history", "what did i copy"]},
]

# ── App-name aliases ────────────────────────────────────────────────────────
_APP_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "browser": "chrome",
    "firefox": "firefox", "edge": "msedge", "brave": "brave",
    "vscode": "code", "vs code": "code", "code editor": "code",
    "notepad": "notepad", "notepad++": "notepad++",
    "word": "winword", "excel": "excel", "powerpoint": "powerpnt",
    "outlook": "outlook", "teams": "teams",
    "spotify": "spotify", "discord": "discord", "slack": "slack",
    "telegram": "telegram", "whatsapp": "whatsapp",
    "vlc": "vlc", "photoshop": "photoshop", "figma": "figma",
    "obs": "obs64", "steam": "steam", "epic": "epicgameslauncher",
    "terminal": "wt", "powershell": "powershell", "cmd": "cmd",
    "file explorer": "explorer", "explorer": "explorer", "files": "explorer",
}

# ── Language code map ───────────────────────────────────────────────────────
_LANG_MAP = {
    "spanish": "es", "español": "es",
    "french": "fr", "français": "fr",
    "german": "de", "deutsch": "de",
    "italian": "it", "portuguese": "pt",
    "urdu": "ur", "hindi": "hi", "arabic": "ar",
    "chinese": "zh", "japanese": "ja", "korean": "ko",
    "russian": "ru", "turkish": "tr", "dutch": "nl",
    "english": "en",
}


# ═════════════════════════════════════════════════════════════════════════════
# UniversalRouter
# ═════════════════════════════════════════════════════════════════════════════

class UniversalRouter:
    """Routes natural-language utterances to action modules.

    Usage:
        router = UniversalRouter()
        route = router.route("open chrome and search for python tutorials")
        → Route(action="open_app", args={"target":"chrome", "and_then":"search..."}, ...)
    """

    def __init__(self, llm_client: Optional[Callable[[str], str]] = None):
        """Args:
            llm_client: Optional callable(prompt)->str used as fallback when
                keyword + regex routing yields low confidence. Pass None to
                disable LLM fallback (pure offline routing).
        """
        self._llm = llm_client
        self._lock = threading.Lock()
        self._stats = {"routed": 0, "fallback_llm": 0, "fallback_ask_ai": 0}

    # ── Public ───────────────────────────────────────────────────────────────

    def route(self, utterance: str) -> Route:
        """Route an utterance to an action. Thread-safe."""
        with self._lock:
            self._stats["routed"] += 1
        u = utterance.strip().lower()
        if not u:
            return Route(action="none", confidence=0.0, explanation="empty utterance",
                        raw_utterance=utterance)

        # 1. Keyword + regex
        route = self._keyword_route(u, utterance)
        if route.confidence >= 0.6:
            return route

        # 2. LLM fallback
        if self._llm is not None:
            with self._lock:
                self._stats["fallback_llm"] += 1
            return self._llm_route(u, utterance)

        # 3. Default → ask_ai
        with self._lock:
            self._stats["fallback_ask_ai"] += 1
        return Route(
            action="ask_ai",
            args={"prompt": utterance},
            confidence=0.3,
            explanation="no specific intent matched — treating as conversational AI",
            source="fallback",
            raw_utterance=utterance,
        )

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    # ── Internals ────────────────────────────────────────────────────────────

    def _keyword_route(self, u: str, original: str) -> Route:
        best: Optional[Route] = None
        best_score = 0.0

        for intent in _INTENTS:
            for phrase in intent["phrases"]:
                if phrase in u:
                    # Score: longer phrase wins; position boost if at start
                    score = len(phrase) / 20.0
                    if u.startswith(phrase):
                        score += 0.4
                    if score > best_score:
                        args = self._extract_args(u, original, intent)
                        best = Route(
                            action=intent["action"],
                            args=args,
                            confidence=min(1.0, 0.55 + score),
                            explanation=f"matched keyword '{phrase}' → {intent['action']}",
                            source="keyword",
                            raw_utterance=original,
                        )
                        best_score = score

        # Apply language detection to translate routes
        if best and best.action == "translate":
            lang = self._detect_language(u)
            if lang:
                best.args["target_lang"] = lang

        # Apply app alias resolution to open_app / close_app / switch_window
        if best and best.action in ("open_app", "close_app", "switch_window"):
            target = best.args.get("target", "")
            alias = self._resolve_app_alias(target)
            if alias:
                best.args["target"] = alias

        # Apply time parsing to set_reminder
        if best and best.action == "set_reminder":
            when = self._parse_time(u, original)
            if when:
                best.args["when"] = when

        # Volume level parsing
        if best and best.action == "set_volume":
            m = re.search(r"(\d{1,3})", u)
            if m:
                best.args["level"] = min(100, max(0, int(m.group(1))))
            elif "mute" in u:
                best.args["level"] = 0
                best.args["mute"] = True

        return best or Route(action="ask_ai", args={"prompt": original},
                              confidence=0.0, explanation="no keyword match",
                              source="fallback", raw_utterance=original)

    def _extract_args(self, u: str, original: str, intent: dict) -> dict:
        """Extract action-specific arguments from the utterance."""
        action = intent["action"]
        args: dict[str, Any] = {}

        # Generic: try to extract "X" after the verb phrase
        if action == "open_app":
            # "open chrome" → target="chrome"
            for prefix in ("open ", "launch ", "start ", "run "):
                if u.startswith(prefix):
                    args["target"] = original[len(prefix):].strip().rstrip(".")
                    return args
            # Fallback: look for known app names
            for alias in _APP_ALIASES:
                if alias in u:
                    args["target"] = alias
                    return args

        elif action == "close_app":
            for prefix in ("close ", "quit ", "exit ", "kill "):
                if u.startswith(prefix):
                    args["target"] = original[len(prefix):].strip().rstrip(".")
                    return args

        elif action == "switch_window":
            for prefix in ("switch to ", "focus ", "go to ", "show "):
                if u.startswith(prefix):
                    args["target"] = original[len(prefix):].strip().rstrip(".")
                    return args

        elif action == "web_search":
            for prefix in ("search for ", "google ", "look up "):
                if u.startswith(prefix):
                    args["query"] = original[len(prefix):].strip().rstrip("?")
                    return args

        elif action == "play_youtube":
            m = re.search(r"play (.+?)(?:on youtube)?$", original, re.IGNORECASE)
            if m:
                args["query"] = m.group(1).strip()

        elif action == "translate":
            args["text"] = original
            args["target_lang"] = "es"  # default; refined by _detect_language

        elif action == "set_reminder":
            # "remind me at 5pm to call mom"
            m = re.search(r"remind me (.+?) to (.+)$", original, re.IGNORECASE)
            if m:
                args["when"] = m.group(1).strip()
                args["what"] = m.group(2).strip()
            else:
                args["when"] = original
                args["what"] = original

        elif action == "run_python":
            m = re.search(r"(?:run python|execute python|evaluate)\s+(.+)$",
                          original, re.IGNORECASE | re.DOTALL)
            if m:
                args["code"] = m.group(1).strip()

        elif action == "ask_ai":
            args["prompt"] = original

        elif action == "generate_code":
            args["prompt"] = original

        elif action == "research":
            m = re.search(r"(?:research|deep dive|investigate)\s+(.+)$",
                          original, re.IGNORECASE)
            if m:
                args["topic"] = m.group(1).strip()
            else:
                args["topic"] = original

        elif action == "summarize":
            args["text"] = original

        return args

    def _detect_language(self, u: str) -> Optional[str]:
        for name, code in _LANG_MAP.items():
            if f"in {name}" in u or f"to {name}" in u or f"into {name}" in u:
                return code
        return None

    def _resolve_app_alias(self, target: str) -> Optional[str]:
        target_low = target.lower().strip()
        for alias, canonical in _APP_ALIASES.items():
            if alias in target_low:
                return canonical
        return None

    def _parse_time(self, u: str, original: str) -> Optional[str]:
        """Returns natural-language time string for the reminder."""
        m = re.search(r"at (\d{1,2})(?::(\d{2}))?\s*(am|pm)?", u)
        if m:
            h = m.group(1)
            mn = m.group(2) or "00"
            ap = m.group(3) or ""
            return f"{h}:{mn} {ap}".strip()
        m = re.search(r"in (\d+) (minute|hour|min|hr)s?", u)
        if m:
            n = m.group(1)
            unit = m.group(2)
            unit_norm = "hours" if unit.startswith("h") else "minutes"
            return f"in {n} {unit_norm}"
        return None

    def _llm_route(self, u: str, original: str) -> Route:
        """LLM-based routing for ambiguous utterances."""
        prompt = (
            "You are SONIC AI's intent classifier. Given a user utterance, "
            "respond ONLY with a JSON object: "
            '{"action": "<action_name>", "args": {...}}. '
            "Choose ONE action from this list: "
            + ", ".join({i["action"] for i in _INTENTS}) + ". "
            f"Utterance: {original!r}"
        )
        try:
            raw = self._llm(prompt) if self._llm else ""
            import json
            # Find JSON in response
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
                return Route(
                    action=data.get("action", "ask_ai"),
                    args=data.get("args", {}),
                    confidence=0.75,
                    explanation="LLM classified",
                    source="llm",
                    raw_utterance=original,
                )
        except Exception:
            pass
        return Route(action="ask_ai", args={"prompt": original},
                     confidence=0.4, explanation="LLM fallback failed",
                     source="fallback", raw_utterance=original)
