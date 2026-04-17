"""
Root API router.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.routes.document_routes import router as document_router
from backend.api.routes.health_routes import router as health_router
from backend.api.routes.output_routes import router as output_router
from backend.api.routes.template_routes import router as template_router
from backend.api.routes.workflow_event_routes import router as workflow_event_router
from backend.api.routes.workflow_routes import router as workflow_router
from backend.core.config import get_settings
from backend.api.routes.workflow_inspection_routes import router as workflow_inspection_router
settings = get_settings()

api_router = APIRouter(prefix=settings.api_prefix)

api_router.include_router(health_router, tags=["health"])
api_router.include_router(document_router)
api_router.include_router(template_router)
api_router.include_router(workflow_router)
api_router.include_router(workflow_event_router)
api_router.include_router(output_router)
api_router.include_router(workflow_inspection_router)