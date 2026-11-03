"""SONIC AI Memory — long-term brain with SQLite, FTS5 search, and cloud sync.

Key modules:
  memory_manager  — legacy JSON bridge + primary public API
  db              — SQLite storage layer with FTS5
  models          — data classes and enums
  extractor       — extract facts from conversations
  retrieval       — rank memories by relevance
  consolidation   — dedup, conflict resolution, decay
  context_builder — assemble prompt context
  patterns        — behaviour pattern recognition
  semantic        — semantic search engine
  cloud_sync      — Firestore bridge
  config_manager  — API keys, voice, device settings
"""
from .models import (
    Memory, MemoryType, Importance, Confidence, MemoryStatus, Preference,
)
from .memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    save_session_summary, pop_last_session,
    search_memory, set_trim_notifier,
    init_memory_system, set_user_id, get_user_id,
    handle_remember, handle_forget, handle_memory_query,
    extract_from_turn, build_prompt_context, consolidate_memory,
    get_memory_stats,
)
from .config_manager import (
    get_brief_enabled, get_voice, get_input_device, get_output_device,
)

__all__ = [
    "Memory", "MemoryType", "Importance", "Confidence", "MemoryStatus", "Preference",
    "load_memory", "update_memory", "format_memory_for_prompt",
    "save_session_summary", "pop_last_session",
    "search_memory", "set_trim_notifier",
    "init_memory_system", "set_user_id", "get_user_id",
    "handle_remember", "handle_forget", "handle_memory_query",
    "extract_from_turn", "build_prompt_context", "consolidate_memory",
    "get_memory_stats",
    "get_brief_enabled", "get_voice", "get_input_device", "get_output_device",
]
