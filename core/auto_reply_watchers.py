"""SONIC AI — Auto-Reply Platform Watchers.

Concrete watcher implementations that the AutoReplyDaemon polls:

  FileWatcher         — reads messages from a JSON file (for testing / dev)
  WhatsAppWatcher     — Playwright web session (assumes logged-in chrome)
  DiscordBotWatcher   — discord.py Bot (requires BOT_TOKEN)
  DiscordWebhookWatcher — Discord Bot REST API (webhook-style, simpler)

Each watcher implements:
  .poll()           → list[IncomingMessage]
  .send_reply(c, t) → bool
  .close()          → cleanup (optional)

Public surface:
  FileWatcher(json_path)
  WhatsAppWatcher(page=None, session_path=None)
  DiscordBotWatcher(token)
  DiscordWebhookWatcher(webhook_url, bot_token, channel_id)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from .auto_reply import IncomingMessage, Platform, PlatformWatcher


logger = logging.getLogger("sonic.auto_reply_watchers")


# ──────────────────────────────────────────────────────────────────────
# 1. File-based watcher (for dev / testing)
# ──────────────────────────────────────────────────────────────────────
class FileWatcher(PlatformWatcher):
    """Reads incoming messages from a JSON-lines file.

    File format (one JSON object per line):
        {"msg_id": "...", "contact": "Ahmed",
         "text": "...", "thread": [...optional...],
         "received_at": <unix_ts>}

    Replies are appended to a separate JSONL file so the daemon can verify.

    Useful for:
      - Testing auto-reply without a real platform
      - Triggering replies from external scripts / webhooks
      - Replaying historical conversations for persona learning
    """

    def __init__(self, inbox_path: str, sent_path: Optional[str] = None,
                 mark_read: bool = True):
        super().__init__(Platform.WHATSAPP)  # generic; platform-agnostic
        self._inbox = Path(inbox_path)
        self._sent = Path(sent_path) if sent_path else None
        self._inbox.parent.mkdir(parents=True, exist_ok=True)
        if not self._inbox.exists():
            self._inbox.write_text("")
        if self._sent and not self._sent.exists():
            self._sent.write_text("")
        self._mark_read = mark_read
        self._processed_ids: set[str] = set()
        self._lock = threading.Lock()

    def poll(self) -> list[IncomingMessage]:
        msgs: list[IncomingMessage] = []
        with self._lock:
            try:
                text = self._inbox.read_text(encoding="utf-8")
                lines = [ln for ln in text.splitlines() if ln.strip()]
                remaining = []
                for line in lines:
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    msg_id = data.get("msg_id") or f"file-{time.time()}-{len(msgs)}"
                    if msg_id in self._processed_ids:
                        remaining.append(line)
                        continue
                    msgs.append(IncomingMessage(
                        msg_id=msg_id,
                        platform=Platform(data.get("platform", "whatsapp").lower()),
                        contact=data.get("contact", "unknown"),
                        text=data.get("text", ""),
                        received_at=data.get("received_at", time.time()),
                        thread_history=data.get("thread", []),
                        metadata=data.get("metadata", {}),
                    ))
                    self._processed_ids.add(msg_id)
                    if not self._mark_read:
                        remaining.append(line)
                if self._mark_read:
                    self._inbox.write_text("")
                else:
                    self._inbox.write_text("\n".join(remaining) + ("\n" if remaining else ""))
            except Exception:
                logger.exception("FileWatcher poll failed")
        return msgs

    def send_reply(self, contact: str, text: str, meta: dict) -> bool:
        if not self._sent:
            logger.debug("FileWatcher no sent_path configured")
            return True  # silently ack
        try:
            entry = {
                "contact": contact,
                "text": text,
                "ts": time.time(),
            }
            with self._lock:
                with self._sent.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            return True
        except Exception:
            logger.exception("FileWatcher send_reply failed")
            return False


# ──────────────────────────────────────────────────────────────────────
# 2. WhatsApp Web Watcher (Playwright)
# ──────────────────────────────────────────────────────────────────────
class WhatsAppWatcher(PlatformWatcher):
    """Auto-reply via WhatsApp Web using Playwright.

    Requires:
      - playwright installed
      - chromium browser (installed via `playwright install chromium`)
      - An active WhatsApp Web session (QR scan already done in browser)

    The watcher keeps an open page and polls the DOM for unread chats.
    When a message matches a watched contact, it's converted to
    IncomingMessage and returned. send_reply uses the page's input box.
    """

    def __init__(self, page=None, headless: bool = False,
                 poll_dom_only: bool = True,
                 session_storage_state: Optional[Path] = None):
        super().__init__(Platform.WHATSAPP)
        self._page = page
        self._owns_page = page is None
        self._headless = headless
        self._poll_dom_only = poll_dom_only
        self._storage = session_storage_state
        self._lock = threading.RLock()
        self._sent_ids: set[str] = set()
        self._last_poll_at = 0.0

    def _ensure_page(self):
        """Lazy-load Playwright + a page connected to web.whatsapp.com."""
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError:
            raise RuntimeError("playwright not installed (pip install playwright)")
        if not hasattr(self, "_pw"):
            self._pw = sync_playwright().start()
            launch_kwargs = {"headless": self._headless}
            if self._storage and self._storage.exists():
                launch_kwargs["storage_state"] = str(self._storage)
            browser = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(Path.home() / ".sonic" / "whatsapp_session"),
                **launch_kwargs,
            ) if not self._headless else self._pw.chromium.launch(**launch_kwargs)
            if hasattr(browser, "pages") and browser.pages:
                self._page = browser.pages[0]
            else:
                self._page = browser.new_page()
            if not self._headless and "web.whatsapp.com" not in (self._page.url or ""):
                self._page.goto("https://web.whatsapp.com/")
        return self._page

    def poll(self) -> list[IncomingMessage]:
        """Poll WhatsApp Web DOM for new messages in watched chats."""
        with self._lock:
            self._last_poll_at = time.time()
        try:
            page = self._ensure_page()
        except Exception as e:
            logger.debug(f"WhatsApp poll: {e}")
            return []
        try:
            return self._poll_dom(page)
        except Exception:
            logger.exception("WhatsApp DOM poll failed")
            return []

    def _poll_dom(self, page) -> list[IncomingMessage]:
        """Read the chat list and recent messages via JS."""
        results: list[IncomingMessage] = []
        try:
            data = page.evaluate("""() => {
                // Find chat pane items with unread badges
                const chats = document.querySelectorAll('[data-testid="cell-frame-container"]');
                const out = [];
                for (const chat of chats) {
                    const nameEl = chat.querySelector('[data-testid="cell-frame-title"] span');
                    const badgeEl = chat.querySelector('[data-testid="icon-unread-count"]');
                    const lastMsgEl = chat.querySelector('[data-testid="last-msg-status"]') ||
                                       chat.querySelector('.matched-text');
                    if (nameEl && badgeEl) {
                        out.push({
                            contact: nameEl.textContent || 'unknown',
                            unread_count: parseInt(badgeEl.textContent || '1', 10),
                            last_msg: lastMsgEl ? lastMsgEl.textContent : '',
                        });
                    }
                }
                return out;
            }""")
            if not isinstance(data, list):
                return []
            for entry in data:
                contact = entry.get("contact", "unknown")
                msg_id = f"wa-{contact}-{int(time.time())}"
                if msg_id in self._sent_ids:
                    continue
                # Only return if there's something new (last_msg non-empty)
                last_msg = (entry.get("last_msg") or "").strip()
                if not last_msg:
                    continue
                results.append(IncomingMessage(
                    msg_id=msg_id,
                    platform=Platform.WHATSAPP,
                    contact=contact,
                    text=last_msg,
                    received_at=time.time(),
                    thread_history=[],
                    metadata={"unread_count": entry.get("unread_count", 1)},
                ))
        except Exception:
            logger.exception("WhatsApp DOM read failed")
        return results

    def send_reply(self, contact: str, text: str, meta: dict) -> bool:
        """Send a reply via WhatsApp Web."""
        try:
            page = self._ensure_page()
        except Exception:
            return False
        try:
            return self._send_via_dom(page, contact, text)
        except Exception:
            logger.exception("WhatsApp send_reply failed")
            return False

    def _send_via_dom(self, page, contact: str, text: str) -> bool:
        """Open chat with contact and send message."""
        try:
            # Search for the contact
            page.evaluate(f"""(name) => {{
                const search = document.querySelector('[data-testid=\"chat-list-search\"]');
                if (search) {{
                    search.click();
                    const input = document.querySelector('[data-testid=\"search-input\"]');
                    if (input) {{
                        input.value = name;
                        input.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }}
                }}
            }}""", contact)
            time.sleep(1.0)
            # Click the first result
            page.evaluate("""() => {
                const cell = document.querySelector('[data-testid=\"cell-frame-container\"]');
                if (cell) cell.click();
            }""")
            time.sleep(0.5)
            # Type into the message box
            page.evaluate(f"""(msg) => {{
                const box = document.querySelector('[data-testid=\"message-input\"]') ||
                            document.querySelector('[contenteditable=\"true\"][data-tab=\"10\"]');
                if (box) {{
                    box.focus();
                    document.execCommand('insertText', false, msg);
                }}
            }}""", text)
            time.sleep(0.3)
            # Click send
            page.evaluate("""() => {
                const send = document.querySelector('[data-testid=\"send\"]');
                if (send) send.click();
            }""")
            return True
        except Exception:
            logger.exception("WhatsApp send_via_dom failed")
            return False

    def close(self):
        if self._owns_page and hasattr(self, "_pw"):
            try:
                self._pw.stop()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────
# 3. Discord Watcher (Bot API)
# ──────────────────────────────────────────────────────────────────────
class DiscordWebhookWatcher(PlatformWatcher):
    """Discord auto-reply via Bot API (REST, no WebSocket needed).

    Requires:
      - DISCORD_BOT_TOKEN env var
      - For each contact: their Discord user ID
      - The bot must be able to DM the user (or share a guild with them)

    Reads new DMs via the /users/@me/channels endpoint and the messages
    endpoint. Sends via POST /channels/{id}/messages.
    """

    DISCORD_API = "https://discord.com/api/v10"

    def __init__(self, token: Optional[str] = None,
                 allowed_user_ids: Optional[list[str]] = None):
        super().__init__(Platform.DISCORD)
        self._token = token or os.environ.get("DISCORD_BOT_TOKEN")
        self._allowed_user_ids = set(allowed_user_ids or [])
        self._channel_cache: dict[str, str] = {}  # user_id -> channel_id
        self._processed_ids: set[str] = set()
        self._lock = threading.RLock()
        if not self._token:
            logger.warning("DiscordWatcher: no bot token configured")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bot {self._token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> Optional[dict]:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.DISCORD_API}{path}",
                headers=self._headers(),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"Discord GET {path}: {e}")
            return None

    def _post(self, path: str, payload: dict) -> Optional[dict]:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self.DISCORD_API}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.debug(f"Discord POST {path}: {e}")
            return None

    def _open_dm(self, user_id: str) -> Optional[str]:
        """Open or fetch existing DM channel with a user."""
        with self._lock:
            if user_id in self._channel_cache:
                return self._channel_cache[user_id]
        result = self._post("/users/@me/channels", {"recipient_id": user_id})
        if result and "id" in result:
            with self._lock:
                self._channel_cache[user_id] = result["id"]
            return result["id"]
        return None

    def poll(self) -> list[IncomingMessage]:
        if not self._token:
            return []
        msgs: list[IncomingMessage] = []
        # List DM channels
        data = self._get("/users/@me/channels")
        if not isinstance(data, list):
            return []
        for channel in data:
            user_id = str(channel.get("recipients", [{}])[0].get("id", ""))
            if self._allowed_user_ids and user_id not in self._allowed_user_ids:
                continue
            channel_id = channel.get("id")
            if not channel_id:
                continue
            # Get last messages
            history = self._get(f"/channels/{channel_id}/messages?limit=5")
            if not isinstance(history, list):
                continue
            for m in history:
                msg_id = m.get("id", "")
                if msg_id in self._processed_ids:
                    continue
                # Skip bot messages
                author = m.get("author", {})
                if author.get("bot"):
                    continue
                self._processed_ids.add(msg_id)
                content = m.get("content", "")
                if not content:
                    continue
                msgs.append(IncomingMessage(
                    msg_id=msg_id,
                    platform=Platform.DISCORD,
                    contact=user_id,
                    text=content,
                    received_at=float(m.get("timestamp", time.time())),
                    thread_history=[],
                    metadata={"channel_id": channel_id, "username":
                                author.get("username", "")},
                ))
        return msgs

    def send_reply(self, contact: str, text: str, meta: dict) -> bool:
        channel_id = meta.get("channel_id") or self._open_dm(contact)
        if not channel_id:
            logger.warning(f"Discord send_reply: no channel for {contact}")
            return False
        result = self._post(f"/channels/{channel_id}/messages",
                              {"content": text})
        return result is not None


# ──────────────────────────────────────────────────────────────────────
# 4. Test-only watcher (no platform needed)
# ──────────────────────────────────────────────────────────────────────
class CallbackWatcher(PlatformWatcher):
    """Watcher driven by user-provided callbacks (for tests / custom flows)."""

    def __init__(self, platform: Platform,
                 poll_fn=None,
                 send_fn=None):
        super().__init__(platform)
        self._poll_fn = poll_fn or (lambda: [])
        self._send_fn = send_fn or (lambda c, t, m: True)

    def poll(self) -> list[IncomingMessage]:
        try:
            return list(self._poll_fn() or [])
        except Exception:
            logger.exception("CallbackWatcher poll failed")
            return []

    def send_reply(self, contact: str, text: str, meta: dict) -> bool:
        try:
            return bool(self._send_fn(contact, text, meta))
        except Exception:
            logger.exception("CallbackWatcher send_reply failed")
            return False


# ──────────────────────────────────────────────────────────────────────
# Helper: quick-start script for the daemon
# ──────────────────────────────────────────────────────────────────────
def make_default_watchers(
    whatsapp_inbox: Optional[Path] = None,
    discord_token: Optional[str] = None,
) -> dict:
    """Construct a sensible set of watchers based on available config."""
    watchers: dict[Platform, PlatformWatcher] = {}
    # Always include a file watcher if path provided
    if whatsapp_inbox:
        watchers[Platform.WHATSAPP] = FileWatcher(
            inbox_path=str(whatsapp_inbox),
            sent_path=str(whatsapp_inbox).replace(".jsonl", "_sent.jsonl"),
        )
    if discord_token:
        watchers[Platform.DISCORD] = DiscordWebhookWatcher(token=discord_token)
    return watchers
