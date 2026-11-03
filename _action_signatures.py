"""Inspect actual function signatures of key action modules."""
import sys, os, importlib, inspect
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

sys.path.insert(0, r"C:\Users\94\Desktop\New folder\ATHERION-LABS-main")
os.chdir(r"C:\Users\94\Desktop\New folder\ATHERION-LABS-main")

# Critical actions we need to wire
key_modules = {
    "open_app":            ("actions.open_app", "open_app"),
    "web_search":          ("actions.web_search", "web_search"),
    "weather":             ("actions.weather_report", "weather"),
    "reminder":            ("actions.reminder", "reminder"),
    "translator":          ("actions.translator", "translator"),
    "screenshot":          ("actions.screen_processor", "screen_process"),
    "send_message":        ("actions.send_message", "send_message"),
    "system_status":       ("actions.system_monitor", "get_system_status"),
    "email":               ("actions.email_api", "email_api"),
    "file_controller":     ("actions.file_controller", "file_controller"),
    "computer_settings":   ("actions.computer_settings", "computer_settings"),
    "browser_control":     ("actions.browser_control", "browser_control"),
    "dev_agent":           ("actions.dev_agent", "dev_agent"),
    "youtube":             ("actions.youtube_video", "youtube_video"),
    "smart_clipboard":     ("actions.smart_clipboard", "smart_clipboard"),
    "voice_shortcut":      ("actions.voice_shortcut", "voice_shortcut"),
    "life_dashboard":      ("actions.life_dashboard", "life_dashboard"),
}

for label, (modname, funcname) in key_modules.items():
    print(f"\n=== {label} → {modname}.{funcname} ===")
    try:
        mod = importlib.import_module(modname)
        fn = getattr(mod, funcname, None)
        if fn is None:
            print(f"  ✗ NOT FOUND")
            continue
        print(f"  Type: {type(fn).__name__}")
        try:
            sig = inspect.signature(fn)
            print(f"  Signature: {sig}")
            params = list(sig.parameters.keys())
            print(f"  Params: {params[:6]}{'...' if len(params) > 6 else ''}")
        except (ValueError, TypeError):
            print(f"  (signature not inspectable)")
        # Try to call it with no args to see what it returns
        try:
            result = fn()
            print(f"  Returns (no args): {type(result).__name__}")
            # Show some methods
            methods = [m for m in dir(result) if not m.startswith("_")
                       and callable(getattr(result, m, None))][:8]
            print(f"  Instance methods (first 8): {methods}")
        except Exception as e:
            print(f"  Call failed: {type(e).__name__}: {str(e)[:100]}")
    except Exception as e:
        print(f"  Import failed: {type(e).__name__}: {str(e)[:100]}")
