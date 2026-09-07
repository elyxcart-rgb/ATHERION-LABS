"""SONIC AI — Tool Contract Validator.

Validates tool calls before execution.
"""
from __future__ import annotations

from typing import Any
from dataclasses import dataclass


TOOL_DEFINITIONS = {
    "file_controller": {
        "required_params": ["action"],
        "valid_actions": [
            "list", "create_file", "create_folder", "write", "read",
            "delete", "move", "copy", "rename", "find", "largest",
            "disk_usage", "organize_desktop", "info", "open",
        ],
        "action_params": {
            "create_file": ["path"],
            "create_folder": ["path"],
            "write": ["path", "content"],
            "read": ["path"],
            "delete": ["path"],
            "move": ["source", "destination"],
            "copy": ["source", "destination"],
            "rename": ["source", "new_name"],
            "find": ["query"],
            "open": ["path"],
            "list": ["path"],
        },
    },
    "weather_report": {
        "required_params": [],
        "optional_params": ["city", "time"],
    },
    "coding_task": {
        "required_params": ["request"],
    },
    "web_search": {
        "required_params": ["query"],
    },
    "open_app": {
        "required_params": ["app_name"],
    },
    "smart_find": {
        "required_params": ["query"],
    },
    "system_controls": {
        "required_params": ["action"],
    },
}


@dataclass
class ValidationResult:
    valid: bool
    error_type: str = ""
    message: str = ""
    supported_actions: list = None
    missing_params: list = None

    def __post_init__(self):
        if self.supported_actions is None:
            self.supported_actions = []
        if self.missing_params is None:
            self.missing_params = []


def validate_tool_call(tool_name: str, parameters: dict) -> ValidationResult:
    if tool_name not in TOOL_DEFINITIONS:
        return ValidationResult(
            valid=False,
            error_type="TOOL_NOT_FOUND",
            message=f"Unknown tool: {tool_name}",
        )

    spec = TOOL_DEFINITIONS[tool_name]

    missing = []
    for param in spec.get("required_params", []):
        if param not in parameters or not parameters[param]:
            missing.append(param)

    if missing:
        return ValidationResult(
            valid=False,
            error_type="MISSING_PARAMETER",
            message=f"Missing required parameters: {', '.join(missing)}",
            missing_params=missing,
        )

    if "valid_actions" in spec and "action" in parameters:
        action = parameters["action"]
        valid_actions = spec.get("valid_actions", [])
        if valid_actions and action not in valid_actions:
            return ValidationResult(
                valid=False,
                error_type="INVALID_ACTION",
                message=f"Invalid action: '{action}'",
                supported_actions=valid_actions,
            )

    action = parameters.get("action", "")
    action_params = spec.get("action_params", {})
    if action in action_params:
        missing = []
        for param in action_params[action]:
            if param not in parameters or not parameters[param]:
                missing.append(param)
        if missing:
            return ValidationResult(
                valid=False,
                error_type="MISSING_PARAMETER",
                message=f"Action '{action}' requires: {', '.join(missing)}",
                missing_params=missing,
            )

    return ValidationResult(valid=True)


def get_supported_actions(tool_name: str) -> list:
    spec = TOOL_DEFINITIONS.get(tool_name, {})
    return spec.get("valid_actions", [])


def get_tool_spec(tool_name: str) -> dict:
    return TOOL_DEFINITIONS.get(tool_name, {})
