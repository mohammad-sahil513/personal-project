"""
Tests for core exceptions.
"""

from __future__ import annotations

from backend.core.exceptions import (
    BackendError,
    ConflictError,
    ConfigurationError,
    NotFoundError,
    StorageError,
    ValidationError,
)


def test_backend_error_defaults():
    err = BackendError("Base error")
    assert err.message == "Base error"
    assert err.error_code == "BACKEND_ERROR"
    assert err.status_code == 500
    assert err.details == {}


def test_validation_error():
    err = ValidationError(details={"field": "test"})
    assert err.status_code == 422
    assert err.error_code == "VALIDATION_ERROR"
    assert err.details == {"field": "test"}


def test_not_found_error():
    err = NotFoundError("Missing item")
    assert err.status_code == 404
    assert err.error_code == "NOT_FOUND"
    assert err.message == "Missing item"


def test_conflict_error():
    err = ConflictError()
    assert err.status_code == 409
    assert err.error_code == "CONFLICT"


def test_configuration_error():
    err = ConfigurationError()
    assert err.status_code == 500
    assert err.error_code == "CONFIG_ERROR"


def test_storage_error():
    err = StorageError()
    assert err.status_code == 500
    assert err.error_code == "STORAGE_ERROR"
