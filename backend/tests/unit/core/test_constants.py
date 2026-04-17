"""
Tests for core constants.
"""

from __future__ import annotations

from backend.core import constants


def test_constants_values():
    assert constants.API_PREFIX == "/api"
    assert constants.DEFAULT_APP_NAME == "backend"
    assert constants.DEFAULT_LOG_LEVEL == "INFO"
    assert "http://localhost:3000" in constants.DEFAULT_CORS_ORIGINS
    assert constants.DEFAULT_STORAGE_ROOT == "backend/storage"
    assert constants.HEALTH_PATH == "/health"
    assert constants.READY_PATH == "/ready"
