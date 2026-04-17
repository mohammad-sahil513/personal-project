"""
Shared FastAPI dependencies.
"""

from __future__ import annotations

from fastapi import Request

from backend.application.services.workflow_event_service import (
    WorkflowEventService,
    get_workflow_event_service,
)
from backend.core.config import Settings, get_settings
from backend.core.logging import get_logger


def get_app_settings() -> Settings:
    """
    FastAPI dependency for application settings.
    """
    return get_settings()


def get_api_logger():
    """
    FastAPI dependency for an API-layer logger.
    """
    return get_logger("backend.api")


def get_request_id(request: Request) -> str | None:
    """
    FastAPI dependency for the current request correlation ID.
    """
    return getattr(request.state, "request_id", None)


def get_workflow_event_broker() -> WorkflowEventService:
    """
    FastAPI dependency for the singleton workflow event service.
    """
    return get_workflow_event_service()