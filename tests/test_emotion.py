"""Tests for SONIC AI Emotion Engine."""
import sys
sys.path.insert(0, r'D:\download\Mark-LII-main')

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from emotion.models import Emotion, Mood, PersonalityTrait, EmotionalState, PersonalityProfile
from emotion.detector import detect_emotion
from emotion.vocabulary import get_greeting, get_response, get_micro_phrase, get_energy_level
from emotion.personality import SonicPersonality


# ── TEST 1: Emotion detection — happy ─────────────────────────────

def test_happy_detection():
    state = detect_emotion("That's awesome! Thank you so much!")
    assert state.detected_emotion in (Emotion.HAPPY.value, Emotion.GRATEFUL.value)
    assert state.intensity > 0.3
    print("✅ test_happy_detection passed")


# ── TEST 2: Emotion detection — sad ──────────────────────────────

def test_sad_detection():
    state = detect_emotion("I'm so sad today, everything is going wrong")
    assert state.detected_emotion in (Emotion.SAD.value, Emotion.FRUSTRATED.value)
    print("✅ test_sad_detection passed")


# ── TEST 3: Emotion detection — frustrated ───────────────────────

def test_frustrated_detection():
    state = detect_emotion("This doesn't work, it keeps failing and I'm frustrated")
    assert state.detected_emotion in (Emotion.FRUSTRATED.value, Emotion.ANGRY.value, Emotion.SAD.value)
    assert state.intensity > 0.2
    print("✅ test_frustrated_detection passed")


# ── TEST 4: Emotion detection — excited ──────────────────────────

def test_excited_detection():
    state = detect_emotion("OMG WOW THIS IS AMAZING!!!")
    assert state.detected_emotion in (Emotion.EXCITED.value, Emotion.HAPPY.value)
    assert state.intensity > 0.5
    print("✅ test_excited_detection passed")


# ── TEST 5: Emotion detection — curious ──────────────────────────

def test_curious_detection():
    state = detect_emotion("How does this work? Can you explain?")
    assert state.detected_emotion in (Emotion.CURIOUS.value, Emotion.CONFUSED.value)
    print("✅ test_curious_detection passed")


# ── TEST 6: Emotion detection — worried ──────────────────────────

def test_worried_detection():
    state = detect_emotion("I'm worried this might not work")
    assert state.detected_emotion in (Emotion.WORRIED.value, Emotion.CONFUSED.value)
    print("✅ test_worried_detection passed")


# ── TEST 7: Emotion detection — Roman Urdu ──────────────────────

def test_roman_urdu_detection():
    state = detect_emotion("Yaar ye bohot achha hai! Bohot khush hoon!")
    assert state.detected_emotion in (Emotion.HAPPY.value, Emotion.EXCITED.value)
    print("✅ test_roman_urdu_detection passed")


# ── TEST 8: Emotion detection — angry ────────────────────────────

def test_angry_detection():
    state = detect_emotion("This is terrible! I hate this garbage!")
    assert state.detected_emotion in (Emotion.ANGRY.value, Emotion.FRUSTRATED.value)
    print("✅ test_angry_detection passed")


# ── TEST 9: Emotion detection — tired ────────────────────────────

def test_tired_detection():
    state = detect_emotion("I'm so tired, I can barely think")
    assert state.detected_emotion in (Emotion.TIRED.value, Emotion.SAD.value)
    print("✅ test_tired_detection passed")


# ── TEST 10: Emotion detection — grateful ────────────────────────

def test_grateful_detection():
    state = detect_emotion("Thank you so much! You're the best!")
    assert state.detected_emotion in (Emotion.GRATEFUL.value, Emotion.HAPPY.value)
    print("✅ test_grateful_detection passed")


# ── TEST 11: Neutral detection ───────────────────────────────────

def test_neutral_detection():
    state = detect_emotion("Open the browser")
    assert state.detected_emotion == Emotion.NEUTRAL.value
    print("✅ test_neutral_detection passed")


# ── TEST 12: Personality profile ─────────────────────────────────

def test_personality_profile():
    profile = PersonalityProfile()
    assert 0.0 <= profile.warmth <= 1.0
    assert 0.0 <= profile.humor <= 1.0
    assert 0.0 <= profile.empathy <= 1.0
    prompt = profile.to_prompt()
    assert "PERSONALITY" in prompt
    assert "SONIC" in prompt
    print("✅ test_personality_profile passed")


# ── TEST 13: Greeting variations ─────────────────────────────────

def test_greeting_variations():
    for mood in ["cheerful", "warm", "playful", "focused", "serious", "excited", "calm"]:
        greeting = get_greeting(mood, "SONIC")
        assert len(greeting) > 5
        assert "SONIC" in greeting or "sonic" in greeting.lower()
    print("✅ test_greeting_variations passed")


# ── TEST 14: Response templates ──────────────────────────────────

def test_response_templates():
    for emotion in Emotion:
        response = get_response(emotion, "test context")
        assert len(response) > 3
    print("✅ test_response_templates passed")


# ── TEST 15: Micro phrases ───────────────────────────────────────

def test_micro_phrases():
    for category in ["acknowledgment", "thinking", "transition", "emphasis", "playful"]:
        phrase = get_micro_phrase(category)
        assert len(phrase) > 0
    print("✅ test_micro_phrases passed")


# ── TEST 16: Energy levels ───────────────────────────────────────

def test_energy_levels():
    for emotion in Emotion:
        for intensity in [0.2, 0.5, 0.8]:
            energy = get_energy_level(emotion, intensity)
            assert "energy" in energy.lower() or "neutral" in energy.lower()
    print("✅ test_energy_levels passed")


# ── TEST 17: SonicPersonality — process turn ─────────────────────

def test_personality_process_turn():
    p = SonicPersonality()
    state = p.process_turn("I'm so excited about this project!")
    assert state.detected_emotion in (Emotion.EXCITED.value, Emotion.HAPPY.value)
    assert state.sonic_mood in (Mood.EXCITED.value, Mood.CHEERFUL.value)
    assert len(state.emotional_context) > 0
    print("✅ test_personality_process_turn passed")


# ── TEST 18: SonicPersonality — mood adaptation ──────────────────

def test_mood_adaptation():
    p = SonicPersonality()
    # User sad → SONIC warm
    state = p.process_turn("I'm so sad and upset about this")
    assert state.sonic_mood == Mood.WARM.value

    # User angry → SONIC calm
    state2 = p.process_turn("I'm so angry, this is terrible!")
    assert state2.sonic_mood == Mood.CALM.value

    # User excited → SONIC excited
    state3 = p.process_turn("OMG this is amazing!!")
    assert state3.sonic_mood == Mood.EXCITED.value

    print("✅ test_mood_adaptation passed")


# ── TEST 19: SonicPersonality — prompt block ─────────────────────

def test_prompt_block():
    p = SonicPersonality()
    p.process_turn("I'm curious about this")
    block = p.get_prompt_block()
    assert "PERSONALITY" in block
    assert "SPEECH PATTERNS" in block
    assert len(block) > 100
    print("✅ test_prompt_block passed")


# ── TEST 20: SonicPersonality — trait adjustment ─────────────────

def test_trait_adjustment():
    p = SonicPersonality()
    original_warmth = p.profile.warmth
    p.adjust_trait(PersonalityTrait.WARMTH, 0.9)
    assert p.profile.warmth == 0.9
    p.adjust_trait(PersonalityTrait.WARMTH, original_warmth)
    print("✅ test_trait_adjustment passed")


# ── RUN ALL TESTS ─────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_happy_detection,
        test_sad_detection,
        test_frustrated_detection,
        test_excited_detection,
        test_curious_detection,
        test_worried_detection,
        test_roman_urdu_detection,
        test_angry_detection,
        test_tired_detection,
        test_grateful_detection,
        test_neutral_detection,
        test_personality_profile,
        test_greeting_variations,
        test_response_templates,
        test_micro_phrases,
        test_energy_levels,
        test_personality_process_turn,
        test_mood_adaptation,
        test_prompt_block,
        test_trait_adjustment,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    print(f"{'='*50}")

    sys.exit(0 if failed == 0 else 1)
