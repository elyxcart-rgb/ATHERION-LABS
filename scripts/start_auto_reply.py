"""SONIC AI — Auto-Reply Startup Helper.

End-user CLI that:
  1. Loads LLM chain (Gemini → OpenAI → Local)
  2. Loads or learns user persona from sample messages
  3. Configures contacts and platforms
  4. Starts the AutoReplyDaemon
  5. Prints live stats every 30s

Usage:
    python scripts/start_auto_reply.py
    python scripts/start_auto_reply.py --inbox D:/whatsapp_inbox.jsonl
    python scripts/start_auto_reply.py --away         # start in away mode immediately
    python scripts/start_auto_reply.py --learn < file_with_past_messages.txt

The simplest setup uses a FileWatcher (no real platform needed).
For real WhatsApp Web / Discord, configure the appropriate watcher.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Allow running from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_llm():
    """Load the project's LLM provider chain (Gemini first)."""
    try:
        from core.providers import get_default_chain
        chain = get_default_chain()
        available = chain.available_providers()
        if available:
            return chain
    except Exception as e:
        print(f"[WARN] LLM chain unavailable: {e}")
    return None


def learn_persona_from_file(daemon, file_path: Path) -> int:
    """Read past messages from a file (one per line) and learn persona."""
    if not file_path.exists():
        print(f"[ERR] File not found: {file_path}")
        return 0
    messages = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            messages.append(line)
    if not messages:
        print("[WARN] No messages found in file")
        return 0
    result = daemon.learn_persona_from_history(messages)
    print(f"[OK] Learned persona from {result['samples']} messages "
          f"(total: {result.get('total_samples', 0)})")
    return result["samples"]


def learn_persona_from_stdin(daemon) -> int:
    """Read messages from stdin (interactive prompt)."""
    print("Enter past messages (one per line), blank line to finish:")
    messages = []
    while True:
        try:
            line = input("  > ").strip()
        except EOFError:
            break
        if not line:
            break
        messages.append(line)
    if not messages:
        return 0
    result = daemon.learn_persona_from_history(messages)
    print(f"[OK] Learned persona from {result['samples']} messages")
    return result["samples"]


def show_persona(daemon):
    desc = daemon._persona.describe()
    if desc["samples_analyzed"] == 0:
        print("[INFO] No persona learned yet")
        return
    print("\n=== Persona ===")
    print(f"  Samples analyzed: {desc['samples_analyzed']}")
    print(f"  Languages: urdu_roman={desc['urdu_roman_ratio']:.0%}  "
          f"english={desc['english_ratio']:.0%}  "
          f"hindi={desc['hindi_ratio']:.0%}  "
          f"mixed={desc['mixed_ratio']:.0%}")
    print(f"  Tone: casual={desc['casual_ratio']:.0%}  "
          f"formal={desc['formal_ratio']:.0%}")
    print(f"  Length: {desc['avg_length_words']:.0f} words / "
          f"{desc['avg_length_chars']:.0f} chars avg")
    if desc["top_words"]:
        print(f"  Top words: {', '.join(desc['top_words'][:10])}")
    if desc["detected_traits"]:
        print(f"  Traits: {', '.join(desc['detected_traits'])}")
    print()


def prompt_for_contacts(daemon):
    """Interactively add contacts."""
    print("\n=== Contacts ===")
    print("Add contacts who should receive auto-replies.")
    print("Format: name,platform[,auto_reply=true/false]")
    print("Platforms: whatsapp, discord, telegram, sms, email, slack")
    print("Press Enter with empty name to finish.")
    while True:
        try:
            raw = input("  Add contact (name,platform[,auto_reply]): ").strip()
        except EOFError:
            break
        if not raw:
            break
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < 2:
            print("  [WARN] Need at least name and platform")
            continue
        name = parts[0]
        platform = parts[1].lower()
        auto_reply = True
        if len(parts) >= 3:
            auto_reply = parts[2].lower() in ("true", "1", "yes", "y")
        try:
            daemon.add_contact(name, platform, auto_reply=auto_reply)
            print(f"  [OK] Added {name} ({platform})")
        except Exception as e:
            print(f"  [ERR] {e}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="SONIC Auto-Reply Daemon starter",
    )
    parser.add_argument(
        "--inbox", type=Path,
        help="Path to inbox JSONL file (for FileWatcher / testing)",
        default=Path.home() / ".sonic" / "auto_reply_inbox.jsonl",
    )
    parser.add_argument(
        "--discord-token",
        help="Discord bot token (or set DISCORD_BOT_TOKEN env var)",
    )
    parser.add_argument(
        "--learn", type=Path,
        help="File with past messages to learn persona from",
    )
    parser.add_argument(
        "--away", action="store_true",
        help="Start in away mode (auto-replies enabled immediately)",
    )
    parser.add_argument(
        "--interactive", action="store_true",
        help="Prompt for contacts and persona interactively",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Run without LLM (uses heuristic fallback only)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
    )
    parser.add_argument(
        "--data-dir", type=Path,
        default=Path.home() / ".sonic" / "auto_reply",
        help="Where to store config + persona + history",
    )
    args = parser.parse_args()

    setup_logging(args.verbose)
    print("=== SONIC AI — Auto-Reply Startup ===\n")

    # 1. LLM
    llm = None if args.no_llm else load_llm()
    if llm:
        print(f"[OK] LLM loaded: providers available")
    else:
        print("[WARN] No LLM — will use heuristic fallback replies")

    # 2. Daemon
    from core.auto_reply import AutoReplyDaemon
    daemon = AutoReplyDaemon(data_dir=args.data_dir, llm=llm)
    print(f"[OK] Daemon ready (data: {args.data_dir})")

    # 3. Persona
    if args.learn:
        learn_persona_from_file(daemon, args.learn)
    elif args.interactive:
        learn_persona_from_stdin(daemon)
    else:
        # Try to load saved persona
        if daemon._persona.load():
            d = daemon._persona.describe()
            if d.get("samples_analyzed", 0) > 0:
                print(f"[OK] Loaded persona ({d['samples_analyzed']} samples)")
    show_persona(daemon)

    # 4. Watchers
    from core.auto_reply import Platform
    from core.auto_reply_watchers import (
        FileWatcher, DiscordWebhookWatcher, CallbackWatcher,
    )

    # Always set up file watcher (good fallback + dev tool)
    file_path = args.inbox
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text("")
    sent_path = file_path.with_name(file_path.stem + "_sent" + file_path.suffix)
    daemon.register_watcher(FileWatcher(
        inbox_path=str(file_path),
        sent_path=str(sent_path),
    ))
    print(f"[OK] FileWatcher active (inbox: {file_path})")
    print(f"      Drop messages into this file to trigger auto-replies.")
    print(f"      Replies will be appended to: {sent_path}")

    # Optional Discord
    discord_token = args.discord_token
    if discord_token:
        daemon.register_watcher(DiscordWebhookWatcher(token=discord_token))
        print(f"[OK] Discord watcher registered")

    # 5. Contacts
    if args.interactive:
        prompt_for_contacts(daemon)
    else:
        # Add a default contact if file watcher is in use
        daemon.add_contact("file-user", "whatsapp")
        print(f"[OK] Default contact 'file-user' registered")

    # 6. Away mode
    if args.away:
        daemon.set_away_mode(True)
        print("[OK] Away mode ON — auto-replies active")
    else:
        daemon.set_away_mode(False)
        print("[OK] Away mode OFF — use set_away_mode(True) to enable")

    # 7. Start
    daemon.start()
    print("\n[OK] Auto-Reply Daemon running. Press Ctrl+C to stop.\n")

    # 8. Live stats
    last_stats = {}
    try:
        while True:
            time.sleep(30)
            stats = daemon.get_stats()
            changed = {k: v for k, v in stats.items() if last_stats.get(k) != v}
            if changed:
                print(f"\n[STATS] away={stats['is_away']}  "
                      f"contacts={stats['contacts_count']}  "
                      f"replies_total={stats['replies_total']}  "
                      f"last_hour={stats['replies_last_hour']}")
                for r in stats.get("recent_replies", [])[-3:]:
                    print(f"  → {r['contact']} ({r['urgency']}): "
                          f"\"{r['reply_preview']}\"")
                last_stats = stats
    except KeyboardInterrupt:
        print("\n[STOP] Stopping daemon...")
        daemon.stop()
        print("[OK] Stopped cleanly.")


if __name__ == "__main__":
    main()
