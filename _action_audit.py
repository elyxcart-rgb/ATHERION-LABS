"""Audit SONIC's action execution system."""
import sys, os, importlib, inspect
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

sys.path.insert(0, r"C:\Users\94\Desktop\New folder\ATHERION-LABS-main")
os.chdir(r"C:\Users\94\Desktop\New folder\ATHERION-LABS-main")

actions_dir = "actions"
ok = []
broken = []
for fn in sorted(os.listdir(actions_dir)):
    if not fn.endswith(".py") or fn.startswith("__"):
        continue
    modname = "actions." + fn[:-3]
    try:
        mod = importlib.import_module(modname)
        funcs = [n for n, o in vars(mod).items()
                 if callable(o) and not n.startswith("_")
                 and getattr(o, "__module__", "") == modname]
        ok.append((modname, funcs))
    except Exception as e:
        broken.append((modname, str(e)[:120]))

print(f"OK modules:     {len(ok)}")
print(f"Broken modules: {len(broken)}")
print()
print("=== BROKEN MODULES ===")
for m, e in broken:
    print(f"  X {m}: {e}")
print()
print("=== OK MODULES + public callables ===")
for m, funcs in ok:
    print(f"  V {m}  ({len(funcs)} callables)")
    for f in funcs[:8]:
        print(f"      - {f}")
    if len(funcs) > 8:
        print(f"      ... and {len(funcs) - 8} more")
