"""
FastAPI application entrypoint.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.api.error_handlers import register_exception_handlers
from backend.api.router import api_router
from backend.core.config import get_settings
from backend.core.logging import configure_logging, get_logger
from backend.core.request_context import (
    clear_request_id,
    generate_request_id,
    set_request_id,
)

settings = get_settings()
configure_logging()
logger = get_logger(__name__)


def ensure_storage_directories() -> None:
    """
    Ensure all required local storage directories exist.
    """
    directories = [
        settings.storage_root_path,
        settings.workflow_runs_path,
        settings.documents_path,
        settings.templates_path,
        settings.outputs_path,
        settings.executions_path,
        settings.logs_path,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Storage directories ensured",
        extra={
            "storage_root": str(settings.storage_root_path),
        },
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan hook.
    """
    logger.info(
        "Starting backend application",
        extra={
            "app_name": settings.app_name,
            "environment": settings.app_env,
        },
    )

    ensure_storage_directories()

    yield

    logger.info("Shutting down backend application")


app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """
    Attach a request correlation ID to request state, context vars,
    logs, and the response header.
    """
    request_id = request.headers.get("X-Request-Id") or generate_request_id()
    request.state.request_id = request_id
    set_request_id(request_id)

    try:
        response = await call_next(request)
    finally:
        clear_request_id()

    response.headers["X-Request-Id"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)