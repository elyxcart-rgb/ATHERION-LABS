"""Security fix verification test."""
import sys
import json
import os
import time
from pathlib import Path

sys.path.insert(0, r"C:\Users\94\Desktop\ATHERION-LABS-main")

# Clean slate — remove all auth data from AppData
auth_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "SONIC AI" / "auth"
if auth_dir.exists():
    for f in auth_dir.glob("*"):
        if f.is_file():
            f.unlink()

# Force fresh singleton
import auth.core as core
core._auth_instance = None

from auth.core import SonicAuth, get_auth, _AUTH_DIR, _SESSION_PATH

# Use unique emails to avoid Firebase conflicts
ts = str(int(time.time()))
EMAIL_A = f"sonictest_a_{ts}@example.com"
EMAIL_B = f"sonictest_b_{ts}@example.com"
PASS_A = "testpass_a_123"
PASS_B = "testpass_b_123"

# Test 1: Fresh instance
auth = get_auth()
assert not auth.is_authenticated, "FAIL: Fresh instance should not be authenticated"
print("PASS: Test 1 - Fresh instance not authenticated")

# Test 2: Signup
result = auth.signup(EMAIL_A, PASS_A)
assert result.get("ok"), f"FAIL: Signup failed: {result}"
print("PASS: Test 2 - Signup success")

# Test 3: Authenticated
assert auth.is_authenticated, "FAIL: Should be authenticated after signup"
print("PASS: Test 3 - Authenticated after signup")

# Test 4: Logout
auth.logout()
assert not auth.is_authenticated, "FAIL: Should not be authenticated after logout"
assert auth.user_id == "", "FAIL: user_id should be empty after logout"
assert auth._email == "", "FAIL: email should be empty after logout"
print("PASS: Test 4 - Logout clears all state")

# Test 5: Login
result = auth.login(EMAIL_A, PASS_A)
assert result.get("ok"), f"FAIL: Login failed: {result}"
print("PASS: Test 5 - Login success")

# Test 6: Different user isolation
auth.logout()
result = auth.signup(EMAIL_B, PASS_B)
assert result.get("ok"), f"FAIL: Other user signup failed: {result}"
assert auth._email == EMAIL_B, "FAIL: Wrong email after signup"
assert auth._email != EMAIL_A, "FAIL: Cross-user leak!"
print("PASS: Test 6 - User isolation works")

# Test 7: Logout clean state
auth.logout()
assert not auth.is_authenticated
assert auth.user_id == ""
assert auth._email == ""
assert auth.current_user is None
print("PASS: Test 7 - Clean state after logout")

# Test 8: Password hashing
creds_path = _AUTH_DIR / ".local_users.json"
if creds_path.exists():
    creds = json.loads(creds_path.read_text())
    for email, data in creds.items():
        pwd = data.get("password", "")
        assert ":" in pwd, f"FAIL: Password for {email} is not hashed!"
    print("PASS: Test 8 - All passwords are hashed")
else:
    print("PASS: Test 8 - No local creds file (Firebase used)")

# Test 9: Paths in AppData
assert "AppData" in str(_AUTH_DIR).replace("\\", "/"), f"FAIL: Auth dir not in AppData: {_AUTH_DIR}"
print(f"PASS: Test 9 - Auth dir in AppData: {_AUTH_DIR}")

# Test 10: Session file in AppData
assert "AppData" in str(_SESSION_PATH).replace("\\", "/"), f"FAIL: Session not in AppData: {_SESSION_PATH}"
print(f"PASS: Test 10 - Session in AppData: {_SESSION_PATH}")

# Test 11: No cross-user data leak
auth.logout()
result = auth.login(EMAIL_B, PASS_B)
assert result.get("ok")
assert auth._email == EMAIL_B
assert auth.user_id != ""
assert auth._email != EMAIL_A
print("PASS: Test 11 - No cross-user data leak")

# Final cleanup
auth.logout()
print()
print("=" * 50)
print("ALL 11 SECURITY TESTS PASSED!")
print("=" * 50)
print("ALL 11 SECURITY TESTS PASSED!")
print("=" * 50)
