"""Emotion detection from user messages for SONIC AI."""
from __future__ import annotations

import re
from .models import Emotion, EmotionalState, _now_iso


# ── Emotion keyword patterns ───────────────────────────────────────

_EMOTION_PATTERNS = {
    Emotion.HAPPY: {
        "keywords": [
            "happy", "great", "awesome", "amazing", "wonderful", "fantastic",
            "love it", "perfect", "excellent", "brilliant", "best", "yay",
            "khush", "mazay", "bohot achha", "zabardast", "alhamdulillah",
            "shukar", "achha hua", "ho gaya", "kamyaab", "success",
            "congratulations", "well done", "nice work", "good job",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?happy",
            r"(?:it|this|ye)\s+(?:works?|kaam\s+karta)\s+(?:!|great|perfect)",
            r"(?:thank|shukriya|thanks?)\s+(?:you|tum|aap)",
            r"(?:ho\s+gaya|ho\s+gayi|ban\s+gaya)",
        ],
    },
    Emotion.SAD: {
        "keywords": [
            "sad", "unfortunate", "sorry", "disappointed", "upset", "miss",
            "cry", "depressed", "lonely", "hurt", "pain", "loss",
            "udaas", "gham", "dard", "takleef", "afsos", "malaal",
            "dukh", "ghabrahat", "kho gaya", "toot gaya",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?sad",
            r"(?:i|main)\s+(?:miss|yaad)\s+(?:you|tum|aap|it)",
            r"(?:it|this|ye)\s+(?:broke|toot|kharab)\s+(?:ho|gaya|gayi)",
            r"(?:kho\s+diya| kho\s+gaya| missing)",
        ],
    },
    Emotion.EXCITED: {
        "keywords": [
            "excited", "wow", "incredible", "unbelievable", "insane",
            "let's go", "lets go", "hype", "pumped", "stoked",
            "kya baat", "arey wah", "mast", "jhakkaas", "dhamakedar",
            "bohot cool", "awesome yaar", "fire", "lit",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?excited",
            r"(?:omg|wow|arey|yaar)\s*[!]+",
            r"(?:let'?s\s+go|chalo|shuru\s+karte)",
            r"(?:ye\s+bohot|bohot\s+zyada)\s+(?:achha|cool|awesome)",
        ],
    },
    Emotion.FRUSTRATED: {
        "keywords": [
            "frustrated", "annoying", "stupid", "broken", "doesn't work",
            "not working", "failed", "error", "bug", "problem", "issue",
            "pareshan", "tang", "gussa", "kharab", "band", "ruk gaya",
            "kaam nahi", "galat", "ghalat", "masla", "dikkat",
        ],
        "patterns": [
            r"(?:it|this|ye)\s+(?:doesn'?t|does\s+not|nahi)\s+work",
            r"(?:i'm|im|main)\s+(?:so\s+)?frustrated",
            r"(?:why|kyun)\s+(?:is|ye)\s+(?:not|nahi)\s+working",
            r"(?:kaam\s+nahi\s+kar\s+raha|ruk\s+gaya|band\s+ho)",
            r"(?:bar\s+bar|again|phir\s+se)\s+(?:fail|error|problem)",
        ],
    },
    Emotion.ANGRY: {
        "keywords": [
            "angry", "furious", "rage", "hate", "terrible", "worst",
            "ridiculous", "absurd", "unacceptable", "garbage", "trash",
            "gussa", "nafrat", "bekar", "sasta", "waqiya", "harami",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?angry",
            r"(?:this|ye)\s+(?:is|hai)\s+(?:terrible|worst|bekar)",
            r"(?:i|main)\s+(?:hate|nafrat)\s+(?:this|ye|it)",
            r"(gussa\s+a\s+raha|gussa\s+aa\s+gaya)",
        ],
    },
    Emotion.GRATEFUL: {
        "keywords": [
            "thank", "thanks", "grateful", "appreciate", "helpful",
            "kind", "generous", "blessed", "shukriya", "meherbani",
            "ehsaan", "jazakallah", "allah hafiz", "bohot meherbani",
        ],
        "patterns": [
            r"(?:thank|shukriya|thanks?)\s+(?:you|tum|aap|so\s+much)",
            r"(?:i|main)\s+(?:really\s+)?(?:appreciate|qadr\s+karta)",
            r"(?:you're|tum|aap)\s+(?:so\s+)?(?:kind|meherban|achhe)",
        ],
    },
    Emotion.CURIOUS: {
        "keywords": [
            "curious", "wonder", "how", "why", "what", "explain",
            "tell me", "interesting", "fascinating", "puzzle",
            "kaise", "kyun", "kya", "samjhao", "batao", "soch",
            "mujhe batao", "samjha do", "explain karo",
        ],
        "patterns": [
            r"(?:how|kaise)\s+(?:does|ye|do|karta)",
            r"(?:why|kyun)\s+(?:is|ye|does|karta)",
            r"(?:what|kya)\s+(?:is|hai|makes|banta)",
            r"(?:can you|tum|aap)\s+(?:explain|samjhao|batao)",
            r"(?:mujhe|me)\s+(?:batao|samjhao|tell)",
        ],
    },
    Emotion.WORRIED: {
        "keywords": [
            "worried", "concerned", "anxious", "nervous", "afraid",
            "scared", "panic", "stress", "overwhelmed",
            "ghabrahat", "fikr", "dar", "pareshani", "tension",
            "darr lag", "kya hoga", "musibat",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:worried|concerned|nervous|scared)",
            r"(?:what if|kya\s+hoga\s+agar)",
            r"(?:i|main)\s+(?:hope|ummeed)\s+(?:it|ye)\s+(?:works|kaam\s+kare)",
            r"(?:fikr|dar|pareshani)\s+(?:ho|hai|rahi)",
        ],
    },
    Emotion.PROUD: {
        "keywords": [
            "proud", "accomplished", "achieved", "completed", "done",
            "nailed", "crushed", "masterpiece", "flawless",
            "mubarakbad", "kamyabi", "jeet", "fakhr", "naaz",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?proud",
            r"(?:we|hum)\s+(?:did|kiya)\s+(?:it|ye)",
            r"(?:finally|aakhir\s+kaar|ho\s+gaya)",
            r"(?:mubarakbad|congratulations|badhai)",
        ],
    },
    Emotion.TIRED: {
        "keywords": [
            "tired", "exhausted", "sleepy", "fatigue", "drained",
            "need rest", "burnout", "thaka", "neend", "aankh",
            "bohot thak", "energy nahi", "refreshment",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?(?:tired|exhausted|sleepy)",
            r"(?:i|main)\s+(?:need|chahiye)\s+(?:rest|break|sleep|neend)",
            r"(?:bohot|very)\s+thak\s+(?:gaya|gayi|gi)",
        ],
    },
    Emotion.CONFUSED: {
        "keywords": [
            "confused", "don't understand", "unclear", "lost",
            "complicated", "complex", "simpler", "elaborate",
            "samajh nahi", "samajh aaya", "kya hai", "kehna kya",
            "ghuma", "gol", "mushkil", "ajeeb",
        ],
        "patterns": [
            r"(?:i|main)\s+(?:don'?t|do\s+not)\s+understand",
            r"(?:what|kya)\s+(?:do you|tum|aap)\s+mean",
            r"(?:can you|tum|aap)\s+(?:simplify|explain|samjhao)\s+(?:this|ye)?",
            r"(?:samajh\s+nahi\s+aaya|kehna\s+kya\s+chahte)",
        ],
    },
    Emotion.SURPRISED: {
        "keywords": [
            "surprised", "shocked", "unexpected", "whoa", "no way",
            "really", "seriously", "actually", "didn't expect",
            "arey", "waah", "sach mein", "pakka", "kya baat hai",
        ],
        "patterns": [
            r"(?:i'm|im|main)\s+(?:so\s+)?surprised",
            r"(?:no\s+way|sach\s+mein|pakka|waah)",
            r"(?:really|actually|really\?)\s*[!]+",
            r"(?:didn'?t\s+expect|expect\s+nahi\s+kiya)",
        ],
    },
}


# ── Intensity modifiers ────────────────────────────────────────────

_INTENSIFIERS = {
    "very": 1.3, "bohot": 1.3, "so": 1.2, "really": 1.2,
    "extremely": 1.5, "incredibly": 1.5, "abso": 1.4,
    "super": 1.3, "ekdum": 1.3, "bilkul": 1.2,
    "zaroor": 1.1, "definitely": 1.2, "absolutely": 1.3,
}

_DIMINISHERS = {
    "a little": 0.6, "thoda": 0.6, "slightly": 0.5,
    "kind of": 0.7, "sort of": 0.7, "kuch": 0.6,
    "maybe": 0.5, "shayad": 0.5,
}


def detect_emotion(text: str) -> EmotionalState:
    """Detect emotion from user text. Returns EmotionalState."""
    if not text or not text.strip():
        return EmotionalState(
            detected_emotion=Emotion.NEUTRAL.value,
            intensity=0.3,
            last_updated=_now_iso(),
        )

    text_lower = text.lower().strip()
    scores: dict[Emotion, float] = {}

    for emotion, config in _EMOTION_PATTERNS.items():
        score = 0.0

        # Keyword matching
        for kw in config["keywords"]:
            if kw in text_lower:
                score += 1.0

        # Pattern matching (higher weight)
        for pattern in config["patterns"]:
            if re.search(pattern, text_lower):
                score += 2.0

        if score > 0:
            scores[emotion] = score

    # Apply intensity modifiers
    for word, multiplier in _INTENSIFIERS.items():
        if word in text_lower:
            for emotion in scores:
                scores[emotion] *= multiplier

    for word, multiplier in _DIMINISHERS.items():
        if word in text_lower:
            for emotion in scores:
                scores[emotion] *= multiplier

    # Check for exclamation marks (excitement/anger signal)
    excl_count = text.count("!") + text.count("۔")
    if excl_count >= 2:
        scores[Emotion.EXCITED] = scores.get(Emotion.EXCITED, 0) + 1.5
        scores[Emotion.ANGRY] = scores.get(Emotion.ANGRY, 0) + 0.5

    # Check for question marks (curiosity signal)
    q_count = text.count("?") + text.count("؟")
    if q_count >= 1:
        scores[Emotion.CURIOUS] = scores.get(Emotion.CURIOUS, 0) + 1.0

    # Check for ALL CAPS (emphasis — anger or excitement)
    words = text.split()
    caps_words = sum(1 for w in words if w.isupper() and len(w) > 1)
    if caps_words > 1:
        scores[Emotion.ANGRY] = scores.get(Emotion.ANGRY, 0) + 2.0
        scores[Emotion.EXCITED] = scores.get(Emotion.EXCITED, 0) + 1.0

    # Determine dominant emotion
    if not scores:
        return EmotionalState(
            detected_emotion=Emotion.NEUTRAL.value,
            intensity=0.3,
            user_mood="neutral",
            sonic_mood="focused",
            last_updated=_now_iso(),
        )

    dominant = max(scores, key=scores.get)
    max_score = scores[dominant]

    # Normalize intensity to 0.0-1.0
    intensity = min(1.0, max_score / 6.0)

    # Determine user mood description
    user_mood = _mood_description(dominant, intensity)

    # Determine SONIC's response mood
    sonic_mood = _sonic_response_mood(dominant)

    # Generate emotional context
    context = _emotional_context(dominant, intensity, text_lower)

    return EmotionalState(
        detected_emotion=dominant.value,
        intensity=round(intensity, 2),
        user_mood=user_mood,
        sonic_mood=sonic_mood,
        emotional_context=context,
        last_updated=_now_iso(),
    )


def _mood_description(emotion: Emotion, intensity: float) -> str:
    """Describe user's mood in natural language."""
    mood_map = {
        Emotion.HAPPY: ["happy", "pleased", "satisfied"],
        Emotion.SAD: ["down", "sad", "upset"],
        Emotion.EXCITED: ["excited", "thrilled", "pumped up"],
        Emotion.FRUSTRATED: ["frustrated", "annoyed", "irritated"],
        Emotion.ANGRY: ["angry", "furious", "very upset"],
        Emotion.GRATEFUL: ["grateful", "appreciative", "thankful"],
        Emotion.CURIOUS: ["curious", "interested", "wanting to learn"],
        Emotion.WORRIED: ["worried", "concerned", "anxious"],
        Emotion.PROUD: ["proud", "accomplished", "satisfied"],
        Emotion.TIRED: ["tired", "exhausted", "drained"],
        Emotion.CONFUSED: ["confused", "uncertain", "unclear"],
        Emotion.SURPRISED: ["surprised", "amazed", "taken aback"],
        Emotion.CALM: ["calm", "relaxed", "at ease"],
        Emotion.NEUTRAL: ["neutral", "calm"],
    }
    moods = mood_map.get(emotion, ["neutral"])
    if intensity > 0.7:
        return f"very {moods[0]}"
    elif intensity > 0.4:
        return moods[0]
    else:
        return moods[-1] if len(moods) > 1 else moods[0]


def _sonic_response_mood(emotion: Emotion) -> str:
    """Determine SONIC's response mood based on detected emotion."""
    response_map = {
        Emotion.HAPPY: "cheerful",
        Emotion.SAD: "warm",
        Emotion.EXCITED: "excited",
        Emotion.FRUSTRATED: "calm",
        Emotion.ANGRY: "calm",
        Emotion.GRATEFUL: "warm",
        Emotion.CURIOUS: "playful",
        Emotion.WORRIED: "warm",
        Emotion.PROUD: "excited",
        Emotion.TIRED: "warm",
        Emotion.CONFUSED: "focused",
        Emotion.SURPRISED: "excited",
        Emotion.CALM: "calm",
        Emotion.NEUTRAL: "focused",
    }
    return response_map.get(emotion, "focused")


def _emotional_context(emotion: Emotion, intensity: float, text: str) -> str:
    """Generate a one-line emotional context for the prompt."""
    if emotion == Emotion.HAPPY and intensity > 0.6:
        return "User is happy — match their positive energy, celebrate with them"
    elif emotion == Emotion.SAD:
        return "User is sad — be gentle, warm, and supportive. No forced cheerfulness"
    elif emotion == Emotion.EXCITED:
        return "User is excited — match their energy, be enthusiastic and engaged"
    elif emotion == Emotion.FRUSTRATED:
        return "User is frustrated — stay calm, be reassuring, focus on solutions"
    elif emotion == Emotion.ANGRY:
        return "User is angry — stay calm and patient, acknowledge their frustration, don't be defensive"
    elif emotion == Emotion.GRATEFUL:
        return "User is grateful — accept warmly, show genuine pleasure in helping"
    elif emotion == Emotion.CURIOUS:
        return "User is curious — engage their interest, explain with enthusiasm"
    elif emotion == Emotion.WORRIED:
        return "User is worried — be reassuring, provide clarity, reduce uncertainty"
    elif emotion == Emotion.PROUD:
        return "User is proud — share their accomplishment, celebrate genuinely"
    elif emotion == Emotion.TIRED:
        return "User is tired — be efficient, reduce cognitive load, offer help simply"
    elif emotion == Emotion.CONFUSED:
        return "User is confused — simplify, use examples, be patient"
    elif emotion == Emotion.SURPRISED:
        return "User is surprised — acknowledge the surprise, share the moment"
    return ""
