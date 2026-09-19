"""SONIC AI — Setup Wizard

Interactive setup wizard for external services.
Guides users step-by-step through configuring GitHub, Twitter, Email.

Usage:
    "Setup karo" → shows available services
    "GitHub setup karo" → guides through GitHub setup
    "Twitter setup karo" → guides through Twitter setup
    "Email setup karo" → guides through Email setup
"""
from __future__ import annotations

import json
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger("SETUP_WIZARD")

# ── Config ──────────────────────────────────────────────────────────────
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
_CONFIG_FILE = _CONFIG_DIR / "api_keys.json"


def _load_config() -> dict:
    """Load current config."""
    if not _CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    """Save config."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = _load_config()
    existing.update(data)
    _CONFIG_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _check_github() -> dict:
    """Check GitHub CLI authentication status."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        output = result.stdout + result.stderr
        if "Logged in" in output:
            # Extract username
            for line in output.split("\n"):
                if "account" in line:
                    return {"configured": True, "status": "connected", "info": line.strip()}
            return {"configured": True, "status": "connected", "info": "GitHub CLI authenticated"}
        return {"configured": False, "status": "not_connected", "info": "GitHub CLI not authenticated"}
    except FileNotFoundError:
        return {"configured": False, "status": "not_installed", "info": "gh CLI not installed"}
    except Exception as e:
        return {"configured": False, "status": "error", "info": str(e)}


def _check_twitter() -> dict:
    """Check Twitter API configuration."""
    config = _load_config()
    has_keys = bool(config.get("twitter_api_key") and config.get("twitter_bearer_token"))
    if has_keys:
        return {"configured": True, "status": "configured", "info": "Twitter API credentials found"}
    return {"configured": False, "status": "not_configured", "info": "Twitter API not configured"}


def _check_email() -> dict:
    """Check Email configuration."""
    config = _load_config()
    has_email = bool(config.get("email_address") and config.get("email_password"))
    has_server = bool(config.get("email_imap_server") and config.get("email_smtp_server"))
    if has_email and has_server:
        return {"configured": True, "status": "configured", "info": f"Email configured: {config['email_address']}"}
    return {"configured": False, "status": "not_configured", "info": "Email not configured"}


# ── Setup Guides ────────────────────────────────────────────────────────

def _setup_github() -> str:
    """Guide for GitHub setup."""
    status = _check_github()
    if status["configured"]:
        return f"GitHub already configured! {status['info']}"

    return """GITHUB SETUP — Step by Step:

1. Install GitHub CLI:
   Download from: https://cli.github.com/
   Or run: winget install GitHub.cli

2. Open Command Prompt (cmd) and run:
   gh auth login

3. Follow the prompts:
   - Choose: GitHub.com
   - Choose: HTTPS
   - Choose: Login with a web browser
   - Copy the code and paste in browser

4. After login, tell SONIC:
   "GitHub setup ho gaya"

To verify: SONIC will automatically check gh auth status."""


def _setup_twitter() -> str:
    """Guide for Twitter setup."""
    status = _check_twitter()
    if status["configured"]:
        return f"Twitter already configured! {status['info']}"

    return """TWITTER SETUP — Step by Step:

1. Go to: https://developer.twitter.com/en/portal/dashboard
   (Login with your Twitter account)

2. Create a Project & App:
   - Click "Create Project"
   - Give it a name (e.g., "SONIC AI")
   - Select "Making a bot" as use case

3. Get your API Keys:
   - Go to "Keys and Tokens" tab
   - Copy these values:
     * API Key
     * API Key Secret
     * Access Token
     * Access Token Secret
     * Bearer Token

4. Tell SONIC the values:
   "Twitter setup karo:
    api_key: YOUR_API_KEY
    api_secret: YOUR_API_SECRET
    access_token: YOUR_ACCESS_TOKEN
    access_secret: YOUR_ACCESS_SECRET
    bearer_token: YOUR_BEARER_TOKEN"

SONIC will save them securely in config/api_keys.json."""


def _setup_email() -> str:
    """Guide for Email setup."""
    status = _check_email()
    if status["configured"]:
        return f"Email already configured! {status['info']}"

    return """EMAIL SETUP — Step by Step:

FOR GMAIL:
1. Enable 2-Factor Authentication:
   https://myaccount.google.com/security

2. Generate App Password:
   https://myaccount.google.com/apppasswords
   (Select "Mail" and "Windows Computer")

3. Tell SONIC:
   "Email setup karo:
    address: your_email@gmail.com
    password: your_16_letter_app_password
    imap_server: imap.gmail.com
    smtp_server: smtp.gmail.com"

FOR OUTLOOK:
   imap_server: outlook.office365.com
   smtp_server: smtp.office365.com

FOR YAHOO:
   imap_server: imap.mail.yahoo.com
   smtp_server: smtp.mail.yahoo.com

SONIC will save them securely in config/api_keys.json."""


# ── Tool Interface ──────────────────────────────────────────────────────

def setup_wizard(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Setup wizard for external services.
    Guides users through configuring GitHub, Twitter, Email.
    """
    action = parameters.get("action", "status")
    service = parameters.get("service", "")

    if action == "status":
        # Show status of all services
        gh = _check_github()
        tw = _check_twitter()
        em = _check_email()

        lines = ["SETUP STATUS:"]
        lines.append(f"  GitHub: {'CONNECTED' if gh['configured'] else 'NOT SET'} — {gh['info']}")
        lines.append(f"  Twitter: {'CONFIGURED' if tw['configured'] else 'NOT SET'} — {tw['info']}")
        lines.append(f"  Email: {'CONFIGURED' if em['configured'] else 'NOT SET'} — {em['info']}")
        lines.append("")
        lines.append("To setup a service, say: 'GitHub setup karo' or 'Twitter setup karo' or 'Email setup karo'")
        return "\n".join(lines)

    elif action == "guide":
        if service == "github":
            return _setup_github()
        elif service == "twitter":
            return _setup_twitter()
        elif service == "email":
            return _setup_email()
        else:
            return "Available services: github, twitter, email. Say: 'GitHub setup karo'"

    elif action == "save_twitter":
        # Save Twitter credentials
        config = {
            "twitter_api_key": parameters.get("api_key", ""),
            "twitter_api_secret": parameters.get("api_secret", ""),
            "twitter_access_token": parameters.get("access_token", ""),
            "twitter_access_secret": parameters.get("access_secret", ""),
            "twitter_bearer_token": parameters.get("bearer_token", ""),
        }
        if config["twitter_api_key"] and config["twitter_bearer_token"]:
            _save_config(config)
            return "Twitter credentials saved successfully! You can now use Twitter features."
        return "Error: api_key and bearer_token are required."

    elif action == "save_email":
        # Save Email credentials
        config = {
            "email_address": parameters.get("address", ""),
            "email_password": parameters.get("password", ""),
            "email_imap_server": parameters.get("imap_server", ""),
            "email_smtp_server": parameters.get("smtp_server", ""),
        }
        if config["email_address"] and config["email_password"] and config["email_imap_server"]:
            _save_config(config)
            return f"Email configured successfully! ({config['email_address']})"
        return "Error: address, password, and imap_server are required."

    elif action == "check":
        if service == "github":
            return json.dumps(_check_github(), indent=2)
        elif service == "twitter":
            return json.dumps(_check_twitter(), indent=2)
        elif service == "email":
            return json.dumps(_check_email(), indent=2)
        else:
            return "Available services: github, twitter, email"

    return f"Unknown action: {action}. Use: status, guide, save_twitter, save_email, check"
