"""
Unit tests — Phase 6.4 (API Layer test_schemas, test_error_handlers, test_dependencies)
Tests schema validations, global exception handlers, and FastAPI dependency overrides.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from backend.api.error_handlers import register_exception_handlers
from backend.api.schemas.common import ApiError, HealthResponseData, StandardResponse
from backend.api.schemas.document import DocumentCreateResponseData
from backend.core.exceptions import BackendError, NotFoundError


# ---------------------------------------------------------------------------
# API Schemas Tests
# ---------------------------------------------------------------------------

class TestSchemas:
    def test_api_error_validation(self):
        err = ApiError(code="E01", message="Error")
        assert err.code == "E01"
        assert err.details is None

    def test_standard_response_generic(self):
        resp = StandardResponse[HealthResponseData](
            success=True,
            message="OK",
            data=HealthResponseData(status="ok")
        )
        assert resp.success is True
        assert resp.data.status == "ok"

    def test_document_response_schema(self):
        doc = DocumentCreateResponseData(
            document_id="doc_1",
            filename="f.txt",
            content_type="text/plain",
            size=10,
            uploaded_at="now",
            status="AVAILABLE",
        )
        assert doc.document_id == "doc_1"


# ---------------------------------------------------------------------------
# API Error Handlers Tests
# ---------------------------------------------------------------------------

class TestErrorHandlers:
    @pytest.fixture
    def client(self):
        app = FastAPI()
        register_exception_handlers(app)

        @app.get("/backend-error")
        async def trigger_backend():
            raise NotFoundError("Resource missing")

        @app.post("/validation-error")
        async def trigger_validation():
            # Triggering RequestValidationError manually for testing
            raise RequestValidationError(errors=[{"loc": ("body", "id"), "msg": "field required", "type": "value_error"}])

        @app.get("/unexpected-error")
        async def trigger_unexpected():
            raise ValueError("Something unexpected")

        return TestClient(app, raise_server_exceptions=False)

    def test_handle_backend_error_returns_structured_response(self, client):
        response = client.get("/backend-error")
        assert response.status_code == 404
        
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "Resource missing"
        assert len(data["errors"]) == 1
        assert data["errors"][0]["code"] == "NOT_FOUND"

    def test_handle_validation_error_returns_422(self, client):
        response = client.post("/validation-error")
        assert response.status_code == 422
        
        data = response.json()
        assert data["success"] is False
        assert data["errors"][0]["code"] == "REQUEST_VALIDATION_ERROR"
        assert "id" in str(data["errors"][0]["details"])

    def test_handle_unexpected_error_returns_500(self, client):
        response = client.get("/unexpected-error")
        assert response.status_code == 500
        
        data = response.json()
        assert data["success"] is False
        assert data["errors"][0]["code"] == "INTERNAL_SERVER_ERROR"


# ---------------------------------------------------------------------------
# API Dependencies Tests
# ---------------------------------------------------------------------------
class TestDependencies:
    def test_get_api_logger(self):
        from backend.api.dependencies import get_api_logger
        logger = get_api_logger()
        # Ensure a standard Python logger is returned
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")
