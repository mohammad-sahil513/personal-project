"""
Integration tests — Phase 7.2a (Template to Workflow)
Tests the end-to-end trace mapping from Template upload -> compile -> Workflow Creation.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, AsyncMock

import pytest

from backend.application.services.document_service import DocumentService
from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_compile_service import TemplateCompileService
from backend.application.services.workflow_service import WorkflowService


@pytest.mark.asyncio
class TestTemplateToWorkflow:
    async def test_upload_compile_create_workflow_flow(self, tmp_path):
        # 1. Setup Document
        doc_service = DocumentService()
        doc = doc_service.create_document(
            filename="my_template.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=1024,
            file_bytes=b"fake_docx_bytes",
        )

        # 2. Setup Template via App Service
        app_service = TemplateAppService()
        template = app_service.create_template(
            filename="my_template.docx",
            template_type="SDLC",
            version="1.0",
        )
        assert template.status == "UPLOADED"

        # 3. Compile Template with mocked bridge
        mock_bridge = AsyncMock()
        mock_bridge.run_compile.return_value = {
            "status": "COMPLETED",
            "compiled_artifacts": [
                {
                    "section_id": "sec_1",
                    "title": "Architecture",
                    "execution_order": 1,
                    "generation_strategy": "summarize_text",
                    "dependencies": [],
                }
            ],
            "errors": []
        }
        
        compiler_service = TemplateCompileService(
            template_app_service=app_service,
            template_runtime_bridge=mock_bridge
        )
        
        compiled_result = await compiler_service.execute_compile(template.template_id)
        assert compiled_result["status"] == "COMPILED"

        # 4. Create Workflow
        wf_service = WorkflowService()
        
        # Upload another document for workflow ingestion
        src_doc = doc_service.create_document(
            filename="source_material.pdf",
            content_type="application/pdf",
            size=2048,
        )
        
        workflow = wf_service.create_workflow(
            document_id=str(src_doc.document_id),
            template_id=template.template_id,
        )
        
        assert workflow.workflow_run_id is not None
        assert workflow.status == "PENDING"
        assert workflow.current_phase == "INPUT_PREPARATION"
