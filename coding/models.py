from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    RECOVERING = "RECOVERING"


@dataclass
class CodingTask:
    request: str
    user_id: str = "default"
    session_id: str = ""
    workspace: str = ""
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    state: TaskState = TaskState.CREATED
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    finished_at: float = 0.0
    files_changed: list[str] = field(default_factory=list)
    tests_run: bool = False
    result: str = ""
    error: str = ""
    raw_output: str = ""
    duration: float = 0.0
    retry_count: int = 0
    context_files: list[str] = field(default_factory=list)
    project_root: str = ""

    def mark_started(self) -> None:
        self.started_at = time.time()
        self.state = TaskState.EXECUTING

    def mark_finished(self, success: bool, result: str = "", error: str = "") -> None:
        self.finished_at = time.time()
        self.duration = self.finished_at - self.started_at
        self.result = result
        self.error = error
        self.state = TaskState.SUCCEEDED if success else TaskState.FAILED

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "request": self.request,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "workspace": self.workspace,
            "project_root": self.project_root,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration": self.duration,
            "files_changed": self.files_changed,
            "tests_run": self.tests_run,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
        }


@dataclass
class CodingResult:
    success: bool
    status: str = ""
    summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    tests_run: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_output: str = ""
    task: CodingTask | None = None

    def to_response_text(self) -> str:
        parts = []
        if self.summary:
            parts.append(self.summary)
        if self.files_changed:
            parts.append(f"Files changed: {', '.join(self.files_changed)}")
        if self.errors:
            parts.append(f"Errors: {'; '.join(self.errors)}")
        if self.warnings:
            parts.append(f"Warnings: {'; '.join(self.warnings)}")
        if not parts:
            parts.append("Coding task completed." if self.success else "Coding task failed.")
        return "\n".join(parts)
