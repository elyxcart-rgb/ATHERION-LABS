"""Memory data models for SONIC AI long-term brain."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PREFERENCE = "preference"
    PROCEDURAL = "procedural"
    PROJECT = "project"
    TASK = "task"
    ERROR = "error"
    LESSON = "lesson"
    ENTITY = "entity"
    FACT = "fact"


class Importance(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    EPHEMERAL = "ephemeral"


class Confidence(str, Enum):
    FACT = "fact"
    INFERRED = "inferred"
    OBSERVATION = "observation"
    LESSON = "lesson"
    GUESS = "guess"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    FORGOTTEN = "forgotten"


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Memory:
    memory_id: str = field(default_factory=_uuid)
    user_id: str = ""
    memory_type: str = MemoryType.EPISODIC.value
    content: str = ""
    importance: str = Importance.MEDIUM.value
    confidence: str = Confidence.OBSERVATION.value
    status: str = MemoryStatus.ACTIVE.value
    tags: str = ""  # comma-separated
    project_id: str = ""
    task_id: str = ""
    session_id: str = ""
    source_message: str = ""
    access_count: int = 0
    reinforcement_count: int = 0
    contradiction_count: int = 0
    superseded_by: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_accessed_at: str = ""
    expires_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Memory:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


@dataclass
class Project:
    project_id: str = field(default_factory=_uuid)
    user_id: str = ""
    name: str = ""
    root_path: str = ""
    technology_stack: str = ""
    architecture_summary: str = ""
    important_files: str = ""
    conventions: str = ""
    current_status: str = "active"
    known_bugs: str = ""
    known_constraints: str = ""
    past_changes: str = ""
    project_preferences: str = ""
    last_activity: str = field(default_factory=_now_iso)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Project:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


@dataclass
class Task:
    task_id: str = field(default_factory=_uuid)
    user_id: str = ""
    project_id: str = ""
    session_id: str = ""
    objective: str = ""
    status: str = "pending"
    steps: str = ""
    tools_used: str = ""
    files_changed: str = ""
    result: str = ""
    failures: str = ""
    lessons_learned: str = ""
    created_at: str = field(default_factory=_now_iso)
    completed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Task:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


@dataclass
class ToolExperience:
    experience_id: str = field(default_factory=_uuid)
    user_id: str = ""
    task_pattern: str = ""
    tool_name: str = ""
    outcome: str = ""
    success: bool = True
    duration_ms: int = 0
    failures: int = 0
    recovery_strategy: str = ""
    project_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    last_used: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> ToolExperience:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


@dataclass
class Preference:
    preference_id: str = field(default_factory=_uuid)
    user_id: str = ""
    category: str = ""  # communication, technical, product, workflow
    key: str = ""
    value: str = ""
    confidence: str = Confidence.OBSERVATION.value
    source: str = ""  # explicit, inferred, observed
    reinforcement_count: int = 1
    superseded_by: str = ""
    status: str = MemoryStatus.ACTIVE.value
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_confirmed_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Preference:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


@dataclass
class SessionSummary:
    session_id: str = field(default_factory=_uuid)
    user_id: str = ""
    started_at: str = ""
    ended_at: str = ""
    summary: str = ""
    topic: str = ""
    tools_used: str = ""
    files_touched: str = ""
    decisions: str = ""
    unresolved: str = ""
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> SessionSummary:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


@dataclass
class Entity:
    entity_id: str = field(default_factory=_uuid)
    user_id: str = ""
    entity_type: str = ""  # project, subsystem, person, tool, concept
    name: str = ""
    description: str = ""
    related_to: str = ""  # comma-separated entity_ids
    project_id: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row: dict) -> Entity:
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})
