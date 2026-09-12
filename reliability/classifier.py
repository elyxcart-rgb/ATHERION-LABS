"""SONIC AI — Error Classifier.

Classifies errors into categories with recovery strategies.
"""
from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ErrorCategory(Enum):
    TRANSIENT_NETWORK = "transient_network"
    SERVICE_UNAVAILABLE = "service_unavailable"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_FAILURE = "authentication_failure"
    INVALID_REQUEST = "invalid_request"
    TOOL_NOT_FOUND = "tool_not_found"
    PATH_NOT_FOUND = "path_not_found"
    PERMISSION_DENIED = "permission_denied"
    AMBIGUOUS_PATH = "ambiguous_path"
    INVALID_ACTION = "invalid_action"
    PROCESS_FAILURE = "process_failure"
    TIMEOUT = "timeout"
    VALIDATION_FAILURE = "validation_failure"
    UNKNOWN = "unknown"


@dataclass
class ErrorClassification:
    category: ErrorCategory
    retryable: bool
    max_retries: int
    initial_delay: float
    max_delay: float
    user_message: str
    original_error: str


TRANSIENT_PATTERNS = [
    (r"503|UNAVAILABLE|unavailable|service\s+overloaded", ErrorCategory.SERVICE_UNAVAILABLE),
    (r"502|bad\s+gateway", ErrorCategory.SERVICE_UNAVAILABLE),
    (r"500|internal\s+server", ErrorCategory.TRANSIENT_NETWORK),
    (r"429|rate\s+limit|too\s+many", ErrorCategory.RATE_LIMITED),
    (r"connection\s+(reset|refused|aborted)|ECONNRESET|ECONNREFUSED", ErrorCategory.TRANSIENT_NETWORK),
    (r"timeout|timed?\s*out|TIMEOUT", ErrorCategory.TIMEOUT),
    (r"network\s+(error|unreachable)|ENETUNREACH", ErrorCategory.TRANSIENT_NETWORK),
    (r"DNS|name\s+resolution|getaddrinfo", ErrorCategory.TRANSIENT_NETWORK),
    (r"SSL|certificate|CERT", ErrorCategory.TRANSIENT_NETWORK),
]

FILE_PATTERNS = [
    (r"path\s+not\s+found|file\s+not\s+found|no\s+such\s+file|cannot\s+find", ErrorCategory.PATH_NOT_FOUND),
    (r"directory\s+not\s+found|folder\s+not\s+found", ErrorCategory.PATH_NOT_FOUND),
    (r"permission\s+denied|access\s+denied|EACCES", ErrorCategory.PERMISSION_DENIED),
    (r"unknown\s+action|unsupported\s+action|invalid\s+action", ErrorCategory.INVALID_ACTION),
    (r"ambiguous|multiple\s+matches|did\s+you\s+mean", ErrorCategory.AMBIGUOUS_PATH),
]

AUTH_PATTERNS = [
    (r"unauthorized|401|invalid_token|token\s+expired", ErrorCategory.AUTHENTICATION_FAILURE),
    (r"forbidden|403", ErrorCategory.PERMISSION_DENIED),
]

TOOL_PATTERNS = [
    (r"Unknown\s+tool|tool\s+not\s+found|no\s+such\s+tool", ErrorCategory.TOOL_NOT_FOUND),
    (r"required\s+parameter|missing\s+parameter|invalid\s+parameter", ErrorCategory.INVALID_REQUEST),
]


def classify_error(error: str, context: str = "") -> ErrorClassification:
    error_lower = error.lower()

    for pattern, category in TRANSIENT_PATTERNS + FILE_PATTERNS + AUTH_PATTERNS + TOOL_PATTERNS:
        if re.search(pattern, error_lower, re.IGNORECASE):
            return _make_classification(category, error)

    if "opencode" in error_lower or "coding" in context.lower():
        if any(w in error_lower for w in ["503", "unavailable", "timeout"]):
            return _make_classification(ErrorCategory.SERVICE_UNAVAILABLE, error)

    return _make_classification(ErrorCategory.UNKNOWN, error)


def _make_classification(category: ErrorCategory, error: str) -> ErrorClassification:
    strategies = {
        ErrorCategory.TRANSIENT_NETWORK: (True, 3, 2.0, 30.0, "Network issue detected. Retrying..."),
        ErrorCategory.SERVICE_UNAVAILABLE: (True, 3, 5.0, 60.0, "Service temporarily unavailable. Retrying..."),
        ErrorCategory.RATE_LIMITED: (True, 3, 10.0, 120.0, "Rate limited. Waiting before retry..."),
        ErrorCategory.TIMEOUT: (True, 2, 3.0, 15.0, "Operation timed out. Retrying..."),
        ErrorCategory.AUTHENTICATION_FAILURE: (False, 0, 0, 0, "Authentication failed. Please log in again."),
        ErrorCategory.INVALID_REQUEST: (False, 0, 0, 0, "Invalid request."),
        ErrorCategory.TOOL_NOT_FOUND: (False, 0, 0, 0, "Tool not available."),
        ErrorCategory.PATH_NOT_FOUND: (False, 0, 0, 0, "Path not found."),
        ErrorCategory.PERMISSION_DENIED: (False, 0, 0, 0, "Permission denied."),
        ErrorCategory.AMBIGUOUS_PATH: (False, 0, 0, 0, "Multiple matches found."),
        ErrorCategory.INVALID_ACTION: (False, 0, 0, 0, "Unsupported action."),
        ErrorCategory.PROCESS_FAILURE: (True, 2, 2.0, 10.0, "Process failed. Retrying..."),
        ErrorCategory.VALIDATION_FAILURE: (False, 0, 0, 0, "Validation failed."),
        ErrorCategory.UNKNOWN: (False, 0, 0, 0, "An error occurred."),
    }

    retryable, max_retries, initial_delay, max_delay, user_msg = strategies[category]

    return ErrorClassification(
        category=category,
        retryable=retryable,
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
        user_message=user_msg,
        original_error=error,
    )
