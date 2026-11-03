"""SONIC AI — Ultra-Pro Persona Engine (Legend Edition).

This is the most sophisticated text-style persona system you can build.
It learns from MULTIPLE dimensions and creates a living, evolving
"feel" of who the user is.

Differences from persona.py (v1):
  v1: learns from text only
  v2: learns from text + voice + behavior + time + emotion + context

Components:
  TextFingerprint       language, vocabulary, grammar, emoji, style
  VoiceFingerprint      pace, energy, pitch, tone, energy patterns
  BehaviorFingerprint   active hours, response latency, session patterns
  EmotionFingerprint     mood baseline, emotional range, triggers
  CulturalFingerprint    idioms, references, regional flavor
  ContextAdaptation      time-of-day, weekday vs weekend, recent mood
  PerContactPersona      different "you" for different people
  EvolutionTracker       drift detection, style change detection
  PredictivePersona      predicts what user would say
  DraftingPersona        drafts replies user can edit

Public API:
    PersonaEngine(user_name="...")
    .observe_text(messages: list[str], contact: str | None = None)
    .observe_voice(audio_features: dict, contact: str | None = None)
    .observe_behavior(event: dict)
    .observe_mood(mood: str, confidence: float)
    .persona_for(contact: str) -> PersonaProfile
    .describe() -> dict
    .fingerprint() -> dict        # multi-modal fingerprint
    .drift_report() -> dict       # how persona has changed
    .draft_reply(contact, message, persona) -> str
    .predict_next(contact, thread) -> str
    .to_prompt(contact: str | None = None) -> str
    .save() / .load()
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .persona import TextPersona, PersonaProfile, URDU_ROMAN_WORDS, Emoji


logger = logging.getLogger("sonic.persona_v2")


# ──────────────────────────────────────────────────────────────────────
# Mood / emotional vocabulary
# ──────────────────────────────────────────────────────────────────────
MOOD_KEYWORDS = {
    "happy":     {"happy", "great", "awesome", "maza", "khushi", "accha",
                  "perfect", "wonderful", "love", "yaar", ":)", "😊", "😄",
                  "yay", "woohoo", "alhamdulillah", "shukr"},
    "sad":       {"sad", "upset", "udaas", "taklif", "hurt", "miss",
                  "alone", "akela", "cry", "rona", "😢", "😭", ":/"},
    "angry":     {"angry", "gussa", "naraz", "frustrated", "irritated",
                  "bore", "fed up", "pagal", "stupid", "idiot", "ugh",
                  "😡", "😤"},
    "tired":     {"tired", "thaka", "thakan", "exhausted", "neend",
                  "sleepy", "so gaya", "bore ho gaya", "yaar nind aa rhi"},
    "excited":   {"excited", "psyched", "stoked", "khush", "hyper",
                  "can't wait", "incredible", "amazing"},
    "stressed":  {"stressed", "tension", "pressure", "chaos", "overwhelmed",
                  "deadline", "burnt out", "pagal ho raha"},
    "calm":      {"calm", "sukoon", "peace", "chill", "relaxed",
                  "theek hai", "all good", "no problem"},
    "playful":   {"haha", "lol", "hehe", "kidding", "mazaak", "pagal",
                  "kid", "joke", "😂", "🤣", "lolol", "lolll"},
    "caring":    {"take care", "khayal rakhna", "fikar mat karo", "love you",
                  "pyar", "jaan", "dua", "allah hafiz", "bye", "see you"},
    "formal":    {"dear", "regards", "sincerely", "please find",
                  "kindly", "sir", "ma'am", "as per", "regarding"},
}

EMOJI = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+", flags=re.UNICODE)


# Cultural idioms (Pakistani/Urdu)
URDU_IDIOMS = {
    "inshallah": "إن شاء اللہ",
    "mashallah": "ما شاء اللہ",
    "alhamdulillah": "الحمد للہ",
    "subhanallah": "سبحان اللہ",
    "bismillah": "بسم اللہ",
    "dua": "دعا",
    "rab rakha": "رب رکھا",
    "khair": "خير",
    "yaar": "یار",
    "bhai": "بھائی",
    "boss": "باس",
    "theek hai": "ٹھیک ہے",
    "chalo": "چلو",
    "arey": "ارے",
    "wah": "واہ",
    "ji": "جی",
    "sahab": "صاحب",
    "janab": "جناب",
}


# ──────────────────────────────────────────────────────────────────────
# Multi-modal fingerprint dataclasses
# ──────────────────────────────────────────────────────────────────────
@dataclass
class TextFingerprint:
    """Deep text-style fingerprint."""
    samples: int = 0
    # Language
    urdu_roman: float = 0.0
    english: float = 0.0
    hindi: float = 0.0
    mixed: float = 0.0
    # Sub-language
    pakistani_urdu: float = 0.0       # uses "yaar", "boss", "theek"
    indian_hindi: float = 0.0         # uses "yaar", "bhai", "achha"
    arabic_loanwords: float = 0.0     # uses "inshallah", "mashallah"
    # Style
    avg_words: float = 0.0
    avg_chars: float = 0.0
    exclamation_density: float = 0.0
    question_density: float = 0.0
    emoji_density: float = 0.0
    all_caps_ratio: float = 0.0
    # Punctuation
    period_ratio: float = 0.0
    comma_ratio: float = 0.0
    ellipsis_ratio: float = 0.0
    # Vocabulary
    top_words: list[str] = field(default_factory=list)
    signature_phrases: list[str] = field(default_factory=list)
    code_switch_points: list[str] = field(default_factory=list)  # where lang switches
    # Grammar
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    # Common patterns
    common_openings: list[str] = field(default_factory=list)
    common_closings: list[str] = field(default_factory=list)
    # Voice-over-text
    has_audio_files: int = 0
    voice_note_ratio: float = 0.0
    # Last seen
    last_text_at: float = 0.0


@dataclass
class VoiceFingerprint:
    """Voice-message style fingerprint."""
    samples: int = 0
    # Pace
    avg_duration_s: float = 0.0
    avg_words_per_minute: float = 0.0
    # Energy
    avg_energy: float = 0.0
    energy_variance: float = 0.0
    # Tone
    pitch_avg: float = 0.0
    pitch_variance: float = 0.0
    # Style
    laughter_per_minute: float = 0.0
    filler_word_ratio: float = 0.0      # "umm", "uhh", "like"
    trailing_silence_ratio: float = 0.0
    # Last seen
    last_voice_at: float = 0.0


@dataclass
class BehaviorFingerprint:
    """User behavior patterns (when active, response latency, etc.)."""
    samples: int = 0
    # Time patterns
    active_hours: dict = field(default_factory=dict)   # hour 0-23 → frequency
    active_days: dict = field(default_factory=dict)    # weekday 0-6 → frequency
    # Session patterns
    avg_session_length_min: float = 0.0
    sessions_per_day: float = 0.0
    # Response latency
    avg_response_time_s: float = 0.0
    response_time_by_contact: dict = field(default_factory=dict)
    # Engagement
    messages_per_session: float = 0.0
    initiation_ratio: float = 0.0  # 0 = always replies, 1 = always starts
    # Last seen
    last_active_at: float = 0.0


@dataclass
class EmotionFingerprint:
    """Emotional baseline + range."""
    samples: int = 0
    mood_baseline: str = "neutral"      # dominant mood
    mood_distribution: dict = field(default_factory=dict)  # mood → frequency
    emotional_range: float = 0.0        # 0 = always one mood, 1 = full range
    mood_volatility: float = 0.0       # how often mood changes per day
    triggers: dict = field(default_factory=dict)  # topic → mood
    # Sensitivity
    responds_to_praise: bool = True
    responds_to_criticism: bool = True
    empathy_level: float = 0.5         # how often uses caring language


@dataclass
class CulturalFingerprint:
    """Cultural references and idioms."""
    samples: int = 0
    # Religious
    religious_phrase_frequency: float = 0.0
    favorite_phrases: list[str] = field(default_factory=list)
    # Regional
    pakistani_markers: float = 0.0      # "yaar", "boss", "theek"
    indian_markers: float = 0.0        # "yaar", "bhai", "achha"
    # Topical
    references_cricket: int = 0
    references_food: int = 0
    references_family: int = 0
    references_work: int = 0
    # Last seen
    last_updated: float = 0.0


@dataclass
class ContactPersona:
    """A specialized persona for a specific contact."""
    contact: str
    samples: int = 0
    formality: float = 0.0             # 0 = super casual, 1 = super formal
    warmth: float = 0.0                # 0 = cold, 1 = warm
    technicality: float = 0.0          # how much technical jargon
    emoji_usage: float = 0.0           # 0 = none, 1 = lots
    avg_length_words: float = 0.0
    common_topics: list[str] = field(default_factory=list)
    last_updated: float = 0.0


# ──────────────────────────────────────────────────────────────────────
# The full persona record
# ──────────────────────────────────────────────────────────────────────
@dataclass
class PersonaRecord:
    user_name: str = ""
    samples_total: int = 0
    text: TextFingerprint = field(default_factory=TextFingerprint)
    voice: VoiceFingerprint = field(default_factory=VoiceFingerprint)
    behavior: BehaviorFingerprint = field(default_factory=BehaviorFingerprint)
    emotion: EmotionFingerprint = field(default_factory=EmotionFingerprint)
    cultural: CulturalFingerprint = field(default_factory=CulturalFingerprint)
    # Per-contact personas
    contacts: dict = field(default_factory=dict)   # name → ContactPersona dict
    # Evolution
    snapshots: list[dict] = field(default_factory=list)   # weekly snapshots
    drift_score: float = 0.0
    last_observation_at: float = 0.0
    created_at: float = 0.0
    version: int = 2

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PersonaRecord":
        # Reconstruct dataclasses from dict
        if "text" in d and isinstance(d["text"], dict):
            d["text"] = TextFingerprint(**d["text"])
        if "voice" in d and isinstance(d["voice"], dict):
            d["voice"] = VoiceFingerprint(**d["voice"])
        if "behavior" in d and isinstance(d["behavior"], dict):
            d["behavior"] = BehaviorFingerprint(**d["behavior"])
        if "emotion" in d and isinstance(d["emotion"], dict):
            d["emotion"] = EmotionFingerprint(**d["emotion"])
        if "cultural" in d and isinstance(d["cultural"], dict):
            d["cultural"] = CulturalFingerprint(**d["cultural"])
        return cls(**d)


# ──────────────────────────────────────────────────────────────────────
# The Engine
# ──────────────────────────────────────────────────────────────────────
class PersonaEngine:
    """The ultra-pro persona engine."""

    def __init__(self, user_name: str = "", data_dir: Optional[Path] = None):
        self.user_name = user_name
        self._data_dir = data_dir or (Path.home() / ".sonic" / "memory" / "persona_v2")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._data_dir / f"{user_name or 'default'}.json"
        self._record = PersonaRecord(user_name=user_name, created_at=time.time())
        self.load()

    # ── Observation API ──────────────────────────────────────────────────

    def observe_text(self, messages: list[str], contact: Optional[str] = None,
                      ts: Optional[float] = None) -> dict:
        """Learn from text messages (optionally tied to a specific contact)."""
        cleaned = [self._clean(m) for m in messages if m and m.strip()]
        if not cleaned:
            return {"samples": 0}

        # Update text fingerprint
        self._update_text(cleaned, ts or time.time())

        # Update emotional fingerprint
        self._update_emotion(cleaned, ts or time.time())

        # Update cultural fingerprint
        self._update_cultural(cleaned, ts or time.time())

        # Update per-contact persona if specified
        if contact:
            self._update_contact_persona(contact, cleaned, ts or time.time())

        # Update behavior from timestamps if available
        self._update_behavior(cleaned, ts or time.time())

        # Take snapshot weekly
        self._maybe_snapshot()

        # Update record-level metadata
        self._record.samples_total += len(cleaned)
        self._record.last_observation_at = time.time()
        self.save()

        return {
            "samples": len(cleaned),
            "contact": contact,
            "total_samples": self._record.samples_total,
        }

    def observe_voice(self, audio_features: dict,
                       contact: Optional[str] = None) -> dict:
        """Learn from voice-message features.

        audio_features expected keys:
          duration_s, words_per_minute, energy_mean, energy_var,
          pitch_mean, pitch_var, laughter_count, filler_count,
          trailing_silence_s
        """
        v = self._record.voice
        n = v.samples
        # Running average
        for attr, key in [("avg_duration_s", "duration_s"),
                            ("avg_words_per_minute", "words_per_minute"),
                            ("avg_energy", "energy_mean"),
                            ("energy_variance", "energy_var"),
                            ("pitch_avg", "pitch_mean"),
                            ("pitch_variance", "pitch_var")]:
            new_val = audio_features.get(key, 0.0)
            old_val = getattr(v, attr)
            if n == 0:
                setattr(v, attr, new_val)
            else:
                setattr(v, attr, (old_val * n + new_val) / (n + 1))

        laughter = audio_features.get("laughter_count", 0)
        dur = max(audio_features.get("duration_s", 60), 1)
        v.laughter_per_minute = (v.laughter_per_minute * n + laughter / (dur / 60)) / (n + 1)

        filler = audio_features.get("filler_count", 0)
        words = audio_features.get("approx_words", 100)
        v.filler_word_ratio = (v.filler_word_ratio * n +
                                (filler / max(words, 1))) / (n + 1)

        v.samples = n + 1
        v.last_voice_at = time.time()
        if contact and self._record.contacts.get(contact.lower()):
            # also track per-contact if known
            pass
        self.save()
        return {"samples": v.samples, "last_at": v.last_voice_at}

    def observe_behavior(self, event: dict) -> dict:
        """Learn from a behavior event.

        event expected keys:
          type: 'message' | 'session_start' | 'session_end' | 'voice_call'
          contact: contact name
          ts: unix timestamp
          duration_s: for sessions
          response_time_s: for messages
        """
        b = self._record.behavior
        et = event.get("type", "")
        ts = event.get("ts", time.time())
        if et == "message":
            hr = datetime.fromtimestamp(ts).hour
            wd = datetime.fromtimestamp(ts).weekday()
            b.active_hours[hr] = b.active_hours.get(hr, 0) + 1
            b.active_days[wd] = b.active_days.get(wd, 0) + 1
            contact = event.get("contact", "").lower()
            if contact:
                rt = event.get("response_time_s", 0)
                if rt > 0:
                    cur = b.response_time_by_contact.get(contact, [])
                    cur.append(rt)
                    b.response_time_by_contact[contact] = cur[-50:]
            if event.get("initiated_by_user"):
                b.initiation_ratio = ((b.initiation_ratio * 100) + 1) / 101
            else:
                b.initiation_ratio = (b.initiation_ratio * 100) / 101
        elif et == "session_end":
            dur = event.get("duration_s", 0)
            if dur > 0:
                n = b.samples
                b.avg_session_length_min = ((b.avg_session_length_min * n + dur / 60) /
                                              (n + 1))
                b.samples = n + 1
        b.last_active_at = ts
        self.save()
        return {"recorded": et, "ts": ts}

    def observe_mood(self, mood: str, confidence: float = 1.0,
                      source: str = "user") -> dict:
        """User explicitly says their mood (e.g., "I'm stressed today")."""
        e = self._record.emotion
        e.mood_distribution[mood] = e.mood_distribution.get(mood, 0) + 1
        e.samples += 1
        e.mood_baseline = max(e.mood_distribution.items(),
                                key=lambda kv: kv[1])[0]
        self.save()
        return {"mood": mood, "baseline": e.mood_baseline}

    # ── Per-contact queries ──────────────────────────────────────────────

    def persona_for(self, contact: str) -> ContactPersona:
        """Get the persona profile tailored for this contact."""
        cp = self._record.contacts.get(contact.lower())
        if cp is None:
            return ContactPersona(contact=contact)
        return ContactPersona(**cp) if isinstance(cp, dict) else cp

    def describe(self) -> dict:
        return self._record.to_dict()

    def fingerprint(self) -> dict:
        """Multi-modal fingerprint summary."""
        r = self._record
        return {
            "text": asdict(r.text),
            "voice": asdict(r.voice),
            "behavior": asdict(r.behavior),
            "emotion": asdict(r.emotion),
            "cultural": asdict(r.cultural),
            "samples_total": r.samples_total,
            "contacts": list(r.contacts.keys()),
        }

    def drift_report(self) -> dict:
        """How has the persona changed over time?"""
        if len(self._record.snapshots) < 2:
            return {"status": "insufficient_data",
                    "snapshots": len(self._record.snapshots)}
        recent = self._record.snapshots[-1]
        older = self._record.snapshots[0]
        changes = {}
        for key in ("urdu_roman", "english", "avg_words",
                     "mood_baseline", "active_hours"):
            old = older.get(key)
            new = recent.get(key)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                changes[key] = round(new - old, 3)
        return {
            "status": "ok",
            "snapshot_count": len(self._record.snapshots),
            "days_tracked": recent.get("ts", 0) - older.get("ts", 0),
            "changes": changes,
            "drift_score": self._record.drift_score,
        }

    def predict_next(self, contact: str, thread: list[dict]) -> str:
        """Predict what the user would likely say next based on persona + thread."""
        cp = self.persona_for(contact)
        prompt = f"""You are predicting what {self.user_name or 'the user'} would say next in a conversation with {contact}.

User's persona for {contact}:
- Formality: {cp.formality:.1f}/1.0
- Warmth: {cp.warmth:.1f}/1.0
- Avg length: {cp.avg_length_words:.0f} words
- Common topics: {', '.join(cp.common_topics[:5]) or 'general'}

Recent thread (most recent last):
{chr(10).join(f"  [{m.get('role', '?')}] {m.get('text', '')}" for m in thread[-6:])}

Write the most likely next message {self.user_name or 'the user'} would send.
Match their style exactly. Output ONLY the message text, no quotes, no commentary.
"""
        llm = self._get_llm()
        if llm is None:
            return self._fallback_predict(cp, thread)
        try:
            r = llm.generate(prompt, max_tokens=200, temperature=0.7)
            return (r.text or "").strip()
        except Exception:
            return self._fallback_predict(cp, thread)

    def draft_reply(self, contact: str, incoming: str,
                     thread: Optional[list[dict]] = None) -> str:
        """Draft a reply in user's persona for this specific contact."""
        cp = self.persona_for(contact)
        text_fp = self._record.text
        emo = self._record.emotion
        prompt = f"""You are drafting a reply that {self.user_name or 'the user'} would send to {contact}.

User's persona for {contact}:
- Formality: {cp.formality:.1f}/1.0
- Warmth: {cp.warmth:.1f}/1.0
- Avg length: {cp.avg_length_words:.0f} words
- Emoji usage: {cp.emoji_usage:.1f}/1.0
- Recent mood: {emo.mood_baseline}

User's overall style:
- Languages: urdu={text_fp.urdu_roman:.0%}, eng={text_fp.english:.0%}, mixed={text_fp.mixed:.0%}
- Top words: {', '.join(text_fp.top_words[:15])}
- Signature phrases: {', '.join(text_fp.signature_phrases[:8])}

Incoming from {contact}: "{incoming}"

Thread context:
{chr(10).join(f"  [{m.get('role', '?')}] {m.get('text', '')}" for m in (thread or [])[-6:])}

Write a reply that {self.user_name or 'the user'} would actually send.
Match their tone, language mix, and style. Be authentic, not robotic.
Output ONLY the reply text, no quotes, no commentary.
"""
        llm = self._get_llm()
        if llm is None:
            return self._fallback_draft(cp, incoming)
        try:
            r = llm.generate(prompt, max_tokens=300, temperature=0.7)
            return (r.text or "").strip()
        except Exception:
            return self._fallback_draft(cp, incoming)

    def to_prompt(self, contact: Optional[str] = None) -> str:
        """Render persona as natural-language description for LLM."""
        r = self._record
        t = r.text
        e = r.emotion
        c = r.cultural
        b = r.behavior
        cp = self.persona_for(contact) if contact else None

        lines = [f"User persona for '{r.user_name or 'the user'}' "
                  f"(v{r.version}, {r.samples_total} samples):"]

        # Languages
        langs = []
        if t.urdu_roman > 0.1:
            sub = "Pakistani" if t.pakistani_urdu > t.indian_hindi else "Indian"
            langs.append(f"Roman Urdu ({t.urdu_roman:.0%}, {sub} flavor)")
        if t.hindi > 0.1:
            langs.append(f"Hindi ({t.hindi:.0%})")
        if t.english > 0.1:
            langs.append(f"English ({t.english:.0%})")
        if t.mixed > 0.2:
            langs.append(f"Code-switching ({t.mixed:.0%})")
        if langs:
            lines.append(f"- Languages: {', '.join(langs)}")
        if t.arabic_loanwords > 0.1:
            lines.append(f"- Uses religious/cultural phrases "
                           f"({t.arabic_loanwords:.0%} of messages)")

        # Style
        lines.append(f"- Message length: {t.avg_words:.0f} words, "
                       f"{t.avg_chars:.0f} chars (avg)")
        if t.exclamation_density > 0.02:
            lines.append("- Uses exclamation marks frequently")
        if t.question_density > 0.02:
            lines.append("- Asks questions")
        if t.emoji_density > 0.01:
            lines.append("- Uses emojis")
        if t.all_caps_ratio > 0.05:
            lines.append("- Uses ALL CAPS for emphasis")
        if t.ellipsis_ratio > 0.01:
            lines.append("- Uses ellipsis...")

        # Vocabulary
        if t.top_words:
            lines.append(f"- Top words: {', '.join(t.top_words[:15])}")
        if t.signature_phrases:
            lines.append(f"- Signature phrases: "
                           f"{', '.join(t.signature_phrases[:8])}")
        if t.common_openings:
            lines.append(f"- Typical openings: {', '.join(t.common_openings[:5])}")
        if t.common_closings:
            lines.append(f"- Typical closings: {', '.join(t.common_closings[:5])}")

        # Mood
        if e.samples > 0:
            top_moods = sorted(e.mood_distribution.items(),
                                  key=lambda kv: -kv[1])[:3]
            mood_str = ", ".join(f"{m}={c}" for m, c in top_moods)
            lines.append(f"- Mood distribution: {mood_str} "
                           f"(baseline: {e.mood_baseline})")
        if e.empathy_level > 0.6:
            lines.append("- High empathy / caring tone")

        # Per-contact
        if cp and cp.samples > 0:
            lines.append("")
            lines.append(f"Persona specifically for {contact}:")
            lines.append(f"- Formality: {cp.formality:.1f}/1.0")
            lines.append(f"- Warmth: {cp.warmth:.1f}/1.0")
            lines.append(f"- Avg length: {cp.avg_length_words:.0f} words")
            if cp.common_topics:
                lines.append(f"- Common topics: {', '.join(cp.common_topics[:5])}")

        # Cultural
        if c.favorite_phrases:
            lines.append(f"- Cultural phrases: {', '.join(c.favorite_phrases[:5])}")

        # Behavior (active hours)
        if b.active_hours:
            top_hours = sorted(b.active_hours.items(),
                                  key=lambda kv: -kv[1])[:3]
            hours_str = ", ".join(f"{h}:00" for h, _ in top_hours)
            lines.append(f"- Most active hours: {hours_str}")

        lines.append("")
        lines.append("Match this style when writing messages on the user's behalf. "
                       "Be authentic to their voice, not generic.")
        return "\n".join(lines)

    # ── Persistence ──────────────────────────────────────────────────────

    def save(self):
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(
                json.dumps(self._record.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Persona v2 save failed")

    def load(self) -> bool:
        if not self._store_path.exists():
            return False
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            self._record = PersonaRecord.from_dict(data)
            return True
        except Exception:
            logger.exception("Persona v2 load failed")
            return False

    # ── Internal: text processing ────────────────────────────────────────

    def _update_text(self, messages: list[str], ts: float) -> None:
        t = self._record.text
        old_n = t.samples
        new_n = old_n + len(messages)
        if new_n == 0:
            return

        # Per-message features
        words_per_msg = []
        chars_per_msg = []
        all_words: list[str] = []
        word_counts: Counter = Counter()
        exclam_total = 0
        question_total = 0
        emoji_total = 0
        all_caps_total = 0
        period_total = 0
        comma_total = 0
        ellipsis_total = 0
        urdu_hits = 0
        hindi_hits = 0
        english_hits = 0
        pak_markers = 0
        ind_markers = 0
        arabic_hits = 0
        sentence_count = 0
        openings: Counter = Counter()
        closings: Counter = Counter()
        phrase_counts: Counter = Counter()
        all_word_tokens = 0
        code_switch_points: list[str] = []

        greetings_kw = {"hi", "hello", "hey", "salam", "aoa", "assalam",
                         "namaste", "good morning", "good evening", "howdy",
                         "yo", "sup"}
        farewells_kw = {"bye", "goodbye", "see you", "tc", "phir milte",
                          "khuda hafiz", "allah hafiz", "take care", "later",
                          "gn", "good night"}

        for msg in messages:
            low = msg.lower().strip()
            words = self._tokenize(msg)
            words_per_msg.append(len(words))
            chars_per_msg.append(len(msg))
            all_words.extend(words)
            all_word_tokens += len(words)
            for w in words:
                word_counts[w] += 1
            exclam_total += msg.count("!")
            question_total += msg.count("?")
            emoji_total += len(EMOJI.findall(msg))
            period_total += msg.count(".")
            comma_total += msg.count(",")
            ellipsis_total += msg.count("...") + msg.count("…")
            if msg == msg.upper() and any(c.isalpha() for c in msg):
                all_caps_total += 1
            sentence_count += max(1, len(re.split(r"[.!?]+", msg.strip())) - 1)

            # Language
            for w in words:
                wl = w.lower()
                if wl in URDU_ROMAN_WORDS:
                    urdu_hits += 1
                    if wl in ("yaar", "boss", "theek"):
                        pak_markers += 1
                    if wl in ("yaar", "bhai", "achha"):
                        ind_markers += 1
                if wl in {"namaste", "dhanyavaad", "kripya", "haanji"}:
                    hindi_hits += 1
                if wl in {"inshallah", "mashallah", "alhamdulillah",
                           "subhanallah", "bismillah"}:
                    arabic_hits += 1

            # Phrases
            for n in (2, 3):
                tokens = low.split()
                for i in range(len(tokens) - n + 1):
                    phrase = " ".join(tokens[i:i + n])
                    if not any(w in phrase for w in ("the", "a", "an")):
                        phrase_counts[phrase] += 1

            # Code-switching points (where Urdu meets English in same msg)
            has_urdu = any(w.lower() in URDU_ROMAN_WORDS for w in words)
            has_eng = any(w.lower() in {"the", "and", "or", "is", "are", "to",
                                          "for", "with"} or len(w) > 5
                            for w in words)
            if has_urdu and has_eng and len(words) > 2:
                # find the switch point
                for i, w in enumerate(words):
                    if i > 0:
                        prev_is_urdu = words[i - 1].lower() in URDU_ROMAN_WORDS
                        curr_is_eng = w.lower() not in URDU_ROMAN_WORDS
                        if prev_is_urdu and curr_is_eng and len(w) > 3:
                            code_switch_points.append(w)
                            break

            # Openings / closings
            tokens = low.split()
            if tokens and tokens[0] in greetings_kw:
                openings[tokens[0]] += 1
            if tokens:
                last = tokens[-1].rstrip(".!?")
                if last in farewells_kw:
                    closings[last] += 1

        # Per-message language classification
        lang_per_msg = []
        for msg in messages:
            words = set(self._tokenize(msg))
            has_urdu = any(w.lower() in URDU_ROMAN_WORDS for w in words)
            has_eng = any(w.lower() in {"the", "and", "to", "for"} or
                            len(w) > 4 for w in words)
            if has_urdu and has_eng:
                lang_per_msg.append("mixed")
            elif has_urdu:
                lang_per_msg.append("urdu_roman")
            elif has_eng:
                lang_per_msg.append("english")
            else:
                lang_per_msg.append("english")
        lang_counter = Counter(lang_per_msg)

        # Update fields (running averages for numbers, new values for sets)
        def r_avg(old, new_vals):
            if not new_vals:
                return old
            avg = sum(new_vals) / len(new_vals)
            if old_n == 0:
                return avg
            return (old * old_n + avg * len(messages)) / new_n

        t.samples = new_n
        t.urdu_roman = self._running_dist(t.urdu_roman, lang_counter.get("urdu_roman", 0), new_n, old_n, len(messages))
        t.english = self._running_dist(t.english, lang_counter.get("english", 0), new_n, old_n, len(messages))
        t.hindi = self._running_dist(t.hindi, hindi_hits / max(all_word_tokens, 1), new_n, old_n, 1)
        t.mixed = self._running_dist(t.mixed, lang_counter.get("mixed", 0), new_n, old_n, len(messages))
        t.pakistani_urdu = self._running_dist(t.pakistani_urdu, pak_markers / max(all_word_tokens, 1),
                                                  new_n, old_n, 1)
        t.indian_hindi = self._running_dist(t.indian_hindi, ind_markers / max(all_word_tokens, 1),
                                              new_n, old_n, 1)
        t.arabic_loanwords = self._running_dist(t.arabic_loanwords, arabic_hits / max(len(messages), 1),
                                                  new_n, old_n, 1)
        t.avg_words = r_avg(t.avg_words, words_per_msg)
        t.avg_chars = r_avg(t.avg_chars, chars_per_msg)
        t.exclamation_density = r_avg(t.exclamation_density,
                                        [m.count("!") / max(len(m), 1) for m in messages])
        t.question_density = r_avg(t.question_density,
                                      [m.count("?") / max(len(m), 1) for m in messages])
        t.emoji_density = r_avg(t.emoji_density,
                                  [len(EMOJI.findall(m)) / max(len(m), 1) for m in messages])
        t.all_caps_ratio = r_avg(t.all_caps_ratio,
                                   [1 if m == m.upper() and any(c.isalpha() for c in m) else 0
                                    for m in messages])
        t.period_ratio = r_avg(t.period_ratio,
                                 [m.count(".") / max(len(m), 1) for m in messages])
        t.comma_ratio = r_avg(t.comma_ratio,
                                [m.count(",") / max(len(m), 1) for m in messages])
        t.ellipsis_ratio = r_avg(t.ellipsis_ratio,
                                   [m.count("...") for m in messages])
        t.sentence_count += sentence_count
        t.avg_sentence_length = (t.avg_words * new_n) / max(t.sentence_count, 1)
        t.top_words = [w for w, _ in word_counts.most_common(50)]
        t.signature_phrases = [p for p, c in phrase_counts.most_common(20) if c >= 3]
        t.code_switch_points = code_switch_points[:20]
        t.common_openings = [o for o, _ in openings.most_common(10)]
        t.common_closings = [c for c, _ in closings.most_common(10)]
        t.last_text_at = ts

    def _running_dist(self, old, new_count, new_n, old_n, divisor):
        if divisor == 0:
            return old
        new_ratio = new_count / divisor
        if old_n == 0:
            return new_ratio
        return (old * old_n + new_ratio * new_n) / (old_n + new_n)

    def _update_emotion(self, messages: list[str], ts: float) -> None:
        e = self._record.emotion
        for msg in messages:
            low = msg.lower()
            detected = None
            for mood, keywords in MOOD_KEYWORDS.items():
                if any(kw in low for kw in keywords):
                    detected = mood
                    break
            if detected:
                e.mood_distribution[detected] = e.mood_distribution.get(detected, 0) + 1
            e.samples += 1
        if e.mood_distribution:
            e.mood_baseline = max(e.mood_distribution.items(),
                                    key=lambda kv: kv[1])[0]
            # emotional range = number of distinct moods with > 5% share
            total = sum(e.mood_distribution.values())
            distinct = sum(1 for v in e.mood_distribution.values() if v / total > 0.05)
            e.emotional_range = distinct / max(len(MOOD_KEYWORDS), 1)
        # empathy proxy
        caring = sum(e.mood_distribution.get(m, 0) for m in ("caring", "calm"))
        e.empathy_level = caring / max(e.samples, 1)

    def _update_cultural(self, messages: list[str], ts: float) -> None:
        c = self._record.cultural
        for msg in messages:
            low = msg.lower()
            for phrase, native in URDU_IDIOMS.items():
                if phrase in low:
                    c.favorite_phrases.append(phrase)
            c.samples += 1
            if "cricket" in low or "match" in low or "wicket" in low:
                c.references_cricket += 1
            if any(w in low for w in ("biryani", "nihari", "haleem", "karahi",
                                          "roti", "chai", "food", "khana")):
                c.references_food += 1
            if any(w in low for w in ("mummy", "papa", "bhai", "behen",
                                          "family", "ghar", "amma", "abbu")):
                c.references_family += 1
            if any(w in low for w in ("work", "office", "meeting", "boss",
                                          "project", "deadline", "client")):
                c.references_work += 1
        c.religious_phrase_frequency = (
            len(c.favorite_phrases) / max(c.samples, 1))
        # Keep only top 20
        seen = []
        for p in c.favorite_phrases:
            if p not in seen:
                seen.append(p)
        c.favorite_phrases = seen[:20]
        c.last_updated = ts

    def _update_behavior(self, messages: list[str], ts: float) -> None:
        # For now, just record activity hour
        b = self._record.behavior
        hr = datetime.fromtimestamp(ts).hour
        wd = datetime.fromtimestamp(ts).weekday()
        b.active_hours[hr] = b.active_hours.get(hr, 0) + len(messages)
        b.active_days[wd] = b.active_days.get(wd, 0) + len(messages)
        b.last_active_at = ts

    def _update_contact_persona(self, contact: str,
                                  messages: list[str], ts: float) -> None:
        key = contact.lower()
        cp_data = self._record.contacts.get(key, {})
        if not cp_data:
            cp_data = {
                "contact": contact, "samples": 0,
                "formality": 0.0, "warmth": 0.0, "technicality": 0.0,
                "emoji_usage": 0.0, "avg_length_words": 0.0,
                "common_topics": [], "last_updated": 0.0,
            }
            self._record.contacts[key] = cp_data
        n = cp_data["samples"]
        new_n = n + len(messages)

        all_words = 0
        casual = formal = warmth = tech = emoji = 0
        topics: Counter = Counter()

        for msg in messages:
            low = msg.lower()
            all_words += len(self._tokenize(msg))
            casual += sum(1 for kw in ("yaar", "bhai", "boss", "haha", "lol")
                            if kw in low)
            formal += sum(1 for kw in ("dear", "regards", "sincerely",
                                          "kindly", "sir", "please find")
                            if kw in low)
            warmth += sum(1 for kw in ("love", "care", "miss", "khow haal",
                                          "khair", "dua", "fikar")
                            if kw in low)
            tech += sum(1 for kw in ("api", "code", "build", "test",
                                        "deploy", "bug", "feature")
                            if kw in low)
            emoji += len(EMOJI.findall(msg))
            for word in ("work", "family", "food", "cricket", "music",
                          "movies", "study", "health", "money", "fun",
                          "travel", "shopping"):
                if word in low:
                    topics[word] += 1

        cp_data["samples"] = new_n
        cp_data["formality"] = self._running_dist(cp_data["formality"], formal,
                                                     new_n, n, len(messages))
        cp_data["warmth"] = self._running_dist(cp_data["warmth"], warmth,
                                                  new_n, n, len(messages))
        cp_data["technicality"] = self._running_dist(cp_data["technicality"],
                                                       tech, new_n, n, len(messages))
        cp_data["emoji_usage"] = self._running_dist(cp_data["emoji_usage"],
                                                       emoji / max(all_words, 1),
                                                       new_n, n, 1)
        cp_data["avg_length_words"] = (cp_data["avg_length_words"] * n +
                                         (all_words / max(len(messages), 1))) / new_n
        # Merge topic counts
        old_topics = dict(zip(cp_data.get("common_topics", [])[::2],
                                cp_data.get("common_topics", [])[1::2]))
        for t, c in topics.items():
            old_topics[t] = old_topics.get(t, 0) + c
        top = sorted(old_topics.items(), key=lambda kv: -kv[1])[:10]
        cp_data["common_topics"] = [t for k in top for t in k]  # flat list
        cp_data["last_updated"] = ts

    def _maybe_snapshot(self) -> None:
        # Weekly snapshot for drift tracking
        last = self._record.snapshots[-1] if self._record.snapshots else None
        now = time.time()
        if last and (now - last.get("ts", 0)) < 7 * 86400:
            return
        t = self._record.text
        e = self._record.emotion
        b = self._record.behavior
        snap = {
            "ts": now,
            "urdu_roman": t.urdu_roman,
            "english": t.english,
            "avg_words": t.avg_words,
            "mood_baseline": e.mood_baseline,
            "active_hours": dict(b.active_hours),
        }
        self._record.snapshots.append(snap)
        if len(self._record.snapshots) > 52:  # ~1 year of weekly
            self._record.snapshots = self._record.snapshots[-52:]
        # Compute drift score (sum of absolute changes from previous)
        if len(self._record.snapshots) >= 2:
            prev = self._record.snapshots[-2]
            diff = sum(abs(snap.get(k, 0) - prev.get(k, 0))
                        for k in ("urdu_roman", "english", "avg_words"))
            self._record.drift_score = min(1.0, diff / 2.0)

    def _get_llm(self):
        try:
            from .providers import get_default_chain
            return get_default_chain()
        except Exception:
            return None

    def _fallback_predict(self, cp: ContactPersona, thread: list) -> str:
        last = thread[-1].get("text", "") if thread else ""
        if not last:
            return "..."
        if "?" in last:
            return cp.common_topics[0] if cp.common_topics else "ok"
        return "ok"

    def _fallback_draft(self, cp: ContactPersona, incoming: str) -> str:
        if cp.warmth > 0.5:
            return "yaar abhi busy hoon, jaldi baat karta hoon"
        return "abhi busy hoon, baad mein reply karta hoon"

    @staticmethod
    def _clean(msg: str) -> str:
        return re.sub(r"\s+", " ", msg.strip())

    @staticmethod
    def _tokenize(msg: str) -> list[str]:
        return re.findall(r"[A-Za-z][A-Za-z0-9'_-]*", msg)
