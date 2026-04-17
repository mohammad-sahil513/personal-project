"""
Shared backend exceptions.
"""

from __future__ import annotations

from typing import Any


class BackendError(Exception):
    """
    Base backend exception.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "BACKEND_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class ValidationError(BackendError):
    def __init__(
        self,
        message: str = "Validation failed",
        *,
        error_code: str = "VALIDATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=422,
            details=details,
        )


class NotFoundError(BackendError):
    def __init__(
        self,
        message: str = "Resource not found",
        *,
        error_code: str = "NOT_FOUND",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=404,
            details=details,
        )


class ConflictError(BackendError):
    def __init__(
        self,
        message: str = "Conflict occurred",
        *,
        error_code: str = "CONFLICT",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=409,
            details=details,
        )


class ConfigurationError(BackendError):
    def __init__(
        self,
        message: str = "Configuration error",
        *,
        error_code: str = "CONFIG_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=500,
            details=details,
        )


class StorageError(BackendError):
    def __init__(
        self,
        message: str = "Storage error",
        *,
        error_code: str = "STORAGE_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=500,
            details=details,
        )