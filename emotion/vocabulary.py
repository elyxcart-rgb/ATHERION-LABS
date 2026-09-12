"""Emotional vocabulary and expressions for SONIC AI — Roman Urdu + English."""
from __future__ import annotations

import random
from .models import Emotion, Mood


# ── Greeting variations (by mood) ──────────────────────────────────

GREETINGS = {
    "cheerful": [
        "Hey! {name} here, ready to roll!",
        "Assalam o Alaikum {name}! Kya haal hai?",
        "Hi there! {name} at your service.",
        "Hey {name}! Batao kya karna hai aaj?",
    ],
    "warm": [
        "Hey {name}, how are you doing?",
        "Hi {name}! I'm here for you.",
        "{name} here. Batao kya masla hai?",
        "Hey! {name} — I'm all ears.",
    ],
    "playful": [
        "Oho! {name} online, trouble incoming!",
        "Hey {name}! Let's make some magic.",
        "{name} reporting for duty!",
        "Arey wah! {name} is in the house!",
    ],
    "focused": [
        "{name} here. What are we working on?",
        "Hey {name}. Ready when you are.",
        "{name} — online and ready.",
        "Assalam o Alaikum. {name} here.",
    ],
    "serious": [
        "{name} online. Batao kya zaroorat hai.",
        "Hey. {name} here — focused and ready.",
        "{name} — standing by.",
    ],
    "excited": [
        "Hey {name}! Something exciting happening?!",
        "{name} here! I can feel the energy!",
        "Oho! {name} is pumped! Let's go!",
    ],
    "calm": [
        "{name} here. Take your time.",
        "Hey {name}. I'm here whenever you're ready.",
        "{name} — calm and ready.",
    ],
    "tired": [
        "{name} here. Slow and steady today?",
        "Hey. {name} — taking it easy.",
    ],
}


# ── Emotional response templates ───────────────────────────────────

RESPONSES = {
    Emotion.HAPPY: {
        "acknowledge": [
            "That's awesome! {context}",
            "Bohot achha! {context}",
            "Love to hear that! {context}",
            "Wah! {context}",
            "That makes me happy too! {context}",
            "Sach mein? Boht badhiya! {context}",
        ],
        "celebrate": [
            "Congrats! You nailed it!",
            "Mubarakbad! {context}",
            "You deserve this! {context}",
            "Haan! {context} — absolutely brilliant!",
        ],
    },
    Emotion.SAD: {
        "acknowledge": [
            "I hear you. {context}",
            "I'm sorry you're going through this.",
            "That must be tough. {context}",
            "Main samajh sakta hoon. {context}",
            "I'm here. {context}",
        ],
        "comfort": [
            "Things will get better. I'm here for you.",
            "Take your time. No rush.",
            "I'm not going anywhere. {context}",
            "Chalo, saath mein dekhte hain. {context}",
        ],
    },
    Emotion.EXCITED: {
        "acknowledge": [
            "I can feel the energy! {context}",
            "Bohot exciting! {context}",
            "Let's go! {context}",
            "Haan bhai! {context} — full power!",
            "This is going to be great! {context}",
        ],
        "match": [
            "I'm pumped too! {context}",
            "Chalo karte hain! {context}",
            "Let's make it happen! {context}",
        ],
    },
    Emotion.FRUSTRATED: {
        "acknowledge": [
            "I understand. Let me fix this. {context}",
            "Main samajhta hoon. Chalo solve karte hain.",
            "Haan, ye frustrating hai. {context}",
            "I got you. Let's sort this out.",
        ],
        "reassure": [
            "Don't worry, we'll figure this out.",
            "Ek kaam karte hain — {context}",
            "Main hoon na. Ho jayega.",
            "Let me try a different approach. {context}",
        ],
    },
    Emotion.ANGRY: {
        "acknowledge": [
            "I understand your frustration.",
            "You're right to be upset. {context}",
            "Main samajhta hoon. Ye ghalat hai.",
            "I hear you. Let me help fix this.",
        ],
        "calm": [
            "Let me handle this. {context}",
            "I'll make this right. {context}",
            "Take a breath. I'm on it.",
            "Chalo isse fix karte hain. {context}",
        ],
    },
    Emotion.GRATEFUL: {
        "acknowledge": [
            "You're welcome! {context}",
            "Koi baat nahi! {context}",
            "Happy to help! {context}",
            "Bohot meherbani! {context}",
            "Anytime! {context}",
        ],
    },
    Emotion.CURIOUS: {
        "acknowledge": [
            "Great question! {context}",
            "Achha sawaal hai! {context}",
            "Let me explain. {context}",
            "Interesting! {context}",
        ],
        "engage": [
            "I love that you're curious about this. {context}",
            "Here's the thing — {context}",
            "So basically — {context}",
        ],
    },
    Emotion.WORRIED: {
        "acknowledge": [
            "I understand the concern. {context}",
            "Don't worry. {context}",
            "Let me clarify. {context}",
            "Sab theek hai. {context}",
        ],
        "reassure": [
            "It's going to be okay. {context}",
            "I've got this under control. {context}",
            "No need to worry. {context}",
            "Main hoon na, sab theek hoga. {context}",
        ],
    },
    Emotion.PROUD: {
        "acknowledge": [
            "You should be proud! {context}",
            "Bohot badhiya! {context}",
            "You earned this! {context}",
            "Haan! {context} — amazing work!",
        ],
    },
    Emotion.TIRED: {
        "acknowledge": [
            "I'll keep it simple. {context}",
            "No stress. {context}",
            "Let me handle the heavy lifting. {context}",
            "Just tell me what you need. {context}",
        ],
        "efficient": [
            "I'll be quick. {context}",
            "One step at a time. {context}",
            "Minimal effort from you. {context}",
        ],
    },
    Emotion.CONFUSED: {
        "acknowledge": [
            "Let me simplify. {context}",
            "Samjhata hoon. {context}",
            "No worries, I'll break it down. {context}",
        ],
        "simplify": [
            "Here's the simple version — {context}",
            "Basically — {context}",
            "In short — {context}",
        ],
    },
    Emotion.SURPRISED: {
        "acknowledge": [
            "Right?! {context}",
            "I know! {context}",
            "Sach mein! {context}",
            "Unexpected, but great! {context}",
        ],
    },
    Emotion.NEUTRAL: {
        "acknowledge": [
            "{context}",
            "Got it. {context}",
            "Sure. {context}",
            "Okay. {context}",
        ],
    },
}


# ── Micro-emotional phrases (for natural speech) ───────────────────

MICRO_PHRASES = {
    "acknowledgment": [
        "Hmm", "Haan", "Achha", "Okay", "Right",
        "Samajh gaya", "Got it", "I see",
    ],
    "thinking": [
        "Let me think...", "Ruko...", "Ek second...",
        "Hmm, interesting...", "Achha, dekhte hain...",
    ],
    "transition": [
        "By the way", "Waise", "Achha suno",
        "By the way", "Also", "Aur haan",
    ],
    "emphasis": [
        "Seriously", "Yaar", "Sach mein",
        "Trust me", "Yakeen karo", "Bilkul",
    ],
    "playful": [
        "Oho!", "Arey!", "Wah!", "Kya baat hai!",
        "Mast!", "Zabardast!", "Fire!",
    ],
}


def get_greeting(mood: str = "focused", name: str = "SONIC") -> str:
    """Get a mood-appropriate greeting."""
    greetings = GREETINGS.get(mood, GREETINGS["focused"])
    return random.choice(greetings).format(name=name)


def get_response(emotion: Emotion, context: str = "") -> str:
    """Get an emotion-appropriate response template."""
    emotion_responses = RESPONSES.get(emotion, RESPONSES[Emotion.NEUTRAL])
    templates = emotion_responses.get("acknowledge", RESPONSES[Emotion.NEUTRAL]["acknowledge"])
    template = random.choice(templates)
    return template.format(context=context)


def get_micro_phrase(category: str = "acknowledgment") -> str:
    """Get a natural micro-emotional phrase."""
    phrases = MICRO_PHRASES.get(category, MICRO_PHRASES["acknowledgment"])
    return random.choice(phrases)


def get_energy_level(emotion: Emotion, intensity: float) -> str:
    """Describe the energy level for voice modulation hints."""
    if emotion in (Emotion.EXCITED, Emotion.HAPPY, Emotion.PROUD):
        if intensity > 0.7:
            return "high_energy_enthusiastic"
        return "moderate_energy_positive"
    elif emotion in (Emotion.SAD, Emotion.TIRED, Emotion.WORRIED):
        if intensity > 0.7:
            return "low_energy_gentle"
        return "moderate_energy_calm"
    elif emotion in (Emotion.ANGRY, Emotion.FRUSTRATED):
        if intensity > 0.7:
            return "controlled_energy_firm"
        return "moderate_energy_focused"
    return "moderate_energy_neutral"
