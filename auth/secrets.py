"""Per-user secret isolation for SONIC AI — API keys, tokens, credentials.

Uses Fernet (AES-128-CBC + HMAC-SHA256) for authenticated encryption.
Keys are derived from machine-specific hardware identifiers.
"""
from __future__ import annotations

import json
import hashlib
import logging
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional
from threading import Lock

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
SECRETS_DIR = BASE_DIR / "user_secrets"
_lock = Lock()


def _get_machine_id() -> str:
    """Get a stable machine-specific identifier."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["powershell", "-Command",
                 "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    # Fallback: hostname + architecture (less unique but stable)
    return f"{platform.node()}|{platform.machine()}"


def _derive_fernet_key(machine_id: str, salt: bytes = b"sonic-v2") -> bytes:
    """Derive a Fernet key from machine ID using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
    return key


class UserSecrets:
    """Per-user encrypted secret storage.

    Each user's secrets are stored in a separate file named by their UID hash.
    Secrets are encrypted with Fernet (AES-128-CBC + HMAC-SHA256).
    """

    def __init__(self, uid: str):
        self._uid = uid
        self._path = SECRETS_DIR / f"{self._uid_hash()}.enc"
        self._legacy_path = SECRETS_DIR / f"{self._uid_hash()}.json"
        self._data: dict[str, str] = {}
        self._loaded = False
        self._fernet: Optional[Fernet] = None

    def _uid_hash(self) -> str:
        return hashlib.sha256(self._uid.encode()).hexdigest()[:16]

    def _get_fernet(self) -> Fernet:
        if self._fernet is None:
            machine_id = _get_machine_id()
            key = _derive_fernet_key(machine_id)
            self._fernet = Fernet(key)
        return self._fernet

    def _encrypt(self, data: str) -> bytes:
        fernet = self._get_fernet()
        return fernet.encrypt(data.encode("utf-8"))

    def _decrypt(self, data: bytes) -> str:
        fernet = self._get_fernet()
        return fernet.decrypt(data).decode("utf-8")

    def _migrate_legacy(self) -> bool:
        """Migrate from old XOR-encrypted .json to new Fernet .enc."""
        if not self._legacy_path.exists():
            return False
        try:
            raw = self._legacy_path.read_bytes()
            # Try old XOR decryption
            import platform as _plat
            key_str = f"sonic-{_plat.node()}-{_plat.machine()}"
            key = hashlib.sha256(key_str.encode()).digest()
            decrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
            data = json.loads(decrypted.decode("utf-8"))
            # Re-encrypt with Fernet
            self._data = data
            self.save()
            self._legacy_path.unlink()
            logger.info("[Secrets] Migrated legacy secrets for %s", self._uid[:8])
            return True
        except Exception as e:
            logger.warning("[Secrets] Legacy migration failed for %s: %s", self._uid[:8], e)
            return False

    def load(self) -> bool:
        if self._loaded:
            return True

        # Try new format first
        if self._path.exists():
            try:
                with _lock:
                    raw = self._path.read_bytes()
                    decrypted = self._decrypt(raw)
                    self._data = json.loads(decrypted)
                    self._loaded = True
                    return True
            except InvalidToken:
                logger.error("[Secrets] Decryption failed for %s — wrong machine?", self._uid[:8])
                self._loaded = True
                return False
            except Exception as e:
                logger.warning("[Secrets] Load failed for %s: %s", self._uid[:8], e)
                self._loaded = True
                return False

        # Try migrating legacy format
        if self._migrate_legacy():
            self._loaded = True
            return True

        self._loaded = True
        return True

    def save(self) -> bool:
        try:
            with _lock:
                SECRETS_DIR.mkdir(parents=True, exist_ok=True)
                encrypted = self._encrypt(json.dumps(self._data))
                self._path.write_bytes(encrypted)
                # Remove legacy file if it exists
                if self._legacy_path.exists():
                    self._legacy_path.unlink()
                return True
        except Exception as e:
            logger.error("[Secrets] Save failed for %s: %s", self._uid[:8], e)
            return False

    def get(self, key: str, default: str = "") -> str:
        self.load()
        return self._data.get(key, default)

    def set(self, key: str, value: str) -> bool:
        self.load()
        self._data[key] = value
        return self.save()

    def delete(self, key: str) -> bool:
        self.load()
        if key in self._data:
            del self._data[key]
            return self.save()
        return True

    def clear(self) -> bool:
        self._data = {}
        self._loaded = True
        return self.save()

    def list_keys(self) -> list[str]:
        self.load()
        return list(self._data.keys())

    def delete_file(self) -> bool:
        try:
            if self._path.exists():
                self._path.unlink()
            if self._legacy_path.exists():
                self._legacy_path.unlink()
            self._data = {}
            self._loaded = True
            return True
        except Exception as e:
            logger.error("[Secrets] Delete file failed for %s: %s", self._uid[:8], e)
            return False


# ── In-memory runtime secrets (cleared on logout) ─────────────────────

_runtime_secrets: dict[str, str] = {}


def set_runtime_secret(key: str, value: str) -> None:
    _runtime_secrets[key] = value


def get_runtime_secret(key: str, default: str = "") -> str:
    return _runtime_secrets.get(key, default)


def clear_runtime_secrets() -> None:
    _runtime_secrets.clear()
    logger.info("[Secrets] Runtime secrets cleared")


def get_user_secrets(uid: str) -> UserSecrets:
    return UserSecrets(uid)
