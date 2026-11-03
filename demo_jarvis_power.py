"""SONIC AI — JARVIS POWER DEMO.

Proves all 7 new power modules work end-to-end:
  1. CodeSandbox         — run Python safely
  2. WorkflowEngine      — multi-step automation
  3. KnowledgeGraph      — entities + queries
  4. Predict             — autocomplete + next-action
  5. Notify              — Windows desktop notification
  6. VoicePipeline       — wake word → STT → think → TTS loop
  7. ActionBridge        — route + execute real action modules

Plus a full JarvisBrain demo showing all 12 subsystems online.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def banner(title: str):
    print()
    print("═" * 70)
    print(f"  {title}")
    print("═" * 70)


def demo_code_sandbox():
    banner("DEMO 1: Code Sandbox — safe Python execution")
    from core.code_sandbox import CodeSandbox
    sb = CodeSandbox(timeout_seconds=3)
    samples = [
        ("factorial", "import math\nfor i in range(1, 8): print(f'{i}! = {math.factorial(i)}')"),
        ("JSON pretty", 'import json\nprint(json.dumps({"jarvis": True, "online": True}, indent=2))'),
        ("loop", "s = 0\nfor i in range(1, 101): s += i\nprint(f'sum 1..100 = {s}')"),
        ("dangerous (blocked)", "import os; os.system('echo BAD')"),
        ("timeout (slow)", "import time; time.sleep(10); print('should not reach')"),
    ]
    for name, code in samples:
        r = sb.run(code)
        print(f"  [{'OK' if r.success else 'ERR'}] {name:<20} ({r.duration_ms:.0f}ms)")
        if r.stdout.strip():
            for line in r.stdout.strip().splitlines()[:3]:
                print(f"        │ {line}")
        if r.error_message:
            print(f"        ✗ {r.error_message[:100]}")
    print()


def demo_workflow():
    banner("DEMO 2: Workflow Engine — multi-step automation with retry+parallel")
    from core.workflow_engine import WorkflowEngine
    engine = WorkflowEngine()

    # Sample workflow: research project, then notify
    def executor(action, args):
        if action == "check_battery":
            return {"pct": 67}
        if action == "research_topic":
            return {"summary": "Jarvis AI is a fictional assistant from Iron Man", "sources": 3}
        if action == "notify":
            return {"delivered": True, "message": args.get("message", "")}
        return {"ok": True, "action": action, "args": args}

    steps = [
        {"id": "check", "action": "check_battery"},
        {"id": "research", "action": "research_topic", "depends_on": ["check"]},
        {"id": "log", "action": "literal", "value": "logged", "depends_on": ["research"], "parallel": True},
        {"id": "notify_a", "action": "notify",
         "args": {"message": "Research done"},
         "depends_on": ["research"], "parallel": True},
        {"id": "notify_b", "action": "notify",
         "args": {"message": "Logged successfully"},
         "depends_on": ["log"], "parallel": True},
    ]
    result = engine.run_simple("daily-research", steps, executor)
    print(f"  {result.summary()}")
    for sr in result.step_results:
        marker = "✓" if sr.success else "✗"
        out = str(sr.output)[:80] if sr.output else ""
        print(f"    {marker} {sr.step_id:<10} ({sr.duration_ms:.0f}ms) → {out}")
    print()


def demo_knowledge_graph():
    banner("DEMO 3: Knowledge Graph — entities + relationships")
    from core.knowledge_graph import KnowledgeGraph
    import tempfile
    kg = KnowledgeGraph(db_path=Path(tempfile.mkdtemp()) / "kg.db")

    # Add entities + relationships manually
    kg.add_entity("Ahmad", "person", {"role": "CEO"})
    kg.add_entity("Atherion Labs", "company", {"founded": 2024})
    kg.add_entity("SONIC AI", "project", {"type": "AI assistant"})
    kg.add_entity("Pakistan", "place", {"city": "Lahore"})
    kg.add_entity("Python", "tool", {"version": "3.11"})
    kg.add_relationship("Ahmad", "works_on", "SONIC AI")
    kg.add_relationship("Ahmad", "manages", "Atherion Labs")
    kg.add_relationship("Atherion Labs", "created", "SONIC AI")
    kg.add_relationship("SONIC AI", "uses", "Python")
    kg.add_relationship("Ahmad", "located_in", "Pakistan")

    # Heuristic learning from text
    learned = kg.learn_from_text("Sara works on Jarvis. Jarvis is a project. Jarvis uses Machine Learning.")
    print(f"  Learned {learned} facts from text")

    # Query
    questions = [
        "Who works on SONIC AI?",
        "What uses Python?",
        "Tell me about Ahmad",
        "What's the relationship between Atherion Labs and SONIC AI?",
    ]
    for q in questions:
        qr = kg.query(q)
        print(f"  Q: {q}")
        print(f"     A: {qr.explanation}")
    print()

    # Neighborhood
    n = kg.neighborhood("SONIC AI", depth=2)
    print(f"  SONIC AI neighborhood: {len(n['entities'])} entities, "
          f"{len(n['relationships'])} relationships")
    print()


def demo_predict():
    banner("DEMO 4: Predict — autocomplete + next-action prediction")
    from core.predict import Predictor, NextActionPredictor
    import tempfile

    # Autocomplete
    p = Predictor()
    history = [
        "open chrome and search for python",
        "open chrome and check gmail",
        "open chrome and download something",
        "remind me at 5pm to call mom",
        "remind me at 6pm to wrap up",
        "remind me at 8am to take medicine",
        "play lofi music on youtube",
        "play despacito on youtube",
        "play latest song on youtube",
        "translate this to spanish",
        "translate hello to french",
    ]
    for h in history:
        p.learn(h)
    partials = ["open", "remind me at", "play", "translate"]
    for partial in partials:
        comps = p.complete(partial)
        print(f"  '{partial}' →")
        for c in comps[:3]:
            print(f"    [{c.source:<11} {c.confidence:.2f}] {c.text}")
    print()

    # Next-action prediction
    nap = NextActionPredictor(db_path=Path(tempfile.mkdtemp()) / "predict.db")
    nap.record(["wake", "check_calendar", "weather", "play_music"])
    nap.record(["wake", "check_calendar", "weather", "play_music"])
    nap.record(["wake", "check_calendar", "weather", "play_music"])
    nap.record(["wake", "check_calendar", "email", "summarize"])
    print(f"  Predictor stats: {nap.get_stats()}")
    recent = ["wake", "check_calendar", "weather"]
    nexts = nap.predict_next(recent)
    print(f"  After {recent}, likely next actions:")
    for action, conf in nexts:
        print(f"    [{conf:.2f}] {action}")
    print()


def demo_notify():
    banner("DEMO 5: Notify — Windows desktop notification")
    from core.notify import Notifier
    n = Notifier()
    result = n.toast("JARVIS Online", "All 12 subsystems reporting nominal. Standing by.")
    print(f"  Toast delivered: {result.delivered} (method={result.method})")
    print(f"  Stats: {n.get_stats()}")
    print()


def demo_voice_pipeline():
    banner("DEMO 6: Voice Pipeline — wake word + transcript simulation")
    from core.jarvis_brain import JarvisBrain
    from core.voice_pipeline import VoicePipeline

    brain = JarvisBrain(db_dir=Path(__file__).parent / "_brain_test_demo")
    voice = VoicePipeline(brain)
    voice.start()

    transcript_events = []
    def on_text(t):
        transcript_events.append(t)
    voice.on_transcript(on_text)

    # Simulate user speaking the wake word + a directive
    voice.push_transcript("hey jarvis open chrome")
    voice.push_transcript("set volume to 50")
    voice.push_transcript("remind me at 5pm to wrap up the project")
    voice.push_transcript("goodbye")

    time.sleep(0.5)
    voice.stop()
    print(f"  Transcripts received: {len(transcript_events)}")
    for t in transcript_events:
        print(f"    > {t}")
    print(f"  Voice stats: {voice.get_stats()}")
    print()


def demo_action_bridge():
    banner("DEMO 7: Action Bridge — real action module execution")
    from core.action_bridge import ActionBridge

    bridge = ActionBridge()
    print(f"  Available actions: {len(bridge.get_available_actions())}")
    print(f"  Missing actions:   {len(bridge.get_missing_actions())}")
    missing = bridge.get_missing_actions()
    for action_name, mod_fn in list(missing.items())[:5]:
        print(f"    ✗ {action_name:<22} → {mod_fn}")
    available = bridge.get_available_actions()
    if available:
        print(f"  Sample available (first 5):")
        for action_name, mod_fn in list(available.items())[:5]:
            print(f"    ✓ {action_name:<22} → {mod_fn}")

    # Try executing a couple of actions
    print(f"\n  Testing execution:")
    print(f"    system_status: {bridge.execute('system_status', {})}")
    print(f"    weather:       {bridge.execute('weather', {})}")
    print(f"    time_now:      {bridge.execute('time_now', {})}")
    print(f"    screenshot:    {bridge.execute('screenshot', {})}")
    print(f"    Stats: {bridge.get_stats()}")
    print()


def demo_jarvis_brain_full():
    banner("DEMO 8: Full Jarvis Brain — all subsystems online")
    import tempfile
    from core.jarvis_brain import JarvisBrain

    brain = JarvisBrain(db_dir=Path(tempfile.mkdtemp()) / "brain_full")
    status = brain.status()

    print(f"  Subsystem status:")
    avail_count = 0
    total_count = 0
    for k, v in status.items():
        if k == "timestamp":
            continue
        if isinstance(v, dict) and "available" in v:
            total_count += 1
            if v.get("available"):
                avail_count += 1
            mark = "✓" if v.get("available") else "○"
            note = ""
            if "stats" in v and isinstance(v["stats"], dict):
                # Show key stats
                stats = v["stats"]
                if stats:
                    keys = [k for k in stats.keys() if not k.endswith("_bytes")][:2]
                    if keys:
                        note = " (" + ", ".join(f"{kk}={stats[kk]}" for kk in keys) + ")"
            print(f"    {mark} {k:<14}{note}")
            if "missing_actions" in v and v["missing_actions"]:
                print(f"        missing: {', '.join(v['missing_actions'][:3])}...")

    print(f"\n  Total: {avail_count}/{total_count} subsystems online")

    # End-to-end directive
    print(f"\n  End-to-end directive flow:")
    directives = [
        "what's my cpu usage?",
        "remind me at 6pm to wrap up",
        "tell me about Ahmad",
    ]
    for d in directives:
        result = brain.think(d, execute=True)
        # Truncate response
        resp = result.response[:80].replace("\n", " ")
        print(f"    > {d}")
        print(f"      {result.route.action} → {resp}...")
        print(f"      elapsed: {result.elapsed_ms:.1f}ms, "
              f"memories: {len(result.context_memories)}, "
              f"kg entities: {len(result.knowledge.get('entities', []))}")
    print()


def main():
    print()
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║  SONIC AI — JARVIS POWER DEMO                                     ║")
    print("║  Real universal capabilities, end-to-end                         ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    demo_code_sandbox()
    demo_workflow()
    demo_knowledge_graph()
    demo_predict()
    demo_notify()
    demo_voice_pipeline()
    demo_action_bridge()
    demo_jarvis_brain_full()

    print("═" * 70)
    print("  ALL POWER DEMOS COMPLETE — Universal JARVIS online")
    print("═" * 70)
    print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
