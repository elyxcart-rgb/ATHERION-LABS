## SONIC Apex v2.5.0 — Universal Computer-Use Engine

### Universal Computer-Use Engine (`core/universal/` — 17 files)
- **UniversalAgent** — goal-driven `observe → resolve → act → verify → recover` loop. No hardcoded button positions.
- **CapabilityRouter** — T1 native API → T2 DOM → T3 UIA → T4 adapter → T5 vision → T6 keyboard → T7 recovery. Fastest reliable tier selected per app, per action.
- **TargetResolver** — multi-signal ranking (UIA, DOM, OCR, historical, ordinal) — finds the right button/field even when UI changes.
- **VerificationEngine** — postcondition checks after every action. No false success. Re-verifies: URL, window, control, text, file, process, volume.
- **RecoveryEngine** — 8 recovery strategies (retry same, retry resolved, downgrade tier, wait & retry...).
- **Checkpoint Manager** — resume/cancel long tasks, idempotent steps.
- **Tool Performance Memory** — learns the best tier per app per action over time.
- **9 App Adapters** — Browser, File Manager, Office, VS Code, WhatsApp, Discord, Spotify, Generic Windows, Unreal Engine.

### Unreal Engine 4.22+ Adapter (93 operations)
- Blueprints, materials, textures, meshes, lighting, C++ build, packaging, sequencer, Niagara, animation, audio.
- 5-tier fallback: Web Remote Control → bundled Python REPL → pywinauto → vision → keyboard.
- Genuine `unreal.*` Python snippets for each operation.

### Legend Edition Persona (`core/persona_v2.py`)
- Multi-dimensional persona learning: text + voice + behavior + emotion + culture.
- Per-contact persona — different "you" for boss vs friends vs family.
- Pakistani/Indian Urdu flavor detection, code-switch detection.
- Mood baseline, weekly drift snapshots, `draft_reply()` via LLM.

### Auto-Reply Daemon
- Away-mode detection, contact policies, platform watchers (WhatsApp/Discord/file JSONL), LLM-driven replies.

### AI UI Upgrades (v2.4.0 carried forward)
- **Apple-level design system** (`apple_design.py`) — AppleButton, AppleInput, AppleCard, AppleDialog, AppleCheckmark, smooth animations.
- **Bootstrap, Onboarding Wizard, Setup Wizard, Update dialogs, QMessageBox** — all redesigned to premium Apple-style: pure black, clean typography, generous spacing, smooth fades.

### Download
- **Installer:** SONIC-AI-Setup.exe
- **Portable:** SONIC-AI.exe

### Permanent update link
https://github.com/elyxcart-rgb/ATHERION-LABS/releases/latest/download/SONIC-AI-Setup.exe
