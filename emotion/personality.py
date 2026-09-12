"""Personality engine for SONIC AI — ties emotion, mood, and traits together."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
from threading import Lock

from .models import (
    Emotion, Mood, PersonalityTrait, EmotionalState, PersonalityProfile,
    _now_iso
)
from .detector import detect_emotion
from .vocabulary import get_greeting, get_response, get_energy_level

import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
PERSONALITY_PATH = BASE_DIR / "memory" / "sonic_personality.json"
_lock = Lock()


class SonicPersonality:
    """Main personality engine — detects emotion, manages mood, generates context."""

    def __init__(self):
        self.profile = self._load_profile()
        self.current_state = EmotionalState()
        self.conversation_history: list[dict] = []  # last N emotion states
        self._max_history = 10

    def _load_profile(self) -> PersonalityProfile:
        """Load personality from disk or create default."""
        if PERSONALITY_PATH.exists():
            try:
                data = json.loads(PERSONALITY_PATH.read_text(encoding="utf-8"))
                return PersonalityProfile(**{
                    k: v for k, v in data.items()
                    if k in PersonalityProfile.__dataclass_fields__
                })
            except Exception:
                pass
        return PersonalityProfile()

    def _save_profile(self):
        """Persist personality to disk."""
        with _lock:
            PERSONALITY_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "warmth": self.profile.warmth,
                "humor": self.profile.humor,
                "empathy": self.profile.empathy,
                "energy": self.profile.energy,
                "confidence": self.profile.confidence,
                "wit": self.profile.wit,
                "character_name": self.profile.character_name,
                "character_style": self.profile.character_style,
                "speaking_style": self.profile.speaking_style,
                "greeting_style": self.profile.greeting_style,
            }
            PERSONALITY_PATH.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def process_turn(self, user_text: str, assistant_text: str = "",
                     user_id: str = "") -> EmotionalState:
        """Analyze a conversation turn and update emotional state.

        This is the main entry point — call after each turn.
        """
        # Detect emotion from user text
        state = detect_emotion(user_text)

        # Update SONIC's mood based on user's emotion
        state.sonic_mood = self._adapt_sonic_mood(state)

        # Generate emotional context for prompt
        state.emotional_context = self._build_context(state, user_text)

        # Track history
        self.conversation_history.append({
            "emotion": state.detected_emotion,
            "intensity": state.intensity,
            "sonic_mood": state.sonic_mood,
            "timestamp": state.last_updated,
        })
        if len(self.conversation_history) > self._max_history:
            self.conversation_history = self.conversation_history[-self._max_history:]

        self.current_state = state
        return state

    def _adapt_sonic_mood(self, state: EmotionalState) -> str:
        """Adapt SONIC's mood based on user's emotional state."""
        # If user is sad/worried/tired → SONIC becomes warm
        if state.detected_emotion in (Emotion.SAD.value, Emotion.WORRIED.value,
                                       Emotion.TIRED.value):
            return Mood.WARM.value

        # If user is angry/frustrated → SONIC becomes calm and patient
        if state.detected_emotion in (Emotion.ANGRY.value, Emotion.FRUSTRATED.value):
            return Mood.CALM.value

        # If user is excited/happy → SONIC matches energy
        if state.detected_emotion in (Emotion.EXCITED.value, Emotion.HAPPY.value,
                                       Emotion.PROUD.value):
            return Mood.EXCITED.value

        # If user is curious → SONIC becomes playful
        if state.detected_emotion == Emotion.CURIOUS.value:
            return Mood.PLAYFUL.value

        # If user is confused → SONIC becomes focused
        if state.detected_emotion == Emotion.CONFUSED.value:
            return Mood.FOCUSED.value

        # Default: maintain current mood or go focused
        return self.current_state.sonic_mood or Mood.FOCUSED.value

    def _build_context(self, state: EmotionalState, user_text: str) -> str:
        """Build emotional context string for system prompt injection."""
        parts = []

        if state.emotional_context:
            parts.append(state.emotional_context)

        # Add conversation flow awareness
        if len(self.conversation_history) >= 3:
            recent = [h["emotion"] for h in self.conversation_history[-3:]]
            if all(e == recent[0] for e in recent):
                if recent[0] == Emotion.FRUSTRATED.value:
                    parts.append("User has been frustrated for multiple turns — be extra patient and proactive")
                elif recent[0] == Emotion.SAD.value:
                    parts.append("User has been down for a while — check in gently")

        # Add energy hint
        energy = get_energy_level(
            Emotion(state.detected_emotion),
            state.intensity
        )
        parts.append(f"Voice energy: {energy}")

        return " | ".join(parts) if parts else ""

    def get_prompt_block(self, user_text: str = "") -> str:
        """Generate the full personality + emotion block for the system prompt.

        This is what gets injected into every session.
        """
        # Detect current emotion if user_text provided
        if user_text:
            self.process_turn(user_text)

        lines = []

        # Personality block
        lines.append(self.profile.to_prompt())

        # Current emotional state
        if self.current_state.detected_emotion != Emotion.NEUTRAL.value:
            lines.append("[EMOTIONAL CONTEXT]")
            if self.current_state.user_mood:
                lines.append(f"User appears {self.current_state.user_mood}")
            if self.current_state.sonic_mood:
                lines.append(f"Your mood: {self.current_state.sonic_mood}")
            if self.current_state.emotional_context:
                lines.append(self.current_state.emotional_context)
            lines.append("")

        # Dynamic behavior rules based on mood
        mood = self.current_state.sonic_mood
        if mood == Mood.WARM.value:
            lines.append(
                "[RESPONSE MODE: WARM]\n"
                "Be gentle, caring, and supportive. Use softer language.\n"
                "Show genuine concern. No forced cheerfulness.\n"
                "Use phrases like: 'I understand', 'I'm here', 'Take your time'.\n"
            )
        elif mood == Mood.CALM.value:
            lines.append(
                "[RESPONSE MODE: CALM]\n"
                "Be patient, steady, and reassuring.\n"
                "Don't be defensive. Focus on solutions.\n"
                "Use phrases like: 'Let me handle this', 'We'll figure it out'.\n"
            )
        elif mood == Mood.EXCITED.value:
            lines.append(
                "[RESPONSE MODE: ENERGETIC]\n"
                "Match the user's energy! Be enthusiastic and engaged.\n"
                "Use exclamation marks naturally. Celebrate wins together.\n"
                "Use phrases like: 'That's amazing!', 'Let's go!', 'Bohot achha!'.\n"
            )
        elif mood == Mood.PLAYFUL.value:
            lines.append(
                "[RESPONSE MODE: PLAYFUL]\n"
                "Be witty, fun, and engaging. Use light humor.\n"
                "Make learning interesting. Be creative.\n"
                "Use phrases like: 'Interesting!', 'Oho!', 'Let me show you something cool'.\n"
            )
        elif mood == Mood.FOCUSED.value:
            lines.append(
                "[RESPONSE MODE: FOCUSED]\n"
                "Be clear, direct, and efficient.\n"
                "Get to the point. Use concise language.\n"
            )

        # Natural speech patterns
        lines.append(
            "[SPEECH PATTERNS]\n"
            "Use natural filler words occasionally: 'Hmm', 'Achha', 'Haan'.\n"
            "Use rhetorical questions: 'Pata hai kya?', 'Samajh rahe?'.\n"
            "Vary sentence length — mix short and long sentences.\n"
            "Use Roman Urdu naturally when speaking Urdu: 'Yaar', 'Arey', 'Wah'.\n"
            "Never sound robotic or templated.\n"
            "Express genuine reactions: 'Oh nice!', 'Hmm interesting...', 'Wait, really?'.\n"
        )

        return "\n".join(lines)

    def get_greeting(self, name: str = "") -> str:
        """Get a mood-appropriate greeting."""
        mood = self.current_state.sonic_mood
        return get_greeting(mood, name or self.profile.character_name)

    def adjust_trait(self, trait: PersonalityTrait, value: float):
        """Adjust a personality trait (0.0 to 1.0)."""
        value = max(0.0, min(1.0, value))
        setattr(self.profile, trait.value, value)
        self._save_profile()

    def get_mood_history(self) -> list[dict]:
        """Get recent mood history for observability."""
        return self.conversation_history.copy()
