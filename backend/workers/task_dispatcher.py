"""
Task dispatch abstraction for backend background execution.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable

from fastapi import BackgroundTasks

from backend.core.logging import get_logger
from backend.workers.background_runner import BackgroundRunner

logger = get_logger(__name__)


class TaskDispatcher:
    """
    Dispatch background work using:
    1. FastAPI BackgroundTasks when available
    2. asyncio.create_task when a running loop exists
    3. asyncio.run as a synchronous fallback when no loop exists

    Supports an optional async/sync on_error callback for hardening.
    """

    def __init__(self, runner: BackgroundRunner | None = None) -> None:
        self.runner = runner or BackgroundRunner()

    async def _run_with_error_handling(
        self,
        func: Callable[..., Any],
        *args,
        on_error: Callable[[Exception], Any] | None = None,
        **kwargs,
    ) -> Any:
        try:
            return await self.runner.run(func, *args, **kwargs)
        except Exception as exc:
            logger.exception(
                "Background task failed",
                extra={
                    "task_name": getattr(func, "__name__", str(func)),
                    "error": str(exc),
                },
            )

            if on_error is not None:
                callback_result = on_error(exc)
                if inspect.isawaitable(callback_result):
                    await callback_result

            return None

    def dispatch(
        self,
        func: Callable[..., Any],
        *args,
        background_tasks: BackgroundTasks | None = None,
        on_error: Callable[[Exception], Any] | None = None,
        **kwargs,
    ) -> str:
        """
        Dispatch a callable for execution.

        Returns a dispatch mode label so callers can log/report it.
        """
        if background_tasks is not None:
            background_tasks.add_task(
                self._run_with_error_handling,
                func,
                *args,
                on_error=on_error,
                **kwargs,
            )

            logger.info(
                "Task dispatched via FastAPI BackgroundTasks",
                extra={"dispatch_mode": "BACKGROUND_TASK"},
            )
            return "BACKGROUND_TASK"

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                self._run_with_error_handling(
                    func,
                    *args,
                    on_error=on_error,
                    **kwargs,
                )
            )

            logger.info(
                "Task executed via synchronous asyncio.run fallback",
                extra={"dispatch_mode": "SYNC_FALLBACK"},
            )
            return "SYNC_FALLBACK"

        loop.create_task(
            self._run_with_error_handling(
                func,
                *args,
                on_error=on_error,
                **kwargs,
            )
        )

        logger.info(
            "Task dispatched via asyncio.create_task",
            extra={"dispatch_mode": "ASYNCIO_TASK"},
        )
        return "ASYNCIO_TASK"