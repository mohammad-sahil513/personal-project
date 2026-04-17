"""
Unit tests — Phase 6.3b (Application Layer: Services)
Covers metadata services: DocumentService, OutputService, WorkflowService.
Uses isolated repository mocks to verify core logic.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.application.services.document_service import DocumentService
from backend.application.services.output_service import OutputService
from backend.application.services.workflow_service import WorkflowService


# ---------------------------------------------------------------------------
# DocumentService
# ---------------------------------------------------------------------------

class TestDocumentService:
    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock()
        return repo

    @pytest.fixture
    def service(self, mock_repo):
        return DocumentService(repository=mock_repo)

    def test_create_document(self, service, mock_repo):
        mock_repo.create.return_value = {
            "document_id": "doc_123",
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "size": 1024,
            "uploaded_at": "2026-04-01T10:00:00+00:00",
            "status": "AVAILABLE",
        }
        
        dto = service.create_document(
            filename="test.pdf",
            content_type="application/pdf",
            size=1024,
            file_bytes=b"fake data",
        )
        
        # Verify repository calls
        assert mock_repo.create.called
        assert mock_repo.save_binary.called
        mock_repo.save_binary.assert_called_with("doc_123", b"fake data")
        
        assert dto.document_id == "doc_123"
        assert dto.filename == "test.pdf"

    def test_get_document(self, service, mock_repo):
        mock_repo.get.return_value = {
            "document_id": "doc_123",
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "size": 1024,
            "uploaded_at": "2026-04-01",
            "status": "AVAILABLE",
        }
        dto = service.get_document("doc_123")
        assert dto.document_id == "doc_123"
        mock_repo.get.assert_called_with("doc_123")

    def test_get_document_bytes(self, service, mock_repo):
        mock_repo.get_binary.return_value = b"binary_data"
        data = service.get_document_bytes("doc_123")
        assert data == b"binary_data"
        mock_repo.get_binary.assert_called_with("doc_123")

    def test_list_documents(self, service, mock_repo):
        mock_repo.list.return_value = [
            {
                "document_id": "doc_1",
                "filename": "1.pdf",
                "content_type": "application/pdf",
                "size": 1,
                "uploaded_at": "...",
                "status": "AVAILABLE",
            }
        ]
        items = service.list_documents()
        assert len(items) == 1
        assert items[0].document_id == "doc_1"

    def test_update_document(self, service, mock_repo):
        mock_repo.update.return_value = {
            "document_id": "doc_123",
            "filename": "test.pdf",
            "content_type": "application/pdf",
            "size": 1024,
            "uploaded_at": "...",
            "status": "DELETED",
        }
        dto = service.update_document("doc_123", {"status": "DELETED"})
        assert dto.status == "DELETED"
        assert mock_repo.update.called

    def test_delete_document(self, service, mock_repo):
        mock_repo.delete.return_value = True
        res = service.delete_document("doc_123")
        assert res is True
        mock_repo.delete.assert_called_with("doc_123")


# ---------------------------------------------------------------------------
# OutputService
# ---------------------------------------------------------------------------

class TestOutputService:
    @pytest.fixture
    def mock_repo(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo):
        return OutputService(repository=mock_repo)

    def test_create_output(self, service, mock_repo):
        mock_repo.create.side_effect = lambda rec: rec  # Return the record passed in
        dto = service.create_output(
            workflow_run_id="wf_123",
            output_type="DOCUMENT",
            format="DOCX",
        )
        assert dto.workflow_run_id == "wf_123"
        assert dto.status == "CREATED"
        assert dto.output_type == "DOCUMENT"
        assert dto.format == "DOCX"

    def test_mark_output_ready(self, service, mock_repo):
        mock_repo.update.side_effect = lambda _id, updates: {
            "output_id": _id,
            "workflow_run_id": "wf_123",
            "status": updates["status"],
            "output_type": "DOCUMENT",
            "format": "DOCX",
            "artifact_path": updates["artifact_path"],
            "created_at": "...",
            "updated_at": updates["updated_at"],
            "metadata": updates["metadata"],
        }
        
        dto = service.mark_output_ready(
            "out_123",
            artifact_path="storage/outputs/out_123.docx",
            metadata={"pages": 10},
        )
        assert dto.status == "READY"
        assert dto.artifact_path == "storage/outputs/out_123.docx"
        assert dto.metadata["pages"] == 10

    def test_mark_output_failed(self, service, mock_repo):
        mock_repo.update.side_effect = lambda _id, updates: {
            "output_id": _id,
            "workflow_run_id": "wf_123",
            "status": updates["status"],
            "output_type": "DOCUMENT",
            "format": "DOCX",
            "errors": updates["errors"],
            "created_at": "...",
            "updated_at": updates["updated_at"],
        }
        
        dto = service.mark_output_failed(
            "out_123",
            error_code="GEN_FAIL",
            error_message="Timeout",
        )
        assert dto.status == "FAILED"
        assert dto.errors[0]["code"] == "GEN_FAIL"


# ---------------------------------------------------------------------------
# WorkflowService
# ---------------------------------------------------------------------------

class TestWorkflowService:
    @pytest.fixture
    def mock_wf_repo(self):
        return MagicMock()

    @pytest.fixture
    def mock_ex_repo(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_wf_repo, mock_ex_repo):
        return WorkflowService(
            workflow_repository=mock_wf_repo,
            execution_repository=mock_ex_repo,
        )

    def test_create_workflow(self, service, mock_wf_repo, mock_ex_repo):
        mock_wf_repo.create.side_effect = lambda rec: rec
        mock_ex_repo.create.side_effect = lambda rec: rec
        
        dto = service.create_workflow(
            document_id="doc_123",
            template_id="tpl_456",
        )
        
        assert dto.document_id == "doc_123"
        assert dto.template_id == "tpl_456"
        assert dto.status == "PENDING"
        assert dto.current_phase == "INPUT_PREPARATION"
        assert mock_wf_repo.create.called
        assert mock_ex_repo.create.called

    def test_get_workflow(self, service, mock_wf_repo):
        mock_wf_repo.get.return_value = {
            "workflow_run_id": "wf_123",
            "status": "PENDING",
            "current_phase": "INPUT_PREPARATION",
            "overall_progress_percent": 0,
            "document_id": "doc_123",
            "template_id": None,
            "output_id": None,
            "created_at": "...",
            "updated_at": "...",
        }
        dto = service.get_workflow("wf_123")
        assert dto.workflow_run_id == "wf_123"

    def test_mark_workflow_started(self, service, mock_wf_repo):
        mock_wf_repo.update.side_effect = lambda _id, updates: {
            "workflow_run_id": _id,
            "status": updates["status"],
            "current_phase": "INPUT_PREPARATION",
            "overall_progress_percent": 0,
            "document_id": "doc_123",
            "template_id": None,
            "output_id": None,
            "created_at": "...",
            "updated_at": "...",
            "started_at": updates["started_at"],
        }
        dto = service.mark_workflow_started("wf_123")
        assert dto.status == "RUNNING"
        assert dto.started_at is not None

    def test_mark_workflow_completed(self, service, mock_wf_repo):
        mock_wf_repo.update.side_effect = lambda _id, updates: {
            "workflow_run_id": _id,
            "status": updates["status"],
            "current_phase": "INPUT_PREPARATION",
            "overall_progress_percent": updates["overall_progress_percent"],
            "document_id": "doc_123",
            "template_id": None,
            "output_id": updates["output_id"],
            "created_at": "...",
            "updated_at": "...",
            "completed_at": updates["completed_at"],
        }
        dto = service.mark_workflow_completed("wf_123", output_id="out_999")
        assert dto.status == "COMPLETED"
        assert dto.output_id == "out_999"
        assert dto.overall_progress_percent == 100
        assert dto.completed_at is not None

    def test_mark_workflow_failed(self, service, mock_wf_repo):
        # We need mock_wf_repo.get to work because mark_workflow_failed calls get_workflow
        mock_wf_repo.get.return_value = {
            "workflow_run_id": "wf_123",
            "status": "RUNNING",
            "current_phase": "INPUT_PREPARATION",
            "overall_progress_percent": 50,
            "document_id": "doc_123",
            "template_id": None,
            "output_id": None,
            "created_at": "...",
            "updated_at": "...",
            "errors": [],
        }
        mock_wf_repo.update.side_effect = lambda _id, updates: {
            "workflow_run_id": _id,
            "status": updates["status"],
            "current_phase": "INPUT_PREPARATION",
            "overall_progress_percent": 50,
            "document_id": "doc_123",
            "template_id": None,
            "output_id": None,
            "created_at": "...",
            "updated_at": "...",
            "errors": updates["errors"],
        }
        dto = service.mark_workflow_failed("wf_123", error_code="E001", error_message="Boom")
        assert dto.status == "FAILED"
        assert len(dto.errors) == 1
        assert dto.errors[0]["code"] == "E001"
