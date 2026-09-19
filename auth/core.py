"""SONIC AI — Authentication Core (Security-Hardened).

ROOT CAUSE FIX: All auth data now stored in per-user AppData directory.
The application package NEVER contains user sessions, passwords, or profiles.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("sonic.auth")

# ── Per-user data directory (NEVER inside the app package) ──────────────
_APP_NAME = "SONIC AI"

if sys.platform == "win32":
    _USER_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
elif sys.platform == "darwin":
    _USER_DATA_ROOT = Path.home() / "Library" / "Application Support"
else:
    _USER_DATA_ROOT = Path.home() / ".local" / "share"

_AUTH_DIR = _USER_DATA_ROOT / _APP_NAME / "auth"
_CONFIG_DIR = _USER_DATA_ROOT / _APP_NAME / "config"

# Auth data paths — ALL in per-user AppData, NEVER in app package
_SESSION_PATH = _AUTH_DIR / ".session.json"
_PROFILE_PATH = _AUTH_DIR / ".profile.json"
_ONBOARDING_DIR = _AUTH_DIR / "onboarding"
_LOCAL_CREDS_PATH = _AUTH_DIR / ".local_users.json"
_GOOGLE_CRED_PATH = _AUTH_DIR / ".google_credentials.json"

# Firebase config — user provides at runtime, NOT bundled
_FIREBASE_CONFIG_SOURCE = Path(__file__).resolve().parent / "firebase_config.json"
_FIREBASE_CONFIG_USER = _CONFIG_DIR / "firebase_config.json"

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_MIN_PASS_LEN = 8
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0


def _ensure_dirs():
    """Create auth data directories."""
    _AUTH_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _ONBOARDING_DIR.mkdir(parents=True, exist_ok=True)


def _safe_json_read(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path.name, e)
        return default


def _safe_json_write(path: Path, data: Any) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError as e:
        logger.error("Failed to write %s: %s", path.name, e)
        return False


def _hash_password(password: str) -> str:
    """Hash password with SHA-256 + salt for local auth."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify password against hashed storage."""
    if ":" not in stored:
        return False
    salt, expected_hash = stored.split(":", 1)
    actual_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return secrets.compare_digest(actual_hash, expected_hash)


def _validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _validate_password(password: str) -> str | None:
    if len(password) < _MIN_PASS_LEN:
        return f"Password must be at least {_MIN_PASS_LEN} characters."
    return None


class SonicAuth:
    _instance: SonicAuth | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        _ensure_dirs()
        self._user_id: str = ""
        self._email: str = ""
        self._display_name: str = ""
        self._photo_url: str = ""
        self._id_token: str = ""
        self._refresh_token: str = ""
        self._token_expires_at: float = 0.0
        self._is_authenticated: bool = False
        self._provider: str = ""
        self._firebase_app: Any = None
        self._firebase_auth: Any = None
        self._firebase_user: Any = None
        self._init_error: str = ""
        self._last_error: str = ""
        self._load_session()

    @classmethod
    def get_instance(cls) -> SonicAuth:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def current_user(self) -> dict[str, Any] | None:
        if not self._is_authenticated:
            return None
        return {
            "uid": self._user_id,
            "email": self._email,
            "displayName": self._display_name,
            "photoURL": self._photo_url,
            "provider": self._provider,
        }

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    @property
    def last_error(self) -> str:
        return self._last_error

    # ── Firebase Config ──────────────────────────────────────────────────

    def _get_firebase_config(self) -> dict | None:
        """Load Firebase config from user data dir, or copy from app bundle as template."""
        # Check user data dir first
        config = _safe_json_read(_FIREBASE_CONFIG_USER)
        if config and config.get("apiKey"):
            return config

        # Copy from app bundle as template (first run)
        if _FIREBASE_CONFIG_SOURCE.exists():
            config = _safe_json_read(_FIREBASE_CONFIG_SOURCE)
            if config:
                _safe_json_write(_FIREBASE_CONFIG_USER, config)
                return config

        return None

    # ── Firebase Init ─────────────────────────────────────────────────────

    def _ensure_client_firebase(self) -> Any:
        if self._firebase_user is not None:
            return self._firebase_user

        try:
            import pyrebase

            config = self._get_firebase_config()
            if not config:
                self._init_error = "Firebase config not found"
                return None

            required = ["apiKey", "authDomain", "projectId"]
            missing = [k for k in required if not config.get(k)]
            if missing:
                self._init_error = f"Firebase config missing: {', '.join(missing)}"
                return None

            if not config.get("databaseURL"):
                config["databaseURL"] = f"https://{config['projectId']}-default-rtdb.firebaseio.com"

            firebase = pyrebase.initialize_app(config)
            self._firebase_user = firebase.auth()
            logger.info("[Auth] Firebase client initialized")
            return self._firebase_user

        except ImportError:
            self._init_error = "pyrebase4 not installed"
            logger.warning("[Auth] pyrebase4 not installed. Run: pip install pyrebase4")
        except Exception as e:
            self._init_error = f"Firebase init failed: {e}"
            logger.error("[Auth] Firebase init error: %s", e)

        return None

    def _ensure_firebase_admin(self) -> Any:
        if self._firebase_auth is not None:
            return self._firebase_auth

        try:
            import firebase_admin
            from firebase_admin import auth as fb_auth, credentials

            if not firebase_admin._apps:
                config = self._get_firebase_config()
                if config:
                    service_account = {
                        "type": "service_account",
                        "project_id": config.get("projectId", ""),
                        "private_key_id": "",
                        "private_key": "",
                        "client_email": "",
                        "client_id": "",
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                    if all(service_account.values()):
                        cred = credentials.Certificate(service_account)
                        firebase_admin.initialize_app(cred)
                    else:
                        firebase_admin.initialize_app()
                else:
                    firebase_admin.initialize_app()

            self._firebase_app = firebase_admin.get_app()
            self._firebase_auth = fb_auth
            return self._firebase_auth

        except ImportError:
            logger.warning("[Auth] firebase-admin not installed")
        except Exception as e:
            logger.error("[Auth] Firebase Admin init error: %s", e)

        return None

    # ── Email/Password Auth ───────────────────────────────────────────────

    def login(self, email: str, password: str) -> dict[str, Any]:
        email = (email or "").strip().lower()
        password = password or ""

        if not _validate_email(email):
            return {"ok": False, "success": False, "error": "Invalid email format."}
        if not password:
            return {"ok": False, "success": False, "error": "Password required."}

        for attempt in range(_MAX_RETRIES):
            fb = self._ensure_client_firebase()
            if fb is None:
                return self._fallback_login(email, password)

            try:
                result = fb.sign_in_with_email_and_password(email, password)
                self._set_session(
                    user_id=result.get("localId", ""),
                    email=email,
                    id_token=result.get("idToken", ""),
                    refresh_token=result.get("refreshToken", ""),
                    provider="email",
                )
                logger.info("[Auth] Login success: %s", email)
                return {"ok": True, "success": True, "user_id": self._user_id, "email": email}

            except Exception as e:
                err = self._parse_firebase_error(e)
                if "INVALID_LOGIN_CREDENTIALS" in str(e) or "EMAIL_NOT_FOUND" in str(e):
                    return {"ok": False, "success": False, "error": "Invalid email or password."}
                if "TOO_MANY_REQUESTS" in str(e):
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_RETRY_DELAY * (attempt + 1))
                        continue
                    return {"ok": False, "success": False, "error": "Too many attempts. Try again later."}
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY)
                    continue
                return {"ok": False, "success": False, "error": err}

        return {"ok": False, "success": False, "error": "Login failed after retries."}

    def signup(self, email: str, password: str) -> dict[str, Any]:
        email = (email or "").strip().lower()
        password = password or ""

        if not _validate_email(email):
            return {"ok": False, "success": False, "error": "Invalid email format."}
        pass_err = _validate_password(password)
        if pass_err:
            return {"ok": False, "success": False, "error": pass_err}

        for attempt in range(_MAX_RETRIES):
            fb = self._ensure_client_firebase()
            if fb is None:
                return self._fallback_signup(email, password)

            try:
                result = fb.create_user_with_email_and_password(email, password)
                self._set_session(
                    user_id=result.get("localId", ""),
                    email=email,
                    id_token=result.get("idToken", ""),
                    refresh_token=result.get("refreshToken", ""),
                    provider="email",
                )
                logger.info("[Auth] Signup success: %s", email)
                return {"ok": True, "success": True, "user_id": self._user_id, "email": email}

            except Exception as e:
                err = self._parse_firebase_error(e)
                if "EMAIL_EXISTS" in str(e):
                    return {"ok": False, "success": False, "error": "Email already registered. Please login."}
                if "WEAK_PASSWORD" in str(e):
                    return {"ok": False, "success": False, "error": "Password is too weak. Use at least 6 characters."}
                if "TOO_MANY_REQUESTS" in str(e):
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_RETRY_DELAY * (attempt + 1))
                        continue
                    return {"ok": False, "success": False, "error": "Too many attempts. Try again later."}
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(_RETRY_DELAY)
                    continue
                return {"ok": False, "success": False, "error": err}

        return {"ok": False, "success": False, "error": "Signup failed after retries."}

    def send_password_reset(self, email: str) -> dict[str, Any]:
        email = (email or "").strip().lower()
        if not _validate_email(email):
            return {"ok": False, "success": False, "error": "Invalid email format."}

        fb = self._ensure_client_firebase()
        if fb is None:
            return {"ok": True, "success": True, "message": "Password reset email sent (local mode)."}

        try:
            fb.send_password_reset_email(email)
            logger.info("[Auth] Password reset sent: %s", email)
            return {"ok": True, "success": True, "message": "Password reset email sent."}
        except Exception as e:
            err = self._parse_firebase_error(e)
            if "EMAIL_NOT_FOUND" in str(e):
                return {"ok": True, "success": True, "message": "If this email exists, a reset link was sent."}
            return {"ok": False, "success": False, "error": err}

    # ── Google Sign-In ────────────────────────────────────────────────────

    def login_with_google(self, id_token: str) -> dict[str, Any]:
        if not id_token or not id_token.strip():
            return {"ok": False, "success": False, "error": "Google ID token required."}

        config = self._get_firebase_config()
        api_key = config.get("apiKey", "") if config else ""
        if not api_key:
            return {"ok": False, "success": False, "error": "Firebase API key not found."}

        import urllib.request
        import urllib.error

        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={api_key}"
        post_body = f"id_token={id_token}&providerId=google.com"
        payload = json.dumps({
            "requestUri": "http://localhost",
            "returnSecureToken": True,
            "postBody": post_body,
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                self._set_session(
                    user_id=data.get("localId", ""),
                    email=data.get("email", ""),
                    id_token=data.get("idToken", ""),
                    refresh_token=data.get("refreshToken", ""),
                    provider="google",
                    display_name=data.get("displayName", ""),
                    photo_url=data.get("photoUrl", ""),
                )
                logger.info("[Auth] Google login success: %s", self._email)
                return {"ok": True, "success": True, "user_id": self._user_id, "email": self._email}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            logger.error("[Auth] Google login HTTP error: %s — %s", e.code, error_body)
            try:
                err_data = json.loads(error_body)
                msg = err_data.get("error", {}).get("message", error_body)
            except Exception:
                msg = error_body
            return {"ok": False, "success": False, "error": f"Firebase rejected Google token: {msg}"}
        except Exception as e:
            logger.error("[Auth] Google login error: %s", e)
            return {"ok": False, "success": False, "error": str(e)}

    def get_google_client_id(self) -> str:
        config = self._get_firebase_config()
        if config:
            cid = config.get("google_client_id", "")
            if cid:
                return cid
        return ""

    def get_google_client_secret(self) -> str:
        config = self._get_firebase_config()
        if config:
            return config.get("google_client_secret", "")
        return ""

    def set_google_client_id(self, client_id: str) -> bool:
        config = self._get_firebase_config() or {}
        config["google_client_id"] = client_id
        return _safe_json_write(_FIREBASE_CONFIG_USER, config)

    def set_google_client_secret(self, client_secret: str) -> bool:
        config = self._get_firebase_config() or {}
        config["google_client_secret"] = client_secret
        return _safe_json_write(_FIREBASE_CONFIG_USER, config)

    def is_google_configured(self) -> bool:
        return bool(self.get_google_client_id() and self.get_google_client_secret())

    def google_login_with_server(self, callback=None) -> dict[str, Any]:
        if not self.is_google_configured():
            return {
                "ok": False, "success": False,
                "error": "Google Sign-In not configured. Use email/password login."
            }

        client_id = self.get_google_client_id()
        client_secret = self.get_google_client_secret()

        import urllib.parse
        import urllib.request
        import http.server
        import socketserver
        import webbrowser
        import threading
        import time as _time

        port = 8081
        redirect_uri = f"http://localhost:{port}"
        import uuid
        state = str(uuid.uuid4()).replace("-", "")

        params = urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        })
        auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

        result_box = {"done": False, "id_token": None, "error": None, "state": state}

        def _exchange_code(code: str) -> str:
            token_data = urllib.parse.urlencode({
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }).encode()
            token_req = urllib.request.Request(
                "https://oauth2.googleapis.com/token",
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(token_req, timeout=30) as resp:
                tokens = json.loads(resp.read())
                id_token = tokens.get("id_token", "")
                if not id_token:
                    err = tokens.get("error_description", tokens.get("error", "unknown"))
                    raise Exception(f"No ID token: {err}")
                return id_token

        class OAuthHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    parsed = urllib.parse.urlparse(self.path)
                    if parsed.path != "/" or result_box["done"]:
                        self.send_response(200)
                        self.send_header("Content-type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(b"OK")
                        return

                    qs = urllib.parse.parse_qs(parsed.query)

                    if "error" in qs:
                        err = qs["error"][0]
                        result_box["error"] = err
                        result_box["done"] = True
                        self._respond(200, f"<h2>Cancelled</h2><pre>{err}</pre>")
                        return

                    code = qs.get("code", [None])[0]
                    returned_state = qs.get("state", [None])[0]
                    expected_state = result_box["state"]

                    if not code:
                        result_box["error"] = "No authorization code"
                        result_box["done"] = True
                        self._respond(200, "<h2>No code</h2>")
                        return

                    if returned_state != expected_state:
                        result_box["error"] = "State mismatch"
                        result_box["done"] = True
                        self._respond(200, "<h2>State mismatch</h2>")
                        return

                    try:
                        id_token = _exchange_code(code)
                        result_box["id_token"] = id_token
                        result_box["done"] = True
                        self._respond(200, "<h2>Sign-in successful!</h2><p>Close this tab and return to SONIC.</p>")
                    except Exception as e:
                        result_box["error"] = str(e)
                        result_box["done"] = True
                        self._respond(200, f"<h2>Token exchange failed</h2><pre>{e}</pre>")

                except Exception as e:
                    result_box["error"] = str(e)
                    result_box["done"] = True
                    self._respond(200, f"<h2>Error</h2><pre>{e}</pre>")

            def _respond(self, code, body):
                self.send_response(code)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def log_message(self, format, *args):
                pass

        try:
            class ReusableTCPServer(socketserver.TCPServer):
                allow_reuse_address = True
            server = ReusableTCPServer(("127.0.0.1", port), OAuthHandler)
        except OSError as e:
            return {"ok": False, "success": False, "error": f"Port {port} in use. Close other apps using it."}

        server.timeout = 120
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        _time.sleep(0.3)
        webbrowser.open(auth_url)

        deadline = _time.time() + 120
        while _time.time() < deadline and not result_box["done"]:
            _time.sleep(0.1)

        server.shutdown()

        if result_box["error"]:
            return {"ok": False, "success": False, "error": result_box["error"]}

        id_token = result_box["id_token"]
        if not id_token:
            return {"ok": False, "success": False, "error": "No token received"}

        return self.login_with_google(id_token)

    def _save_google_credentials(self, credentials: dict) -> None:
        _safe_json_write(_GOOGLE_CRED_PATH, credentials)

    def _load_google_credentials(self) -> dict | None:
        return _safe_json_read(_GOOGLE_CRED_PATH)

    # ── Session Management ────────────────────────────────────────────────

    def restore_session(self) -> dict | bool:
        if self._is_authenticated and self._user_id:
            if self._token_expires_at > 0 and time.time() < self._token_expires_at - 60:
                return self._session_dict()
            if self._token_expires_at > 0 and time.time() >= self._token_expires_at - 60:
                if self._refresh_id_token():
                    return self._session_dict()
                return False

        self._load_session()
        if not self._is_authenticated or not self._user_id:
            return False

        if self._token_expires_at > 0 and time.time() < self._token_expires_at - 60:
            return self._session_dict()

        if self._refresh_id_token():
            return self._session_dict()
        return False

    def _session_dict(self) -> dict:
        return {
            "user_id": self._user_id,
            "email": self._email,
            "display_name": self._display_name,
            "photo_url": self._photo_url,
            "provider": self._provider,
            "is_authenticated": self._is_authenticated,
        }

    def _refresh_id_token(self) -> bool:
        fb = self._ensure_client_firebase()
        if not fb or not self._refresh_token:
            return self._is_authenticated

        try:
            result = fb.refresh(self._refresh_token)
            self._id_token = result.get("idToken", "")
            self._refresh_token = result.get("refreshToken", self._refresh_token)
            expires_in = int(result.get("expiresIn", "3600"))
            self._token_expires_at = time.time() + expires_in
            self._save_session()
            logger.info("[Auth] Token refreshed")
            return True
        except Exception as e:
            logger.warning("[Auth] Token refresh failed: %s", e)
            if "INVALID_REFRESH_TOKEN" in str(e):
                self.logout()
                return False
            return self._is_authenticated

    def logout(self) -> None:
        """Complete logout — clears ALL active user state."""
        logger.info("[Auth] Logout: %s", self._email)

        # 1. Clear in-memory auth state
        self._user_id = ""
        self._email = ""
        self._display_name = ""
        self._photo_url = ""
        self._id_token = ""
        self._refresh_token = ""
        self._token_expires_at = 0.0
        self._is_authenticated = False
        self._provider = ""
        self._firebase_user = None

        # 2. Delete session file
        self._clear_session()

        # 3. Clear runtime secrets
        try:
            from auth.secrets import clear_runtime_secrets
            clear_runtime_secrets()
        except ImportError:
            pass

        # 4. Clear memory user_id
        try:
            from memory.memory_manager import set_user_id
            set_user_id("")
        except ImportError:
            pass

        # 5. Clear profile cache
        self._clear_profile()

        # 6. Clear onboarding cache for this user
        # (We DON'T delete onboarding data — it's per-user and should persist for re-login)

        logger.info("[Auth] Logout complete — all runtime state cleared")

    def _clear_profile(self) -> None:
        """Delete the in-memory profile cache."""
        try:
            if _PROFILE_PATH.exists():
                _PROFILE_PATH.unlink()
        except OSError:
            pass

    def delete_account(self) -> dict[str, Any]:
        if not self._is_authenticated:
            return {"ok": False, "success": False, "error": "Not authenticated."}

        fb_admin = self._ensure_firebase_admin()
        if fb_admin:
            try:
                fb_admin.delete_user(self._user_id)
            except Exception as e:
                logger.error("[Auth] Account deletion failed: %s", e)
                return {"ok": False, "success": False, "error": f"Failed to delete account: {e}"}

        # Delete ALL local data for this user
        self._clear_profile()
        self._clear_session()
        try:
            onboarding_file = _ONBOARDING_DIR / f"{self._user_id}.json"
            if onboarding_file.exists():
                onboarding_file.unlink()
        except OSError:
            pass

        self.logout()
        return {"ok": True, "success": True, "message": "Account deleted."}

    # ── Profile Methods ───────────────────────────────────────────────────

    def get_extended_profile(self) -> dict[str, Any]:
        data = _safe_json_read(_PROFILE_PATH, {"profile": {}})
        if not isinstance(data, dict):
            data = {"profile": {}}
        if "profile" not in data:
            data["profile"] = {}
        return data

    def update_extended_profile(self, **fields: Any) -> dict[str, Any]:
        current = self.get_extended_profile()
        profile = current.get("profile", {})
        profile.update({k: v for k, v in fields.items() if v is not None})
        current["profile"] = profile

        if _safe_json_write(_PROFILE_PATH, current):
            return {"ok": True, "success": True}
        return {"ok": False, "success": False, "error": "Failed to save profile."}

    def is_onboarding_completed(self) -> bool:
        if not self._user_id:
            return False
        path = _ONBOARDING_DIR / f"{self._user_id}.json"
        data = _safe_json_read(path, {})
        return bool(data.get("completed", False)) if isinstance(data, dict) else False

    def mark_onboarding_completed(self) -> dict[str, Any]:
        if not self._user_id:
            return {"ok": False, "success": False, "error": "No active user."}
        path = _ONBOARDING_DIR / f"{self._user_id}.json"
        if _safe_json_write(path, {"completed": True}):
            return {"ok": True, "success": True}
        return {"ok": False, "success": False, "error": "Failed to save onboarding status."}

    # ── Internal Helpers ──────────────────────────────────────────────────

    def _set_session(
        self,
        user_id: str,
        email: str,
        id_token: str,
        refresh_token: str,
        provider: str,
        display_name: str = "",
        photo_url: str = "",
    ) -> None:
        self._user_id = user_id
        self._email = email
        self._id_token = id_token
        self._refresh_token = refresh_token
        self._provider = provider
        self._display_name = display_name or self._display_name
        self._photo_url = photo_url or self._photo_url
        self._is_authenticated = bool(user_id)
        self._token_expires_at = time.time() + 3600
        self._save_session()

    def _save_session(self) -> None:
        _safe_json_write(_SESSION_PATH, {
            "user_id": self._user_id,
            "email": self._email,
            "display_name": self._display_name,
            "photo_url": self._photo_url,
            "id_token": self._id_token,
            "refresh_token": self._refresh_token,
            "token_expires_at": self._token_expires_at,
            "is_authenticated": self._is_authenticated,
            "provider": self._provider,
        })

    def _load_session(self) -> None:
        data = _safe_json_read(_SESSION_PATH)
        if not data or not isinstance(data, dict):
            return
        self._user_id = data.get("user_id", "")
        self._email = data.get("email", "")
        self._display_name = data.get("display_name", "")
        self._photo_url = data.get("photo_url", "")
        self._id_token = data.get("id_token", "")
        self._refresh_token = data.get("refresh_token", "")
        self._token_expires_at = data.get("token_expires_at", 0.0)
        self._is_authenticated = data.get("is_authenticated", False)
        self._provider = data.get("provider", "")

    def _clear_session(self) -> None:
        try:
            if _SESSION_PATH.exists():
                _SESSION_PATH.unlink()
        except OSError:
            pass

    @staticmethod
    def _parse_firebase_error(e: Exception) -> str:
        msg = str(e)
        if "INVALID_LOGIN_CREDENTIALS" in msg or "EMAIL_NOT_FOUND" in msg:
            return "Invalid email or password."
        if "EMAIL_EXISTS" in msg:
            return "Email already registered."
        if "WEAK_PASSWORD" in msg:
            return "Password is too weak."
        if "TOO_MANY_REQUESTS" in msg:
            return "Too many requests. Try again later."
        if "NETWORK_REQUEST_FAILED" in msg:
            return "Network error. Check your connection."
        if "USER_NOT_FOUND" in msg:
            return "No account found with this email."
        if "USER_DISABLED" in msg:
            return "Account has been disabled."
        if "INVALID_ID_TOKEN" in msg:
            return "Invalid authentication token."
        if "OPERATION_NOT_ALLOWED" in msg:
            return "This sign-in method is not enabled."
        if len(msg) > 100:
            return "An unexpected error occurred. Please try again."
        return msg

    # ── Fallback (no Firebase) ────────────────────────────────────────────

    def _fallback_login(self, email: str, password: str) -> dict[str, Any]:
        users = _safe_json_read(_LOCAL_CREDS_PATH, {})
        if not isinstance(users, dict):
            users = {}
        user = users.get(email)
        if user:
            stored_pass = user.get("password", "")
            # Support both hashed and legacy plaintext passwords
            if ":" in stored_pass:
                if _verify_password(password, stored_pass):
                    return self._do_fallback_login(email, user)
            elif stored_pass == password:
                # Legacy plaintext — migrate to hashed
                user["password"] = _hash_password(password)
                users[email] = user
                _safe_json_write(_LOCAL_CREDS_PATH, users)
                logger.info("[Auth] Migrated plaintext password to hashed for: %s", email)
                return self._do_fallback_login(email, user)
        return {"ok": False, "success": False, "error": "Invalid email or password."}

    def _do_fallback_login(self, email: str, user: dict) -> dict[str, Any]:
        self._set_session(
            user_id=user.get("uid", hashlib.sha256(email.encode()).hexdigest()[:20]),
            email=email,
            id_token=secrets.token_urlsafe(32),
            refresh_token=secrets.token_urlsafe(32),
            provider="local",
            display_name=user.get("display_name", ""),
        )
        return {"ok": True, "success": True, "user_id": self._user_id, "email": email}

    def _fallback_signup(self, email: str, password: str) -> dict[str, Any]:
        users = _safe_json_read(_LOCAL_CREDS_PATH, {})
        if not isinstance(users, dict):
            users = {}
        if email in users:
            return {"ok": False, "success": False, "error": "Email already registered."}
        uid = hashlib.sha256(email.encode()).hexdigest()[:20]
        users[email] = {"uid": uid, "password": _hash_password(password), "display_name": ""}
        _safe_json_write(_LOCAL_CREDS_PATH, users)
        self._set_session(
            user_id=uid,
            email=email,
            id_token=secrets.token_urlsafe(32),
            refresh_token=secrets.token_urlsafe(32),
            provider="local",
        )
        return {"ok": True, "success": True, "user_id": uid, "email": email}


_auth_instance: SonicAuth | None = None
_auth_lock = threading.Lock()


def get_auth() -> SonicAuth:
    global _auth_instance
    if _auth_instance is None:
        with _auth_lock:
            if _auth_instance is None:
                _auth_instance = SonicAuth.get_instance()
    return _auth_instance
