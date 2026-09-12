"""SONIC AI — Reliability Module.

Error classification, retry engine, path resolution,
operation verification, and tool contract validation.
"""
from .classifier import classify_error, ErrorCategory, ErrorClassification
from .retry import RetryEngine, RetryResult
from .paths import resolve_path, search_files, get_known_folder, normalize_path, KNOWN_FOLDERS
from .verify import (
    verify_file_exists, verify_file_deleted, verify_move,
    verify_copy, verify_create, verify_folder_contains, verify_open,
    VerifyResult,
)
from .validator import validate_tool_call, get_supported_actions, ValidationResult

__all__ = [
    "classify_error", "ErrorCategory", "ErrorClassification",
    "RetryEngine", "RetryResult",
    "resolve_path", "search_files", "get_known_folder", "normalize_path", "KNOWN_FOLDERS",
    "verify_file_exists", "verify_file_deleted", "verify_move",
    "verify_copy", "verify_create", "verify_folder_contains", "verify_open",
    "VerifyResult",
    "validate_tool_call", "get_supported_actions", "ValidationResult",
]
