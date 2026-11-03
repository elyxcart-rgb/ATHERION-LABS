"""SONIC AI — Text Persona System.

Learns and stores the user's text-style persona so AutoReply can match
their voice in auto-replies. Captures:

  - Tone (formal / casual / playful / serious)
  - Vocabulary (Roman Urdu, English, mixed, technical terms)
  - Phrase patterns ("theek hai", "kar do", "yaar", "boss")
  - Reply length tendency
  - Emoji usage
  - Punctuation style (lots of !!, ?!, periods, none)

Personas are per-contact-context — you might write professionally to your
boss but casually to friends.

Public API:
    TextPersona(user_name="...")
    .learn_from_history(messages: list[str]) -> dict
    .to_prompt() -> str   # for LLM context
    .save() / .load()
    .describe() -> dict
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


logger = logging.getLogger("sonic.persona")


# Language/script detectors
URDU_ROMAN_WORDS = {
    "yaar", "bhai", "theek", "haan", "nahi", "kar", "ker", "ho", "raha",
    "kya", "kyun", "kaisa", "acha", "wah", "shukriya", "ji", "bhai",
    "boss", "chal", "phir", "abhi", "kal", "aaj", "raat", "subah",
    "tum", "main", "mera", "tera", "apna", "hum", "tumhara", "humara",
    "bohot", "bohut", "sirf", "bilkul", "zaroor", "shayad",
}

HINDI_ROMAN_WORDS = {
    "namaste", "dhanyavaad", "kripya", "haan", "nahi", "theek",
    "kya", "kab", "kahan", "kaise", "kyun", "haanji",
}

ENGLISH_FILLERS = {
    "actually", "basically", "literally", "honestly", "anyway",
    "btw", "imo", "tbh", "lol", "lmao", "haha", "ok", "okay",
}

TECH_VOCAB = {
    "api", "sdk", "deploy", "build", "commit", "merge", "pr",
    "ci", "cd", "test", "lint", "refactor", "bug", "feature",
}

Emoji = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+", flags=re.UNICODE)


@dataclass
class PersonaProfile:
    user_name: str = ""
    samples_analyzed: int = 0
    # Tone classification
    formal_ratio: float = 0.0
    casual_ratio: float = 0.0
    # Language distribution
    urdu_roman_ratio: float = 0.0
    english_ratio: float = 0.0
    mixed_ratio: float = 0.0
    hindi_ratio: float = 0.0
    # Style
    avg_length_words: float = 0.0
    avg_length_chars: float = 0.0
    exclamation_density: float = 0.0
    question_density: float = 0.0
    emoji_density: float = 0.0
    # Vocabulary fingerprint (top 50 words by frequency)
    top_words: list[str] = field(default_factory=list)
    # Phrase patterns
    signature_phrases: list[str] = field(default_factory=list)
    # Greeting/farewell style
    common_greetings: list[str] = field(default_factory=list)
    common_farewells: list[str] = field(default_factory=list)
    # Detected tone labels
    detected_traits: list[str] = field(default_factory=list)
    last_updated: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class TextPersona:
    """Learns the user's writing style from message history."""

    def __init__(self, user_name: str = "", data_dir: Optional[Path] = None):
        self.user_name = user_name
        self._profile = PersonaProfile(user_name=user_name)
        self._data_dir = data_dir or (Path.home() / ".sonic" / "memory" / "persona")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._data_dir / f"{user_name or 'default'}.json"

    # ── Learning ─────────────────────────────────────────────────────────

    def learn_from_history(self, messages: list[str]) -> dict:
        """Analyze a list of past messages and update the persona."""
        if not messages:
            return {"samples": 0, "updated": False}

        cleaned = [self._clean(m) for m in messages if m and m.strip()]
        if not cleaned:
            return {"samples": 0, "updated": False}

        all_words = []
        word_counts: Counter = Counter()
        char_total = 0
        exclam_total = 0
        question_total = 0
        emoji_total = 0
        urdu_hits = 0
        hindi_hits = 0
        english_hits = 0
        tech_hits = 0
        greetings = []
        farewells = []

        greeting_words = {"hi", "hello", "hey", "salam", "aoa", "assalam",
                           "namaste", "good morning", "good evening"}
        farewell_words = {"bye", "goodbye", "see you", "talk later", "tc",
                           "phir milte", "khuda hafiz", "allah hafiz",
                           "take care", "later"}

        for msg in cleaned:
            words = self._tokenize(msg)
            all_words.extend(words)
            for w in words:
                word_counts[w] += 1
            char_total += len(msg)
            exclam_total += msg.count("!")
            question_total += msg.count("?")
            emoji_total += len(Emoji.findall(msg))

            low = msg.lower().strip()
            tokens = low.split()
            if tokens and tokens[0] in greeting_words:
                greetings.append(tokens[0])
            if tokens and any(w in low for w in farewell_words):
                farewells.append(low[:30])

            urdu_hits += sum(1 for w in words if w.lower() in URDU_ROMAN_WORDS)
            hindi_hits += sum(1 for w in words if w.lower() in HINDI_ROMAN_WORDS)
            english_hits += sum(1 for w in words
                                  if w.lower() in ENGLISH_FILLERS or len(w) > 4)
            tech_hits += sum(1 for w in words if w.lower() in TECH_VOCAB)

        total_words = len(all_words)
        total_chars = char_total
        total_msgs = len(cleaned)

        # Update profile (running average)
        old = self._profile
        old_n = old.samples_analyzed
        new_n = old_n + total_msgs

        def running_avg(old_val: float, new_vals: list[float]) -> float:
            if not new_vals:
                return old_val
            new_avg = sum(new_vals) / len(new_vals)
            if old_n == 0:
                return new_avg
            return (old_val * old_n + new_avg * total_msgs) / new_n

        # Language classification (per-message, not per-word)
        # A message is "mixed" if it contains both Urdu and English
        lang_per_msg = []
        for msg in cleaned:
            words = set(self._tokenize(msg))
            has_urdu = any(w.lower() in URDU_ROMAN_WORDS for w in words)
            has_eng = any(w.lower() in ENGLISH_FILLERS for w in words)
            has_hindi = any(w.lower() in HINDI_ROMAN_WORDS for w in words)
            if (has_urdu or has_hindi) and has_eng:
                lang_per_msg.append("mixed")
            elif has_urdu:
                lang_per_msg.append("urdu")
            elif has_hindi:
                lang_per_msg.append("hindi")
            else:
                lang_per_msg.append("english")
        lang_counter = Counter(lang_per_msg)

        # Tone (formal vs casual)
        # Heuristic: very short replies, lots of filler, slang → casual
        casual_signals = sum(1 for msg in cleaned
                             if any(w in msg.lower() for w in
                                    ("lol", "lmao", "haha", "btw", "tbh",
                                     "yaar", "bro", "boss", "hmm", "achha")))
        formal_signals = sum(1 for msg in cleaned
                             if any(p in msg for p in
                                    ("Dear", "Regards,", "Sincerely,", "Sir,", "Ma'am",
                                     "Please find", "Kindly")))

        # Update profile fields
        self._profile = PersonaProfile(
            user_name=self.user_name,
            samples_analyzed=new_n,
            formal_ratio=formal_signals / max(total_msgs, 1),
            casual_ratio=casual_signals / max(total_msgs, 1),
            urdu_roman_ratio=lang_counter.get("urdu", 0) / max(total_msgs, 1),
            english_ratio=lang_counter.get("english", 0) / max(total_msgs, 1),
            mixed_ratio=lang_counter.get("mixed", 0) / max(total_msgs, 1),
            hindi_ratio=lang_counter.get("hindi", 0) / max(total_msgs, 1),
            avg_length_words=running_avg(old.avg_length_words,
                                           [len(self._tokenize(m)) for m in cleaned]),
            avg_length_chars=running_avg(old.avg_length_chars,
                                            [len(m) for m in cleaned]),
            exclamation_density=running_avg(old.exclamation_density,
                                              [m.count("!") / max(len(m), 1)
                                               for m in cleaned]),
            question_density=running_avg(old.question_density,
                                            [m.count("?") / max(len(m), 1)
                                             for m in cleaned]),
            emoji_density=running_avg(old.emoji_density,
                                        [len(Emoji.findall(m)) / max(len(m), 1)
                                         for m in cleaned]),
            top_words=[w for w, _ in word_counts.most_common(50)],
            signature_phrases=self._extract_signature_phrases(cleaned),
            common_greetings=[w for w, _ in Counter(greetings).most_common(5)],
            common_farewells=[f for f, _ in Counter(farewells).most_common(5)],
            detected_traits=self._detect_traits(lang_counter, cleaned,
                                                  casual_signals, formal_signals),
            last_updated=__import__("time").time(),
        )

        return {
            "samples": total_msgs,
            "updated": True,
            "total_samples": new_n,
            "language": dict(lang_counter),
        }

    # ── Persistence ─────────────────────────────────────────────────────

    def save(self):
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(
                json.dumps(self._profile.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("Persona save failed")

    def load(self) -> bool:
        if not self._store_path.exists():
            return False
        try:
            data = json.loads(self._store_path.read_text(encoding="utf-8"))
            self._profile = PersonaProfile(**data)
            return True
        except Exception:
            logger.exception("Persona load failed")
            return False

    # ── LLM context ─────────────────────────────────────────────────────

    def to_prompt(self) -> str:
        """Render persona as a natural-language description for the LLM."""
        p = self._profile
        lines = [f"User persona for '{p.user_name or 'the user'}' "
                  f"(learned from {p.samples_analyzed} messages):"]

        # Language
        langs = []
        if p.urdu_roman_ratio > 0.2:
            langs.append(f"Roman Urdu ({p.urdu_roman_ratio:.0%})")
        if p.hindi_ratio > 0.1:
            langs.append(f"Hindi ({p.hindi_ratio:.0%})")
        if p.english_ratio > 0.2:
            langs.append(f"English ({p.english_ratio:.0%})")
        if p.mixed_ratio > 0.2:
            langs.append(f"Mixed ({p.mixed_ratio:.0%})")
        if langs:
            lines.append(f"- Primary language: {', '.join(langs)}")

        # Length
        lines.append(f"- Typical message length: {p.avg_length_words:.0f} words, "
                       f"{p.avg_length_chars:.0f} chars")

        # Style
        style_bits = []
        if p.casual_ratio > 0.4:
            style_bits.append("casual/friendly")
        if p.formal_ratio > 0.3:
            style_bits.append("formal/professional")
        if style_bits:
            lines.append(f"- Tone: {', '.join(style_bits)}")
        if p.exclamation_density > 0.02:
            lines.append("- Uses exclamation marks frequently")
        if p.question_density > 0.02:
            lines.append("- Uses question marks frequently")
        if p.emoji_density > 0.01:
            lines.append("- Uses emojis")

        # Vocabulary
        if p.top_words:
            lines.append(f"- Common words: {', '.join(p.top_words[:15])}")
        if p.signature_phrases:
            lines.append(f"- Signature phrases: {', '.join(p.signature_phrases[:5])}")
        if p.common_greetings:
            lines.append(f"- Typical greetings: {', '.join(p.common_greetings)}")
        if p.common_farewells:
            lines.append(f"- Typical farewells: {', '.join(p.common_farewells)}")
        if p.detected_traits:
            lines.append(f"- Traits: {', '.join(p.detected_traits)}")

        lines.append("")
        lines.append("Match this style when writing auto-replies. Keep responses "
                       "natural and authentic, not robotic.")
        return "\n".join(lines)

    def describe(self) -> dict:
        return self._profile.to_dict()

    # ── Internals ───────────────────────────────────────────────────────

    @staticmethod
    def _clean(msg: str) -> str:
        return re.sub(r"\s+", " ", msg.strip())

    @staticmethod
    def _tokenize(msg: str) -> list[str]:
        # Keep apostrophes, hyphens, alphanumeric
        return re.findall(r"[A-Za-z][A-Za-z0-9'_-]*", msg)

    @staticmethod
    def _extract_signature_phrases(messages: list[str]) -> list[str]:
        # 2-3 word phrases that appear in multiple messages
        phrase_counts: Counter = Counter()
        for msg in messages:
            words = msg.lower().split()
            for n in (2, 3):
                for i in range(len(words) - n + 1):
                    phrase = " ".join(words[i:i + n])
                    if not any(w in phrase for w in ("the", "a", "an", "is", "are")):
                        phrase_counts[phrase] += 1
        return [p for p, c in phrase_counts.most_common(20) if c >= 3]

    @staticmethod
    def _detect_traits(lang_counter: Counter, messages: list[str],
                       casual: int, formal: int) -> list[str]:
        traits = []
        dominant_lang = lang_counter.most_common(1)
        if dominant_lang and dominant_lang[0][0] == "mixed":
            traits.append("code-switches between Urdu and English")
        if dominant_lang and dominant_lang[0][0] == "urdu":
            traits.append("writes in Roman Urdu")
        if casual > formal * 1.5:
            traits.append("casual register")
        elif formal > casual * 1.5:
            traits.append("formal register")

        avg_len = sum(len(m.split()) for m in messages) / max(len(messages), 1)
        if avg_len < 8:
            traits.append("terse / short replies")
        elif avg_len > 25:
            traits.append("verbose / detailed replies")

        if any(m.endswith("!") or m.endswith("!!") for m in messages):
            traits.append("expressive / emphatic")
        if any(Emoji.findall(m) for m in messages):
            traits.append("uses emojis")
        return traits
