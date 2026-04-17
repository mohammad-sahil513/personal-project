"""
Shared API schema models.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ApiError(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(default=None, description="Optional field name")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured error details",
    )


class ApiMeta(BaseModel):
    request_id: str | None = Field(default=None, description="Optional request correlation ID")


class StandardResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: T | None = None
    errors: list[ApiError] = Field(default_factory=list)
    meta: ApiMeta = Field(default_factory=ApiMeta)


class HealthResponseData(BaseModel):
    status: str


class ReadyResponseData(BaseModel):
    status: str
    app_name: str
    environment: str
    storage_root: str