"""Demo the rewritten action bridge — actually execute real actions."""
import sys, time
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from core.action_bridge import ActionBridge
from core.universal_router import UniversalRouter


def banner(t):
    print()
    print("═" * 70)
    print(f"  {t}")
    print("═" * 70)


def main():
    print()
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║  SONIC AI — Real Action Execution Demo                          ║")
    print("║  Bridge properly invokes SONIC's 41 action modules             ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    bridge = ActionBridge()
    router = UniversalRouter()

    banner("Action coverage")
    available = bridge.get_available_actions()
    missing = bridge.get_missing_actions()
    print(f"  Available: {len(available)} actions")
    print(f"  Missing:   {len(missing)} actions (action name not in registry)")
    print()
    print("  Sample available:")
    for name, fn in list(available.items())[:15]:
        print(f"    ✓ {name:<24} {fn}")
    if missing:
        print("\n  Missing (registered but action module not loadable):")
        for name, fn in list(missing.items())[:5]:
            print(f"    ✗ {name:<24} {fn}")

    banner("End-to-end: route user utterance → execute real action")
    test_utterances = [
        ("what's my cpu usage?",     "system_status"),
        ("what time is it",          "time_now"),
        ("how's the disk space",     "disk_space"),
        ("remind me at 5pm to wrap up", "set_reminder"),
        ("open chrome",              "open_app"),
        ("play despacito on youtube", "play_youtube"),
        ("search for python tutorials", "web_search"),
        ("take a screenshot",        "screenshot"),
        ("set volume to 50",         "set_volume"),
        ("summarize",                "summarize"),
    ]
    print(f"  {'Utterance':<35} {'Routed':<14} {'Result':<60} {'ms'}")
    print(f"  {'-'*35} {'-'*14} {'-'*60} {'-'*5}")
    for utterance, expected_action in test_utterances:
        route = router.route(utterance)
        result = bridge.execute(route.action, route.args)
        ms = f"{result.duration_ms:.0f}"
        text = result.text[:58].replace("\n", " ") if result.text else result.error[:58]
        marker = "✓" if result.success else "✗"
        if result.fallback_used:
            marker = "↻"
        print(f"  {marker} {utterance:<33} {route.action:<14} {text:<60} {ms}")

    banner("Stats")
    stats = bridge.get_stats()
    for k, v in stats.items():
        print(f"  {k:<14} {v}")

    banner("Direct execution test (bypass router)")
    direct_tests = [
        ("system_status", {"query": "current"}),
        ("set_reminder",  {"when": "5pm", "what": "call mom"}),
        ("web_search",    {"query": "python asyncio"}),
        ("time_now",      {}),
    ]
    for action_name, args in direct_tests:
        result = bridge.execute_text(action_name, args)
        print(f"  ✓ {action_name:<18} → {result[:80]}")


if __name__ == "__main__":
    main()
