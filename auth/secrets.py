"""Per-user secret isolation for SONIC AI — API keys, tokens, credentials."""
from __future__ import annotations

import json
import hashlib
import secrets
import logging
from pathlib import Path
from typing import Any, Optional
from threading import Lock

logger = logging.getLogger(__name__)


def get_base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
SECRETS_DIR = BASE_DIR / "user_secrets"
_lock = Lock()


class UserSecrets:
    """Per-user encrypted secret storage.

    Each user's secrets are stored in a separate file named by their UID hash.
    Secrets are XOR-encrypted with a machine-specific key to prevent casual reading.
    """

    def __init__(self, uid: str):
        self._uid = uid
        self._path = SECRETS_DIR / f"{self._uid_hash()}.json"
        self._data: dict[str, str] = {}
        self._loaded = False

    def _uid_hash(self) -> str:
        """Hash UID for filename — not for security, just to avoid special chars."""
        return hashlib.sha256(self._uid.encode()).hexdigest()[:16]

    def _machine_key(self) -> bytes:
        """Machine-specific key for XOR encryption."""
        import platform
        key_str = f"sonic-{platform.node()}-{platform.machine()}"
        return hashlib.sha256(key_str.encode()).digest()

    def _xor_encrypt(self, data: str) -> bytes:
        """Simple XOR encryption — not cryptographically strong, prevents casual reading."""
        key = self._machine_key()
        encoded = data.encode("utf-8")
        encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(encoded))
        return encrypted

    def _xor_decrypt(self, data: bytes) -> str:
        """Simple XOR decryption."""
        key = self._machine_key()
        decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
        return decrypted.decode("utf-8")

    def load(self) -> bool:
        """Load secrets from disk."""
        if self._loaded:
            return True
        if not self._path.exists():
            self._loaded = True
            return True
        try:
            with _lock:
                raw = self._path.read_bytes()
                decrypted = self._xor_decrypt(raw)
                self._data = json.loads(decrypted)
                self._loaded = True
                return True
        except Exception as e:
            logger.warning("[Secrets] Load failed for %s: %s", self._uid[:8], e)
            self._loaded = True
            return False

    def save(self) -> bool:
        """Save secrets to disk."""
        try:
            with _lock:
                SECRETS_DIR.mkdir(parents=True, exist_ok=True)
                encrypted = self._xor_encrypt(json.dumps(self._data))
                self._path.write_bytes(encrypted)
                return True
        except Exception as e:
            logger.error("[Secrets] Save failed for %s: %s", self._uid[:8], e)
            return False

    def get(self, key: str, default: str = "") -> str:
        """Get a secret value."""
        self.load()
        return self._data.get(key, default)

    def set(self, key: str, value: str) -> bool:
        """Set a secret value."""
        self.load()
        self._data[key] = value
        return self.save()

    def delete(self, key: str) -> bool:
        """Delete a secret."""
        self.load()
        if key in self._data:
            del self._data[key]
            return self.save()
        return True

    def clear(self) -> bool:
        """Clear all secrets for this user (but keep file for potential reuse)."""
        self._data = {}
        self._loaded = True
        return self.save()

    def list_keys(self) -> list[str]:
        """List all secret keys (not values)."""
        self.load()
        return list(self._data.keys())

    def delete_file(self) -> bool:
        """Permanently delete the secrets file."""
        try:
            if self._path.exists():
                self._path.unlink()
            self._data = {}
            self._loaded = True
            return True
        except Exception as e:
            logger.error("[Secrets] Delete file failed for %s: %s", self._uid[:8], e)
            return False


# ── In-memory runtime secrets (cleared on logout) ─────────────────────

_runtime_secrets: dict[str, str] = {}


def set_runtime_secret(key: str, value: str) -> None:
    """Set a secret in runtime memory (cleared on logout)."""
    _runtime_secrets[key] = value


def get_runtime_secret(key: str, default: str = "") -> str:
    """Get a secret from runtime memory."""
    return _runtime_secrets.get(key, default)


def clear_runtime_secrets() -> None:
    """Clear ALL runtime secrets (called on logout)."""
    _runtime_secrets.clear()
    logger.info("[Secrets] Runtime secrets cleared")


def get_user_secrets(uid: str) -> UserSecrets:
    """Get UserSecrets instance for a user."""
    return UserSecrets(uid)
