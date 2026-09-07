"""SONIC AI Emotion Engine — makes SONIC feel human."""
from .models import (
    Emotion, Mood, PersonalityTrait,
    EmotionalState, PersonalityProfile,
)
from .detector import detect_emotion
from .personality import SonicPersonality
from .vocabulary import (
    get_greeting, get_response, get_micro_phrase,
    get_energy_level, GREETINGS, RESPONSES, MICRO_PHRASES,
)

__all__ = [
    "Emotion", "Mood", "PersonalityTrait",
    "EmotionalState", "PersonalityProfile",
    "detect_emotion",
    "SonicPersonality",
    "get_greeting", "get_response", "get_micro_phrase",
    "get_energy_level",
]
