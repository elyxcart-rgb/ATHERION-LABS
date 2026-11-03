"""Adapter-friendly import of the core ActionType enum and Action dataclass.

Allows adapter modules to import ActionType/Action without circular imports
when run standalone (e.g. tests).
"""
from __future__ import annotations

try:
    from ..actions import ActionType, Action  # noqa: F401
except Exception:  # pragma: no cover
    # Fallback shim — allows adapters to be imported in isolation
    from enum import Enum
    from dataclasses import dataclass, field
    import uuid

    class ActionType(str, Enum):
        CLICK = "click"
        DOUBLE_CLICK = "double_click"
        RIGHT_CLICK = "right_click"
        HOVER = "hover"
        TYPE = "type"
        KEYPRESS = "keypress"
        SCROLL = "scroll"
        DRAG = "drag"
        MOUSE_MOVE = "mouse_move"
        FOCUS = "focus"
        INVOKE = "invoke"
        SET_VALUE = "set_value"
        TOGGLE = "toggle"
        OPEN_APP = "open_app"
        CLOSE_APP = "close_app"
        NAVIGATE = "navigate"
        SWITCH_TAB = "switch_tab"
        NEW_TAB = "new_tab"
        CLOSE_TAB = "close_tab"
        FILE_OPEN = "file_open"
        FILE_SAVE = "file_save"
        FILE_MOVE = "file_move"
        FILE_COPY = "file_copy"
        FILE_DELETE = "file_delete"
        FILE_RENAME = "file_rename"
        FILE_SEARCH = "file_search"
        RUN_WORKFLOW = "run_workflow"
        EXECUTE_COMMAND = "execute_command"
        WAIT = "wait"
        OBSERVE = "observe"
        NOOP = "noop"

    @dataclass
    class Action:
        action_id: str = field(default_factory=lambda: str(uuid.uuid4())[:10])
        action_type: ActionType = ActionType.NOOP
        target_name: str = ""
        target_role: str = ""
        target_text: str = ""
        target_automation_id: str = ""
        target_url: str = ""
        target_process: str = ""
        target_path: str = ""
        coordinates: tuple = (0, 0)
        text: str = ""
        keys: list = field(default_factory=list)
        scroll_direction: str = ""
        scroll_amount: int = 0
        drag_to: tuple = (0, 0)
        parameters: dict = field(default_factory=dict)
        preferred_tier: object = None
        verification: object = None
        is_destructive: bool = False
        require_confirmation: bool = False
        description: str = ""
        parent_action_id: str = ""

        def to_dict(self):
            from dataclasses import asdict
            d = asdict(self)
            d["action_type"] = self.action_type.value
            return d


__all__ = ["ActionType", "Action"]
