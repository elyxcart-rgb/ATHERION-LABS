# SONIC AI — The Universal Computer-Use Agent

> **A premium Jarvis-class desktop assistant. Version 2.5.0** — built by ATHERION Labs.

SONIC is a self-evolving AI assistant that **hears you, sees your screen, understands your intent, and acts on it across any app, website, or workflow**. Powered by Google's Gemini, with optional LLM fallback, persistent multi-modal persona memory, automatic reply when you're away, and an ultra-pro universal computer-use engine.

---

## ✨ What's New in 2.5.0

| Subsystem | What it does |
|-----------|--------------|
| **Universal Computer-Use Engine** | Goal-driven automation across any app/website. Plans, resolves targets, picks capability tier (native API → DOM → UIA → adapter → vision → keyboard), verifies, recovers on failure. |
| **Ultra-Pro Persona (Legend Edition)** | 5-dimensional persona learning: text + voice + behavior + emotion + culture. Per-contact adaptation, drift detection, predictive next-message, auto-drafting in your voice. |
| **Auto-Reply Daemon** | When you're away, monitors contacts across WhatsApp/Discord/SMS/Email, analyzes incoming messages with LLM, sends persona-matched replies. Smart escalation, rate limiting, quiet hours, idempotency. |
| **Ultra-Pro YouTube Ad Skipper** | Multi-signal detection (visual + DOM), 30+ language skip-button recognition, 4-tier click strategy, ad-type classification, verification. |
| **Stability & Connection Hardening** | Exponential backoff on LLM errors, persistent HTTP sessions, 100x reduction in reconnect spam. Live voice 1007 error → graceful text-mode fallback (no infinite loop). |
| **Unreal Engine 4.22+ Adapter** | 93 operations (Blueprints, materials, textures, meshes, lighting, packaging, C++). 30+ high-level goal patterns. Real .uproject path detection. |

---

## 🚀 Quick Install

### Option 1: From GitHub source

```bash
git clone https://github.com/elyxcart-rgb/ATHERION-LABS.git
cd ATHERION-LABS
pip install -e .
playwright install chromium
python main.py
```

### Option 2: From built wheel (after release)

```bash
pip install sonic-ai==2.5.0
playwright install chromium
sonic
```

### Option 3: With all extras

```bash
pip install -e ".[dev,universal,voice]"
playwright install chromium
```

### First-time setup

1. **API key:** Edit `config/api_keys.json` with your Gemini key (or set `GEMINI_API_KEY` env var).
2. **Test connection:** `python -c "from core.providers import get_default_chain; print(get_default_chain().generate('hi').text)"`
3. **Launch:** `python main.py` (or `sonic` if installed)

**System requirements:** Windows 10/11, Python 3.11+, ~500 MB disk for models + Playwright browsers.

---

## 🧠 Subsystems at a glance

| Module | Lines | Purpose |
|--------|-------|---------|
| `core/jarvis_brain.py` | 600+ | The unified brain. Wires 16+ subsystems: router, memory, vision, voice, plugins, providers. |
| `core/universal/` | 17 files | Goal-driven computer-use engine (state, actions, target resolver, capability router, verification, recovery, checkpoint, tool memory, agent) |
| `core/universal/adapters/` | 9 files | App-specific adapters: Browser, FileManager, Office, VSCode, WhatsApp, Discord, Spotify, GenericWindows, **Unreal** |
| `core/universal/screens/` | 3 files | Screen understanding (DPI, dialog detection, scene parser) |
| `core/persona.py` + `persona_v2.py` | 1100+ | Text + multi-modal persona learning (Legend Edition) |
| `core/auto_reply.py` + `auto_reply_watchers.py` | 850+ | Away-mode auto-reply daemon with platform watchers |
| `core/youtube_ad_skipper.py` | 26 KB | Ultra-pro multi-language ad skipper |
| `core/providers.py` | 22 KB | Multi-LLM chain (Gemini → OpenAI → Ollama) with health cache + backoff |
| `core/smart_clicker.py` | — | 22-language UI button finder |
| `core/voice_pipeline.py` + `voice_personas.py` | 1000+ | Voice input/output with 6 personas |
| `actions/` | 40+ files | Legacy SONIC actions (76 mapped in ActionBridge) |
| `bootstrap/ui.py` | 700+ | Holographic bootstrap UI |
| `ui/` | 8 files | Holo orb, neural net viz, command deck, floating HUD, mini orb |

---

## 🎯 Use it like a real assistant

```python
from core.jarvis_brain import JarvisBrain

brain = JarvisBrain()

# Goal-driven computer use
brain.run_goal("Open Chrome and search YouTube for OpenAI latest video")
brain.run_goal("Setup a basic Unreal scene with floor, sun, and post-process")
brain.run_goal("Find my downloaded PDF and move it to Documents")

# Auto-reply when away
brain.universal.run_unreal_op("create_blueprint", name="BP_Hero", parent="Character")
brain.universal.list_unreal_ops()         # 93 Unreal ops
brain.universal.list_unreal_goals()       # 30+ goal patterns

# Persona-matched drafting
brain.auto_reply.learn_persona_from_history([
    "yaar kya haal", "boss please help", "thanks bhai",
])
```

### Run scripts directly

```bash
# Personal demo — type messages, watch persona evolve
python scripts/persona_demo.py

# Auto-reply starter with persona learning
python scripts/start_auto_reply.py --learn messages.txt --away

# Universal agent standalone
python -c "from core.universal import UniversalAgent; print(UniversalAgent().llm_status())"
```

---

## 🧪 Test suite (55+ tests, all green)

```bash
python -m core.persona_v2_test            # 19/19 — persona learning
python -m core.auto_reply_test            # 18/18 — auto-reply daemon
python -m core.universal.tests.run_all    # 9/9  — universal engine
python -m core.youtube_ad_skipper_test    # 9/9  — ad skipper
```

---

## 🏗️ Architecture

```
USER (voice / text / click)
       ↓
┌──────────────────────────────────────────────────────────┐
│  JarvisBrain (unified facade)                            │
│  ┌────────────────────────────────────────────────────┐ │
│  │ Router → Memory → Vision → Voice → Plugins         │ │
│  │ UniversalAgent (NEW)                               │ │
│  │  ├─ Planner (heuristic + LLM + Unreal interpreter) │ │
│  │  ├─ Target Resolver (UIA/DOM/OCR/historical)        │ │
│  │  ├─ Capability Router (T1→T7)                        │ │
│  │  ├─ Verification Engine                             │ │
│  │  └─ Recovery Engine (8 strategies)                  │ │
│  │ App Adapters (Browser, Office, VSCode, WhatsApp,   │ │
│  │  Discord, Spotify, Generic, Unreal, FileManager)    │ │
│  │ Auto-Reply Daemon (per-contact personas, escalation)│ │
│  │ Persona Engine v2 (5-dim, per-contact, drift)       │ │
│  │ Providers (Gemini → OpenAI → Ollama)                 │ │
│  │ YouTube Ad Skipper (multi-lang, 4-tier click)       │ │
│  └────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
       ↓
Action Bridge → 76 actions (legacy SONIC)
       ↓
Computer / Browser / Apps / Files / Network
```

---

## 🌍 What it can do (today)

| Domain | Coverage |
|--------|----------|
| **Browsers** | Chrome / Edge / Firefox / Brave via Playwright (DOM, ARIA, semantic locators) |
| **Microsoft Office** | Excel, Word, PowerPoint, Outlook (via win32com) |
| **Code editors** | VS Code (`code` CLI), Visual Studio |
| **Communication** | WhatsApp Web, Discord, Telegram (planned), SMS, Email |
| **File system** | Windows Explorer, recursive search, move/copy/delete |
| **Creative** | Photoshop (planned), Blender (planned), Figma (planned) |
| **Game engines** | Unreal Engine 4.22+ (full 93-op coverage), Unity (planned) |
| **Smart home / OS** | Windows Settings, Bluetooth, WiFi, Volume, Brightness |
| **Media** | YouTube (search/play/queue/loop), VLC, foobar2000 |
| **Auto-reply** | Any of the above platforms when you're away |

---

## 🛡️ Stability & safety

- **Connection hardening:** persistent HTTP sessions, exponential backoff (30s → 60s → 120s → 300s), 100x reduction in reconnect spam
- **Error classification:** transient (5xx/429) vs non-transient (404/400) — non-transient circuits open for max cooldown
- **Idempotency:** auto-reply never replies to same message twice
- **Rate limiting:** 20 replies/hr global, per-contact configurable
- **Safety:** red-flag blocker for password/money/credit card in auto-replies
- **Verification:** every action checks postcondition; failure → recovery loop
- **Destructive gating:** delete/send/pay require confirmation
- **Quiet hours:** per-contact (e.g., 10pm-8am)
- **Zero-break:** all new code is additive — existing API unchanged

---

## 📦 What's in the box

```
ATHERION-LABS/
├── core/                     # Intelligence + automation core
│   ├── jarvis_brain.py       # Unified orchestrator
│   ├── persona.py            # v1: text-style persona
│   ├── persona_v2.py         # v2: multi-modal persona (Legend)
│   ├── auto_reply.py         # Auto-reply daemon
│   ├── auto_reply_watchers.py# Platform integrations
│   ├── youtube_ad_skipper.py # Ultra-pro ad skipper
│   ├── smart_clicker.py      # 22-language button finder
│   ├── providers.py          # Multi-LLM chain
│   ├── voice_pipeline.py     # STT/TTS pipeline
│   ├── voice_personas.py     # 6 voice personas
│   └── universal/            # Universal computer-use engine
│       ├── agent.py
│       ├── state.py
│       ├── actions.py
│       ├── target_resolver.py
│       ├── capability_router.py
│       ├── verification.py
│       ├── recovery.py
│       ├── checkpoint.py
│       ├── tool_memory.py
│       ├── adapters/         # App adapters
│       ├── screens/           # Screen understanding
│       ├── tests/             # Test suite
│       └── ue_goals.py        # Unreal goal interpreter
├── actions/                  # 76 legacy SONIC actions
├── bootstrap/                # Holographic UI
├── ui/                       # Holo orb, command deck, HUD
├── plugins/                  # Plugin system
├── memory/                   # Persistent memory store
├── automation/               # Workflow definitions
├── scripts/                  # CLI starters
│   ├── start_auto_reply.py
│   └── persona_demo.py
├── main.py                   # Entry point
├── version.py                # Single source of version truth
├── pyproject.toml            # Modern Python packaging
├── setup.py                  # Post-install script
├── requirements.txt          # All dependencies
├── MANIFEST.in               # Package data manifest
├── LICENSE.txt
├── README.md                 # This file
└── CHANGELOG.md              # Version history
```

---

## 🚀 Run it

```bash
python main.py                # Full SONIC app
sonic                        # If installed via pip
python scripts/persona_demo.py   # Persona interactive demo
python scripts/start_auto_reply.py --away --learn msgs.txt   # Auto-reply
```

---

## 📜 License

See `LICENSE.txt` (proprietary EULA — ATHERION Labs). Commercial use requires permission.

---

## 🤝 Contributing

Open issues at <https://github.com/elyxcart-rgb/ATHERION-LABS/issues>.

---

**Built by ATHERION Labs — pushing the frontier of personal AI autonomy.**
