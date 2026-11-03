"""SONIC AI — Ultra-Pro Persona Demo (Legend Edition).

This is the "feel" experience. It walks you through:
  1. Live persona learning (you type, it learns in real-time)
  2. Multi-modal fingerprint visualization
  3. Per-contact persona adaptation demo
  4. Persona drift report
  5. Reply drafting in your voice
  6. Next-message prediction
  7. Mood timeline

Run:  python scripts/persona_demo.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Pretty terminal colors (Windows-friendly)
class C:
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    BLUE = "\033[94m"
    GREY = "\033[90m"
    RED = "\033[91m"
    END = "\033[0m"


def banner(text: str, char: str = "═"):
    width = 70
    print(f"\n{C.CYAN}{char * width}{C.END}")
    print(f"{C.BOLD}{C.CYAN}  {text.center(width - 2)}{C.END}")
    print(f"{C.CYAN}{char * width}{C.END}\n")


def section(text: str):
    print(f"\n{C.BOLD}{C.MAGENTA}▶ {text}{C.END}")
    print(f"{C.GREY}{'─' * 60}{C.END}")


def show_fingerprint(engine):
    fp = engine.fingerprint()
    t = fp["text"]
    e = fp["emotion"]
    c = fp["cultural"]
    v = fp["voice"]
    b = fp["behavior"]

    section("MULTI-MODAL FINGERPRINT")
    print(f"  {C.BOLD}Total samples:{C.END} {fp['samples_total']}")
    print(f"  {C.BOLD}Contacts learned:{C.END} {len(fp['contacts'])}")
    print()
    print(f"  {C.CYAN}━━━ TEXT ━━━{C.END}")
    langs = []
    if t["urdu_roman"] > 0.01: langs.append(f"Roman Urdu {t['urdu_roman']:.0%}")
    if t["english"] > 0.01: langs.append(f"English {t['english']:.0%}")
    if t["hindi"] > 0.01: langs.append(f"Hindi {t['hindi']:.0%}")
    if t["mixed"] > 0.01: langs.append(f"Code-switch {t['mixed']:.0%}")
    print(f"  Languages: {', '.join(langs) or 'insufficient data'}")
    if t["pakistani_urdu"] > 0.01 or t["indian_hindi"] > 0.01:
        flavor = "Pakistani" if t["pakistani_urdu"] > t["indian_hindi"] else "Indian"
        print(f"  Flavor: {flavor} (yaar/bhai/theek patterns)")
    print(f"  Avg length: {t['avg_words']:.0f} words, {t['avg_chars']:.0f} chars")
    print(f"  Punctuation density: ! {t['exclamation_density']:.0%} | "
          f"? {t['question_density']:.0%} | emoji {t['emoji_density']:.0%}")
    if t["top_words"]:
        print(f"  Top words: {', '.join(t['top_words'][:10])}")
    if t["signature_phrases"]:
        print(f"  Signature phrases: {', '.join(t['signature_phrases'][:5])}")
    if t["common_openings"]:
        print(f"  Openings: {', '.join(t['common_openings'][:5])}")
    if t["common_closings"]:
        print(f"  Closings: {', '.join(t['common_closings'][:5])}")

    print()
    print(f"  {C.MAGENTA}━━━ EMOTION ━━━{C.END}")
    if e["samples"] > 0:
        moods = sorted(e["mood_distribution"].items(),
                        key=lambda kv: -kv[1])[:5]
        bar = ""
        for m, c in moods:
            bar += f"  {m} {c} "
        print(f"  Baseline: {e['mood_baseline']}")
        print(f"  Distribution: {bar}")
        print(f"  Emotional range: {e['emotional_range']:.0%}")
        print(f"  Empathy level: {e['empathy_level']:.0%}")
    else:
        print("  No mood data yet")

    print()
    print(f"  {C.YELLOW}━━━ CULTURAL ━━━{C.END}")
    if c["samples"] > 0:
        print(f"  Religious/cultural phrases: {c['religious_phrase_frequency']:.0%}")
        if c["favorite_phrases"]:
            print(f"  Top phrases: {', '.join(c['favorite_phrases'][:8])}")
        topics = []
        if c["references_cricket"]: topics.append(f"cricket ({c['references_cricket']})")
        if c["references_food"]: topics.append(f"food ({c['references_food']})")
        if c["references_family"]: topics.append(f"family ({c['references_family']})")
        if c["references_work"]: topics.append(f"work ({c['references_work']})")
        print(f"  Topics: {', '.join(topics) or 'general'}")
    else:
        print("  No cultural data yet")

    print()
    print(f"  {C.BLUE}━━━ VOICE ━━━{C.END}")
    if v["samples"] > 0:
        print(f"  Voice samples: {v['samples']}")
        print(f"  Avg duration: {v['avg_duration_s']:.0f}s, "
              f"{v['avg_words_per_minute']:.0f} wpm")
        print(f"  Energy: {v['avg_energy']:.2f} (±{v['energy_variance']:.2f})")
        print(f"  Pitch: {v['pitch_avg']:.0f} Hz (±{v['pitch_variance']:.0f})")
        print(f"  Laughter per min: {v['laughter_per_minute']:.1f}")
    else:
        print(f"  {C.GREY}No voice samples yet. Send voice messages to populate.{C.END}")

    print()
    print(f"  {C.GREEN}━━━ BEHAVIOR ━━━{C.END}")
    if b["active_hours"]:
        top = sorted(b["active_hours"].items(),
                      key=lambda kv: -kv[1])[:3]
        print(f"  Most active hours: {', '.join(f'{h}:00 ({c} msgs)' for h, c in top)}")
    if b["avg_session_length_min"] > 0:
        print(f"  Avg session: {b['avg_session_length_min']:.0f} min")
    if b["response_time_by_contact"]:
        print(f"  Per-contact response times:")
        for c, times in list(b["response_time_by_contact"].items())[:5]:
            if times:
                avg = sum(times) / len(times)
                print(f"    {c}: {avg/60:.1f} min avg")

    print()
    print(f"  {C.RED}━━━ DRIFT ━━━{C.END}")
    drift = engine.drift_report()
    if drift.get("status") == "ok":
        print(f"  Tracked: {drift['snapshot_count']} snapshots, "
              f"{drift['days_tracked']/86400:.0f} days")
        print(f"  Drift score: {drift['drift_score']:.0%}")
        if drift["changes"]:
            print(f"  Recent changes: {drift['changes']}")
    else:
        print(f"  {C.GREY}{drift.get('status', 'unknown')} — "
              f"need at least 1 week of data{C.END}")


def interactive_learn(engine):
    """Live persona learning — type messages, watch the persona evolve."""
    banner("LIVE PERSONA LEARNING", "▓")
    print(f"{C.GREY}Type messages as if you were chatting. Empty line to stop.")
    print(f"The persona updates in real-time — watch the fingerprint evolve!{C.END}\n")

    while True:
        try:
            line = input(f"{C.GREEN}  you> {C.END}").strip()
        except EOFError:
            break
        if not line:
            break
        result = engine.observe_text([line])
        # Quick feedback
        fp = engine.fingerprint()
        t = fp["text"]
        n = t["samples"]
        print(f"  {C.GREY}[learned] total samples: {n} | "
              f"avg length: {t['avg_words']:.1f} words | "
              f"latest mood hint: ", end="")
        low = line.lower()
        if any(w in low for w in ("yaar", "bhai", "boss")):
            print(f"{C.CYAN}casual/buddy tone detected{C.END}")
        elif "?" in line:
            print(f"{C.YELLOW}questioning tone{C.END}")
        elif any(w in low for w in ("inshallah", "mashallah", "alhamdulillah")):
            print(f"{C.GREEN}religious/cultural phrase detected{C.END}")
        else:
            print(f"{C.GREY}neutral{C.END}")


def contact_persona_demo(engine):
    """Show how persona adapts per contact."""
    section("PER-CONTACT PERSONA")
    contacts = list(engine.describe().get("contacts", {}).keys())
    if not contacts:
        print(f"  {C.GREY}No contacts learned yet.{C.END}")
        return
    for c in contacts:
        cp = engine.persona_for(c)
        bar_f = _bar(cp.formality, "formality")
        bar_w = _bar(cp.warmth, "warmth    ")
        bar_t = _bar(cp.technicality, "technical")
        print(f"\n  {C.BOLD}{c}{C.END} ({cp.samples} messages)")
        print(f"    {bar_f} {cp.formality:.2f}")
        print(f"    {bar_w} {cp.warmth:.2f}")
        print(f"    {bar_t} {cp.technicality:.2f}")
        print(f"    Length: {cp.avg_length_words:.0f} words avg")
        if cp.common_topics:
            print(f"    Topics: {', '.join(cp.common_topics[:5])}")


def _bar(value, label, width=20):
    filled = int(value * width)
    empty = width - filled
    return f"  {label}: [{('█' * filled) + ('░' * empty)}]"


def drafting_demo(engine, contact):
    """Live reply drafting in user's persona."""
    section(f"PERSONA-DRAFTING for {contact}")
    print(f"{C.GREY}I'll show you a draft of how {engine.user_name or 'the user'} would")
    print(f"reply to a hypothetical incoming message, in their own voice.{C.END}\n")
    test_messages = [
        "kal mil sakte ho project discuss karna hai?",
        "yaar bohot thak gaya aaj, kuch samajh nahi aa raha",
        "thank you so much, tum ne bohot help ki",
    ]
    cp = engine.persona_for(contact)
    for incoming in test_messages:
        print(f"  {C.YELLOW}incoming:{C.END} \"{incoming}\"")
        reply = engine.draft_reply(contact, incoming, thread=[
            {"role": "user", "text": "kya haal hai"},
            {"role": "assistant", "text": "theek hoon yaar"},
        ])
        print(f"  {C.GREEN}drafted:{C.END} \"{reply}\"")
        print()


def predict_demo(engine, contact):
    """Show next-message prediction."""
    section(f"NEXT-MESSAGE PREDICTION for {contact}")
    print(f"{C.GREY}Given a recent thread, predict what user would say next.{C.END}\n")
    thread = [
        {"role": "user", "text": "kal 5 baje milte hain?"},
        {"role": "assistant", "text": "haan chal milte hain"},
        {"role": "user", "text": "kahan chalna hai?"},
    ]
    next_msg = engine.predict_next(contact, thread)
    print(f"  {C.GREY}Recent thread:{C.END}")
    for m in thread:
        print(f"    [{m['role']}] {m['text']}")
    print()
    print(f"  {C.MAGENTA}▶ Predicted next:{C.END} \"{next_msg}\"")
    print()


def main():
    print(f"\n{C.BOLD}{C.CYAN}")
    print("   ███████╗ ██████╗ ███╗   ██╗██╗ ██████╗")
    print("   ██╔════╝██╔═══██╗████╗  ██║██║██╔════╝")
    print("   ███████╗██║   ██║██╔██╗ ██║██║██║     ")
    print("   ██╔════╝██║   ██║██║╚██╗██║██║██║     ")
    print("   ██║     ╚██████╔╝██║ ╚████║██║╚██████╗")
    print("   ╚═╝      ╚═════╝ ╚═╝  ╚═══╝╚═╝ ╚═════╝")
    print(f"{C.END}")
    banner("ULTRA-PRO PERSONA ENGINE — Legend Edition")

    from core.persona_v2 import PersonaEngine
    name = input(f"{C.BOLD}What's your name? {C.END}").strip() or "You"
    engine = PersonaEngine(user_name=name,
                            data_dir=Path.home() / ".sonic" / "memory" / "persona_v2_demo")

    # Try to load existing
    if engine.load() and engine._record.samples_total > 0:
        print(f"\n  {C.GREEN}✓{C.END} Welcome back {name}! "
              f"Loaded persona with {engine._record.samples_total} samples.")
    else:
        print(f"\n  {C.CYAN}Hi {name}! Let's build your ultra-pro persona.{C.END}")
        print(f"  {C.GREY}We'll start with text — voice, behavior, mood tracking")
        print(f"  come automatically as you use SONIC more.{C.END}\n")

    # Always show the current fingerprint
    show_fingerprint(engine)

    # Interactive learning
    if input(f"\n{C.BOLD}Type some messages to teach the persona? (y/n){C.END} ").strip().lower().startswith("y"):
        interactive_learn(engine)
        # Re-show after learning
        print()
        show_fingerprint(engine)

    # Contact persona
    if engine._record.contacts:
        contact_persona_demo(engine)
    else:
        contact = input(f"\n{C.BOLD}Add a contact name to demo per-contact personas: {C.END}").strip()
        if contact:
            print(f"  {C.GREY}(Type a few messages 'to' {contact} — they'll be tagged with that contact){C.END}")
            for _ in range(3):
                try:
                    line = input(f"{C.GREEN}  to {contact}> {C.END}").strip()
                except EOFError:
                    break
                if not line:
                    break
                engine.observe_text([line], contact=contact)
            contact_persona_demo(engine)

            # Drafting demo
            if input(f"\n{C.BOLD}See drafted replies in your persona? (y/n){C.END} ").strip().lower().startswith("y"):
                drafting_demo(engine, contact)
            if input(f"{C.BOLD}See next-message prediction? (y/n){C.END} ").strip().lower().startswith("y"):
                predict_demo(engine, contact)

    print()
    banner("DONE", "─")
    print(f"  Your persona is saved at: {C.GREY}{engine._store_path}{C.END}")
    print(f"  Next time you run this, you'll see your persona's evolution.")
    print(f"  Use {C.BOLD}engine.to_prompt(contact){C.END} in auto-reply to inject this")
    print(f"  persona context into the LLM.")
    print()


if __name__ == "__main__":
    main()
