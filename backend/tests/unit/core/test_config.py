"""
Tests for core configuration settings.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from backend.core.config import Settings, get_settings


def test_settings_load_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_DEBUG", raising=False)
    settings = Settings(model_config={"env_file": None})
    assert settings.app_name == "backend"
    assert settings.app_env == "local"
    assert settings.app_debug is True
    assert settings.api_prefix == "/api"


def test_settings_property_paths():
    settings = Settings(local_storage_root="/dummy/path")
    assert isinstance(settings.storage_root_path, Path)
    assert str(settings.storage_root_path) == os.path.normpath("/dummy/path")
    assert str(settings.workflow_runs_path).endswith("workflow_runs")
    assert str(settings.documents_path).endswith("documents")
    assert str(settings.templates_path).endswith("templates")
    assert str(settings.outputs_path).endswith("outputs")
    assert str(settings.executions_path).endswith("executions")
    assert str(settings.logs_path).endswith("logs")


def test_get_settings_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
