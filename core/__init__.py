"""SONIC AI Core services.

Modules:
  plugin_loader   — plugin discovery, validation, and dispatch
  plugin_verifier — plugin trust and permission verification
  undo            — shared undo stack for reversible actions
  confirm         — human-confirmation gate for destructive actions
  audio_devices   — microphone and speaker selection
  tts             — text-to-speech engines (EdgeTTS, Kokoro, ElevenLabs)
  stt             — speech-to-text engines (Whisper, Vosk)
  llm_client      — local LLM client (Ollama, OpenAI-compatible)
  providers       — LLM provider abstraction (Gemini, OpenAI, local, fallback)
  self_improve    — self-improvement engine (learns from interactions)
  installer       — dependency auto-installer
  prompt          — system prompt management
"""
from .plugin_loader import discover_plugins, PluginRecord, PluginRegistry
from .undo import push_undo, undo_last, can_undo, peek, history, clear as undo_clear
from .confirm import request as confirm_request, resolve as confirm_resolve
from .audio_devices import (
    list_devices, resolve as resolve_device,
    configure, prefetch,
)
from .llm_client import (
    call_llm, call_llm_text, call_llm_stream,
    ensure_ollama_running, warmup_model, check_model_available, get_llm_settings,
)
from .providers import (
    LLMProvider, LLMResponse, GeminiProvider, OpenAIProvider,
    LocalProvider, CachedProvider, FallbackChain, get_default_chain,
)
from .self_improve import (
    log_tool_usage, get_tool_stats,
    log_correction, get_corrections, get_correction_patterns,
    log_performance, get_performance,
    log_pattern, get_patterns, generate_improvement_report,
    self_improve,
)
from .installer import install_for_config
from .tts import TTSPlayer, EdgeTTSEngine, KokoroTTSEngine, ElevenLabsTTSEngine, create_tts_player
from .stt import WhisperSTT, VoskSTT

__all__ = [
    "discover_plugins", "PluginRecord", "PluginRegistry",
    "push_undo", "undo_last", "can_undo", "peek", "history", "undo_clear",
    "confirm_request", "confirm_resolve",
    "list_devices", "resolve_device", "configure", "prefetch",
    "call_llm", "call_llm_text", "call_llm_stream",
    "ensure_ollama_running", "warmup_model", "check_model_available", "get_llm_settings",
    "LLMProvider", "LLMResponse", "GeminiProvider", "OpenAIProvider",
    "LocalProvider", "CachedProvider", "FallbackChain", "get_default_chain",
    "log_tool_usage", "get_tool_stats",
    "log_correction", "get_corrections", "get_correction_patterns",
    "log_performance", "get_performance",
    "log_pattern", "get_patterns", "generate_improvement_report",
    "self_improve",
    "install_for_config",
    "TTSPlayer", "EdgeTTSEngine", "KokoroTTSEngine", "ElevenLabsTTSEngine", "create_tts_player",
    "WhisperSTT", "VoskSTT",
]
