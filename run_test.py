import sys, io, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
try:
    import main
    main.main()
except Exception as e:
    print(f"FATAL ERROR: {e}")
    traceback.print_exc()
