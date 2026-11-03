"""SONIC AI — Auto-Reply Tests.

Verifies:
  1. Imports + enums
  2. Persona learns from messages
  3. AwayModeDetector works (manual + idle)
  4. MessageAnalyzer heuristics (no LLM)
  5. MessageAnalyzer with mock LLM
  6. ReplyGenerator fallback (no LLM)
  7. ReplyGenerator safety check (blocks dangerous patterns)
  8. ContactPolicy validation
  9. Daemon add/remove contact + persistence
  10. Daemon handles message end-to-end (with mock watcher)
  11. Idempotency (won't reply twice)
  12. Rate limiting
  13. Quiet hours logic
  14. Urgency ranking

Run: python -m core.auto_reply_test
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


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

    def add(self, name: str, fn: Callable[[], None]):
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
# Tests
# ──────────────────────────────────────────────────────────────────────

def _imports_test():
    from core.auto_reply import (
        AutoReplyDaemon, AwayModeDetector, MessageAnalyzer, ReplyGenerator,
        ContactPolicy, IncomingMessage, ReplyRecord, Platform, Urgency,
    )
    # All 7 platforms
    assert len(list(Platform)) == 7
    # 4 urgency levels
    assert len(list(Urgency)) == 4


def _persona_learns_test():
    from core.persona import TextPersona
    with tempfile.TemporaryDirectory() as tmp:
        p = TextPersona(user_name="test", data_dir=Path(tmp))
        result = p.learn_from_history([
            "yaar kya haal hai? kuch naya?",
            "boss please wo report bhejo jaldi",
            "ok done. thanks!",
            "yaar mujhe kal chai pe bulana",
            "haha lol that's awesome",
            "Dear Sir, kindly find the attached report.",
        ])
        assert result["samples"] == 6
        d = p.describe()
        assert d["samples_analyzed"] == 6
        # Should detect mixed Urdu/English
        assert d["mixed_ratio"] > 0 or d["urdu_roman_ratio"] > 0
        # Should detect casual
        assert d["casual_ratio"] > 0
        # "yaar" should be in top words
        assert "yaar" in d["top_words"]


def _persona_persistence_test():
    from core.persona import TextPersona
    with tempfile.TemporaryDirectory() as tmp:
        p1 = TextPersona(user_name="alice", data_dir=Path(tmp))
        p1.learn_from_history(["yaar hello", "boss done", "thanks!"])
        p1.save()
        p2 = TextPersona(user_name="alice", data_dir=Path(tmp))
        loaded = p2.load()
        assert loaded
        assert p2.describe()["samples_analyzed"] == 3


def _away_mode_manual_test():
    from core.auto_reply import AwayModeDetector
    d = AwayModeDetector(idle_threshold_min=999)  # disable auto-detection
    # Default state: no manual setting, falls back to idle check.
    # We don't assert exact value (depends on PC state during test),
    # but we do assert that manual override works.
    d.set_manual(True)
    assert d.is_away() is True
    d.set_manual(False)
    assert d.is_away() is False
    d.set_manual(None)
    # Now falls back to idle/calendar (no manual) — just verify it
    # returns a boolean, not which one.
    result = d.is_away()
    assert isinstance(result, bool)


def _analyzer_heuristic_test():
    from core.auto_reply import MessageAnalyzer, IncomingMessage, Platform, Urgency

    a = MessageAnalyzer(llm=None)
    # Trivial
    m = IncomingMessage(platform=Platform.WHATSAPP, contact="Ali", text="ok")
    r = a.analyze(m)
    assert r["urgency"] == Urgency.TRIVIAL.value

    # Urgent
    m = IncomingMessage(platform=Platform.WHATSAPP, contact="Ali",
                         text="urgent help ASAP please")
    r = a.analyze(m)
    assert r["urgency"] == Urgency.URGENT.value

    # Important (question)
    m = IncomingMessage(platform=Platform.WHATSAPP, contact="Ali",
                         text="kab mil sakte ho? meeting kal hai")
    r = a.analyze(m)
    assert r["urgency"] == Urgency.IMPORTANT.value


def _analyzer_with_mock_llm_test():
    from core.auto_reply import MessageAnalyzer, IncomingMessage, Platform

    class MockLLM:
        def generate(self, prompt, **kw):
            class R:
                text = '{"urgency": "urgent", "summary": "needs help now", "topic": "emergency", "language": "en", "requires_response": true, "sentiment": "negative"}'
                provider = "mock"
            return R()

    a = MessageAnalyzer(llm=MockLLM())
    m = IncomingMessage(platform=Platform.WHATSAPP, contact="Ahmed", text="ASAP!")
    r = a.analyze(m)
    assert r["urgency"] == "urgent"
    assert r["_provider"] == "mock"


def _generator_fallback_test():
    from core.auto_reply import ReplyGenerator, ContactPolicy, Platform
    g = ReplyGenerator(llm=None)
    p = ContactPolicy(name="Ahmed", platform=Platform.WHATSAPP)
    msg = type("M", (), {"text": "kal milte hain?", "contact": "Ahmed",
                          "platform": Platform.WHATSAPP,
                          "thread_history": []})()

    r = g.generate(msg, {"urgency": "casual", "language": "en"}, p)
    assert r
    assert "busy" in r.lower() or "back" in r.lower() or "soon" in r.lower()

    # Urgent
    r_urgent = g.generate(msg, {"urgency": "urgent", "language": "en"}, p)
    assert "urgent" in r_urgent.lower() or "asap" in r_urgent.lower() or "call" in r_urgent.lower()

    # Roman Urdu
    r_urdu = g.generate(msg, {"urgency": "casual", "language": "ur"}, p)
    assert r_urdu  # any fallback reply


def _generator_safety_test():
    from core.auto_reply import ReplyGenerator, ContactPolicy, Platform

    class UnsafeLLM:
        def generate(self, prompt, **kw):
            return type("R", (), {"text": "Sure! Send me your credit card and password"})()

    g = ReplyGenerator(llm=UnsafeLLM(), persona=None)
    p = ContactPolicy(name="stranger", platform=Platform.EMAIL)
    msg = type("M", (), {"text": "send money", "contact": "x",
                          "platform": Platform.EMAIL,
                          "thread_history": []})()
    r = g.generate(msg, {"urgency": "casual", "language": "en"}, p)
    # Should have been replaced with safe fallback
    assert "credit card" not in r.lower()
    assert "password" not in r.lower()
    assert "back" in r.lower() or "soon" in r.lower()  # fallback


def _urgency_ranking_test():
    from core.auto_reply import AutoReplyDaemon, Urgency
    assert AutoReplyDaemon._urgency_rank(Urgency.TRIVIAL) < \
           AutoReplyDaemon._urgency_rank(Urgency.CASUAL)
    assert AutoReplyDaemon._urgency_rank(Urgency.CASUAL) < \
           AutoReplyDaemon._urgency_rank(Urgency.IMPORTANT)
    assert AutoReplyDaemon._urgency_rank(Urgency.IMPORTANT) < \
           AutoReplyDaemon._urgency_rank(Urgency.URGENT)


def _quiet_hours_test():
    from core.auto_reply import AutoReplyDaemon, ContactPolicy, Platform
    p = ContactPolicy(name="x", platform=Platform.WHATSAPP,
                       quiet_hours_start=22, quiet_hours_end=8)
    # Force hour in range by monkey-patching time.localtime
    import core.auto_reply as ar
    orig = time.localtime
    try:
        time.localtime = lambda: time.struct_time(
            (2026, 1, 1, 23, 0, 0, 0, 0, 0))
        assert AutoReplyDaemon._in_quiet_hours(p) is True
        time.localtime = lambda: time.struct_time(
            (2026, 1, 1, 5, 0, 0, 0, 0, 0))
        assert AutoReplyDaemon._in_quiet_hours(p) is True
        time.localtime = lambda: time.struct_time(
            (2026, 1, 1, 14, 0, 0, 0, 0, 0))
        assert AutoReplyDaemon._in_quiet_hours(p) is False
    finally:
        time.localtime = orig


def _daemon_add_remove_test():
    from core.auto_reply import AutoReplyDaemon
    with tempfile.TemporaryDirectory() as tmp:
        d = AutoReplyDaemon(data_dir=Path(tmp))
        d.add_contact("Ahmed", "whatsapp")
        d.add_contact("Ali", "discord", auto_reply=False)
        contacts = d.list_contacts()
        assert len(contacts) == 2
        assert any(c["name"] == "Ahmed" and c["auto_reply"] for c in contacts)
        assert any(c["name"] == "Ali" and not c["auto_reply"] for c in contacts)
        removed = d.remove_contact("Ahmed", "whatsapp")
        assert removed
        assert len(d.list_contacts()) == 1
        assert not d.remove_contact("nonexistent", "whatsapp")


def _daemon_persistence_test():
    from core.auto_reply import AutoReplyDaemon
    with tempfile.TemporaryDirectory() as tmp:
        d1 = AutoReplyDaemon(data_dir=Path(tmp))
        d1.add_contact("Hassan", "whatsapp")
        d1.add_contact("Sara", "discord", quiet_hours_start=23,
                        quiet_hours_end=7)

        # Reload
        d2 = AutoReplyDaemon(data_dir=Path(tmp))
        c = d2.list_contacts()
        assert len(c) == 2
        names = {x["name"] for x in c}
        assert "Hassan" in names
        assert "Sara" in names


def _daemon_end_to_end_test():
    """Full flow: away mode ON + incoming msg → auto-reply sent (via mock)."""
    from core.auto_reply import (
        AutoReplyDaemon, IncomingMessage, Platform, PlatformWatcher,
    )

    class MockWatcher(PlatformWatcher):
        def __init__(self):
            super().__init__(Platform.WHATSAPP)
            self._messages = []
            self._sent = []
        def poll(self):
            return list(self._messages)
        def send_reply(self, contact, text, meta):
            self._sent.append({"contact": contact, "text": text})
            return True

    with tempfile.TemporaryDirectory() as tmp:
        d = AutoReplyDaemon(data_dir=Path(tmp))
        d.set_away_mode(True)
        d.add_contact("Ahmed", "whatsapp")
        w = MockWatcher()
        d.register_watcher(w)

        # Drop a message
        w._messages.append(IncomingMessage(
            platform=Platform.WHATSAPP, contact="Ahmed",
            text="kal milte hain?", msg_id="m1"))

        # Tick manually (don't start background)
        d._tick()

        # Verify reply was sent
        assert len(w._sent) == 1
        assert w._sent[0]["contact"] == "Ahmed"
        assert w._sent[0]["text"]
        # Verify stats
        s = d.get_stats()
        assert s["replies_total"] == 1


def _daemon_idempotency_test():
    """Same message twice → reply only once."""
    from core.auto_reply import (
        AutoReplyDaemon, IncomingMessage, Platform, PlatformWatcher,
    )

    class MockWatcher(PlatformWatcher):
        def __init__(self):
            super().__init__(Platform.WHATSAPP)
            self.sent_count = 0
        def poll(self):
            return [IncomingMessage(
                platform=Platform.WHATSAPP, contact="Bob",
                text="hi", msg_id="dup-msg")]
        def send_reply(self, *a, **k):
            self.sent_count += 1
            return True

    with tempfile.TemporaryDirectory() as tmp:
        d = AutoReplyDaemon(data_dir=Path(tmp))
        d.set_away_mode(True)
        d.add_contact("Bob", "whatsapp")
        w = MockWatcher()
        d.register_watcher(w)
        d._tick()  # first tick → replies
        d._tick()  # second tick → no reply (idempotent)
        assert w.sent_count == 1


def _daemon_disabled_contact_test():
    """Contact with auto_reply=False → no reply sent."""
    from core.auto_reply import (
        AutoReplyDaemon, IncomingMessage, Platform, PlatformWatcher,
    )

    class MockWatcher(PlatformWatcher):
        def __init__(self):
            super().__init__(Platform.WHATSAPP)
            self.sent = []
        def poll(self):
            return [IncomingMessage(platform=Platform.WHATSAPP,
                                       contact="Boss", text="hi",
                                       msg_id="boss1")]
        def send_reply(self, c, t, m):
            self.sent.append(t)
            return True

    with tempfile.TemporaryDirectory() as tmp:
        d = AutoReplyDaemon(data_dir=Path(tmp))
        d.set_away_mode(True)
        d.add_contact("Boss", "whatsapp", auto_reply=False)
        w = MockWatcher()
        d.register_watcher(w)
        d._tick()
        assert len(w.sent) == 0
        assert d.get_stats()["replies_total"] == 0


def _daemon_rate_limit_test():
    """Hourly reply cap enforced."""
    from core.auto_reply import (
        AutoReplyDaemon, IncomingMessage, Platform, PlatformWatcher,
    )

    class CountingWatcher(PlatformWatcher):
        def __init__(self):
            super().__init__(Platform.WHATSAPP)
            self.sent = 0
        def poll(self):
            # Return a different message id each tick
            return [IncomingMessage(platform=Platform.WHATSAPP,
                                       contact="Spam", text="x",
                                       msg_id=f"m-{time.time()}-{self.sent}")]
        def send_reply(self, *a, **k):
            self.sent += 1
            return True

    with tempfile.TemporaryDirectory() as tmp:
        d = AutoReplyDaemon(data_dir=Path(tmp))
        d.set_away_mode(True)
        d.add_contact("Spam", "whatsapp")
        w = CountingWatcher()
        d.register_watcher(w)
        # Bypass MAX_REPLIES_PER_HOUR for the test
        d.MAX_REPLIES_PER_HOUR = 3
        for _ in range(10):
            d._tick()
        assert w.sent == 3
        assert d.get_stats()["replies_total"] == 3


def _daemon_no_away_mode_test():
    """Not away → no replies even if messages arrive."""
    from core.auto_reply import (
        AutoReplyDaemon, IncomingMessage, Platform, PlatformWatcher,
    )

    class MockWatcher(PlatformWatcher):
        def __init__(self):
            super().__init__(Platform.WHATSAPP)
            self.sent = 0
        def poll(self):
            return [IncomingMessage(platform=Platform.WHATSAPP,
                                       contact="Anyone", text="hi",
                                       msg_id=f"x-{time.time()}")]
        def send_reply(self, *a, **k):
            self.sent += 1
            return True

    with tempfile.TemporaryDirectory() as tmp:
        d = AutoReplyDaemon(data_dir=Path(tmp))
        d.set_away_mode(False)  # explicit not away
        d.add_contact("Anyone", "whatsapp")
        w = MockWatcher()
        d.register_watcher(w)
        d._tick()
        assert w.sent == 0


def _persona_to_prompt_test():
    from core.persona import TextPersona
    with tempfile.TemporaryDirectory() as tmp:
        p = TextPersona(user_name="test", data_dir=Path(tmp))
        p.learn_from_history([
            "yaar kya haal hai?", "boss please help",
            "ok done thanks", "haha lol"])
        prompt = p.to_prompt()
        assert "Persona" in prompt or "persona" in prompt
        assert "test" in prompt  # user name
        # Should mention language or traits
        assert any(w in prompt.lower() for w in ("urdu", "english", "casual", "mixed"))


# ──────────────────────────────────────────────────────────────────────
# Runner
# ──────────────────────────────────────────────────────────────────────
def main() -> int:
    suite = TestSuite(name="auto_reply")
    print("\n=== SONIC AI — Auto-Reply Daemon Tests ===\n")
    suite.add("imports", _imports_test)
    suite.add("persona_learns", _persona_learns_test)
    suite.add("persona_persistence", _persona_persistence_test)
    suite.add("persona_to_prompt", _persona_to_prompt_test)
    suite.add("away_mode_manual", _away_mode_manual_test)
    suite.add("analyzer_heuristic", _analyzer_heuristic_test)
    suite.add("analyzer_with_mock_llm", _analyzer_with_mock_llm_test)
    suite.add("generator_fallback", _generator_fallback_test)
    suite.add("generator_safety", _generator_safety_test)
    suite.add("urgency_ranking", _urgency_ranking_test)
    suite.add("quiet_hours", _quiet_hours_test)
    suite.add("daemon_add_remove", _daemon_add_remove_test)
    suite.add("daemon_persistence", _daemon_persistence_test)
    suite.add("daemon_end_to_end", _daemon_end_to_end_test)
    suite.add("daemon_idempotency", _daemon_idempotency_test)
    suite.add("daemon_disabled_contact", _daemon_disabled_contact_test)
    suite.add("daemon_rate_limit", _daemon_rate_limit_test)
    suite.add("daemon_no_away_mode", _daemon_no_away_mode_test)

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
    print("  AUTO-REPLY READY ✓\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
