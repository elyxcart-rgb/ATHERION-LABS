from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from .models import CodingTask, CodingResult, TaskState
from .workspace import WorkspaceManager
from .process import ProcessManager
from .output_parser import OutputParser
from .verification import Verifier
from .intent_detector import IntentDetector

logger = logging.getLogger("sonic.coding")

# ── Smart workspace extraction ──────────────────────────────────────────
_DESKTOP = str(Path.home() / "Desktop")
_DOCUMENTS = str(Path.home() / "Documents")
_DOWNLOADS = str(Path.home() / "Downloads")

_LOCATION_MAP = {
    "desktop": _DESKTOP,
    "save to desktop": _DESKTOP,
    "desktop per": _DESKTOP,
    "documents": _DOCUMENTS,
    "downloads": _DOWNLOADS,
}


def extract_target_dir(request: str) -> str | None:
    """Extract explicit save location from natural language request."""
    low = request.lower()
    for keyword, path in _LOCATION_MAP.items():
        if keyword in low:
            return path
    return None


class OpenCodeAdapter:
    def __init__(self) -> None:
        self._process = ProcessManager()
        self._max_concurrent = 2
        self._default_timeout = 300
        self._recovery_attempts = 2

    @property
    def is_available(self) -> bool:
        return self._process.find_opencode() is not None

    async def execute(
        self,
        request: str,
        workspace: str | None = None,
        user_id: str = "default",
        session_id: str = "",
        timeout: int | None = None,
    ) -> CodingResult:
        task = CodingTask(
            request=request,
            user_id=user_id,
            session_id=session_id,
        )
        timeout = timeout or self._default_timeout

        # Smart: extract target dir from request if no workspace specified
        if not workspace:
            extracted = extract_target_dir(request)
            if extracted:
                workspace = extracted
                logger.info("[SONIC] extracted workspace from request: %s", workspace)

        project_root = WorkspaceManager.resolve_project_root(workspace)
        if not WorkspaceManager.validate_workspace(project_root):
            return CodingResult(
                success=False, status="REJECTED",
                summary="Invalid or blocked workspace path.",
                task=task,
            )

        task.project_root = project_root
        task.workspace = project_root

        if not WorkspaceManager.acquire_workspace(task.task_id, project_root):
            return CodingResult(
                success=False, status="QUEUED",
                summary="Another coding task is running on this workspace. Wait or cancel it.",
                task=task,
            )

        try:
            return await self._run_task(task, timeout)
        finally:
            WorkspaceManager.release_workspace(task.task_id, project_root)

    async def _run_task(self, task: CodingTask, timeout: int) -> CodingResult:
        task.state = TaskState.ANALYZING
        logger.info("[SONIC] task created id=%s request=%s", task.task_id, task.request[:80])

        context_files = WorkspaceManager.gather_context(
            task.project_root, task.request)
        task.context_files = context_files
        logger.info("[SONIC] workspace resolved root=%s context_files=%d",
                     task.project_root, len(context_files))

        prompt = self._build_prompt(task)
        task.mark_started()
        logger.info("[SONIC] process started id=%s", task.task_id)

        from reliability.classifier import classify_error, ErrorCategory
        from reliability.retry import RetryEngine
        retry_engine = RetryEngine()

        for attempt in range(self._recovery_attempts + 1):
            success, raw, err = await self._process.run_opencode(
                task, task.project_root, prompt, timeout)

            task.raw_output = raw + ("\n" + err if err else "")

            if not success and err:
                classification = classify_error(err, "opencode")
                is_transient = classification.category in (
                    ErrorCategory.SERVICE_UNAVAILABLE,
                    ErrorCategory.TRANSIENT_NETWORK,
                    ErrorCategory.TIMEOUT,
                    ErrorCategory.RATE_LIMITED,
                )

                if is_transient and attempt < self._recovery_attempts:
                    task.state = TaskState.RECOVERING
                    task.retry_count += 1
                    delay = classification.initial_delay * (2 ** attempt)
                    logger.info("[SONIC] transient failure (attempt %d/%d): %s — retrying in %.1fs",
                                attempt + 1, self._recovery_attempts + 1,
                                classification.category.value, delay)
                    await asyncio.sleep(delay)
                    continue
                elif not is_transient:
                    logger.info("[SONIC] non-transient error: %s", classification.category.value)
                    break

            logger.info("[SONIC] execution finished success=%s", success)
            break

        result = OutputParser.parse(task.raw_output, success)
        result.task = task

        if success:
            task.state = TaskState.VERIFYING
            logger.info("[SONIC] verification started")
            verify_state = Verifier.verify(task)
            task.state = verify_state
            if verify_state == TaskState.SUCCEEDED:
                logger.info("[SONIC] verification passed")
                result.success = True
                result.status = "SUCCEEDED"
            else:
                logger.info("[SONIC] verification failed: %s", task.error)
                result.success = False
                result.status = "VERIFICATION_FAILED"
                result.errors.append(task.error)
        else:
            result.success = False
            result.status = "FAILED"

        task.mark_finished(result.success, result.summary, "; ".join(result.errors))
        logger.info("[SONIC] task completed id=%s status=%s duration=%.1fs",
                     task.task_id, result.status, task.duration)
        return result

    def _build_prompt(self, task: CodingTask) -> str:
        parts = [f"TASK: {task.request}"]
        # Explicit output directory — files MUST be saved here
        parts.append(f"\nOUTPUT DIRECTORY: {task.project_root}")
        parts.append("All files must be saved in the OUTPUT DIRECTORY above.")
        parts.append("Do NOT save files in any other location.")
        if task.context_files:
            parts.append(f"\nRelevant files in project: {', '.join(task.context_files[:10])}")
        parts.append(f"\nProject root: {task.project_root}")
        return "\n".join(parts)

    def cancel_task(self, task_id: str) -> bool:
        cancelled = self._process.cancel(task_id)
        if cancelled:
            logger.info("[SONIC] task cancelled id=%s", task_id)
        return cancelled
