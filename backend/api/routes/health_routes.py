"""
Health and readiness routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.core.config import get_settings
from backend.core.response import success_response

router = APIRouter()

settings = get_settings()


@router.get("/health")
async def health_check() -> dict:
    """
    Lightweight liveness check.
    """
    return success_response(
        message="Service is healthy",
        data={"status": "ok"},
    )


@router.get("/ready")
async def readiness_check() -> dict:
    """
    Readiness check for config/bootstrap visibility.
    """
    return success_response(
        message="Service is ready",
        data={
            "status": "ready",
            "app_name": settings.app_name,
            "environment": settings.app_env,
            "storage_root": str(settings.storage_root_path),
        },
    )