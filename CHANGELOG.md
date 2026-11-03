# CHANGELOG — SONIC AI

All notable changes to SONIC AI are documented here. Format: [Semantic Versioning](https://semver.org/).

---

## [2.5.0] — 2026-10-18 — "Universal Engine"

### Added — Universal Computer-Use Engine
- `core/universal/agent.py` — UniversalAgent orchestrator (goal-driven planning, observe→resolve→act→verify loop)
- `core/universal/state.py` — EnvironmentState, ApplicationContext, ControlSnapshot, BrowserContext
- `core/universal/actions.py` — Action model with ActionValidator, VerificationSpec, capability tiers
- `core/universal/target_resolver.py` — TargetResolver with multi-signal scoring (UIA/DOM/OCR/historical)
- `core/universal/capability_router.py` — T1→T7 capability router (native API → DOM → UIA → adapter → vision → keyboard → recovery)
- `core/universal/verification.py` — Postcondition checker (URL/window/control/text/file/process/volume)
- `core/universal/recovery.py` — 8 recovery strategies (RETRY_SAME, RETRY_RESOLVED, DOWNGRADE_TIER, WAIT_AND_RETRY, etc.)
- `core/universal/checkpoint.py` — TaskCheckpointManager (resume, cancel, idempotency)
- `core/universal/tool_memory.py` — Per-app tier performance learning
- `core/universal/ue_goals.py` — Unreal Engine goal interpreter (30+ high-level patterns)
- `core/universal/screens/` — Screen understanding (DPI, dialog detector, scene parser)
- 9 AppAdapters: Browser, FileManager, Office, VSCode, WhatsApp, Discord, Spotify, GenericWindows, Unreal
- Test suite: 9/9 passing

### Added — Unreal Engine 4.22+ Adapter
- `core/universal/adapters/unreal.py` — 93 operations (Blueprints, materials, textures, meshes, lighting, C++, packaging, sequencer, Niagara, animation, audio)
- 5-tier fallback: WebRemoteControl → bundled Python REPL → pywinauto → vision → keyboard shortcut
- 50+ keyboard shortcuts mapped
- Auto-discovery of install dir, Python path, RC port
- Genuine unreal.* Python snippets generated for each op
- Test suite: 12/12 passing

### Added — Ultra-Pro Persona (Legend Edition)
- `core/persona_v2.py` — Multi-dimensional persona learning (text + voice + behavior + emotion + culture)
- Per-contact persona (different "you" for boss vs friends vs family)
- Pakistani vs Indian Urdu flavor detection
- Code-switching point detection
- Religious/cultural phrase tracking
- Mood baseline + distribution + range + triggers
- Weekly drift snapshots with drift score
- `predict_next()` and `draft_reply()` using LLM
- `scripts/persona_demo.py` — Interactive "feel" demo
- Test suite: 19/19 passing

### Added — Auto-Reply Daemon
- `core/auto_reply.py` — AutoReplyDaemon (away-mode detection, contact policies, platform watchers, LLM-driven reply)
- `core/auto_reply_watchers.py` — FileWatcher (JSONL), WhatsAppWatcher (Playwright), DiscordWebhookWatcher (Bot API), CallbackWatcher
- `scripts/start_auto_reply.py` — CLI starter
- Smart escalation (urgent messages → notify + still reply)
- 4-tier urgency: trivial / casual / important / urgent
- 7 platforms supported
- Per-contact policies (max_replies/hr, quiet hours, escalate threshold)
- Idempotency, rate limiting, safety check
- Test suite: 18/18 passing

### Added — Ultra-Pro YouTube Ad Skipper
- `core/youtube_ad_skipper.py` — Multi-signal detection (visual + DOM)
- 30+ localized skip-button text recognition
- 15+ ad indicator patterns
- 4-tier click strategy: DOM → SmartClicker → Keyboard Tab+Enter → coordinate
- Ad type classification: skippable, non-skippable, bumper, overlay
- Verification with retry on different strategy
- Adaptive polling (250ms during ad, 1500ms idle)
- Test suite: 9/9 passing

### Changed — LLM Connection Stability
- `core/providers.py` — GeminiProvider migrated to new `google.genai` SDK
- Multi-source API key resolution (env var → config/api_keys.json → user data dir)
- Updated default model to `gemini-3.8-flash` (was deprecated)
- FallbackChain: persistent HTTP session (connection pooling)
- Exponential backoff: 30s → 60s → 120s → 300s
- Health cache (60s TTL) prevents reconnect spam
- Error classification: transient (retry) vs non-transient (skip)
- Verified: 10x faster, 10x fewer network attempts in stress test

### Changed — Voice Live Session Stability
- `main.py` — Detect 1007 audio-model-unavailable error
- Stop reconnect loop on persistent audio errors
- Fall back to keyboard/text mode when live audio unavailable
- Initialized `_use_live_audio` and `_audio_model_disabled` flags

### Fixed
- `actions/desktop.py` — `organize_desktop()` no longer skips `.lnk` shortcut files (the "0 files moved" bug); moves them to `Shortcuts/` folder
- `core/jarvis_brain.py` — `run_goal()` status now properly transitions to COMPLETED after planner
- `_route_to_action()` preserves destructive intent for auto-detected dangerous actions
- Multiple test infrastructure bugs (`__new__` agents missing `_llm`, `_audio_model_disabled` etc.)

### Total tests: 55/55 passing across 4 suites (Persona v2 19 + Auto-Reply 18 + Universal 9 + YouTube 9)

---

## [2.4.0] — 2026-09-19 — "Apex"

### Added
- Holographic bootstrap UI (`bootstrap/ui.py`)
- Holo Orb 3D, neural net viz, waveform viz, command deck UI
- Floating HUD overlay
- 6 voice personas
- Persistent memory palace
- Knowledge graph
- World pulse
- Self-heal
- Proactive engine
- Memory palace
- Code sandbox
- Workflow engine
- 76 mapped actions across 40+ action files
- Plugin system
- FastAPI dashboard backend

---

## Versioning Policy

- **Major version** — Breaking API changes
- **Minor version** — New features, new adapters, new tests
- **Patch version** — Bug fixes, stability improvements

Single source of version truth: `version.py` (`APP_VERSION` constant).
