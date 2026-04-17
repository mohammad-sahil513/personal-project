"""
Unit tests — Phase 6.3a (Application Layer: DTOs)
Covers all application-layer DTOs: document, workflow, output, template.
No I/O, no services — pure contract shape testing.
"""

from __future__ import annotations

from backend.application.dto.document_dto import DocumentDTO
from backend.application.dto.output_dto import OutputDTO
from backend.application.dto.template_dto import TemplateDTO
from backend.application.dto.workflow_dto import WorkflowDTO


class TestDocumentDTO:
    def _make(self, **overrides) -> DocumentDTO:
        defaults = dict(
            document_id="doc_abc123",
            filename="requirements.pdf",
            content_type="application/pdf",
            size=204800,
            uploaded_at="2026-04-01T10:00:00+00:00",
            status="AVAILABLE",
        )
        defaults.update(overrides)
        return DocumentDTO(**defaults)

    def test_happy_path(self):
        dto = self._make()
        assert dto.document_id == "doc_abc123"
        assert dto.filename == "requirements.pdf"
        assert dto.size == 204800

    def test_to_dict_includes_all_fields(self):
        dto = self._make()
        d = dto.to_dict()
        assert "document_id" in d
        assert "filename" in d
        assert "size" in d
        assert "status" in d

    def test_status_arbitrary_string(self):
        dto = self._make(status="PROCESSING")
        assert dto.status == "PROCESSING"


class TestWorkflowDTO:
    def _make(self, **overrides) -> WorkflowDTO:
        defaults = dict(
            workflow_run_id="wf_run_001",
            status="PENDING",
            current_phase="INPUT_PREPARATION",
            overall_progress_percent=0,
            document_id="doc_001",
            template_id=None,
            output_id=None,
            created_at="2026-04-01T10:00:00+00:00",
            updated_at="2026-04-01T10:00:00+00:00",
        )
        defaults.update(overrides)
        return WorkflowDTO(**defaults)

    def test_happy_path(self):
        dto = self._make()
        assert dto.status == "PENDING"
        assert dto.overall_progress_percent == 0

    def test_optional_fields_default_none(self):
        dto = self._make()
        assert dto.started_at is None
        assert dto.completed_at is None
        assert dto.template_id is None
        assert dto.section_plan is None

    def test_to_dict_includes_started_at(self):
        dto = self._make(started_at="2026-04-01T11:00:00+00:00", status="RUNNING")
        d = dto.to_dict()
        assert d["started_at"] is not None
        assert d["status"] == "RUNNING"

    def test_errors_list_attached(self):
        dto = self._make(errors=[{"code": "E001", "message": "Failed."}])
        assert len(dto.errors) == 1


class TestOutputDTO:
    def _make(self, **overrides):
        from backend.application.dto.output_dto import OutputDTO
        defaults = dict(
            output_id="out_001",
            workflow_run_id="wf_run_001",
            status="CREATED",
            output_type="DOCUMENT",
            format="DOCX",
            artifact_path=None,
            metadata={},
            errors=[],
            created_at="2026-04-01T10:00:00+00:00",
            updated_at="2026-04-01T10:00:00+00:00",
        )
        defaults.update(overrides)
        return OutputDTO(**defaults)

    def test_happy_path(self):
        dto = self._make()
        assert dto.output_id == "out_001"
        assert dto.status == "CREATED"

    def test_ready_status_with_artifact_path(self):
        dto = self._make(status="READY", artifact_path="storage/outputs/out_001.docx")
        assert dto.artifact_path is not None
        assert dto.status == "READY"

    def test_to_dict_serializes(self):
        dto = self._make()
        d = dto.to_dict()
        assert "output_id" in d
        assert "format" in d


class TestTemplateDTO:
    def _make(self, **overrides):
        defaults = dict(
            template_id="tpl_001",
            filename="sdlc_design_template.docx",
            template_type="SDLC",
            version="1.0",
            status="ACTIVE",
            created_at="2026-04-01T09:00:00+00:00",
            updated_at="2026-04-01T09:00:00+00:00",
        )
        defaults.update(overrides)
        return TemplateDTO(**defaults)

    def test_happy_path(self):
        dto = self._make()
        assert dto.template_id == "tpl_001"
        assert dto.version == "1.0"
        assert dto.filename == "sdlc_design_template.docx"

    def test_optional_compile_job_id_defaults_none(self):
        dto = self._make()
        assert dto.compile_job_id is None

    def test_to_dict(self):
        dto = self._make()
        d = dto.to_dict()
        assert "template_id" in d
        assert "status" in d
        assert "filename" in d
