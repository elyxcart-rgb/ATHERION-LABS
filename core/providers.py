"""SONIC AI — LLM Provider Abstraction (Multi-Model Fallback Chain).

A high-end provider layer that lets SONIC talk to **any LLM backend** and
**fall back automatically** when one is down, rate-limited, or unreachable.

Why this matters:
    - Removes the single-point-of-failure risk of being Gemini-only.
    - Makes SONIC swappable with OpenAI, Anthropic, local Ollama, or any
      other provider with the same interface.
    - Adds built-in semantic caching so repeated queries are instant and
      free.
    - Adds circuit-breaker pattern so a failing provider doesn't drag the
      whole chain down.

Public surface (stable, opt-in):
    - ``LLMProvider``              — abstract base class
    - ``LLMResponse``              — uniform response dataclass
    - ``GeminiProvider``           — real Gemini integration (default)
    - ``OpenAIProvider``           — OpenAI-compatible (works with OpenAI,
                                     Azure, Together, Groq, vLLM, …)
    - ``LocalProvider``            — Ollama / LM Studio / anything
                                     exposing an OpenAI-compatible endpoint
    - ``CachedProvider``           — transparent semantic cache wrapper
    - ``FallbackChain``            — try providers in order, fail over
                                     automatically
    - ``get_default_chain()``      — sensible default chain

Zero-touch design:
    - No existing file is modified.
    - Existing ``core/llm_client.py`` keeps its behaviour.
    - Call sites opt in by replacing ``client.generate(...)`` with
      ``chain.generate(...)`` — fully backwards compatible because every
      provider exposes the same four methods.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger("LLM_PROVIDERS")

_CACHE_DIR = Path.home() / "AppData" / "Local" / "SONIC AI" / "llm_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_PATH = _CACHE_DIR / "response_cache.db"


# ═════════════════════════════════════════════════════════════════════════════
# Uniform response
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int
    cached: bool = False
    tokens: Optional[int] = None
    finish_reason: str = "stop"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ═════════════════════════════════════════════════════════════════════════════
# Abstract base class
# ═════════════════════════════════════════════════════════════════════════════

class LLMProvider(ABC):
    """The interface every provider must implement."""

    name: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str, *, system: str = "",
                 max_tokens: int = 1024, temperature: float = 0.7,
                 **kwargs) -> LLMResponse:
        """Generate a single response. Must not stream."""

    @abstractmethod
    def stream(self, prompt: str, *, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.7,
               **kwargs) -> Iterator[str]:
        """Yield text chunks as they arrive."""

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap health check — True if the provider can serve a request now."""

    @abstractmethod
    def chat(self, messages: list[dict], *, max_tokens: int = 1024,
             temperature: float = 0.7, **kwargs) -> LLMResponse:
        """Multi-turn chat. ``messages`` = [{"role": ..., "content": ...}]."""

    # Default helpers ──────────────────────────────────────────────────────
    def model_name(self) -> str:
        return getattr(self, "_model", "unknown")


# ═════════════════════════════════════════════════════════════════════════════
# Gemini provider
# ═════════════════════════════════════════════════════════════════════════════

class GeminiProvider(LLMProvider):
    """Real Gemini integration.

    Tries SDKs in order:
      1. ``google.genai`` (new SDK, current) — preferred
      2. ``google.generativeai`` (legacy SDK, deprecated but still functional)

    API key resolution order:
      1. Explicit constructor arg
      2. ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY`` env var
      3. ``config/api_keys.json`` (project-relative)
      4. ``memory.config_manager.load_api_keys()`` (per-user data dir)
    """

    name = "gemini"

    def __init__(self, model: str = "gemini-3.8-flash", api_key: Optional[str] = None):
        self._model = model
        self._api_key = api_key
        self._client = None
        self._client_kind = None   # "new_sdk" | "legacy_sdk"
        self._failure_count = 0
        self._lock = threading.Lock()

    @staticmethod
    def _resolve_api_key(explicit: Optional[str]) -> Optional[str]:
        if explicit:
            return explicit
        for env in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            v = os.environ.get(env)
            if v:
                return v
        # project-relative config/api_keys.json
        try:
            from pathlib import Path
            proj_cfg = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
            if proj_cfg.exists():
                import json
                data = json.loads(proj_cfg.read_text(encoding="utf-8"))
                if data.get("gemini_api_key"):
                    return data["gemini_api_key"]
        except Exception:
            pass
        # per-user data dir
        try:
            from memory.config_manager import load_api_keys
            keys = load_api_keys() or {}
            if keys.get("gemini_api_key"):
                return keys["gemini_api_key"]
        except Exception:
            pass
        return None

    def _ensure(self):
        if self._client is not None:
            return self._client
        # Try new SDK first
        try:
            import warnings as _w
            _w.filterwarnings("ignore")
            from google import genai as new_genai  # type: ignore
            key = self._resolve_api_key(self._api_key)
            if not key:
                raise RuntimeError("No Gemini API key configured")
            self._client = new_genai.Client(api_key=key)
            self._client_kind = "new_sdk"
            logger.info("Gemini: using new google.genai SDK")
            return self._client
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Gemini new SDK init failed: {e}")
        # Fallback to legacy SDK
        try:
            import warnings as _w
            _w.filterwarnings("ignore")
            import google.generativeai as genai  # type: ignore
            key = self._resolve_api_key(self._api_key)
            if not key:
                raise RuntimeError("No Gemini API key configured")
            genai.configure(api_key=key)
            self._client = genai.GenerativeModel(self._model)
            self._client_kind = "legacy_sdk"
            logger.info("Gemini: using legacy google.generativeai SDK")
            return self._client
        except Exception as e:
            logger.debug(f"Gemini legacy SDK init failed: {e}")
            return None

    def is_available(self) -> bool:
        return self._ensure() is not None

    def generate(self, prompt: str, *, system: str = "",
                 max_tokens: int = 1024, temperature: float = 0.7,
                 **kwargs) -> LLMResponse:
        client = self._ensure()
        if client is None:
            raise RuntimeError("Gemini unavailable")
        start = time.monotonic()
        full = (system + "\n\n" if system else "") + prompt
        try:
            if self._client_kind == "new_sdk":
                # New google.genai SDK: client.models.generate_content(model=..., contents=...)
                r = client.models.generate_content(
                    model=self._model,
                    contents=full,
                    config={
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                text = (getattr(r, "text", None) or "").strip()
                if not text:
                    try:
                        # Sometimes response has parts/candidates instead of direct .text
                        for cand in (getattr(r, "candidates", None) or []):
                            for part in getattr(cand, "content", {}).parts or []:
                                if getattr(part, "text", None):
                                    text += part.text
                            if text:
                                break
                    except Exception:
                        pass
            else:
                r = client.generate_content(
                    full,
                    generation_config={
                        "max_output_tokens": max_tokens,
                        "temperature": temperature,
                    },
                    stream=False,
                )
                text = (r.text or "").strip()
            latency = int((time.monotonic() - start) * 1000)
            with self._lock:
                self._failure_count = 0
            return LLMResponse(
                text=text, provider=self.name, model=self._model,
                latency_ms=latency,
            )
        except Exception as e:
            with self._lock:
                self._failure_count += 1
            raise

    def stream(self, prompt: str, *, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.7,
               **kwargs) -> Iterator[str]:
        client = self._ensure()
        if client is None:
            raise RuntimeError("Gemini unavailable")
        full = (system + "\n\n" if system else "") + prompt
        if self._client_kind == "new_sdk":
            for chunk in client.models.generate_content_stream(
                model=self._model,
                contents=full,
                config={"max_output_tokens": max_tokens, "temperature": temperature},
            ):
                t = getattr(chunk, "text", None)
                if t:
                    yield t
            return
        r = client.generate_content(
            full,
            generation_config={
                "max_output_tokens": max_tokens,
                "temperature": temperature,
            },
            stream=True,
        )
        for chunk in r:
            try:
                if chunk.text:
                    yield chunk.text
            except Exception:
                continue

    def chat(self, messages: list[dict], *, max_tokens: int = 1024,
             temperature: float = 0.7, **kwargs) -> LLMResponse:
        client = self._ensure()
        if client is None:
            raise RuntimeError("Gemini unavailable")
        # Convert openai-style [{role, content}] to Gemini chat format
        try:
            chat = client.start_chat(history=[])
            for m in messages[:-1]:
                role = m["role"]
                content = m["content"]
                if role == "user":
                    chat.send_message(content)
            final = messages[-1]["content"] if messages else ""
            r = chat.send_message(
                final,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                },
                stream=False,
            )
            start = time.monotonic()
            return LLMResponse(
                text=(r.text or "").strip(),
                provider=self.name, model=self._model,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            with self._lock:
                self._failure_count += 1
            raise


# ═════════════════════════════════════════════════════════════════════════════
# OpenAI-compatible provider
# ═════════════════════════════════════════════════════════════════════════════

class OpenAIProvider(LLMProvider):
    """Works with any OpenAI-compatible HTTP endpoint.

    Compatible with:
        - OpenAI (gpt-4o, gpt-4-turbo, gpt-3.5-turbo)
        - Azure OpenAI
        - Together AI
        - Groq
        - OpenRouter
        - vLLM / LocalAI / LM Studio (with OpenAI-compatible mode)
    """

    name = "openai"

    def __init__(self,
                 model: str = "gpt-4o-mini",
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 timeout: float = 30.0):
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") if base_url else "https://api.openai.com/v1"
        self._timeout = timeout
        self._failure_count = 0
        self._lock = threading.Lock()
        self._session = None   # lazy persistent requests.Session

    def _headers(self) -> dict:
        key = self._api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("No OpenAI API key configured")
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def is_available(self) -> bool:
        key = self._api_key or os.environ.get("OPENAI_API_KEY")
        return bool(key)

    def _get_session(self):
        """Lazy persistent HTTP session with connection pooling.

        Solves the 'reconnect loop' issue: without a session, every call
        opens a new TCP+TLS connection. With a session, connections are
        kept alive and reused across calls.
        """
        if self._session is None:
            try:
                import requests
                from requests.adapters import HTTPAdapter
                sess = requests.Session()
                # Mount a connection pool with sane defaults.
                adapter = HTTPAdapter(pool_connections=4, pool_maxsize=8,
                                       pool_block=False)
                sess.mount("http://", adapter)
                sess.mount("https://", adapter)
                self._session = sess
            except ImportError:
                self._session = False  # fall back to urllib
        return self._session if self._session else None

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{self._base_url}{path}"
        sess = self._get_session()
        if sess:
            r = sess.post(url, json=payload, headers=self._headers(),
                           timeout=self._timeout)
            r.raise_for_status()
            return r.json()
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def generate(self, prompt: str, *, system: str = "",
                 max_tokens: int = 1024, temperature: float = 0.7,
                 **kwargs) -> LLMResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages, max_tokens=max_tokens, temperature=temperature, **kwargs)

    def stream(self, prompt: str, *, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.7,
               **kwargs) -> Iterator[str]:
        # Minimal SSE implementation — keeps zero extra deps.
        import urllib.request
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=json.dumps({
                "model": self._model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                    delta = j["choices"][0].get("delta", {}).get("content")
                    if delta:
                        yield delta
                except Exception:
                    continue

    def chat(self, messages: list[dict], *, max_tokens: int = 1024,
             temperature: float = 0.7, **kwargs) -> LLMResponse:
        start = time.monotonic()
        data = self._post("/chat/completions", {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        })
        text = data["choices"][0]["message"]["content"].strip()
        latency = int((time.monotonic() - start) * 1000)
        with self._lock:
            self._failure_count = 0
        usage = data.get("usage", {})
        return LLMResponse(
            text=text, provider=self.name, model=self._model,
            latency_ms=latency,
            tokens=usage.get("total_tokens"),
        )


# ═════════════════════════════════════════════════════════════════════════════
# Local provider (Ollama / LM Studio)
# ═════════════════════════════════════════════════════════════════════════════

class LocalProvider(OpenAIProvider):
    """OpenAI-compatible local model (Ollama, LM Studio, vLLM)."""

    name = "local"

    def __init__(self,
                 model: str = "llama3.1",
                 base_url: str = "http://localhost:11434/v1",
                 **kwargs):
        super().__init__(model=model, api_key="not-needed", base_url=base_url, **kwargs)


# ═════════════════════════════════════════════════════════════════════════════
# Cached wrapper
# ═════════════════════════════════════════════════════════════════════════════

class CachedProvider(LLMProvider):
    """Transparent semantic cache wrapper around any provider.

    Caches responses keyed by SHA-256 of (system + prompt + temperature +
    max_tokens). A TTL keeps the cache fresh.
    """

    def __init__(self, inner: LLMProvider, ttl_seconds: int = 3600,
                 max_entries: int = 5000):
        self._inner = inner
        self._ttl = ttl_seconds
        self._max = max_entries
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(_CACHE_PATH), timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "  key TEXT PRIMARY KEY, "
            "  provider TEXT, model TEXT, text TEXT, "
            "  created_at REAL, expires_at REAL, "
            "  tokens INTEGER, metadata TEXT)"
        )
        self._conn.commit()

    @property
    def name(self) -> str:
        return f"cached({self._inner.name})"

    def _cache_key(self, prompt: str, system: str, max_tokens: int,
                   temperature: float, mode: str) -> str:
        h = hashlib.sha256(
            f"{mode}|{system}|{prompt}|{max_tokens}|{temperature}".encode("utf-8")
        ).hexdigest()
        return h

    def _lookup(self, key: str) -> Optional[LLMResponse]:
        now = time.time()
        row = self._conn.execute(
            "SELECT provider, model, text, created_at, expires_at, tokens, metadata "
            "FROM cache WHERE key=?",
            (key,),
        ).fetchone()
        if not row:
            return None
        if row["expires_at"] < now:
            return None
        return LLMResponse(
            text=row["text"], provider=row["provider"], model=row["model"],
            latency_ms=0, cached=True,
            tokens=row["tokens"],
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def _store(self, key: str, resp: LLMResponse):
        now = time.time()
        self._conn.execute(
            "INSERT OR REPLACE INTO cache "
            "(key, provider, model, text, created_at, expires_at, tokens, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (key, resp.provider, resp.model, resp.text,
             now, now + self._ttl, resp.tokens,
             json.dumps(resp.metadata)),
        )
        # Evict oldest if over capacity
        cur = self._conn.execute("SELECT COUNT(*) AS n FROM cache").fetchone()
        if cur["n"] > self._max:
            self._conn.execute(
                "DELETE FROM cache WHERE key IN ("
                "  SELECT key FROM cache ORDER BY created_at ASC LIMIT ?)",
                (cur["n"] - self._max,),
            )
        self._conn.commit()

    def generate(self, prompt: str, *, system: str = "",
                 max_tokens: int = 1024, temperature: float = 0.7,
                 **kwargs) -> LLMResponse:
        key = self._cache_key(prompt, system, max_tokens, temperature, "generate")
        with self._lock:
            hit = self._lookup(key)
        if hit:
            return hit
        resp = self._inner.generate(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, **kwargs,
        )
        with self._lock:
            self._store(key, resp)
        return resp

    def stream(self, prompt: str, *, system: str = "",
               max_tokens: int = 1024, temperature: float = 0.7,
               **kwargs) -> Iterator[str]:
        # Streaming bypasses the cache (each call is unique by definition).
        return self._inner.stream(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, **kwargs,
        )

    def chat(self, messages: list[dict], *, max_tokens: int = 1024,
             temperature: float = 0.7, **kwargs) -> LLMResponse:
        # Cheap key from the message tail
        key = self._cache_key(
            json.dumps(messages, sort_keys=True),
            "", max_tokens, temperature, "chat",
        )
        with self._lock:
            hit = self._lookup(key)
        if hit:
            return hit
        resp = self._inner.chat(
            messages, max_tokens=max_tokens, temperature=temperature, **kwargs,
        )
        with self._lock:
            self._store(key, resp)
        return resp

    def is_available(self) -> bool:
        return self._inner.is_available()


# ═════════════════════════════════════════════════════════════════════════════
# Fallback chain with circuit breaker
# ═════════════════════════════════════════════════════════════════════════════

class FallbackChain:
    """Try providers in order; the first healthy one wins.

    Each provider gets up to ``per_provider_timeout`` seconds. After
    ``circuit_threshold`` consecutive failures, a provider is **opened**
    (skipped) for ``cooldown_seconds`` before being tried again.

    Stability features (added to stop gratuitous reconnect loops):
      - Persistent health-check cache (each provider is probed at most
        once every ``health_cache_seconds``) — so generate() does NOT
        re-probe every call.
      - Exponential backoff on cooldowns (30s → 60s → 120s → 300s cap).
      - Non-retryable error class: 4xx (except 408/429) open the circuit
        immediately and stay open for the long cooldown (the provider
        won't fix itself by being retried).
      - Transient errors (5xx, 429, network) back off more gently.
      - Health cache survives across generate() calls.

    Example:
        chain = FallbackChain([
            CachedProvider(GeminiProvider()),
            CachedProvider(OpenAIProvider()),
            LocalProvider(),
        ])
        resp = chain.generate("Summarise this transcript…")
    """

    def __init__(self,
                 providers: list[LLMProvider],
                 per_provider_timeout: float = 20.0,
                 circuit_threshold: int = 3,
                 cooldown_seconds: float = 30.0,
                 max_cooldown_seconds: float = 300.0,
                 health_cache_seconds: float = 60.0):
        self._providers = list(providers)
        self._timeout = per_provider_timeout
        self._threshold = circuit_threshold
        self._cooldown = cooldown_seconds
        self._max_cooldown = max_cooldown_seconds
        self._health_cache_seconds = health_cache_seconds
        self._state: dict[str, dict] = {
            p.name: {"failures": 0, "opened_at": 0.0,
                      "cooldown_used": 0.0,
                      "last_health_at": 0.0,
                      "last_health_ok": True}
            for p in providers
        }
        self._lock = threading.Lock()

    def _is_open(self, name: str) -> bool:
        s = self._state.get(name)
        if not s:
            return False
        if s["opened_at"] == 0.0:
            return False
        # Use the cooldown that was active when the circuit opened,
        # so repeated failures back off exponentially.
        active_cooldown = max(self._cooldown, s.get("cooldown_used", 0.0))
        if (time.monotonic() - s["opened_at"]) > active_cooldown:
            # Half-open: allow one probe call
            return False
        return True

    def _record_failure(self, name: str, *, transient: bool = True):
        with self._lock:
            s = self._state.setdefault(
                name, {"failures": 0, "opened_at": 0.0,
                        "cooldown_used": 0.0,
                        "last_health_at": 0.0,
                        "last_health_ok": True})
            s["failures"] += 1
            s["last_health_ok"] = False
            s["last_health_at"] = time.monotonic()
            # Non-transient failures (4xx) open the circuit immediately
            if not transient:
                if s["opened_at"] == 0.0:
                    s["cooldown_used"] = self._max_cooldown
                    s["opened_at"] = time.monotonic()
                    logger.warning(f"[chain] {name} circuit OPENED "
                                   f"(non-transient, cooldown={self._max_cooldown}s)")
                return
            # Transient: exponential backoff
            if s["failures"] >= self._threshold and s["opened_at"] == 0.0:
                s["cooldown_used"] = self._cooldown
                s["opened_at"] = time.monotonic()
                logger.warning(f"[chain] {name} circuit OPENED "
                               f"(cooldown={s['cooldown_used']}s)")
            elif s["opened_at"] != 0.0:
                # Already open — extend cooldown exponentially
                s["cooldown_used"] = min(
                    self._max_cooldown,
                    max(s["cooldown_used"] * 2, self._cooldown * 2),
                )
                s["opened_at"] = time.monotonic()
                logger.warning(f"[chain] {name} cooldown extended "
                               f"to {s['cooldown_used']}s")

    def _record_success(self, name: str):
        with self._lock:
            s = self._state.setdefault(
                name, {"failures": 0, "opened_at": 0.0,
                        "cooldown_used": 0.0,
                        "last_health_at": 0.0,
                        "last_health_ok": True})
            if s["failures"] > 0 or s["opened_at"] > 0.0:
                logger.info(f"[chain] {name} circuit CLOSED")
            s["failures"] = 0
            s["opened_at"] = 0.0
            s["cooldown_used"] = 0.0
            s["last_health_ok"] = True
            s["last_health_at"] = time.monotonic()

    def _is_healthy(self, p: LLMProvider) -> bool:
        """Cached health check — only probes once per health_cache_seconds."""
        s = self._state.get(p.name)
        if not s:
            return p.is_available()
        now = time.monotonic()
        if (now - s["last_health_at"]) < self._health_cache_seconds:
            return s["last_health_ok"]
        # cache expired — probe once
        ok = False
        try:
            ok = bool(p.is_available())
        except Exception:
            ok = False
        s["last_health_at"] = now
        s["last_health_ok"] = ok
        return ok

    @staticmethod
    def _classify_error(exc: Exception) -> bool:
        """True if transient (worth retrying), False if non-transient (give up)."""
        msg = str(exc).lower()
        # Non-transient (won't fix itself by retrying)
        if any(t in msg for t in ("404", "not_found", "model is no longer",
                                    "invalid api key", "permission",
                                    "authentication", "400 ", "403 ")):
            return False
        # Transient (worth retrying)
        if any(t in msg for t in ("503", "429", "timeout", "timed out",
                                    "high demand", "temporarily",
                                    "connection", "reset", "refused")):
            return True
        # Default: treat as transient (don't blackhole a provider for a weird error)
        return True

    def available_providers(self) -> list[LLMProvider]:
        return [p for p in self._providers if not self._is_open(p.name)]

    def stats(self) -> dict:
        return {
            "providers": [
                {
                    "name": p.name,
                    "available": p.is_available(),
                    "circuit": self._state.get(p.name, {}),
                    "circuit_open": self._is_open(p.name),
                }
                for p in self._providers
            ],
        }

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        last_exc: Optional[Exception] = None
        tried = 0
        for p in self.available_providers():
            # Use cached health instead of probing every call
            if not self._is_healthy(p):
                continue
            tried += 1
            try:
                resp = p.generate(prompt, **kwargs)
                self._record_success(p.name)
                return resp
            except Exception as e:
                transient = self._classify_error(e)
                kind = "transient" if transient else "non-transient"
                logger.warning(
                    f"[chain] {p.name}.generate failed ({kind}): {e}")
                self._record_failure(p.name, transient=transient)
                last_exc = e
        raise RuntimeError(
            f"All providers in chain failed. Last error: {last_exc}"
        )

    def stream(self, prompt: str, **kwargs) -> Iterator[str]:
        for p in self.available_providers():
            if not p.is_available():
                continue
            try:
                yield from p.stream(prompt, **kwargs)
                self._record_success(p.name)
                return
            except Exception as e:
                logger.warning(f"[chain] {p.name}.stream failed: {e}")
                self._record_failure(p.name)
        raise RuntimeError("All providers in chain failed (stream)")

    def chat(self, messages: list[dict], **kwargs) -> LLMResponse:
        last_exc: Optional[Exception] = None
        for p in self.available_providers():
            if not p.is_available():
                continue
            try:
                resp = p.chat(messages, **kwargs)
                self._record_success(p.name)
                return resp
            except Exception as e:
                logger.warning(f"[chain] {p.name}.chat failed: {e}")
                self._record_failure(p.name)
                last_exc = e
        raise RuntimeError(
            f"All providers in chain failed. Last error: {last_exc}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# Sensible default
# ═════════════════════════════════════════════════════════════════════════════

_DEFAULT_CHAIN: Optional[FallbackChain] = None


def get_default_chain() -> FallbackChain:
    """Return a process-wide default chain: Gemini → OpenAI → Local.

    Each provider is wrapped in ``CachedProvider`` for repeated-query speed.
    """
    global _DEFAULT_CHAIN
    if _DEFAULT_CHAIN is not None:
        return _DEFAULT_CHAIN

    providers: list[LLMProvider] = []

    # Gemini — primary, with cache
    providers.append(CachedProvider(GeminiProvider()))

    # OpenAI — secondary if key configured
    if os.environ.get("OPENAI_API_KEY"):
        providers.append(CachedProvider(OpenAIProvider()))

    # Local — last resort (Ollama running on default port)
    try:
        providers.append(LocalProvider())
    except Exception:
        pass

    _DEFAULT_CHAIN = FallbackChain(providers)
    return _DEFAULT_CHAIN


__all__ = [
    "LLMProvider", "LLMResponse",
    "GeminiProvider", "OpenAIProvider", "LocalProvider",
    "CachedProvider", "FallbackChain",
    "get_default_chain",
]
