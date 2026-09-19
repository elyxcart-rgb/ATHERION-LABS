## SONIC AI v2.1.4 — Volume & Brightness Absolute Control

### New Feature: Absolute Percentage Control

**Problem:** Commands like "volume 100%" or "brightness 50%" were not working — they fell back to relative adjustments.

**What was fixed:**
- Added `brightness_set` action to computer_settings tool
- Added percentage parsing for both volume and brightness
- Natural language support: "full volume", "half brightness", "minimum volume", etc.
- Relative with delta: "volume up 10%", "brightness down 20%"
- Verification after absolute changes (reads actual value, compares with target)

**New commands supported:**
- **Volume:** `volume 100%`, `volume 50`, `full volume`, `half volume`, `minimum volume`
- **Brightness:** `brightness 100%`, `brightness 50`, `full brightness`, `half brightness`, `minimum brightness`
- **Relative:** `volume up 10%`, `volume down 10%`, `brightness up 10%`, `brightness down 10%`
- **Multi-language:** `awaz 100%`, `poori awaz`, `aadhi awaz`, `roshni 100%`

**Files modified:**
- `actions/computer_settings.py` — Added brightness_set, percentage parsing, delta support
- `main.py` — Updated tool declaration with brightness_set
- `core/prompt.txt` — Updated documentation

**Tests:** 27/27 passed

### Download
- **Installer:** SONIC-AI-Setup.exe
- **Portable:** SONIC-AI.exe

### Permanent Update URL
https://github.com/elyxcart-rgb/ATHERION-LABS/releases/latest/download/SONIC-AI-Setup.exe
