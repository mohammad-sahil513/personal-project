"""
Root conftest for the backend test suite.

Provides shared fixtures used across all unit and integration tests,
including temporary directories, settings overrides, and mock clients.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Force test-safe environment *before* any backend module is imported.
# This ensures get_settings() will never hit a real .env file.
# ---------------------------------------------------------------------------
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "DEBUG")


@pytest.fixture()
def tmp_storage(tmp_path: Path) -> Path:
    """
    Create a temporary storage root with all sub-directories the app expects.
    Returns the root ``tmp_path`` so tests can point repositories at it.
    """
    for sub in (
        "documents",
        "templates",
        "workflow_runs",
        "executions",
        "outputs",
        "logs",
    ):
        (tmp_path / sub).mkdir()
    return tmp_path


@pytest.fixture()
def settings_override(tmp_storage: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Monkeypatch environment variables so ``get_settings()`` returns a
    Settings instance that points at the temporary storage root.

    Because ``get_settings()`` is cached with ``@lru_cache``, we also
    clear the cache so the patched env vars are picked up.
    """
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_storage))

    from backend.core.config import get_settings

    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()
