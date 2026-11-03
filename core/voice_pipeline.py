"""SONIC AI — Voice Pipeline.

Complete bidirectional voice loop: wake word → listen → transcribe (STT)
→ route to action → execute → speak response (TTS). This is the JARVIS talk
loop.

Public API:
    VoicePipeline(brain: JarvisBrain)
    .start()    # starts background listen loop
    .stop()
    .is_listening -> bool
    .push_audio(audio_bytes or array)    # push from any source
    .on_wake(fn)        # called when wake word detected
    .on_transcript(fn)  # called when STT gets text
    .on_response(fn)    # called when SONIC responds
    .get_stats()
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Callable, Any


# ═════════════════════════════════════════════════════════════════════════════
# State
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class PipelineState:
    listening: bool = False
    last_wake_at: float = 0.0
    last_stt_text: str = ""
    last_response: str = ""
    interactions: int = 0
    wake_words: int = 0
    errors: int = 0


# ═════════════════════════════════════════════════════════════════════════════
# Voice Pipeline
# ═════════════════════════════════════════════════════════════════════════════

class VoicePipeline:
    """Continuous voice conversation loop."""

    WAKE_WORDS = {
        "jarvis", "hey sonic", "hey sonics", "ok sonic", "okay sonic",
        "sonic", "hey assistant", "computer", "at your service",
    }
    END_PHRASES = {"goodbye", "bye", "thanks that's all", "thanks that's it",
                   "stop listening", "go to sleep"}

    def __init__(self, brain, stt_fn: Optional[Callable[[bytes], str]] = None,
                 tts_fn: Optional[Callable[[str], None]] = None,
                 wake_word: str = "jarvis"):
        """Args:
            brain:      A JarvisBrain instance to route actions through.
            stt_fn:     Speech-to-text function. audio_bytes -> str.
                        Defaults to a stub that reads from a queue.
            tts_fn:     Text-to-speech function. str -> None.
                        Defaults to Notifier.speak.
            wake_word:  Custom wake word (default 'jarvis').
        """
        self._brain = brain
        self._stt = stt_fn
        self._tts = tts_fn or self._default_tts
        self._wake = wake_word.lower()

        self._state = PipelineState()
        self._lock = threading.RLock()
        self._audio_queue: deque = deque(maxlen=8)
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Subscriber callbacks
        self._cb_wake: list[Callable[[str], None]] = []
        self._cb_transcript: list[Callable[[str], None]] = []
        self._cb_response: list[Callable[[str], None]] = []

        # Try to wire notifier for TTS
        try:
            from core.notify import Notifier
            self._notifier = Notifier()
        except Exception:
            self._notifier = None

    # ── Public ───────────────────────────────────────────────────────────────

    @property
    def is_listening(self) -> bool:
        with self._lock:
            return self._state.listening

    @property
    def state(self) -> PipelineState:
        with self._lock:
            return PipelineState(**asdict(self._state))

    def start(self):
        """Start the background listening loop."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._state.listening = True
        self._thread = threading.Thread(
            target=self._run_loop, name="sonic-voice-loop", daemon=True
        )
        self._thread.start()

    def stop(self):
        with self._lock:
            self._running = False
            self._state.listening = False

    def push_audio(self, audio):
        """Push raw audio samples for processing."""
        self._audio_queue.append(audio)

    def push_transcript(self, text: str):
        """Push already-transcribed text (e.g. from external STT)."""
        with self._lock:
            self._state.last_stt_text = text
        if self._detect_wake(text):
            self._on_wake(text)
            self._process(text)
        elif self._detect_end(text):
            self._on_end(text)
        else:
            # Already in conversation mode? Process.
            if self._in_conversation:
                self._process(text)

    def on_wake(self, fn: Callable[[str], None]):
        self._cb_wake.append(fn)

    def on_transcript(self, fn: Callable[[str], None]):
        self._cb_transcript.append(fn)

    def on_response(self, fn: Callable[[str], None]):
        self._cb_response.append(fn)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "listening": self._state.listening,
                "wake_count": self._state.wake_words,
                "interactions": self._state.interactions,
                "errors": self._state.errors,
                "last_wake_ago_s": (
                    time.time() - self._state.last_wake_at
                    if self._state.last_wake_at else None
                ),
                "audio_queue_size": len(self._audio_queue),
            }

    # ── Internals ────────────────────────────────────────────────────────────

    def _run_loop(self):
        """Background loop: poll audio, run STT, process."""
        while self._running:
            try:
                # 1. Drain audio queue
                audio_chunks = []
                while self._audio_queue:
                    audio_chunks.append(self._audio_queue.popleft())

                if not audio_chunks:
                    time.sleep(0.05)
                    continue

                # 2. STT
                if self._stt:
                    try:
                        audio_bytes = b"".join(
                            a if isinstance(a, bytes) else bytes(a)
                            for a in audio_chunks
                        )
                        text = self._stt(audio_bytes).strip()
                    except Exception as e:
                        text = ""
                        with self._lock:
                            self._state.errors += 1
                else:
                    text = ""

                if not text:
                    continue

                # 3. Notify subscribers
                for cb in self._cb_transcript:
                    try:
                        cb(text)
                    except Exception:
                        pass

                # 4. Check wake word or conversation
                with self._lock:
                    self._state.last_stt_text = text

                if self._detect_wake(text):
                    self._on_wake(text)
                    self._process(text)
                elif self._detect_end(text):
                    self._on_end(text)
                elif self._in_conversation:
                    self._process(text)

            except Exception:
                with self._lock:
                    self._state.errors += 1
                time.sleep(0.1)

    def _detect_wake(self, text: str) -> bool:
        t = text.lower().strip()
        for w in self.WAKE_WORDS:
            if w in t:
                return True
        if self._wake in t:
            return True
        return False

    def _detect_end(self, text: str) -> bool:
        t = text.lower().strip()
        return any(p in t for p in self.END_PHRASES)

    def _on_wake(self, text: str):
        with self._lock:
            self._state.last_wake_at = time.time()
            self._state.wake_words += 1
            self._in_conversation = True
        for cb in self._cb_wake:
            try:
                cb(text)
            except Exception:
                pass

    def _on_end(self, text: str):
        self._in_conversation = False

    def _process(self, text: str):
        """Send text to the brain and speak the response."""
        with self._lock:
            self._state.interactions += 1
        # Strip wake word from text
        cleaned = text
        for w in self.WAKE_WORDS | {self._wake}:
            cleaned = re.sub(w, "", cleaned, flags=re.IGNORECASE).strip()
        if not cleaned:
            cleaned = "hello"
        try:
            result = self._brain.think(cleaned)
            response = result.response
        except Exception as e:
            response = f"Sorry, I encountered an error: {e}"
            with self._lock:
                self._state.errors += 1
        with self._lock:
            self._state.last_response = response
        for cb in self._cb_response:
            try:
                cb(response)
            except Exception:
                pass
        try:
            self._tts(response)
        except Exception:
            pass

    def _default_tts(self, text: str):
        if self._notifier is not None:
            self._notifier.speak(text)
        else:
            print(f"[JARVIS] {text}")
