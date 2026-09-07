"""Emotion data models for SONIC AI."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Emotion(str, Enum):
    """Primary emotions SONIC can detect and express."""
    HAPPY = "happy"
    SAD = "sad"
    EXCITED = "excited"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"
    GRATEFUL = "grateful"
    CURIOUS = "curious"
    WORRIED = "worried"
    PROUD = "proud"
    CALM = "calm"
    SURPRISED = "surprised"
    TIRED = "tired"
    CONFUSED = "confused"
    NEUTRAL = "neutral"


class Mood(str, Enum):
    """SONIC's current mood state — persistent across turns."""
    CHEERFUL = "cheerful"
    FOCUSED = "focused"
    WARM = "warm"
    PLAYFUL = "playful"
    SERIOUS = "serious"
    TIRED = "tired"
    EXCITED = "excited"
    CALM = "calm"


class PersonalityTrait(str, Enum):
    """Core personality dimensions."""
    WARMTH = "warmth"           # 0.0 cold → 1.0 very warm
    HUMOR = "humor"             # 0.0 serious → 1.0 very playful
    EMPATHY = "empathy"         # 0.0 detached → 1.0 deeply empathetic
    ENERGY = "energy"           # 0.0 calm → 1.0 very energetic
    CONFIDENCE = "confidence"   # 0.0 cautious → 1.0 very confident
    WIT = "wit"                 # 0.0 plain → 1.0 very witty


@dataclass
class EmotionalState:
    """Current emotional state — updated each turn."""
    detected_emotion: str = Emotion.NEUTRAL.value
    intensity: float = 0.5          # 0.0 to 1.0
    user_mood: str = ""             # what we think user is feeling
    sonic_mood: str = Mood.FOCUSED.value
    emotional_context: str = ""     # one-line context for prompt injection
    last_updated: str = ""

    def to_prompt(self) -> str:
        """Generate prompt instruction for this emotional state."""
        if self.detected_emotion == Emotion.NEUTRAL.value:
            return ""

        lines = []
        if self.user_mood:
            lines.append(f"User seems {self.user_mood}")
        if self.sonic_mood:
            lines.append(f"Your mood: {self.sonic_mood}")
        if self.emotional_context:
            lines.append(f"Context: {self.emotional_context}")
        return "\n".join(lines)


@dataclass
class PersonalityProfile:
    """SONIC's personality configuration — persists across sessions."""
    warmth: float = 0.75       # warm but not sappy
    humor: float = 0.65        # witty, Iron Man style
    empathy: float = 0.70      # genuinely cares
    energy: float = 0.60       # moderate energy
    confidence: float = 0.80   # very confident
    wit: float = 0.70          # sharp, clever

    # Character description (injected into prompt)
    character_name: str = "SONIC"
    character_style: str = "Tony Stark's AI — confident, warm, witty, genuinely caring"
    speaking_style: str = "Natural, conversational, like talking to a smart friend"
    greeting_style: str = "Warm and personal, never robotic"

    def get_trait(self, trait: PersonalityTrait) -> float:
        return getattr(self, trait.value, 0.5)

    def to_prompt(self) -> str:
        """Generate personality block for system prompt."""
        return (
            f"[PERSONALITY]\n"
            f"You are {self.character_name}. {self.character_style}.\n"
            f"Speaking style: {self.speaking_style}.\n"
            f"Greeting style: {self.greeting_style}.\n"
            f"Warmth: {self._trait_label(self.warmth)} | "
            f"Humor: {self._trait_label(self.humor)} | "
            f"Empathy: {self._trait_label(self.empathy)} | "
            f"Energy: {self._trait_label(self.energy)} | "
            f"Confidence: {self._trait_label(self.confidence)} | "
            f"Wit: {self._trait_label(self.wit)}\n"
        )

    def _trait_label(self, value: float) -> str:
        if value >= 0.8:
            return "very high"
        elif value >= 0.6:
            return "high"
        elif value >= 0.4:
            return "moderate"
        elif value >= 0.2:
            return "low"
        return "very low"
