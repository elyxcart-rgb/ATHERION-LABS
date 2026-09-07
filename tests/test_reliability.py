"""Tests for SONIC AI Reliability Module."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reliability.classifier import classify_error, ErrorCategory
from reliability.retry import RetryEngine, RetryResult
from reliability.paths import resolve_path, search_files, KNOWN_FOLDERS, normalize_path
from reliability.verify import (
    verify_file_exists, verify_file_deleted, verify_move,
    verify_copy, verify_create, verify_open,
)
from reliability.validator import validate_tool_call, get_supported_actions
import asyncio
import tempfile
import time


def test_error_classification():
    print("=== Error Classification Tests ===")

    e = classify_error("503 UNAVAILABLE: service overloaded")
    assert e.category == ErrorCategory.SERVICE_UNAVAILABLE
    assert e.retryable == True
    assert e.max_retries == 3
    print("  PASS: 503 classified as SERVICE_UNAVAILABLE")

    e = classify_error("429 rate limit exceeded")
    assert e.category == ErrorCategory.RATE_LIMITED
    assert e.retryable == True
    print("  PASS: 429 classified as RATE_LIMITED")

    e = classify_error("connection reset by peer")
    assert e.category == ErrorCategory.TRANSIENT_NETWORK
    assert e.retryable == True
    print("  PASS: connection reset classified as TRANSIENT_NETWORK")

    e = classify_error("timeout waiting for response")
    assert e.category == ErrorCategory.TIMEOUT
    assert e.retryable == True
    print("  PASS: timeout classified as TIMEOUT")

    e = classify_error("permission denied: /etc/passwd")
    assert e.category == ErrorCategory.PERMISSION_DENIED
    assert e.retryable == False
    print("  PASS: permission denied classified as PERMISSION_DENIED")

    e = classify_error("file not found: test.txt")
    assert e.category == ErrorCategory.PATH_NOT_FOUND
    assert e.retryable == False
    print("  PASS: file not found classified as PATH_NOT_FOUND")

    e = classify_error("unauthorized: invalid token")
    assert e.category == ErrorCategory.AUTHENTICATION_FAILURE
    assert e.retryable == False
    print("  PASS: unauthorized classified as AUTHENTICATION_FAILURE")

    e = classify_error("Unknown tool: random_tool")
    assert e.category == ErrorCategory.TOOL_NOT_FOUND
    assert e.retryable == False
    print("  PASS: unknown tool classified as TOOL_NOT_FOUND")

    print("  ALL ERROR CLASSIFICATION TESTS PASSED\n")


def test_retry_engine():
    print("=== Retry Engine Tests ===")

    engine = RetryEngine()
    classification = classify_error("503 UNAVAILABLE")

    async def run_tests():
        def immediate_success():
            return "ok"

        result = await engine.execute_with_retry(immediate_success, classification)
        assert result.success == True
        assert result.attempts == 1
        print(f"  PASS: First attempt success ({result.attempts} attempt)")

    asyncio.run(run_tests())
    print("  ALL RETRY ENGINE TESTS PASSED\n")


def test_path_resolution():
    print("=== Path Resolution Tests ===")

    p = resolve_path("downloads")
    assert p is not None
    assert "Downloads" in str(p)
    print(f"  PASS: 'downloads' -> {p}")

    p = resolve_path("desktop")
    assert p is not None
    assert "Desktop" in str(p)
    print(f"  PASS: 'desktop' -> {p}")

    p = resolve_path("documents")
    assert p is not None
    assert "Documents" in str(p)
    print(f"  PASS: 'documents' -> {p}")

    p = resolve_path("C:\\Users\\94\\Desktop")
    assert p is not None
    print(f"  PASS: absolute path -> {p}")

    p = resolve_path("")
    assert p is None
    print(f"  PASS: empty string -> None")

    assert "downloads" in KNOWN_FOLDERS
    assert "desktop" in KNOWN_FOLDERS
    print(f"  PASS: known folders initialized ({len(KNOWN_FOLDERS)} folders)")

    n = normalize_path("C:/Users/test/file.txt")
    assert n == "C:\\Users\\test\\file.txt"
    print(f"  PASS: normalize slashes")

    print("  ALL PATH RESOLUTION TESTS PASSED\n")


def test_operation_verification():
    print("=== Operation Verification Tests ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "test.txt")
        with open(test_file, "w") as f:
            f.write("hello")

        v = verify_file_exists(test_file)
        assert v.success == True
        print(f"  PASS: verify_file_exists (exists)")

        v = verify_file_exists(os.path.join(tmpdir, "nonexistent.txt"))
        assert v.success == False
        print(f"  PASS: verify_file_exists (not found)")

        v = verify_create(test_file)
        assert v.success == True
        print(f"  PASS: verify_create")

        v = verify_open(test_file)
        assert v.success == True
        print(f"  PASS: verify_open")

        os.remove(test_file)
        v = verify_file_deleted(test_file)
        assert v.success == True
        print(f"  PASS: verify_file_deleted")

    print("  ALL OPERATION VERIFICATION TESTS PASSED\n")


def test_tool_validation():
    print("=== Tool Validation Tests ===")

    v = validate_tool_call("file_controller", {"action": "list", "path": "."})
    assert v.valid == True
    print(f"  PASS: valid list action")

    v = validate_tool_call("file_controller", {"action": "invalid_action"})
    assert v.valid == False
    assert v.error_type == "INVALID_ACTION"
    assert len(v.supported_actions) > 0
    print(f"  PASS: invalid action rejected with supported list")

    v = validate_tool_call("file_controller", {"action": "move"})
    assert v.valid == False
    assert "destination" in str(v.missing_params)
    print(f"  PASS: missing destination detected")

    v = validate_tool_call("unknown_tool", {})
    assert v.valid == False
    assert v.error_type == "TOOL_NOT_FOUND"
    print(f"  PASS: unknown tool rejected")

    v = validate_tool_call("weather_report", {})
    assert v.valid == True
    print(f"  PASS: weather without city is valid")

    v = validate_tool_call("coding_task", {"request": "fix bug"})
    assert v.valid == True
    print(f"  PASS: coding_task with request is valid")

    v = validate_tool_call("coding_task", {})
    assert v.valid == False
    print(f"  PASS: coding_task without request rejected")

    actions = get_supported_actions("file_controller")
    assert "open" in actions
    assert "create_file" in actions
    print(f"  PASS: supported actions returned ({len(actions)} actions)")

    print("  ALL TOOL VALIDATION TESTS PASSED\n")


def test_file_search():
    print("=== File Search Tests ===")
    from pathlib import Path as PPath

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "report.pdf")
        with open(test_file, "w") as f:
            f.write("content")

        results = search_files("report", [PPath(tmpdir)])
        assert len(results) > 0
        assert results[0]["confidence"] > 0.5
        print(f"  PASS: found 'report' with confidence {results[0]['confidence']}")

        results = search_files("nonexistent_xyz", [PPath(tmpdir)])
        assert len(results) == 0
        print(f"  PASS: no results for nonexistent file")

    print("  ALL FILE SEARCH TESTS PASSED\n")


if __name__ == "__main__":
    from pathlib import Path
    test_error_classification()
    test_retry_engine()
    test_path_resolution()
    test_operation_verification()
    test_tool_validation()
    test_file_search()
    print("=" * 50)
    print("ALL TESTS PASSED!")
