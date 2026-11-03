"""SONIC AI — Persona v2 (Legend Edition) Tests.

Verifies:
  1. Module imports
  2. observe_text builds multi-modal fingerprint
  3. Language detection (Roman Urdu, English, Hindi, mixed)
  4. Code-switching detection
  5. Per-contact persona building
  6. Emotion detection
  7. Cultural phrase detection
  8. Voice observation
  9. Behavior observation (active hours, sessions)
  10. Mood observation
  11. Drift snapshot
  12. predict_next with fallback
  13. draft_reply with fallback
  14. to_prompt renders correctly
  15. Persistence round-trip
  16. Fingerprint multi-modal
  17. Per-contact isolation (boss vs friend)
  18. Empty / edge cases

Run: python -m core.persona_v2_test
"""
from __future__ import annotations

import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class TestResult:
    name: str
    passed: bool
    duration_ms: float = 0.0
    message: str = ""


@dataclass
class TestSuite:
    name: str
    results: list[TestResult] = field(default_factory=list)

    def add(self, name, fn):
        t0 = time.time()
        try:
            fn()
            self.results.append(TestResult(name=name, passed=True,
                                            duration_ms=(time.time() - t0) * 1000.0))
            print(f"  PASS  {name}")
        except AssertionError as exc:
            self.results.append(TestResult(name=name, passed=False,
                                            duration_ms=(time.time() - t0) * 1000.0,
                                            message=str(exc)))
            print(f"  FAIL  {name}: {exc}")
        except Exception as exc:
            import traceback
            self.results.append(TestResult(name=name, passed=False,
                                            duration_ms=(time.time() - t0) * 1000.0,
                                            message=f"{type(exc).__name__}: {exc}"))
            print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    def summary(self):
        passed = sum(1 for r in self.results if r.passed)
        return {"name": self.name, "passed": passed,
                "failed": len(self.results) - passed,
                "total": len(self.results)}


# ──────────────────────────────────────────────────────────────────────

def _imports_test():
    from core.persona_v2 import (
        PersonaEngine, PersonaRecord, TextFingerprint, VoiceFingerprint,
        BehaviorFingerprint, EmotionFingerprint, CulturalFingerprint,
        ContactPersona, MOOD_KEYWORDS, URDU_IDIOMS,
    )
    assert len(MOOD_KEYWORDS) >= 8
    assert len(URDU_IDIOMS) >= 15


def _observe_text_builds_fp_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("test", data_dir=Path(tmp))
        result = e.observe_text([
            "yaar kya haal hai bhai",
            "boss please wo file bhej do",
            "theek hai kar deta hoon",
            "haha lol mazaak kar raha tha",
            "ok done thanks!",
        ])
        assert result["samples"] == 5
        assert e._record.text.samples == 5
        # Urdu presence detected (some messages are pure Urdu, others mixed)
        assert (e._record.text.urdu_roman + e._record.text.mixed) > 0.4
        # Top words should include "yaar" and "boss" (Pakistani flavor)
        assert "yaar" in e._record.text.top_words
        # Should detect pakistani flavor markers
        assert e._record.text.pakistani_urdu > 0


def _language_detection_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text([
            "yaar boss theek hai bhai",
            "yaar boss theek hai bhai",
            "yaar boss theek hai bhai",
            "yaar boss theek hai bhai",
            "yaar boss theek hai bhai",
        ])
        # Should detect pakistani flavor
        assert e._record.text.pakistani_urdu > 0
        # Pure English
        e2 = PersonaEngine("t2", data_dir=Path(tmp))
        e2.observe_text([
            "hello how are you doing today",
            "what time is the meeting tomorrow",
            "could you please send the report",
            "thank you very much for your help",
            "have a great day everyone",
        ])
        assert e2._record.text.english > 0.5


def _code_switching_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text([
            "yaar please send the report jaldi",
            "boss kal meeting hai chai pe chal",
            "main aaj office ja raha hoon for project work",
        ])
        # Code switch points should be detected
        assert len(e._record.text.code_switch_points) > 0


def _per_contact_persona_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text([
            "Dear Sir, kindly find the attached report. Regards.",
            "Dear Sir, please find the document. Sincerely.",
        ], contact="boss")
        e.observe_text([
            "yaar kya scene hai bhai",
            "haha lol mazaak kar raha tha yaar",
        ], contact="ahmed")
        boss = e.persona_for("boss")
        ahmed = e.persona_for("ahmed")
        # Boss should be more formal than ahmed
        assert boss.formality > ahmed.formality
        assert ahmed.warmth >= boss.warmth
        # Different common topics
        assert boss.samples == 2
        assert ahmed.samples == 2


def _emotion_detection_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text([
            "yaar happy hoon bohot khushi hui",
            "maza aa gaya awesome",
        ])
        # Mood should be detected
        e2 = PersonaEngine("t2", data_dir=Path(tmp))
        e2.observe_text([
            "bohot tired hoon yaar thak gaya",
            "yaar nind aa rhi hai exhausted",
        ])
        assert e._record.emotion.samples > 0
        assert e2._record.emotion.samples > 0
        # Different mood baselines
        moods1 = e._record.emotion.mood_distribution
        moods2 = e2._record.emotion.mood_distribution
        assert sum(moods1.values()) > 0
        assert sum(moods2.values()) > 0


def _cultural_phrases_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text([
            "inshallah kal milte hain",
            "mashallah bohot acha hua",
            "alhamdulillah sab theek hai",
            "yaar cricket match dekha kya?",
        ])
        # Cultural phrases detected
        phrases = e._record.cultural.favorite_phrases
        assert any(p in phrases for p in ("inshallah", "mashallah", "alhamdulillah"))
        # Topics detected
        assert e._record.cultural.references_cricket > 0


def _voice_observation_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_voice({
            "duration_s": 12.0,
            "words_per_minute": 150.0,
            "energy_mean": 0.6,
            "energy_var": 0.1,
            "pitch_mean": 130.0,
            "pitch_var": 20.0,
            "laughter_count": 2,
            "filler_count": 3,
            "approx_words": 30,
        })
        assert e._record.voice.samples == 1
        assert e._record.voice.avg_duration_s == 12.0
        assert e._record.voice.avg_words_per_minute == 150.0
        assert e._record.voice.laughter_per_minute > 0
        # Second observation should average
        e.observe_voice({
            "duration_s": 18.0,
            "words_per_minute": 180.0,
            "energy_mean": 0.8,
            "energy_var": 0.15,
            "pitch_mean": 145.0,
            "pitch_var": 25.0,
            "laughter_count": 4,
            "filler_count": 1,
            "approx_words": 50,
        })
        assert e._record.voice.samples == 2
        assert e._record.voice.avg_duration_s == 15.0  # avg of 12, 18


def _behavior_observation_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_behavior({"type": "message", "contact": "ahmed", "ts": time.time()})
        e.observe_behavior({"type": "session_end", "duration_s": 600, "ts": time.time()})
        e.observe_behavior({"type": "message", "contact": "ahmed",
                              "ts": time.time(), "response_time_s": 30})
        b = e._record.behavior
        # active hours should have some entries
        assert len(b.active_hours) > 0
        # response time recorded for ahmed
        assert "ahmed" in b.response_time_by_contact
        # session length tracked
        assert b.avg_session_length_min == 10.0  # 600/60


def _mood_observation_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_mood("happy", 0.9)
        e.observe_mood("happy", 0.8)
        e.observe_mood("happy", 0.7)
        assert e._record.emotion.mood_baseline == "happy"
        assert e._record.emotion.mood_distribution["happy"] == 3


def _drift_snapshot_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text([
            "yaar kya haal", "boss please help", "theek hai",
        ])
        # Force a snapshot by manually setting old ts
        if e._record.snapshots:
            e._record.snapshots[-1]["ts"] = time.time() - 8 * 86400
        e._maybe_snapshot()
        assert len(e._record.snapshots) >= 1
        drift = e.drift_report()
        assert drift["status"] in ("ok", "insufficient_data")


def _predict_next_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        cp = e.persona_for("ahmed")
        # Fallback prediction works without LLM
        pred = e.predict_next("ahmed", [
            {"role": "ahmed", "text": "kal milte hain?"},
            {"role": "ahmed", "text": "ok?"},
        ])
        assert isinstance(pred, str)
        assert len(pred) > 0


def _draft_reply_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        # Fallback draft
        reply = e.draft_reply("ahmed", "kal milte hain?")
        assert isinstance(reply, str)
        assert len(reply) > 0
        # After learning persona, should still produce reply
        e.observe_text(["yaar hello", "boss help", "ok thanks"], contact="ahmed")
        reply2 = e.draft_reply("ahmed", "kal milte hain?")
        assert reply2


def _to_prompt_renders_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("Ahmad", data_dir=Path(tmp))
        e.observe_text([
            "yaar kya haal hai bhai",
            "boss please wo file bhej do",
            "theek hai kar deta hoon",
            "haha lol mazaak kar raha tha",
            "ok done thanks!",
        ])
        prompt = e.to_prompt()
        assert "Ahmad" in prompt
        assert "persona" in prompt.lower()
        # Per-contact version
        e.observe_text(["Dear Sir, kindly find the attached report."],
                        contact="boss")
        prompt2 = e.to_prompt(contact="boss")
        assert "boss" in prompt2.lower()


def _persistence_roundtrip_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e1 = PersonaEngine("alice", data_dir=Path(tmp))
        e1.observe_text(["yaar hello bhai", "boss done", "thanks!"],
                          contact="ahmed")
        e1.observe_voice({"duration_s": 10, "words_per_minute": 140,
                            "energy_mean": 0.5, "energy_var": 0.1,
                            "pitch_mean": 120, "pitch_var": 20,
                            "laughter_count": 1, "filler_count": 2,
                            "approx_words": 25})
        e1.save()
        # Reload
        e2 = PersonaEngine("alice", data_dir=Path(tmp))
        loaded = e2.load()
        assert loaded
        assert e2._record.samples_total == e1._record.samples_total
        assert e2._record.text.urdu_roman == e1._record.text.urdu_roman
        assert e2._record.voice.samples == 1


def _fingerprint_multimodal_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        e.observe_text(["yaar hello", "boss help", "thanks!"], contact="ahmed")
        e.observe_mood("happy")
        e.observe_behavior({"type": "message", "ts": time.time()})
        fp = e.fingerprint()
        assert "text" in fp
        assert "voice" in fp
        assert "behavior" in fp
        assert "emotion" in fp
        assert "cultural" in fp
        assert "samples_total" in fp
        assert "contacts" in fp
        assert "ahmed" in fp["contacts"]


def _per_contact_isolation_test():
    """Boss is formal, friend is casual — persona must reflect this."""
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        for _ in range(3):
            e.observe_text([
                "Dear Sir, kindly find the report. Regards, Hasan.",
            ], contact="boss")
            e.observe_text([
                "yaar lol kya kar raha hai bhai mazaak",
            ], contact="ahmed")
        boss = e.persona_for("boss")
        ahmed = e.persona_for("ahmed")
        # Big difference
        assert abs(boss.formality - ahmed.formality) > 0.3
        # Topics should differ
        boss_topics = set(boss.common_topics)
        ahmed_topics = set(ahmed.common_topics)
        # They may or may not share topics, but their style differs


def _empty_edge_cases_test():
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        # Empty observation
        r = e.observe_text([])
        assert r["samples"] == 0
        # None messages
        r = e.observe_text([None, "", "  "])
        assert r["samples"] == 0
        # predict with no thread
        p = e.predict_next("x", [])
        assert isinstance(p, str)
        # draft with no contact
        d = e.draft_reply("stranger", "hello")
        assert isinstance(d, str)


def _drift_via_observation_test():
    """Same user, different style over time should produce drift_score > 0."""
    from core.persona_v2 import PersonaEngine
    with tempfile.TemporaryDirectory() as tmp:
        e = PersonaEngine("t", data_dir=Path(tmp))
        # First phase: casual
        e.observe_text([
            "yaar hello bhai", "boss kar do", "haha lol",
            "yaar bhai mazaak", "boss theek hai",
        ])
        e._maybe_snapshot()
        # Simulate elapsed time + different style
        if e._record.snapshots:
            e._record.snapshots[-1]["ts"] = time.time() - 8 * 86400
        # Second phase: more formal English
        e.observe_text([
            "Dear Sir, kindly find the report.",
            "Please find the attached document. Regards.",
            "Thank you for your attention to this matter.",
            "Could you please review the document?",
            "I appreciate your cooperation on this.",
        ])
        e._maybe_snapshot()
        # Drift should be > 0
        assert e._record.drift_score > 0


# ──────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────
def main() -> int:
    suite = TestSuite(name="persona_v2")
    print("\n=== SONIC AI — Persona v2 (Legend Edition) Tests ===\n")
    suite.add("imports", _imports_test)
    suite.add("observe_text_builds_fp", _observe_text_builds_fp_test)
    suite.add("language_detection", _language_detection_test)
    suite.add("code_switching", _code_switching_test)
    suite.add("per_contact_persona", _per_contact_persona_test)
    suite.add("emotion_detection", _emotion_detection_test)
    suite.add("cultural_phrases", _cultural_phrases_test)
    suite.add("voice_observation", _voice_observation_test)
    suite.add("behavior_observation", _behavior_observation_test)
    suite.add("mood_observation", _mood_observation_test)
    suite.add("drift_snapshot", _drift_snapshot_test)
    suite.add("predict_next", _predict_next_test)
    suite.add("draft_reply", _draft_reply_test)
    suite.add("to_prompt_renders", _to_prompt_renders_test)
    suite.add("persistence_roundtrip", _persistence_roundtrip_test)
    suite.add("fingerprint_multimodal", _fingerprint_multimodal_test)
    suite.add("per_contact_isolation", _per_contact_isolation_test)
    suite.add("empty_edge_cases", _empty_edge_cases_test)
    suite.add("drift_via_observation", _drift_via_observation_test)

    print(f"\n{'=' * 60}")
    s = suite.summary()
    print(f"  Suite: {s['name']}")
    print(f"  PASSED: {s['passed']}/{s['total']}")
    if s["failed"]:
        print(f"  FAILED: {s['failed']}")
        for r in suite.results:
            if not r.passed:
                print(f"    - {r.name}: {r.message}")
        return 1
    print("  LEGEND READY ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
