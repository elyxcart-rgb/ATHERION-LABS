# SONIC AI

**The Ultimate Cross-Platform Personal AI Assistant**

A real-time voice AI that can hear, see, understand, and control your computer. Built on the Gemini Live API for native audio streaming — zero subscriptions, total digital autonomy.

---

## Features

### Voice & Conversation
| Feature | Description |
|---|---|
| Real-time Voice | Ultra-low latency conversation via Gemini Live API |
| Voice Picker | Choose from 5 native Gemini voices — switch live from UI |
| Affective Dialog | Hears emotion in your voice and adapts its tone |
| Proactive Audio | Knows when you're not talking — background chatter never triggers a reply |
| Unlimited Sessions | Sliding-window context compression — conversations last for hours |
| Session Continuity | Dropped connections or voice changes don't wipe the conversation |
| Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

### Memory & Intelligence
| Feature | Description |
|---|---|
| Persistent Memory | Deeply remembers projects, preferences, and context across sessions |
| Memory Panel | See every fact stored about you, when learned, delete in one click |
| Recallable Memory | On-demand search from local store — no size limit |
| Silent Language Memory | Detects spoken language on first use — all sessions adapt automatically |

### System Control
| Feature | Description |
|---|---|
| System Control | Launch apps, adjust volume/brightness, WiFi, shortcuts, power |
| Browser Control | Open URLs, navigate tabs, interact with browser by voice |
| File Operations | Move, rename, create, copy, write, delete files |
| Desktop Control | Taskbar, window management, and desktop-level operations |
| Clipboard Intelligence | Copy any text → floating panel with Translate / Summarise / Explain |

### Visual & Interface
| Feature | Description |
|---|---|
| Reactive HUD | Waveform and reactor core pulse to real audio — mic while listening, SONIC while speaking |
| Live Theming | Recolour the entire HUD from a hex code or hue wheel |
| Boot Animation | Cinematic startup with reactor spin-up sound and HUD swell |
| Orb Interface | 2400-particle 3D consciousness orb with audio-reactive displacement |
| Dark HUD Theme | Angular panels, metallic borders, sci-fi aesthetic |
| Dynamic Content Panel | Scrollable display for web results, news, and search data |

### Productivity
| Feature | Description |
|---|---|
| Web Search | News / Research / Price / Compare — Gemini Grounded, DDG fallback |
| Smart Reminders | OS-native scheduled notifications |
| Weather Report | Live weather data for your city |
| Morning Briefing | On first boot: greets you, recaps yesterday, fetches live news |
| Proactive 2.0 | Time-aware, context-aware check-ins |
| Flight Finder | Live flight price and availability lookup |
| Game Updater | Checks and triggers game updates on Steam and Epic |

### Security & Control
| Feature | Description |
|---|---|
| Confirmation Gate | Shutdown, restart, WiFi wait for a button you press — model can't confirm |
| Undo System | Take back file moves, renames, creates, and settings changes |
| Plugin System | Drop a single `.py` file into `plugins/` — new skill on next launch |
| Remote Dashboard | Control the assistant from your phone via QR code pairing |
| Auto-Start on Boot | Registers with OS startup system |

---

## Quick Start

### Option 1: Install from Release (Recommended)

1. Download the [latest installer](https://github.com/elyxcart-rgb/ATHERION-LABS/releases/latest/download/SONIC-AI-Setup.exe)
2. Run `SONIC-AI-Setup.exe` and follow the wizard
3. Launch SONIC AI from your desktop

### Option 2: Run from Source

```bash
git clone https://github.com/elyxcart-rgb/ATHERION-LABS.git
cd ATHERION-LABS
pip install -r requirements.txt
python main.py
```

### First Run

1. **Onboarding Wizard** — Create an account or sign in (skip to run offline)
2. **API Key** — Enter your free Gemini API key (get one at [Google AI Studio](https://aistudio.google.com/apikey))
3. **Preferences** — Choose your theme, voice, and assistant name
4. **Start talking** — Click the microphone or type a command

---

## Requirements

| Requirement | Details |
|---|---|
| OS | Windows 10/11 (primary), macOS, or Linux |
| Python | 3.11+ (for source installs) |
| Microphone | Required for voice interaction |
| Speakers | Required for voice replies |
| API Key | Free Gemini API key |
| Display | 980×700 minimum window size |

---

## Project Structure

```
ATHERION-LABS/
├── main.py                    # Entry point — Gemini Live session, audio I/O, tool dispatch
├── ui.py                      # PyQt6 HUD — reactive orb, log panel, overlays, controls
├── splash.py                  # Boot splash screen
├── version.py                 # Version declaration (single source of truth)
├── build.py                   # Production build script (EXE + installer)
├── sonic.spec                 # PyInstaller spec file
├── sonic_setup.iss            # Inno Setup installer script
│
├── actions/                   # Tool modules (called by Gemini via function calling)
│   ├── web_search.py          # Multi-mode search (news, research, price, compare)
│   ├── screen_processor.py    # Screen capture & webcam vision
│   ├── background_monitor.py  # User-configured topic watching
│   ├── proactive.py           # Time/context-aware check-ins
│   ├── reminder.py            # OS-native scheduled notifications
│   ├── system_monitor.py      # CPU / RAM / GPU / temperature telemetry
│   ├── computer_settings.py   # Volume, brightness, WiFi, power
│   ├── computer_control.py    # Keyboard, mouse, window management
│   ├── file_controller.py     # File system operations
│   ├── file_processor.py      # Document reading and summarization
│   ├── code_helper.py         # Code review and generation
│   ├── dev_agent.py           # Developer task agent
│   ├── browser_control.py     # Web browser control
│   ├── send_message.py        # Messaging integration
│   ├── weather_report.py      # Live weather data
│   ├── flight_finder.py       # Flight search
│   ├── youtube_video.py       # YouTube playback control
│   ├── game_updater.py        # Game update management
│   ├── smart_clipboard.py     # Clipboard intelligence panel
│   ├── hologram_mode.py       # Visual hologram effects
│   ├── recipe_engine.py       # Recipe suggestions
│   ├── squad_agent.py         # Multi-agent collaboration
│   ├── voice_shortcut.py      # Voice command shortcuts
│   ├── life_dashboard.py      # Life metrics dashboard
│   ├── autopilot.py           # Automated task execution
│   ├── open_app.py            # Application launcher
│   └── desktop.py             # Desktop and taskbar control
│
├── memory/                    # Persistent memory system
│   ├── memory_manager.py      # Load/save — sessions, monitors, identity
│   ├── config_manager.py      # API keys, OS, name, voice, colour, plugin toggles
│   ├── db.py                  # SQLite + FTS5 search engine
│   ├── retrieval.py           # On-demand memory search
│   ├── extractor.py           # Extract facts from conversations
│   ├── context_builder.py     # Build context for Gemini
│   ├── consolidation.py       # Memory consolidation and cleanup
│   ├── cloud_sync.py          # Firestore cloud synchronization
│   └── models.py              # Memory data models
│
├── core/                      # Core engine
│   ├── prompt.txt             # Assistant personality and tool-routing rules
│   ├── llm_client.py          # Gemini Live API client
│   ├── tts.py                 # Text-to-speech
│   ├── stt.py                 # Speech-to-text
│   ├── plugin_loader.py       # Plugin engine — discovery, validation, crash isolation
│   ├── undo.py                # Shared undo stack
│   ├── confirm.py             # Irreversible-action gate
│   ├── audio_devices.py       # Microphone / speaker — filtered, measured, resolved
│   └── installer.py           # Core installer logic
│
├── auth/                      # Authentication system
│   ├── core.py                # Firebase Auth (email/password + Google OAuth)
│   ├── firestore_sync.py      # Firestore data sync
│   ├── secrets.py             # Secrets management
│   └── firebase_config.json   # Firebase configuration
│
├── emotion/                   # Emotion detection engine
│   ├── detector.py            # Text emotion analysis
│   ├── personality.py         # Personality traits
│   ├── vocabulary.py          # Emotion vocabulary
│   └── models.py              # Emotion data models
│
├── coding/                    # Code execution engine
│   ├── adapter.py             # Language adapters
│   ├── process.py             # Sandboxed execution
│   ├── verification.py        # Code verification
│   └── workspace.py           # Workspace management
│
├── reliability/               # Tool reliability system
│   ├── classifier.py          # Error classification
│   ├── retry.py               # Smart retry logic
│   ├── validator.py           # Input validation
│   └── verify.py              # Output verification
│
├── security/                  # Advanced security
│   └── advanced.py            # Rate limiter, audit logger, intrusion detection
│
├── updater/                   # Auto-update system
│   ├── ui.py                  # Update UI overlay
│   ├── startup.py             # Startup update check
│   └── migrations.py          # Data migration between versions
│
├── bootstrap/                 # First-run bootstrapper
│   ├── cinematic.py           # Cinematic boot animation
│   ├── ui.py                  # Bootstrap UI
│   ├── detector.py            # System detection
│   └── state.py               # Bootstrap state management
│
├── sonic-frontend-theme/      # Design system
│   └── pyqt6_theme/
│       ├── theme.py           # Design tokens (C, HU classes)
│       ├── theme_scifi.py     # Sci-Fi Gold alternate theme
│       ├── widgets.py         # Custom widgets (HudPanel, HudButton, HudCanvas, etc.)
│       └── icons.py           # SVG icon system
│
├── dashboard/                 # Web dashboard
│   ├── server.py              # Local web server
│   └── static/                # Dashboard HTML/CSS/JS
│
├── config/                    # Configuration
│   ├── api_keys.json          # API keys and settings
│   ├── sonic.ico              # Application icon
│   └── certs/                 # TLS certificates
│
├── plugins/                   # User plugins
│   └── _template.py           # Plugin template
│
├── tests/                     # Test suite (166 tests)
│   ├── test_security.py
│   ├── test_coding.py
│   ├── test_memory.py
│   ├── test_emotion.py
│   ├── test_auth.py
│   ├── test_cloud_sync.py
│   ├── test_reliability.py
│   └── test_updater.py
│
└── releases/
    └── stable.json            # Release metadata
```

---

## Configuration

### API Keys

Set your Gemini API key via the onboarding wizard or manually in `config/api_keys.json`:

```json
{
  "gemini_api_key": "AIzaSy..."
}
```

### Firebase (Optional)

For cloud sync and multi-device access, configure `auth/firebase_config.json`:

```json
{
  "apiKey": "...",
  "authDomain": "your-project.firebaseapp.com",
  "projectId": "your-project-id"
}
```

### Customization

- **Theme**: Settings → Customize → Theme (Dark / Sci-Fi Gold)
- **Voice**: Settings → Customize → Voice (5 Gemini voices)
- **Name**: Settings → Customize → Assistant Name
- **Color**: Settings → Customize → UI Colour (live preview)

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `F4` | Toggle microphone mute |
| `F11` | Toggle fullscreen |
| `Escape` | Interrupt SONIC mid-speech |

---

## Building from Source

### EXE Build

```bash
python build.py
```

Output: `dist/SONIC-AI.exe` (~230 MB)

### Installer Build

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```bash
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" sonic_setup.iss
```

Output: `installer_output/SONIC-AI-Setup.exe` (~270 MB)

---

## Testing

```bash
python -m pytest tests/ -v
```

**166 tests** across 8 test files covering security, coding, memory, emotion, auth, cloud sync, reliability, and updater.

---

## License

Personal and non-commercial use only.
Licensed under [Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/).

---

## Support

- **Issues**: [GitHub Issues](https://github.com/elyxcart-rgb/ATHERION-LABS/issues)
- **Releases**: [GitHub Releases](https://github.com/elyxcart-rgb/ATHERION-LABS/releases)

---

## Author

**Ahmad** — CEO, Atherion Labs

> Built with passion. Engineered for autonomy.
