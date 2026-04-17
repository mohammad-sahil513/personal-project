"""
Tests for TaskDispatcher dispatching across all modes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import BackgroundTasks

from backend.workers.task_dispatcher import TaskDispatcher


def test_task_dispatcher_fastapi_background_tasks():
    # Dispatch Mode 1: BackgroundTasks
    dispatcher = TaskDispatcher()
    fastapi_tasks = BackgroundTasks()

    def sample_task(x: int):
        pass

    mode = dispatcher.dispatch(sample_task, 42, background_tasks=fastapi_tasks)
    assert mode == "BACKGROUND_TASK"
    # Verify the task was added to the BackgroundTasks object
    assert len(fastapi_tasks.tasks) == 1


@pytest.mark.asyncio
async def test_task_dispatcher_asyncio_create_task():
    # Dispatch Mode 2: asyncio.create_task (requires a running event loop)
    dispatcher = TaskDispatcher()
    execution_result = {}

    def sample_task():
        execution_result["done"] = True

    # The running loop during a pytest.mark.asyncio test will be used
    mode = dispatcher.dispatch(sample_task)
    assert mode == "ASYNCIO_TASK"

    # Give the event loop a tiny moment to execute the generated task
    await asyncio.sleep(0.01)
    assert execution_result.get("done") is True


def test_task_dispatcher_sync_fallback():
    # Dispatch Mode 3: asyncio.run (used when NO event loop is running)
    dispatcher = TaskDispatcher()
    execution_result = {}

    def sample_task():
        execution_result["done"] = True

    # Call dispatch directly in a sync test context (no running loop)
    mode = dispatcher.dispatch(sample_task)
    assert mode == "SYNC_FALLBACK"
    assert execution_result.get("done") is True


@pytest.mark.asyncio
async def test_task_dispatcher_on_error_callback():
    # Verify the callback is properly invoked
    dispatcher = TaskDispatcher()
    error_state = {}

    def failing_task():
        raise ValueError("Boom")

    def on_error(exc: Exception):
        error_state["caught"] = exc

    # Dispatch to the running loop with an error callback attached
    dispatcher.dispatch(failing_task, on_error=on_error)
    
    # Wait for execution
    await asyncio.sleep(0.01)
    
    assert "caught" in error_state
    assert isinstance(error_state["caught"], ValueError)
