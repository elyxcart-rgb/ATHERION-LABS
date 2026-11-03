"""SONIC AI — Voice Personas.

JARVIS-quality neural voices via Microsoft Edge TTS (free, no API key).
Falls back to SAPI (Microsoft David/Zira) if Edge unavailable.

Public API:
    VoicePersonaManager()
    .list_personas() -> list[str]
    .get_persona_info(name) -> dict
    .set_persona(name) -> persona_name
    .get_persona() -> str
    .speak(text) -> bool               # speaks using current persona
    .speak_as(text, persona) -> bool   # one-off speak with different persona
    .synthesize_to_file(text, path) -> bool   # save to MP3/WAV
    .list_edge_voices(filter_locale=None) -> list  # discover ALL available voices
    .get_stats() -> dict

PERSONAS (zero-impact on existing Notifier/JarvisBrain paths):
    jarvis_male   en-US-GuyNeural        deep, formal, JARVIS-like
    cute_girl     en-US-AnaNeural         young, warm, friendly  ← the new voice
    sweet_aria    en-US-AriaNeural        conversational female
    calm_jenny    en-US-JennyNeural       calm, slow female
    hindi_sara    hi-IN-SwaraNeural       Hindi female (cute)
    urdu_uzma     ur-PK-UzmaNeural        Urdu female
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional


# ═════════════════════════════════════════════════════════════════════════════
# Persona catalogue
# ═════════════════════════════════════════════════════════════════════════════

PERSONAS: dict[str, dict] = {
    "jarvis_male": {
        "voice": "en-US-GuyNeural",
        "rate": "-8%",
        "pitch": "-3Hz",
        "description": "Deep, measured, formal — Tony Stark's JARVIS",
        "gender": "male",
        "locale": "en-US",
        "is_existing": True,
    },
    "cute_girl": {
        "voice": "en-US-AnaNeural",
        "rate": "+5%",
        "pitch": "+8Hz",
        "description": "Young, warm, friendly — natural conversational",
        "gender": "female",
        "locale": "en-US",
        "is_existing": False,
    },
    "sweet_aria": {
        "voice": "en-US-AriaNeural",
        "rate": "+0%",
        "pitch": "+3Hz",
        "description": "Friendly, expressive — Apple-style assistant",
        "gender": "female",
        "locale": "en-US",
        "is_existing": False,
    },
    "calm_jenny": {
        "voice": "en-US-JennyNeural",
        "rate": "-10%",
        "pitch": "-2Hz",
        "description": "Calm, slow, reassuring — late-night mode",
        "gender": "female",
        "locale": "en-US",
        "is_existing": False,
    },
    "hindi_sara": {
        "voice": "hi-IN-SwaraNeural",
        "rate": "+0%",
        "pitch": "+5Hz",
        "description": "Hindi female — natural desi warmth",
        "gender": "female",
        "locale": "hi-IN",
        "is_existing": False,
    },
    "urdu_uzma": {
        "voice": "ur-PK-UzmaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
        "description": "Urdu female — Pakistani conversational",
        "gender": "female",
        "locale": "ur-PK",
        "is_existing": False,
    },
}

DEFAULT_PERSONA = "jarvis_male"


# ═════════════════════════════════════════════════════════════════════════════
# TTS engine wrapper
# ═════════════════════════════════════════════════════════════════════════════

class _EdgeTTS:
    """Wrapper around edge-tts (Microsoft neural voices)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._stats = {"synth": 0, "errors": 0}

    def synth(self, text: str, voice: str, rate: str = "+0%",
              pitch: str = "+0Hz") -> Optional[bytes]:
        """Synthesize text to MP3 bytes using edge-tts."""
        try:
            import edge_tts
        except ImportError:
            self._stats["errors"] += 1
            return None
        with self._lock:
            self._stats["synth"] += 1
        try:
            return asyncio.run(self._do_synth(text, voice, rate, pitch))
        except Exception as e:
            self._stats["errors"] += 1
            return None

    async def _do_synth(self, text: str, voice: str,
                         rate: str, pitch: str) -> Optional[bytes]:
        try:
            import edge_tts
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf) if buf else None
        except Exception:
            return None

    def list_voices(self, locale: Optional[str] = None) -> list[dict]:
        """List all available Edge voices, optionally filtered by locale."""
        try:
            import edge_tts
            voices = asyncio.run(edge_tts.list_voices())
            if locale:
                voices = [v for v in voices
                          if v.get("Locale", "").lower().startswith(locale.lower())]
            return [{
                "name": v.get("ShortName"),
                "gender": v.get("Gender"),
                "locale": v.get("Locale"),
                "friendly": v.get("FriendlyName"),
            } for v in voices]
        except Exception:
            return []

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)


class _SapiTTS:
    """Wrapper around pyttsx3 / SAPI for fully offline fallback."""

    def __init__(self):
        self._engine = None
        self._lock = threading.Lock()
        self._stats = {"synth": 0, "errors": 0}
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            # Try to find a female voice
            for v in self._engine.getProperty("voices"):
                if "female" in (v.name or "").lower() or "zira" in (v.name or "").lower():
                    self._engine.setProperty("voice", v.id)
                    break
        except Exception:
            self._engine = None

    def synth(self, text: str) -> Optional[bytes]:
        """SAPI doesn't easily expose bytes; return None to signal fallback."""
        if self._engine is None:
            return None
        with self._lock:
            self._stats["synth"] += 1
        # SAPI doesn't directly give bytes — use it via the playback helper
        return None  # caller falls back to direct SAPI playback

    def speak_direct(self, text: str) -> bool:
        if self._engine is None:
            return False
        try:
            with self._lock:
                self._engine.say(text)
                self._engine.runAndWait()
            return True
        except Exception as e:
            self._stats["errors"] += 1
            return False

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)


# ═════════════════════════════════════════════════════════════════════════════
# MP3 playback on Windows
# ═════════════════════════════════════════════════════════════════════════════

def _play_mp3(path: str) -> bool:
    """Play MP3 file on Windows using MediaPlayer (WPF). Non-blocking."""
    try:
        # Use Windows MediaPlayer via PowerShell — async playback
        ps_script = (
            f"Add-Type -AssemblyName PresentationCore;"
            f"$p = New-Object System.Windows.Media.MediaPlayer;"
            f"$p.Open([Uri]'{path}');"
            f"$p.Play();"
            f"Start-Sleep -Milliseconds 200;"  # let it start
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        return True
    except Exception:
        return False


def _estimate_audio_duration(text: str, rate: str = "+0%") -> float:
    """Rough estimate of audio duration in seconds (Edge speaks ~150 wpm)."""
    words = len(text.split())
    wpm = 150
    # Adjust for rate: "+10%" → 165, "-10%" → 135
    try:
        rate_pct = int(rate.replace("%", "").replace("+", ""))
        wpm = int(150 * (1 + rate_pct / 100))
    except Exception:
        pass
    return max(1.0, words / wpm * 60)


# ═════════════════════════════════════════════════════════════════════════════
# VoicePersonaManager
# ═════════════════════════════════════════════════════════════════════════════

class VoicePersonaManager:
    """Multi-persona TTS using Edge neural voices with SAPI fallback.

    Existing JARVIS voice (`jarvis_male` / GuyNeural) is the DEFAULT — the
    existing pipeline behavior is preserved 100% when this module is not
    explicitly enabled.
    """

    def __init__(self, default_persona: str = DEFAULT_PERSONA):
        self._persona = default_persona
        self._edge = _EdgeTTS()
        self._sapi = _SapiTTS()
        self._lock = threading.Lock()
        self._stats = {
            "speaks": 0,
            "synths": 0,
            "edge_uses": 0,
            "sapi_uses": 0,
            "errors": 0,
        }

    # ── Public ───────────────────────────────────────────────────────────────

    def list_personas(self) -> list[str]:
        return list(PERSONAS.keys())

    def get_persona_info(self, name: Optional[str] = None) -> dict:
        """Get info for one persona (or current if name is None)."""
        target = name or self._persona
        if target not in PERSONAS:
            target = DEFAULT_PERSONA
        info = dict(PERSONAS[target])
        info["name"] = target
        return info

    def set_persona(self, name: str) -> str:
        """Switch the active persona. Returns the new persona name."""
        if name not in PERSONAS:
            return self._persona
        with self._lock:
            self._persona = name
        return name

    def get_persona(self) -> str:
        return self._persona

    def list_edge_voices(self, locale: Optional[str] = None) -> list[dict]:
        """Discover ALL Microsoft Edge voices (300+ available)."""
        return self._edge.list_voices(locale)

    def speak(self, text: str, blocking: bool = False) -> bool:
        """Speak text using the current persona."""
        return self.speak_as(text, self._persona, blocking=blocking)

    def speak_as(self, text: str, persona: str,
                  blocking: bool = False) -> bool:
        """Speak using a specific persona (one-off override)."""
        if persona not in PERSONAS:
            persona = DEFAULT_PERSONA
        cfg = PERSONAS[persona]
        with self._lock:
            self._stats["speaks"] += 1

        # 1. Try Edge TTS (neural, non-robotic)
        audio = self._edge.synth(
            text, cfg["voice"], rate=cfg["rate"], pitch=cfg["pitch"]
        )
        if audio is not None and len(audio) > 100:
            with self._lock:
                self._stats["edge_uses"] += 1
            # Save + play
            tmp = Path(tempfile.gettempdir()) / f"sonic_tts_{persona}_{int(time.time()*1000)}.mp3"
            try:
                tmp.write_bytes(audio)
                ok = _play_mp3(str(tmp))
                if blocking:
                    duration = _estimate_audio_duration(text, cfg["rate"])
                    time.sleep(duration)
                # Schedule cleanup
                def _cleanup():
                    time.sleep(20)
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass
                threading.Thread(target=_cleanup, daemon=True).start()
                return ok
            except Exception as e:
                with self._lock:
                    self._stats["errors"] += 1
                # fall through to SAPI

        # 2. Fall back to SAPI (offline)
        with self._lock:
            self._stats["sapi_uses"] += 1
        return self._sapi.speak_direct(text)

    def synthesize_to_file(self, text: str, output_path: str,
                            persona: Optional[str] = None) -> bool:
        """Synthesize to a file (MP3). Useful for demos + testing."""
        persona = persona or self._persona
        if persona not in PERSONAS:
            persona = DEFAULT_PERSONA
        cfg = PERSONAS[persona]
        audio = self._edge.synth(text, cfg["voice"],
                                  rate=cfg["rate"], pitch=cfg["pitch"])
        if audio is None or len(audio) < 100:
            return False
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(audio)
            with self._lock:
                self._stats["synths"] += 1
            return True
        except Exception as e:
            with self._lock:
                self._stats["errors"] += 1
            return False

    def preview_persona(self, persona: str) -> str:
        """Return a short preview text for a persona (for UI cards)."""
        previews = {
            "jarvis_male": "Good evening, sir. All systems are operating within normal parameters.",
            "cute_girl":   "Hi there! I'm Ana — let's get things done together, shall we?",
            "sweet_aria":  "Hey! Aria here. What can I help you with today?",
            "calm_jenny":  "Take a deep breath. Everything is going to be just fine.",
            "hindi_sara":  "Namaste! Main Swara hoon. Aap kaise hain aaj?",
            "urdu_uzma":   "Assalam-o-Alaikum! Main Uzma hoon. Kya haal hain aap ke?",
        }
        return previews.get(persona, "Hello, I'm SONIC.")

    def get_stats(self) -> dict:
        with self._lock:
            stats = dict(self._stats)
            stats["current_persona"] = self._persona
            stats["edge_stats"] = self._edge.get_stats()
            stats["sapi_stats"] = self._sapi.get_stats()
            return stats
