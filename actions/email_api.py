"""SONIC AI — Email Integration

Full email control via IMAP/SMTP.
Features:
- Read inbox emails
- Send emails
- Search emails
- Star/flag emails
- Delete emails
- View attachments info
- Auto-reply (basic)

Setup:
    Set these in config/api_keys.json:
    {
        "email_address": "your_email@example.com",
        "email_password": "your_app_password",
        "email_imap_server": "imap.your_provider.com",
        "email_smtp_server": "smtp.your_provider.com"
    }

    For Gmail: imap.gmail.com / smtp.gmail.com
    For Outlook: outlook.office365.com / smtp.office365.com
    For Yahoo: imap.mail.yahoo.com / smtp.mail.yahoo.com
    Use App Password (not regular password) for Gmail/Yahoo.

Usage:
    "Mere emails check karo"
    "Email bhejo john@example.com ko subject: Hello body: Kya hal hai"
    "Emails search karo project se"
    "Starred emails dikhao"
"""
from __future__ import annotations

import json
import email
import imaplib
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from pathlib import Path
from typing import Any

logger = logging.getLogger("EMAIL_API")

# ── Config ──────────────────────────────────────────────────────────────
_CONFIG_FILE = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def _load_config() -> dict:
    """Load email configuration."""
    if not _CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        return {
            "address": data.get("email_address", ""),
            "password": data.get("email_password", ""),
            "imap_server": data.get("email_imap_server", ""),
            "smtp_server": data.get("email_smtp_server", ""),
            "smtp_port": data.get("email_smtp_port", 587),
        }
    except Exception:
        return {}


def _save_config(config: dict) -> None:
    """Save email configuration."""
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {}
    else:
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    data.update({
        "email_address": config.get("address", ""),
        "email_password": config.get("password", ""),
        "email_imap_server": config.get("imap_server", ""),
        "email_smtp_server": config.get("smtp_server", ""),
        "email_smtp_port": config.get("smtp_port", 587),
    })

    _CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _decode_subject(subject: str) -> str:
    """Decode email subject header."""
    if not subject:
        return "(No Subject)"
    decoded = decode_header(subject)
    result = []
    for part, encoding in decoded:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def _get_body(msg) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


# ── IMAP Operations ─────────────────────────────────────────────────────

def _connect_imap(config: dict) -> imaplib.IMAP4_SSL | None:
    """Connect to IMAP server."""
    if not config.get("address") or not config.get("password"):
        return None
    try:
        mail = imaplib.IMAP4_SSL(config["imap_server"])
        mail.login(config["address"], config["password"])
        return mail
    except Exception as e:
        logger.error(f"IMAP connection failed: {e}")
        return None


def _list_emails(folder: str = "INBOX", limit: int = 20, unread_only: bool = False) -> list[dict]:
    """List emails from a folder."""
    config = _load_config()
    mail = _connect_imap(config)
    if not mail:
        return [{"error": "Email not configured. Run: email_api(action='setup', ..."}]

    try:
        mail.select(folder)

        # Search criteria
        if unread_only:
            status, messages = mail.search(None, "UNSEEN")
        else:
            status, messages = mail.search(None, "ALL")

        if status != "OK":
            return [{"error": "Failed to search emails"}]

        msg_ids = messages[0].split()
        # Get most recent emails
        msg_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
        msg_ids.reverse()  # newest first

        emails = []
        for msg_id in msg_ids:
            status, msg_data = mail.fetch(msg_id, "(RFC822)")
            if status == "OK":
                msg = email.message_from_bytes(msg_data[0][1])
                from_addr = msg.get("From", "")
                to_addr = msg.get("To", "")
                date = msg.get("Date", "")
                subject = _decode_subject(msg.get("Subject", ""))
                body = _get_body(msg)[:200]  # First 200 chars

                emails.append({
                    "id": msg_id.decode(),
                    "from": from_addr,
                    "to": to_addr,
                    "subject": subject,
                    "date": date[:25],
                    "preview": body[:100],
                })

        return emails

    except Exception as e:
        return [{"error": str(e)}]
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def _read_email(msg_id: str, folder: str = "INBOX") -> dict:
    """Read a specific email."""
    config = _load_config()
    mail = _connect_imap(config)
    if not mail:
        return {"error": "Email not configured"}

    try:
        mail.select(folder)
        status, msg_data = mail.fetch(msg_id.encode(), "(RFC822)")
        if status != "OK":
            return {"error": "Email not found"}

        msg = email.message_from_bytes(msg_data[0][1])
        body = _get_body(msg)

        return {
            "from": msg.get("From", ""),
            "to": msg.get("To", ""),
            "cc": msg.get("Cc", ""),
            "subject": _decode_subject(msg.get("Subject", "")),
            "date": msg.get("Date", ""),
            "body": body[:2000],
        }

    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def _search_emails(query: str, folder: str = "INBOX", limit: int = 20) -> list[dict]:
    """Search emails."""
    config = _load_config()
    mail = _connect_imap(config)
    if not mail:
        return [{"error": "Email not configured"}]

    try:
        mail.select(folder)

        # Search by subject or body
        status, messages = mail.search(None, f'(OR SUBJECT "{query}" BODY "{query}")')
        if status != "OK":
            return [{"error": "Search failed"}]

        msg_ids = messages[0].split()
        msg_ids = msg_ids[-limit:] if len(msg_ids) > limit else msg_ids
        msg_ids.reverse()

        emails = []
        for msg_id in msg_ids:
            status, msg_data = mail.fetch(msg_id, "(BODY[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if status == "OK":
                header = msg_data[0][1].decode("utf-8", errors="replace")
                msg = email.message_from_string(header)
                emails.append({
                    "id": msg_id.decode(),
                    "from": msg.get("From", ""),
                    "subject": _decode_subject(msg.get("Subject", "")),
                    "date": msg.get("Date", "")[:25],
                })

        return emails

    except Exception as e:
        return [{"error": str(e)}]
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def _star_email(msg_id: str, folder: str = "INBOX") -> dict:
    """Star/flag an email."""
    config = _load_config()
    mail = _connect_imap(config)
    if not mail:
        return {"error": "Email not configured"}

    try:
        mail.select(folder)
        mail.store(msg_id.encode(), "+FLAGS", "\\Flagged")
        return {"success": True, "message": "Email starred"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def _delete_email(msg_id: str, folder: str = "INBOX") -> dict:
    """Delete an email (moves to trash in Gmail)."""
    config = _load_config()
    mail = _connect_imap(config)
    if not mail:
        return {"error": "Email not configured"}

    try:
        mail.select(folder)
        mail.store(msg_id.encode(), "+FLAGS", "\\Deleted")
        mail.expunge()
        return {"success": True, "message": "Email deleted"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


def _mark_unread(msg_id: str, folder: str = "INBOX") -> dict:
    """Mark email as unread."""
    config = _load_config()
    mail = _connect_imap(config)
    if not mail:
        return {"error": "Email not configured"}

    try:
        mail.select(folder)
        mail.store(msg_id.encode(), "-FLAGS", "\\Seen")
        return {"success": True, "message": "Marked as unread"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass


# ── SMTP Operations ─────────────────────────────────────────────────────

def _send_email(to: str, subject: str, body: str, cc: str = "") -> dict:
    """Send an email."""
    config = _load_config()
    if not config.get("address") or not config.get("password"):
        return {"error": "Email not configured. Run: email_api(action='setup', ...)"}

    try:
        msg = MIMEMultipart()
        msg["From"] = config["address"]
        msg["To"] = to
        if cc:
            msg["Cc"] = cc
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(config["smtp_server"], config.get("smtp_port", 587)) as server:
            server.starttls()
            server.login(config["address"], config["password"])
            recipients = [to]
            if cc:
                recipients.extend(cc.split(","))
            server.sendmail(config["address"], recipients, msg.as_string())

        return {"success": True, "message": f"Email sent to {to}"}

    except Exception as e:
        return {"error": f"Failed to send email: {e}"}


def _setup_email(address: str, password: str, imap_server: str = "", smtp_server: str = "") -> dict:
    """Save email configuration."""
    if not imap_server or not smtp_server:
        return {"error": "imap_server and smtp_server are required. Examples: imap.your_provider.com, smtp.your_provider.com"}

    config = {
        "address": address,
        "password": password,
        "imap_server": imap_server,
        "smtp_server": smtp_server,
    }
    _save_config(config)

    # Test connection
    mail = _connect_imap(config)
    if mail:
        try:
            mail.logout()
            return {"success": True, "message": f"Email configured and connected: {address}"}
        except Exception:
            pass

    return {"success": True, "message": "Email credentials saved (connection test failed - check credentials)"}


# ── Tool Interface ──────────────────────────────────────────────────────

def email_api(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Email integration tool.
    Full email control via IMAP/SMTP.
    """
    action = parameters.get("action", "inbox")

    # ── Setup ──
    if action == "setup":
        result = _setup_email(
            parameters.get("address", ""),
            parameters.get("password", ""),
            parameters.get("imap_server", ""),
            parameters.get("smtp_server", ""),
        )
        return result.get("message", result.get("error", "Setup failed"))

    # ── Check config ──
    config = _load_config()
    if not config.get("address"):
        return "Email not configured. Run: email_api(action='setup', address='you@example.com', password='your_app_password', imap_server='imap.example.com', smtp_server='smtp.example.com')"

    # ── Inbox ──
    if action == "inbox":
        limit = parameters.get("limit", 10)
        unread_only = parameters.get("unread_only", False)
        emails = _list_emails(limit=limit, unread_only=unread_only)
        if emails and not emails[0].get("error"):
            lines = [f"Inbox ({len(emails)} emails):"]
            for e in emails:
                lines.append(f"  [{e['date'][:10]}] From: {e['from'][:30]} - {e['subject'][:50]}")
            return "\n".join(lines)
        return f"Error: {emails[0].get('error', 'No emails')}" if emails else "No emails"

    # ── Read ──
    elif action == "read":
        msg_id = parameters.get("msg_id", "")
        if not msg_id:
            return "Error: msg_id is required"
        result = _read_email(msg_id)
        if "error" not in result:
            return (
                f"From: {result['from']}\n"
                f"To: {result['to']}\n"
                f"Subject: {result['subject']}\n"
                f"Date: {result['date']}\n"
                f"---\n{result['body'][:1000]}"
            )
        return f"Error: {result['error']}"

    # ── Search ──
    elif action == "search":
        query = parameters.get("query", "")
        if not query:
            return "Error: query is required"
        limit = parameters.get("limit", 10)
        emails = _search_emails(query, limit=limit)
        if emails and not emails[0].get("error"):
            lines = [f"Search Results ({len(emails)}):"]
            for e in emails:
                lines.append(f"  [{e['date'][:10]}] {e['from'][:30]} - {e['subject'][:50]}")
            return "\n".join(lines)
        return f"No results or error"

    # ── Send ──
    elif action == "send":
        to = parameters.get("to", "")
        subject = parameters.get("subject", "")
        body = parameters.get("body", "")
        if not to or not subject:
            return "Error: to and subject are required"
        cc = parameters.get("cc", "")
        result = _send_email(to, subject, body, cc)
        return result.get("message", result.get("error", "Send failed"))

    # ── Star ──
    elif action == "star":
        msg_id = parameters.get("msg_id", "")
        if not msg_id:
            return "Error: msg_id is required"
        result = _star_email(msg_id)
        return result.get("message", result.get("error", "Failed"))

    # ── Delete ──
    elif action == "delete":
        msg_id = parameters.get("msg_id", "")
        if not msg_id:
            return "Error: msg_id is required"
        result = _delete_email(msg_id)
        return result.get("message", result.get("error", "Failed"))

    # ── Mark Unread ──
    elif action == "unread":
        msg_id = parameters.get("msg_id", "")
        if not msg_id:
            return "Error: msg_id is required"
        result = _mark_unread(msg_id)
        return result.get("message", result.get("error", "Failed"))

    return f"Unknown action: {action}. Use: setup, inbox, read, search, send, star, delete, unread"
