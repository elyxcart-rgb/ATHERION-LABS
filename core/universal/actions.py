"""SONIC AI — Action Model + Validation.

A typed representation of every interaction SONIC can perform. Every action
must declare:
  - capability tier it requires
  - preconditions
  - postconditions (used by VerificationEngine)
  - whether it is destructive (gates confirmation)

The UniversalAgent never emits raw mouse/keyboard — it emits an Action
struct, which CapabilityRouter turns into an actual driver call.

The Action model is intentionally UI-control oriented (not LLM function
calling) because SONIC reasons about visual/programmatic targets, not
text-only function arguments.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class ActionType(str, Enum):
    # Physical / input fallback
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    HOVER = "hover"
    TYPE = "type"
    KEYPRESS = "keypress"
    SCROLL = "scroll"
    DRAG = "drag"
    MOUSE_MOVE = "mouse_move"

    # Semantic / accessibility
    FOCUS = "focus"                 # set focus to a control by name/automation_id
    INVOKE = "invoke"               # click a button via UIA Invoke pattern
    SET_VALUE = "set_value"         # set a text input value
    TOGGLE = "toggle"               # checkbox/switch

    # Application-level
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    NAVIGATE = "navigate"           # browser URL change
    SWITCH_TAB = "switch_tab"
    NEW_TAB = "new_tab"
    CLOSE_TAB = "close_tab"

    # File operations
    FILE_OPEN = "file_open"
    FILE_SAVE = "file_save"
    FILE_MOVE = "file_move"
    FILE_COPY = "file_copy"
    FILE_DELETE = "file_delete"
    FILE_RENAME = "file_rename"
    FILE_SEARCH = "file_search"

    # Higher-order
    RUN_WORKFLOW = "run_workflow"
    EXECUTE_COMMAND = "execute_command"
    WAIT = "wait"
    OBSERVE = "observe"             # re-snapshot environment
    NOOP = "noop"


class CapabilityTier(str, Enum):
    """Ranked interaction hierarchy — see spec section 3."""

    T1_NATIVE_API = "t1_native_api"         # app exposes a real automation API
    T2_DOM_ARIA = "t2_dom_aria"             # browser DOM / accessibility tree
    T3_UIA = "t3_uia"                       # Windows UI Automation
    T4_ADAPTER = "t4_adapter"               # app-specific adapter (Office, VSCode, etc.)
    T5_VISION = "t5_vision"                 # screenshot + OCR + visual detection
    T6_INPUT_FALLBACK = "t6_input_fallback" # mouse/keyboard
    T7_RECOVERY = "t7_recovery"             # recovery-mode driver (escape hatch)


@dataclass
class VerificationSpec:
    """How to verify the action succeeded."""

    # Free-form check instructions interpreted by VerificationEngine
    expect_url_substring: str = ""
    expect_window_title_substring: str = ""
    expect_control_name: str = ""
    expect_text_present: str = ""
    expect_file_path: str = ""
    expect_process_running: str = ""
    expect_volume: Optional[int] = None          # 0-100
    expect_screenshot_signature_stable: bool = False
    custom_check: str = ""                      # name of a registered check fn
    timeout_ms: int = 5000
    poll_interval_ms: int = 250


@dataclass
class Action:
    """A single typed interaction SONIC plans to perform."""

    action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:10])
    action_type: ActionType = ActionType.NOOP
    target_name: str = ""                  # human description ("Save button")
    target_role: str = ""                  # ControlRole value
    target_text: str = ""                  # text to match
    target_automation_id: str = ""         # UIA AutomationId / aria-testid
    target_url: str = ""                   # for NAVIGATE
    target_process: str = ""               # for OPEN_APP
    target_path: str = ""                  # for FILE_*
    coordinates: tuple[int, int] = (0, 0)  # for input fallback
    text: str = ""                         # for TYPE / SET_VALUE
    keys: list[str] = field(default_factory=list)  # for KEYPRESS
    scroll_direction: str = ""             # "up"/"down"/"left"/"right"
    scroll_amount: int = 0
    drag_to: tuple[int, int] = (0, 0)
    parameters: dict = field(default_factory=dict)
    preferred_tier: CapabilityTier = CapabilityTier.T3_UIA
    verification: Optional[VerificationSpec] = None
    is_destructive: bool = False           # delete, send, pay, etc.
    require_confirmation: bool = False
    description: str = ""                  # human-readable
    parent_action_id: str = ""             # for parallel sub-actions

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action_type"] = self.action_type.value
        d["preferred_tier"] = self.preferred_tier.value
        return d


@dataclass
class ActionResult:
    """The outcome of executing an Action."""

    action_id: str = ""
    success: bool = False
    error: str = ""
    error_class: str = ""                  # "validation" / "resolution" / "execution" / "verification"
    used_tier: CapabilityTier = CapabilityTier.T6_INPUT_FALLBACK
    used_method: str = ""                  # e.g. "playwright_click", "uia_invoke"
    duration_ms: float = 0.0
    verification: Optional[dict] = None     # result of postcondition check
    recovered_from: Optional[str] = None   # previous failed attempt action_id
    screenshot_path: str = ""
    raw_response: Any = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["used_tier"] = self.used_tier.value
        return d


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────
class ActionValidator:
    """Pre-execution guard. Blocks dangerous / malformed actions."""

    @staticmethod
    def validate(action: Action) -> tuple[bool, str]:
        if action.action_type == ActionType.NOOP:
            return True, ""

        if action.action_type in (ActionType.CLICK, ActionType.DOUBLE_CLICK,
                                  ActionType.RIGHT_CLICK, ActionType.HOVER,
                                  ActionType.MOUSE_MOVE):
            x, y = action.coordinates
            if action.target_name == "" and action.target_text == "" and (x, y) == (0, 0):
                return False, "click target unspecified"

        if action.action_type == ActionType.TYPE and not action.text:
            return False, "type action missing text"

        if action.action_type == ActionType.KEYPRESS and not action.keys:
            return False, "keypress action missing keys"

        if action.action_type == ActionType.NAVIGATE and not action.target_url:
            return False, "navigate action missing url"

        if action.action_type == ActionType.OPEN_APP and not action.target_process and not action.target_name:
            return False, "open_app action missing target"

        if action.action_type in (ActionType.FILE_DELETE, ActionType.FILE_MOVE,
                                  ActionType.CLOSE_APP):
            if not action.is_destructive:
                # implicitly mark destructive; require explicit opt-in to skip confirm
                action.is_destructive = True
            if action.require_confirmation is False:
                # Destructive default — caller must opt in to skip confirmation
                action.require_confirmation = True

        return True, ""
