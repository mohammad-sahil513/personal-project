"""
Tests for BackgroundRunner executing async and sync callables.
"""

from __future__ import annotations

import pytest
from backend.workers.background_runner import BackgroundRunner


@pytest.mark.asyncio
async def test_background_runner_sync_callable():
    runner = BackgroundRunner()

    def sync_func(a, b):
        return a + b

    result = await runner.run(sync_func, 2, 3)
    assert result == 5


@pytest.mark.asyncio
async def test_background_runner_async_callable():
    runner = BackgroundRunner()

    async def async_func(a, b):
        return a * b

    result = await runner.run(async_func, 4, 3)
    assert result == 12
