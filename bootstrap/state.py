"""SONIC AI Bootstrapper - State Manager.

Persists bootstrap state to disk.
Tracks completed checks, installed dependencies, and bootstrap version.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional


class BootstrapState:
    def __init__(self, state_dir: Optional[str] = None):
        if state_dir is None:
            state_dir = str(Path.home() / "AppData" / "Local" / "SONIC AI")
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._file = self._dir / "bootstrap_state.json"
        self._data = self._load()

    def _load(self) -> dict:
        if self._file.exists():
            try:
                with open(self._file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "schema_version": 1,
            "bootstrap_version": "1.0.0",
            "completed": False,
            "last_check": 0,
            "installed_requirements": [],
            "failed_requirements": [],
            "skipped_optional": [],
            "system_info": {},
        }

    def _save(self) -> None:
        try:
            with open(self._file, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception:
            pass

    @property
    def completed(self) -> bool:
        return self._data.get("completed", False)

    @completed.setter
    def completed(self, value: bool) -> None:
        self._data["completed"] = value
        self._save()

    @property
    def last_check(self) -> float:
        return self._data.get("last_check", 0)

    def mark_completed(self) -> None:
        self._data["completed"] = True
        self._data["last_check"] = time.time()
        self._save()

    def mark_requirement_installed(self, req_id: str) -> None:
        if req_id not in self._data["installed_requirements"]:
            self._data["installed_requirements"].append(req_id)
        if req_id in self._data["failed_requirements"]:
            self._data["failed_requirements"].remove(req_id)
        self._save()

    def mark_requirement_failed(self, req_id: str) -> None:
        if req_id not in self._data["failed_requirements"]:
            self._data["failed_requirements"].append(req_id)
        self._save()

    def mark_optional_skipped(self, req_id: str) -> None:
        if req_id not in self._data["skipped_optional"]:
            self._data["skipped_optional"].append(req_id)
        self._save()

    def is_requirement_installed(self, req_id: str) -> bool:
        return req_id in self._data.get("installed_requirements", [])

    def is_requirement_failed(self, req_id: str) -> bool:
        return req_id in self._data.get("failed_requirements", [])

    def set_system_info(self, info: dict) -> None:
        self._data["system_info"] = info
        self._save()

    def get_system_info(self) -> dict:
        return self._data.get("system_info", {})

    def needs_check(self, max_age_hours: int = 24) -> bool:
        if not self.completed:
            return True
        age = time.time() - self.last_check
        return age > max_age_hours * 3600

    def reset(self) -> None:
        self._data = {
            "schema_version": 1,
            "bootstrap_version": "1.0.0",
            "completed": False,
            "last_check": 0,
            "installed_requirements": [],
            "failed_requirements": [],
            "skipped_optional": [],
            "system_info": {},
        }
        self._save()
