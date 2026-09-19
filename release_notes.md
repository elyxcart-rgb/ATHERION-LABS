## SONIC Apex v2.3.0 — Computer Use Upgrade (GPT-6 Astra Level)

### What's New

**1. Pixel-Perfect Screen Finding**
- Upgraded from `gemini-flash-lite` to `gemini-2.0-flash` for better accuracy
- Now returns bounding box (x, y, width, height) + confidence score + element type
- Clicks center of bounding box for accurate targeting

**2. Smart Click with Retry**
- New `smart_click` action: AI finds element + clicks with retry logic
- Retries up to 3 times if element not found
- Verifies coordinates are within screen bounds

**3. Type Into Field**
- New `type_into` action: finds input field by description + types text
- Combines screen_find + click + type in one action

**4. Gemini-Powered Command Parsing**
- Autopilot now uses Gemini for complex voice commands
- Falls back to regex for simple commands
- Supports multi-step workflows: "open Chrome, go to YouTube, click search"

**5. Better Error Recovery**
- All actions have retry logic
- Graceful fallbacks when AI vision fails
- Coordinate bounds checking

### Backup
Previous files backed up to: `backup_v2.2.0_computer_use/`

### Download
- **Installer:** SONIC-AI-Setup.exe
- **Portable:** SONIC-AI.exe

### Permanent Update URL
https://github.com/elyxcart-rgb/ATHERION-LABS/releases/latest/download/SONIC-AI-Setup.exe
