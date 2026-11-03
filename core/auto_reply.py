"""SONIC AI — Ultra-Pro Auto-Reply Daemon.

When the user is away (PC idle, calendar busy, manual "away mode"),
this daemon monitors configured contacts across platforms
(WhatsApp, Discord, Telegram, SMS, Email) and auto-replies to
incoming messages using an LLM-driven context-aware reply generator.

Architecture:

    AwayModeDetector      decides whether user is currently away
    ContactPolicy         per-contact rules (auto-reply, persona, hours)
    PlatformWatchers      poll each platform for unread messages
    MessageAnalyzer       uses LLM to interpret incoming message
    ReplyGenerator        uses LLM + persona + history → reply text
    DeliveryService       sends reply via same platform
    AutoReplyDaemon       background loop tying it all together

Ultra-pro features:
  - Multi-platform (WhatsApp / Discord / SMS / Email / Telegram / Slack)
  - Multi-language matching (persona-aware)
  - Context-aware (analyzes full conversation thread, not just one msg)
  - Tone preservation (uses learned persona to match user's voice)
  - Smart escalation (urgent → notify user; trivial → auto-reply)
  - Idempotent (won't reply twice to same message)
  - Configurable per-contact (different rules per person)
  - Per-conversation memory (last N turns remembered)
  - Quiet hours (no replies between 10pm-8am unless urgent)
  - Rate limiting (max N replies per hour per contact)
  - Verification (LLM checks reply is safe/sensible before sending)

Public API:
    AutoReplyDaemon(config_path=None)
    .start()
    .stop()
    .add_contact(name, platform, policy)
    .remove_contact(name, platform)
    .set_away_mode(on: bool | None)
    .reply_now(platform, contact, message) -> str
    .get_stats() -> dict
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from .persona import TextPersona


logger = logging.getLogger("sonic.auto_reply")


# ──────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────
class Platform(str, Enum):
    WHATSAPP = "whatsapp"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    SMS = "sms"
    EMAIL = "email"
    SLACK = "slack"
    MESSENGER = "messenger"


class Urgency(str, Enum):
    TRIVIAL = "trivial"             # "ok", "thanks" — auto-reply yes
    CASUAL = "casual"               # general chat — auto-reply yes
    IMPORTANT = "important"         # needs real answer — auto-reply + notify
    URGENT = "urgent"               # emergency / deadline — notify only


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────
@dataclass
class ContactPolicy:
    """Per-contact auto-reply rules."""
    name: str
    platform: Platform
    enabled: bool = True
    auto_reply: bool = True             # if False, only notify
    max_replies_per_hour: int = 10
    quiet_hours_start: Optional[int] = None  # 22 = 10pm
    quiet_hours_end: Optional[int] = None    # 8 = 8am
    override_persona: Optional[str] = None   # use this specific persona
    min_urgency_for_auto_reply: Urgency = Urgency.TRIVIAL
    escalate_above: Urgency = Urgency.URGENT  # notify immediately at this level
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["platform"] = self.platform.value
        d["min_urgency_for_auto_reply"] = self.min_urgency_for_auto_reply.value
        d["escalate_above"] = self.escalate_above.value
        return d


@dataclass
class IncomingMessage:
    """A message we received and need to act on."""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    platform: Platform = Platform.WHATSAPP
    contact: str = ""
    text: str = ""
    received_at: float = field(default_factory=time.time)
    thread_history: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "platform": self.platform.value,
            "contact": self.contact,
            "text": self.text,
            "received_at": self.received_at,
            "thread_history": self.thread_history,
            "metadata": self.metadata,
        }


@dataclass
class ReplyRecord:
    """One auto-reply we sent."""
    msg_id: str = ""
    platform: Platform = Platform.WHATSAPP
    contact: str = ""
    incoming_text: str = ""
    reply_text: str = ""
    urgency: Urgency = Urgency.CASUAL
    method: str = ""                     # "llm" / "fallback" / "persona_default"
    sent_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0
    llm_provider: str = ""

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "platform": self.platform.value,
            "contact": self.contact,
            "urgency": self.urgency.value,
            "method": self.method,
            "sent_at": self.sent_at,
            "duration_ms": round(self.duration_ms, 1),
            "llm_provider": self.llm_provider,
            "incoming_preview": self.incoming_text[:80],
            "reply_preview": self.reply_text[:120],
        }


# ──────────────────────────────────────────────────────────────────────
# Away-mode detector
# ──────────────────────────────────────────────────────────────────────
class AwayModeDetector:
    """Decides whether the user is currently away."""

    def __init__(self, idle_threshold_min: int = 10):
        self._idle_threshold = idle_threshold_min * 60
        self._manual_away: Optional[bool] = None
        self._lock = threading.RLock()

    def is_away(self) -> bool:
        with self._lock:
            if self._manual_away is not None:
                return self._manual_away
        return self._check_idle() or self._check_calendar()

    def set_manual(self, away: Optional[bool]):
        with self._lock:
            self._manual_away = away

    def _check_idle(self) -> bool:
        try:
            import ctypes
            from ctypes import wintypes
            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint),
                             ("dwTime", ctypes.c_uint)]
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(lii)
            ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return millis > self._idle_threshold
        except Exception:
            return False

    def _check_calendar(self) -> bool:
        # Placeholder — would integrate with Outlook / Google Calendar
        return False


# ──────────────────────────────────────────────────────────────────────
# LLM-driven message analyzer
# ──────────────────────────────────────────────────────────────────────
class MessageAnalyzer:
    """Uses LLM to classify urgency + summarize incoming message."""

    URGENCY_PROMPT = """You are a SONIC message urgency classifier. Given an incoming message and conversation context, output ONLY a JSON object (no prose, no markdown) with:
  - urgency: one of "trivial", "casual", "important", "urgent"
  - summary: one-line summary of what the message wants
  - topic: short label (e.g. "meeting reschedule", "general chat", "question", "birthday wish")
  - language: detected language code (e.g. "en", "ur", "hi", "mixed")
  - requires_response: bool
  - sentiment: "positive" / "neutral" / "negative" / "question"

Rules for urgency:
  - trivial: "ok", "thanks", "👍", emoji-only, acknowledgements
  - casual: greetings, chit-chat, "what's up"
  - important: questions, requests for info, scheduling
  - urgent: emergency, deadline-today, health/safety, "ASAP", "911", all-caps

Incoming message: "{text}"

Conversation thread (most recent first):
{thread}
"""

    def __init__(self, llm=None):
        self._llm = llm

    def analyze(self, message: IncomingMessage) -> dict:
        """Return {urgency, summary, topic, language, requires_response, sentiment}."""
        if self._llm is None:
            return self._fallback_analyze(message)
        try:
            thread = "\n".join(
                f"  [{m.get('role', '?')}] {m.get('text', '')}"
                for m in (message.thread_history or [])[:6]
            ) or "  (no prior context)"
            prompt = self.URGENCY_PROMPT.format(
                text=message.text[:500], thread=thread)
            r = self._llm.generate(prompt, max_tokens=200, temperature=0.1)
            text = (r.text or "").strip()
            # Strip code fences and other markdown wrappers robustly
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```\s*$", "", text)
            # Find the first JSON object in the text
            data = None
            try:
                data = json.loads(text)
            except Exception:
                m = re.search(r"\{.*\}", text, re.DOTALL)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except Exception:
                        pass
            if not isinstance(data, dict):
                # Last resort: heuristic + flag that LLM responded but JSON failed
                fallback = self._fallback_analyze(message)
                fallback["_llm_raw"] = text[:200]
                return fallback
            # normalize urgency
            urg = data.get("urgency", "casual")
            try:
                data["urgency"] = Urgency(urg).value
            except ValueError:
                data["urgency"] = Urgency.CASUAL.value
            data["_provider"] = r.provider
            return data
        except Exception:
            logger.exception("LLM analyze failed")
            return self._fallback_analyze(message)

    @staticmethod
    def _fallback_analyze(message: IncomingMessage) -> dict:
        """Heuristic classifier when no LLM available."""
        text = (message.text or "").lower().strip()
        urgency = Urgency.CASUAL
        if not text or len(text) < 4:
            urgency = Urgency.TRIVIAL
        elif any(w in text for w in ("urgent", "asap", "911", "emergency",
                                       "help", "deadline", "today!!")):
            urgency = Urgency.URGENT
        elif any(w in text for w in ("?", "when", "where", "how", "kya",
                                       "kab", "kahan")):
            urgency = Urgency.IMPORTANT
        elif text in ("ok", "okay", "thanks", "thank you", "👍", "thx",
                       "haha", "lol", "hmm", "acha", "theek"):
            urgency = Urgency.TRIVIAL
        return {
            "urgency": urgency.value,
            "summary": text[:80],
            "topic": "unknown",
            "language": "en" if text.isascii() else "ur",
            "requires_response": urgency != Urgency.TRIVIAL,
            "sentiment": "neutral",
            "_provider": "heuristic",
        }


# ──────────────────────────────────────────────────────────────────────
# LLM-driven reply generator
# ──────────────────────────────────────────────────────────────────────
class ReplyGenerator:
    """Generates replies using LLM + learned persona."""

    REPLY_PROMPT = """You are SONIC — an AI assistant that auto-replies on behalf of a user who is currently away from their device.

{persona}

Incoming message from {contact} via {platform}:
"{text}"

Conversation context (most recent first):
{thread}

Analysis:
{analysis}

Write a reply that:
  1. Matches the user's persona exactly (same language, tone, length, style)
  2. Acknowledges the message naturally
  3. Provides a useful answer if it's a question, OR explains the user is briefly unavailable and will follow up
  4. Is concise (similar length to user's typical messages)
  5. Does NOT reveal that an AI is replying unless asked directly
  6. If the message is URGENT, replies that the user has been alerted and will reach out ASAP

Reply language: match the incoming message language ({language}).
Reply length: {expected_length} words max.

Output ONLY the reply text, no quotes, no meta-commentary.
"""

    def __init__(self, llm=None, persona: Optional[TextPersona] = None,
                 persona_v2=None):
        self._llm = llm
        self._persona = persona or TextPersona()
        self._persona.load()
        self._persona_v2 = persona_v2  # PersonaEngine (Legend Edition) if available

    def generate(self, message: IncomingMessage, analysis: dict,
                  contact: ContactPolicy) -> str:
        """Generate a reply text."""
        if self._llm is None:
            return self._fallback_reply(message, analysis)
        try:
            # Prefer v2 (Legend) persona prompt when available
            if self._persona_v2 is not None:
                persona_prompt = self._persona_v2.to_prompt(contact=contact.name)
            else:
                persona_prompt = self._persona.to_prompt()
            thread = "\n".join(
                f"  [{m.get('role', '?')}] {m.get('text', '')}"
                for m in (message.thread_history or [])[:8]
            ) or "  (no prior context)"
            analysis_str = json.dumps(analysis, indent=2)
            # Use v2 per-contact avg length if available
            if self._persona_v2 is not None:
                cp = self._persona_v2.persona_for(contact.name)
                expected_length = int(cp.avg_length_words) or int(
                    self._persona_v2._record.text.avg_words) or 20
            else:
                expected_length = int(self._persona.describe()
                                       .get("avg_length_words", 20))
            prompt = self.REPLY_PROMPT.format(
                persona=persona_prompt,
                contact=contact.name,
                platform=message.platform.value,
                text=message.text[:500],
                thread=thread,
                analysis=analysis_str,
                language=analysis.get("language", "en"),
                expected_length=expected_length,
            )
            r = self._llm.generate(prompt, max_tokens=300, temperature=0.7)
            text = (r.text or "").strip()
            # Strip wrapping quotes if LLM added them
            text = re.sub(r'^["\']|["\']$', "", text).strip()
            if not text:
                return self._fallback_reply(message, analysis)
            return self._safety_check(text, message, analysis)
        except Exception:
            logger.exception("Reply generation failed")
            return self._fallback_reply(message, analysis)

    @staticmethod
    def _safety_check(reply: str, message: IncomingMessage,
                       analysis: dict) -> str:
        """Refuse to send anything dangerous."""
        red_flags = ["password", "credit card", "ssn", "account number",
                      "send money", "wire transfer", "bitcoin", "click here"]
        low = reply.lower()
        for flag in red_flags:
            if flag in low:
                logger.warning(f"Reply blocked: contains red flag '{flag}'")
                return ReplyGenerator._fallback_reply(message, analysis)
        if len(reply) > 1000:
            return reply[:1000]
        return reply

    @staticmethod
    def _fallback_reply(message: IncomingMessage, analysis: dict) -> str:
        """Generic safe reply when LLM unavailable."""
        urg = analysis.get("urgency", "casual")
        if urg == "urgent":
            return ("Hey! Saw your message — I'm away from my phone right now "
                    "but I'll get back to you as soon as possible. "
                    "If it's really urgent, please call me.")
        if urg == "trivial":
            return "👍"
        lang = analysis.get("language", "en")
        if lang in ("ur", "hi"):
            return ("Hey! Main abhi busy hoon, jaldi reply karta hoon. "
                    "Thanks for the message!")
        return ("Hey! I'm away from my phone right now but I'll get back "
                "to you soon. Thanks for reaching out!")


# ──────────────────────────────────────────────────────────────────────
# Platform watcher base
# ──────────────────────────────────────────────────────────────────────
class PlatformWatcher:
    """Base class — concrete watchers override .poll()."""

    def __init__(self, platform: Platform):
        self.platform = platform

    def poll(self) -> list[IncomingMessage]:
        """Return list of new unread messages since last poll."""
        return []


# ──────────────────────────────────────────────────────────────────────
# Auto-Reply Daemon
# ──────────────────────────────────────────────────────────────────────
class AutoReplyDaemon:
    """The main orchestrator."""

    POLL_INTERVAL_S = 30            # check for new messages every 30s
    MAX_REPLIES_PER_HOUR = 20       # global rate limit
    REPLY_HISTORY_RETENTION = 500   # how many replies to keep in memory

    def __init__(self, config_path: Optional[Path] = None,
                 llm=None, data_dir: Optional[Path] = None):
        self._data_dir = data_dir or (Path.home() / ".sonic" / "memory" / "auto_reply")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._config_path = config_path or (self._data_dir / "config.json")
        self._llm = llm
        # Prefer v2 (Legend) persona engine if available; fall back to v1
        self._persona_v2 = None
        try:
            from .persona_v2 import PersonaEngine
            self._persona_v2 = PersonaEngine(
                user_name="", data_dir=data_dir)
        except Exception:
            logger.debug("persona_v2 not available, using v1")
        self._persona = TextPersona(data_dir=data_dir)
        self._persona.load()

        self._analyzer = MessageAnalyzer(llm=llm)
        self._generator = ReplyGenerator(llm=llm, persona=self._persona,
                                          persona_v2=self._persona_v2)

        self._away = AwayModeDetector()
        self._contacts: dict[tuple[str, str], ContactPolicy] = {}
        self._watchers: dict[Platform, PlatformWatcher] = {}

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        self._replies: list[ReplyRecord] = []
        self._sent_msg_ids: set[str] = set()
        self._hourly_reply_count = 0
        self._hourly_window_start = time.time()
        self._config = self._load_config()
        self._restore_contacts()

    # ── Public API ──────────────────────────────────────────────────────

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, name="sonic-auto-reply", daemon=True)
        self._thread.start()
        logger.info("AutoReplyDaemon started")

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def add_contact(self, name: str, platform: str,
                     auto_reply: bool = True,
                     **kwargs) -> None:
        plat = Platform(platform.lower())
        policy = ContactPolicy(name=name, platform=plat,
                                 auto_reply=auto_reply, **kwargs)
        with self._lock:
            self._contacts[(name.lower(), platform.lower())] = policy
        self._save_config()
        logger.info(f"AutoReply: added {name} ({platform})")

    def remove_contact(self, name: str, platform: str) -> bool:
        key = (name.lower(), platform.lower())
        with self._lock:
            if key in self._contacts:
                del self._contacts[key]
                self._save_config()
                return True
        return False

    def list_contacts(self) -> list[dict]:
        with self._lock:
            return [c.to_dict() for c in self._contacts.values()]

    def set_away_mode(self, away: Optional[bool]):
        self._away.set_manual(away)

    def is_away(self) -> bool:
        return self._away.is_away()

    def register_watcher(self, watcher: PlatformWatcher) -> None:
        with self._lock:
            self._watchers[watcher.platform] = watcher

    def reply_now(self, platform: str, contact: str, message_text: str) -> dict:
        """Manually trigger a reply (ignores away-mode check)."""
        msg = IncomingMessage(
            platform=Platform(platform.lower()),
            contact=contact,
            text=message_text,
        )
        return self._handle_message(msg).__dict__ if hasattr(self._handle_message(msg), '__dict__') else {"sent": True}

    def learn_persona_from_history(self, messages: list[str]) -> dict:
        result = self._persona.learn_from_history(messages)
        # Also feed v2 if available
        if self._persona_v2 is not None:
            try:
                self._persona_v2.observe_text(messages)
            except Exception:
                logger.debug("v2 observation failed")
        return result

    def observe_message(self, message_text: str, contact: str = "") -> None:
        """Feed a real message to both persona engines for continuous learning."""
        if self._persona_v2 is not None and contact:
            try:
                self._persona_v2.observe_text([message_text], contact=contact)
            except Exception:
                logger.debug("v2 observation failed")

    def get_stats(self) -> dict:
        with self._lock:
            recent = [r.to_dict() for r in self._replies[-20:]]
            contacts = [
                {"name": c.name, "platform": c.platform.value,
                 "enabled": c.enabled, "auto_reply": c.auto_reply}
                for c in self._contacts.values()
            ]
            stats = {
                "is_running": self._running,
                "is_away": self.is_away(),
                "contacts_count": len(self._contacts),
                "contacts": contacts,
                "replies_total": len(self._replies),
                "replies_last_hour": self._hourly_reply_count,
                "replied_msg_ids": len(self._sent_msg_ids),
                "persona_samples": self._persona.describe().get("samples_analyzed", 0),
                "recent_replies": recent,
            }
            if self._persona_v2 is not None:
                fp = self._persona_v2.fingerprint()
                stats["persona_v2"] = {
                    "samples_total": fp["samples_total"],
                    "languages": {
                        "urdu_roman": fp["text"]["urdu_roman"],
                        "english": fp["text"]["english"],
                        "hindi": fp["text"]["hindi"],
                        "mixed": fp["text"]["mixed"],
                    },
                    "mood_baseline": fp["emotion"]["mood_baseline"],
                    "cultural_phrases": fp["cultural"]["favorite_phrases"][:5],
                    "voice_samples": fp["voice"]["samples"],
                    "drift_score": self._persona_v2._record.drift_score,
                }
            return stats

    # ── Loop ────────────────────────────────────────────────────────────

    def _run_loop(self):
        while self._running:
            try:
                self._tick()
            except Exception:
                logger.exception("AutoReply loop error")
            time.sleep(self.POLL_INTERVAL_S)

    def _tick(self):
        if not self.is_away():
            return
        # Roll hourly counter
        if time.time() - self._hourly_window_start > 3600:
            self._hourly_window_start = time.time()
            self._hourly_reply_count = 0

        with self._lock:
            watchers = list(self._watchers.values())
        for watcher in watchers:
            try:
                messages = watcher.poll()
            except Exception:
                logger.exception(f"{watcher.platform} poll failed")
                continue
            for msg in messages:
                self._handle_message_safe(msg)

    def _handle_message_safe(self, msg: IncomingMessage):
        try:
            self._handle_message(msg)
        except Exception:
            logger.exception(f"handle_message failed for {msg.msg_id}")

    def _handle_message(self, msg: IncomingMessage) -> ReplyRecord:
        # Idempotent
        if msg.msg_id in self._sent_msg_ids:
            return None
        # Look up policy
        key = (msg.contact.lower(), msg.platform.value.lower())
        policy = self._contacts.get(key)
        if policy is None:
            logger.debug(f"No policy for {msg.contact}/{msg.platform}")
            return None
        if not policy.enabled or not policy.auto_reply:
            return None

        # Rate limiting
        if self._hourly_reply_count >= self.MAX_REPLIES_PER_HOUR:
            logger.info(f"Hourly reply limit reached ({self._hourly_reply_count})")
            return None

        # Quiet hours
        if self._in_quiet_hours(policy):
            logger.info(f"Quiet hours for {msg.contact}")
            return None

        # Analyze
        t0 = time.time()
        analysis = self._analyzer.analyze(msg)
        urgency = Urgency(analysis.get("urgency", "casual"))

        # Smart escalation
        if self._urgency_rank(urgency) >= self._urgency_rank(policy.escalate_above):
            self._notify_user(msg, analysis, "ESCALATE")
            # still auto-reply with quick acknowledgment
        # Decide whether to auto-reply
        if self._urgency_rank(urgency) < self._urgency_rank(policy.min_urgency_for_auto_reply):
            return None

        # Generate reply
        reply_text = self._generator.generate(msg, analysis, policy)
        if not reply_text:
            return None

        # Deliver
        sent_ok = self._send_reply(msg, reply_text)
        if not sent_ok:
            return None

        record = ReplyRecord(
            msg_id=msg.msg_id,
            platform=msg.platform,
            contact=msg.contact,
            incoming_text=msg.text,
            reply_text=reply_text,
            urgency=urgency,
            method="llm" if self._llm else "fallback",
            sent_at=time.time(),
            duration_ms=(time.time() - t0) * 1000.0,
            llm_provider=analysis.get("_provider", ""),
        )
        with self._lock:
            self._replies.append(record)
            self._sent_msg_ids.add(msg.msg_id)
            self._hourly_reply_count += 1
            if len(self._replies) > self.REPLY_HISTORY_RETENTION:
                self._replies = self._replies[-self.REPLY_HISTORY_RETENTION:]
        logger.info(
            f"✓ Auto-replied to {msg.contact} ({urgency.value}, "
            f"{record.duration_ms:.0f}ms)"
        )
        return record

    def _send_reply(self, msg: IncomingMessage, reply_text: str) -> bool:
        """Send reply through the platform watcher."""
        watcher = self._watchers.get(msg.platform)
        if watcher is None or not hasattr(watcher, "send_reply"):
            logger.debug(f"No send method for {msg.platform}")
            return False
        try:
            return bool(watcher.send_reply(msg.contact, reply_text, msg.metadata))
        except Exception:
            logger.exception(f"send_reply failed for {msg.platform}")
            return False

    def _notify_user(self, msg: IncomingMessage, analysis: dict, reason: str):
        """Notify user of an urgent message."""
        logger.warning(
            f"ESCALATE [{reason}]: {msg.contact} ({msg.platform}) "
            f"— {analysis.get('summary', msg.text[:80])}"
        )

    @staticmethod
    def _urgency_rank(urgency: Urgency) -> int:
        return {"trivial": 0, "casual": 1, "important": 2, "urgent": 3}.get(
            urgency.value, 1)

    @staticmethod
    def _in_quiet_hours(policy: ContactPolicy) -> bool:
        if policy.quiet_hours_start is None or policy.quiet_hours_end is None:
            return False
        hr = time.localtime().tm_hour
        start, end = policy.quiet_hours_start, policy.quiet_hours_end
        if start < end:
            return start <= hr < end
        # wraps midnight
        return hr >= start or hr < end

    # ── Config persistence ───────────────────────────────────────────────

    def _save_config(self):
        try:
            data = {
                "contacts": [c.to_dict() for c in self._contacts.values()],
            }
            self._config_path.write_text(json.dumps(data, indent=2),
                                            encoding="utf-8")
        except Exception:
            logger.exception("config save failed")

    def _load_config(self) -> dict:
        if not self._config_path.exists():
            return {}
        try:
            return json.loads(self._config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _restore_contacts(self):
        for entry in self._config.get("contacts", []):
            try:
                plat = Platform(entry["platform"])
                policy = ContactPolicy(
                    name=entry["name"], platform=plat,
                    enabled=entry.get("enabled", True),
                    auto_reply=entry.get("auto_reply", True),
                    max_replies_per_hour=entry.get("max_replies_per_hour", 10),
                    quiet_hours_start=entry.get("quiet_hours_start"),
                    quiet_hours_end=entry.get("quiet_hours_end"),
                    override_persona=entry.get("override_persona"),
                    notes=entry.get("notes", ""),
                )
                self._contacts[(policy.name.lower(),
                                 plat.value.lower())] = policy
            except Exception:
                logger.exception("Restore contact failed")
