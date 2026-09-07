"""SONIC AI — Retry Engine.

Bounded retry with exponential backoff and jitter.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Callable, Any, Optional
from dataclasses import dataclass, field

from .classifier import ErrorClassification, ErrorCategory


@dataclass
class RetryResult:
    success: bool
    result: Any = None
    error: str = ""
    attempts: int = 0
    total_time: float = 0.0
    recovery_action: str = ""


class RetryEngine:
    def __init__(self):
        self._history: dict[str, list] = {}

    async def execute_with_retry(
        self,
        func: Callable,
        classification: ErrorClassification,
        task_id: str = "",
        on_retry: Optional[Callable] = None,
    ) -> RetryResult:
        if not classification.retryable:
            try:
                result = await self._await_func(func)
                return RetryResult(success=True, result=result, attempts=1)
            except Exception as e:
                return RetryResult(
                    success=False, error=str(e), attempts=1,
                    recovery_action="no_retry"
                )

        start = time.time()
        last_error = ""
        max_attempts = classification.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                result = await self._await_func(func)
                elapsed = time.time() - start
                if attempt > 1:
                    print(f"[RETRY] Succeeded on attempt {attempt} ({elapsed:.1f}s)")
                return RetryResult(
                    success=True, result=result,
                    attempts=attempt, total_time=elapsed,
                    recovery_action=f"retry_attempt_{attempt}" if attempt > 1 else "first_attempt"
                )
            except Exception as e:
                last_error = str(e)
                if attempt < max_attempts:
                    delay = self._calculate_delay(attempt, classification)
                    print(f"[RETRY] Attempt {attempt} failed: {last_error[:100]}")
                    print(f"[RETRY] Waiting {delay:.1f}s before retry {attempt + 1}/{max_attempts}")
                    if on_retry:
                        await on_retry(attempt, delay, last_error)
                    await asyncio.sleep(delay)

        elapsed = time.time() - start
        print(f"[RETRY] All {max_attempts} attempts exhausted ({elapsed:.1f}s)")
        return RetryResult(
            success=False, error=last_error,
            attempts=max_attempts, total_time=elapsed,
            recovery_action="exhausted"
        )

    def _calculate_delay(self, attempt: int, classification: ErrorClassification) -> float:
        delay = classification.initial_delay * (2 ** (attempt - 1))
        delay = min(delay, classification.max_delay)
        jitter = random.uniform(0.8, 1.2)
        return delay * jitter

    async def _await_func(self, func: Callable) -> Any:
        if asyncio.iscoroutinefunction(func):
            return await func()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func)

    def record_task(self, task_id: str, event: str) -> None:
        if task_id not in self._history:
            self._history[task_id] = []
        self._history[task_id].append({
            "event": event,
            "time": time.time(),
        })

    def get_task_history(self, task_id: str) -> list:
        return self._history.get(task_id, [])
