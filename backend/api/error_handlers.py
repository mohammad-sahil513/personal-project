"""
Global API exception handlers.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.exceptions import BackendError
from backend.core.logging import get_logger
from backend.core.response import error_response

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register global exception handlers on the FastAPI app.
    """

    @app.exception_handler(BackendError)
    async def handle_backend_error(
        request: Request,
        exc: BackendError,
    ) -> JSONResponse:
        logger.error(
            "BackendError raised",
            extra={
                "path": str(request.url.path),
                "method": request.method,
                "error_code": exc.error_code,
                "details": exc.details,
            },
        )

        return JSONResponse(
            status_code=exc.status_code,
            content=error_response(
                message=exc.message,
                errors=[
                    {
                        "code": exc.error_code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                ],
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        logger.warning(
            "Request validation failed",
            extra={
                "path": str(request.url.path),
                "method": request.method,
                "errors": exc.errors(),
            },
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response(
                message="Request validation failed",
                errors=[
                    {
                        "code": "REQUEST_VALIDATION_ERROR",
                        "message": "Invalid request payload",
                        "details": {"errors": exc.errors()},
                    }
                ],
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.exception(
            "Unhandled exception occurred",
            extra={
                "path": str(request.url.path),
                "method": request.method,
            },
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                message="An unexpected error occurred",
                errors=[
                    {
                        "code": "INTERNAL_SERVER_ERROR",
                        "message": "An unexpected error occurred",
                    }
                ],
            ),
        )