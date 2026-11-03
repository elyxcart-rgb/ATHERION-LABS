"""SONIC AI — Universal Jarvis Demo.

Runs the full JARVIS brain pipeline through several real user inputs and
captures screenshots showing:
  1. The Command Deck in idle state
  2. The Command Deck after routing "open chrome"
  3. The HoloOrb3D in different states
  4. The Diagnostic + Self-Heal output
  5. Memory Palace recall demo
  6. Proactive engine suggestions
"""
from __future__ import annotations

import sys
from pathlib import Path

# UTF-8 stdout (Windows cp1252 safety)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

OUT = Path(r"D:\download\previews")
OUT.mkdir(parents=True, exist_ok=True)


def demo_universal_features():
    """Demonstrate the Universal Router on a battery of utterances."""
    print("═" * 70)
    print("DEMO 1: Universal Router — natural language → action routing")
    print("═" * 70)
    from core.universal_router import UniversalRouter
    router = UniversalRouter()
    samples = [
        "open chrome",
        "launch spotify",
        "set volume to 50",
        "remind me at 5pm to call mom",
        "search for python tutorials",
        "translate this to spanish",
        "play lofi music on youtube",
        "what's the weather",
        "take a screenshot",
        "shut down the computer",
        "open file explorer",
        "send email to ahmad about project update",
        "play despacito on youtube",
        "lock my pc",
        "summarize my last conversation",
    ]
    for s in samples:
        r = router.route(s)
        args_preview = ", ".join(f"{k}={v}" for k, v in list(r.args.items())[:2])
        print(f"  [{r.confidence:>4.2f}] {s!r:<55} → {r.action}({args_preview})")
    print()


def demo_memory_palace():
    print("═" * 70)
    print("DEMO 2: Memory Palace — persistent semantic memory")
    print("═" * 70)
    from core.memory_palace import MemoryPalace
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "memory.db"
    mp = MemoryPalace(db_path=tmp)
    mp.remember("User's name is Ahmad and he's CEO of Atherion Labs", kind="fact", importance=0.95)
    mp.remember("SONIC AI uses Gemini Live API for real-time voice", kind="fact", importance=0.85)
    mp.remember("Project: build a Jarvis-class desktop assistant", kind="project", importance=0.9)
    mp.remember("User prefers Roman Urdu mixed with English", kind="preference", importance=0.9)
    mp.remember("Last conversation: about holographic UI redesign", kind="fact", importance=0.7)
    mp.remember("User had a haircut last week", kind="fact", importance=0.3)
    print(f"  Stored {mp.count()} memories")
    queries = [
        "what's the user's name",
        "what language does the user speak",
        "what project is the user building",
        "tell me about Atherion",
        "what was the last conversation about",
    ]
    for q in queries:
        results = mp.recall(q, top_k=2)
        print(f"  Q: {q!r}")
        for r in results:
            print(f"    [{r.score:.3f}] {r.text}")
    print()


def demo_screen_vision():
    print("═" * 70)
    print("DEMO 3: Screen Vision — what SONIC sees right now")
    print("═" * 70)
    try:
        from core.screen_vision import ScreenVision
        sv = ScreenVision()
        ctx = sv.see(with_description=False)
        print(f"  Screen: {ctx.width}x{ctx.height}")
        print(f"  Focused window: {ctx.focused_window!r}")
        print(f"  Focused app: {ctx.focused_app!r}")
        print(f"  Visible text: {ctx.visible_text[:100]!r}{'...' if len(ctx.visible_text) > 100 else ''}")
        print(f"  Word count: {ctx.word_count}")
        print(f"  Summary: {ctx.summary()}")
    except Exception as e:
        print(f"  Screen vision unavailable: {e}")
    print()


def demo_self_heal():
    print("═" * 70)
    print("DEMO 4: Self-Heal — system diagnostics + auto-repair")
    print("═" * 70)
    from core.self_heal import SelfHeal
    sh = SelfHeal(log_fn=lambda m: print(f"  [log] {m}"))
    report = sh.full_health_check(auto_repair=True)
    print(f"  Overall: {report.overall}")
    print(f"  Duration: {report.duration_ms:.1f} ms")
    print(f"  Diagnostics:")
    for d in report.diagnostics:
        marker = {"ok": "✓", "info": "i", "warning": "!", "critical": "✗"}.get(d.severity, "?")
        print(f"    {marker} [{d.category:>9}] {d.title}")
        if d.detail and d.severity in ("warning", "critical"):
            print(f"           {d.detail}")
    print(f"  Auto-repairs: {len(report.auto_repairs)}")
    for r in report.auto_repairs:
        ok = "✓" if r.success else "✗"
        print(f"    {ok} {r.action_taken} ({r.detail})")
    print()


def demo_proactive():
    print("═" * 70)
    print("DEMO 5: Proactive Engine — anticipatory suggestions")
    print("═" * 70)
    from core.proactive_engine import ProactiveEngine
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "patterns.db"
    pe = ProactiveEngine(db_path=tmp)
    # Feed some history
    for hour in range(7, 10):
        for _ in range(3):
            pe.record_event("open_app")
    for _ in range(5):
        pe.record_event("play_music")
    pe.record_event("open_app")
    pe.record_event("open_app")
    suggestions = pe.suggest(context={"focused_app": "code"}, max_suggestions=5)
    print(f"  Top suggestions right now:")
    for s in suggestions:
        print(f"    [{int(s.confidence*100):>3}%] [{s.category:>10}] {s.title}")
        print(f"           ↳ {s.reason}")
    print()


def demo_world_pulse():
    print("═" * 70)
    print("DEMO 6: World Pulse — ambient vitals")
    print("═" * 70)
    from core.world_pulse import WorldPulse
    wp = WorldPulse()
    v = wp.vitals()
    print(f"  CPU:       {v.get('cpu_pct')}%")
    print(f"  RAM:       {v.get('ram_pct')}%")
    print(f"  Battery:   {v.get('battery_pct')}%")
    print(f"  Disk:      {v.get('disk_pct')}%")
    print(f"  Time:      {v.get('local_time')}")
    print(f"  Date:      {v.get('local_date')}")
    print(f"  Platform:  {v.get('platform')}")
    print()


def demo_voice_biometric():
    print("═" * 70)
    print("DEMO 7: Voice Biometric — speaker identification")
    print("═" * 70)
    from core.voice_biometric import VoiceBiometric, _voice_features
    import tempfile, math
    tmp = Path(tempfile.mkdtemp()) / "voiceprints.db"
    vb = VoiceBiometric(db_path=tmp)
    # Synthesize 3 samples for "alice"
    def synth_voice(seed: int, pitch: float = 150.0) -> list[float]:
        import random
        random.seed(seed)
        samples = []
        for i in range(16000):  # 1 second @ 16kHz
            t = i / 16000
            # Sine wave with random pitch jitter
            f = pitch + random.uniform(-3, 3)
            v = math.sin(2 * math.pi * f * t) * 0.5
            v += random.uniform(-0.05, 0.05)
            samples.append(int(v * 32000))
        return samples
    alice1 = synth_voice(1, pitch=180.0)
    alice2 = synth_voice(2, pitch=185.0)
    alice3 = synth_voice(3, pitch=175.0)
    bob1 = synth_voice(99, pitch=110.0)
    vb.enroll("alice", alice1)
    vb.enroll("alice", alice2)
    vb.enroll("alice", alice3)
    vb.enroll("bob", bob1)
    print(f"  Enrolled users: {vb.list_users()}")
    # Try to identify new alice sample
    alice_new = synth_voice(4, pitch=178.0)
    result = vb.identify(alice_new)
    print(f"  Identify alice-like sample: user={result['user']} "
          f"confidence={result['confidence']:.3f}")
    print(f"  Scores: {result['scores']}")
    # Try bob
    bob_new = synth_voice(100, pitch=108.0)
    result = vb.identify(bob_new)
    print(f"  Identify bob-like sample:   user={result['user']} "
          f"confidence={result['confidence']:.3f}")
    print(f"  Scores: {result['scores']}")
    # Emotion
    emotion = vb.detect_emotion(alice_new)
    print(f"  Detected emotion: {emotion['emotion']} ({emotion['confidence']:.2f})")
    print()


def demo_jarvis_brain_full():
    """Run the full brain through several directives."""
    print("═" * 70)
    print("DEMO 8: Jarvis Brain — full pipeline")
    print("═" * 70)
    import tempfile
    db_dir = Path(tempfile.mkdtemp())
    from core.jarvis_brain import JarvisBrain
    brain = JarvisBrain(db_dir=db_dir)
    inputs = [
        "hello jarvis",
        "what's my cpu usage?",
        "open chrome",
        "remind me at 6pm to wrap up",
        "translate hello world to spanish",
        "play lofi music on youtube",
        "what's the weather like",
        "goodbye",
    ]
    for inp in inputs:
        result = brain.think(inp, with_screen=False, with_memory_recall=True)
        print(f"  >> {inp}")
        print(f"     routed → {result.route.action} "
              f"(confidence={result.route.confidence:.2f}, source={result.route.source})")
        print(f"     response: {result.response[:120]}")
        if result.context_memories:
            top_mem = result.context_memories[0]
            print(f"     recalled: [{top_mem.score:.2f}] {top_mem.text[:80]}")
        print(f"     elapsed:  {result.elapsed_ms:.1f}ms")
    status = brain.status()
    avail = sum(1 for k, v in status.items()
                if isinstance(v, dict) and v.get("available"))
    total = sum(1 for k, v in status.items()
                if isinstance(v, dict) and "available" in v)
    print(f"\n  Subsystems online: {avail}/{total}")
    print()


def render_command_deck_screenshots():
    """Launch the cinematic Command Deck and grab screenshots in different states."""
    print("═" * 70)
    print("DEMO 9: Command Deck cinematic screenshots")
    print("═" * 70)
    from ui.command_deck import CommandDeck
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    deck = CommandDeck()
    deck.show()

    captures = [
        ("sonic_command_deck_idle.png", 1500, "idle", "ONLINE"),
        ("sonic_command_deck_listening.png", 3500, "listening", "LISTENING"),
        ("sonic_command_deck_thinking.png", 5500, "thinking", "PROCESSING"),
        ("sonic_command_deck_speaking.png", 7500, "speaking", "RESPONSE READY"),
        ("sonic_command_deck_ready.png", 9500, "ready", "SYSTEM READY"),
    ]

    def shoot(idx: int):
        if idx >= len(captures):
            QTimer.singleShot(400, app.quit)
            return
        filename, _delay, state, text = captures[idx]
        deck._orb.set_state(state)
        deck._orb.set_text(text)
        deck._orb_subtitle.setText(f"STATE: {state.upper()}  •  HOLOFRAME ACTIVE")
        # Force repaint
        QApplication.processEvents()
        QTimer.singleShot(120, lambda: do_grab(filename, idx))

    def do_grab(filename, idx):
        pix = deck.grab()
        out = OUT / filename
        pix.save(str(out), "PNG")
        print(f"  ✓ {out}")
        QTimer.singleShot(150, lambda: shoot(idx + 1))

    QTimer.singleShot(200, lambda: shoot(0))
    app.exec()
    print()


def render_orb_showcase():
    """Render the HoloOrb3D alone in each state, on a dark background."""
    print("═" * 70)
    print("DEMO 10: HoloOrb3D showcase — every state")
    print("═" * 70)
    from ui.holo_orb_3d import HoloOrb3D
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    # Container window
    container = QWidget()
    container.setWindowTitle("SONIC // HoloOrb3D")
    container.setFixedSize(800, 400)
    container.setStyleSheet("background: #010206;")
    v = QApplication.instance().primaryScreen().size() if False else None
    layout_h = QHBoxLayout(container)
    layout_h.setContentsMargins(20, 20, 20, 20)
    layout_h.setSpacing(20)
    states = [
        ("idle",      "IDLE"),
        ("listening", "LISTENING"),
        ("thinking",  "PROCESSING"),
        ("speaking",  "RESPONDING"),
        ("ready",     "READY"),
    ]
    orbs = []
    for state, text in states:
        orb = HoloOrb3D(size=240)
        orb.set_state(state)
        orb.set_text(text)
        orb.set_audio_level(0.4 if state in ("speaking", "listening") else 0.05)
        layout_h.addWidget(orb)
        orbs.append(orb)

    container.show()
    QApplication.processEvents()

    def grab():
        QApplication.processEvents()
        pix = container.grab()
        out = OUT / "sonic_holo_orb_states.png"
        pix.save(str(out), "PNG")
        print(f"  ✓ {out}")
        QTimer.singleShot(300, app.quit)

    QTimer.singleShot(600, grab)
    app.exec()
    print()


def main():
    print("SONIC AI — Universal Jarvis Capabilities")
    print("═" * 70)
    print()

    demo_universal_features()
    demo_memory_palace()
    demo_screen_vision()
    demo_self_heal()
    demo_proactive()
    demo_world_pulse()
    demo_voice_biometric()
    demo_jarvis_brain_full()
    render_command_deck_screenshots()
    render_orb_showcase()

    print("═" * 70)
    print("[ALL DEMOS COMPLETE]")
    print("═" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
