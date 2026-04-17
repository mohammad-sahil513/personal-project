"""
Integration tests — Phase 7.2b (Workflow Lifecycle orchestration)
Simulates a full workflow from PENDING -> INPUT_PREPARATION -> INGESTION -> PLAN -> GENERATE -> COMPLETE.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from backend.application.services.document_service import DocumentService
from backend.application.services.workflow_executor_service import WorkflowExecutorService
from backend.application.services.workflow_service import WorkflowService


@pytest.mark.asyncio
async def test_workflow_lifecycle_orchestration():
    # 1. Setup Services & Repositories
    doc_service = DocumentService()
    workflow_service = WorkflowService()
    
    # Create the target source document
    doc = doc_service.create_document(
        filename="system_design.pdf",
        content_type="application/pdf",
        size=1024,
    )
    
    # Create workflow entry
    workflow = workflow_service.create_workflow(
        document_id=doc.document_id,
        template_id="tpl_dummy_001",
    )
    
    assert workflow.status == "PENDING"
    assert workflow.current_phase == "INPUT_PREPARATION"
    
    # 2. Setup the Executor with mocked bridges
    executor = WorkflowExecutorService(workflow_service=workflow_service)
    
    # We mock out the ingestion bridge so it doesn't try to call real Azure AI SDK
    mock_ingestion_bridge = AsyncMock()
    mock_ingestion_bridge.run_ingestion.return_value = {
        "status": "COMPLETED",
        "current_stage": "03_EMBED_AND_INDEX",
        "completed_stages": 3,
        "total_stages": 3,
        "warnings": [],
        "errors": [],
        "artifacts": [{"id": "art_1"}],
    }
    executor.ingestion_runtime_bridge = mock_ingestion_bridge
    
    # 3. Step 1: Execute skeleton (simulating initial dispatch)
    # This prepares the workflow, starts it, calls ingestion
    result_wf = await executor.execute_workflow_skeleton(workflow.workflow_run_id)
    
    # Because we mocked ingestion to return COMPLETED directly, the phase jumps to INGESTION (completed)
    assert result_wf["status"] == "RUNNING"
    assert "INGESTION" in result_wf["current_phase"] or result_wf["overall_progress_percent"] > 0
    
    # Ensure ingestion was called
    mock_ingestion_bridge.run_ingestion.assert_called_once()
    
    # 4. Mock the section plan attachment
    from backend.application.services.section_planning_service import SectionPlanningService
    executor.section_planning_service = AsyncMock(spec=SectionPlanningService)
    executor.section_planning_service.build_plan_dict.return_value = {
        "template_id": "tpl_dummy_001",
        "total_sections": 1,
        "sections": [
            {
                "section_id": "sec_01",
                "title": "Dummy",
                "execution_order": 1,
                "generation_strategy": "summarize_text",
                "retrieval_profile": "default",
            }
        ]
    }
    await executor.build_and_attach_section_plan(workflow.workflow_run_id)
    
    # Verify section plan is attached
    current = workflow_service.get_workflow(workflow.workflow_run_id)
    assert current.section_plan is not None
    assert current.section_plan["total_sections"] == 1
    
    # 5. Initialize section progress
    await executor.initialize_section_progress(workflow.workflow_run_id)
    current = workflow_service.get_workflow(workflow.workflow_run_id)
    assert current.section_progress is not None
    assert current.section_progress["total_sections"] == 1
    
    # Attach mocked retrieval results
    workflow_service.attach_section_retrieval_results(
        workflow.workflow_run_id,
        section_retrieval_results={"sec_01": "Mock Evidence Data"},
    )
    
    # 6. Run Generation (Mocked generation service)
    from backend.application.services.workflow_section_generation_service import WorkflowSectionGenerationService
    executor.workflow_section_generation_service = AsyncMock(spec=WorkflowSectionGenerationService)
    executor.workflow_section_generation_service.run_generation_for_workflow.return_value = {
        "sec_01": {
            "output_type": "markdown",
            "content": "# Dummy Content",
            "raw_result": {},
        }
    }
    
    await executor.run_section_generation(workflow.workflow_run_id)
    
    # Verify section progress was complete
    current = workflow_service.get_workflow(workflow.workflow_run_id)
    assert current.section_generation_results is not None
    assert "sec_01" in current.section_generation_results
    assert current.section_progress["completed_sections"] == 1
    
    # 7. Document Assembly
    # We will mock DocumentAssemblyService to just return a dummy
    from backend.application.services.document_assembly_service import DocumentAssemblyService
    executor.document_assembly_service = MagicMock(spec=DocumentAssemblyService)
    doc_mock = MagicMock()
    doc_mock.to_dict.return_value = {
        "title": "Compiled Doc",
        "total_sections": 1,
        "blocks": [{"type": "markdown", "content": "hello"}],
    }
    executor.document_assembly_service.build_assembled_document.return_value = doc_mock
    
    await executor.assemble_generated_sections(workflow.workflow_run_id)
    current = workflow_service.get_workflow(workflow.workflow_run_id)
    assert current.assembled_document is not None
    
    # 8. Export preparation and finalize
    from backend.application.services.output_export_service import OutputExportService
    executor.output_export_service = MagicMock(spec=OutputExportService)
    executor.output_export_service.prepare_docx_export.return_value = {"output_id": "out_999"}
    executor.output_export_service.export_docx.return_value = {
        "output_id": "out_999",
        "status": "READY",
        "format": "DOCX",
        "artifact_path": "storage/out_999.docx",
    }
    
    await executor.prepare_output_export(workflow.workflow_run_id)
    res = await executor.render_and_finalize_output(workflow.workflow_run_id)
    
    assert res["status"] == "READY"
    assert res["output_id"] == "out_999"
    
    # Finally, mark workflow completed
    final_workflow = workflow_service.mark_workflow_completed(workflow.workflow_run_id, output_id="out_999")
    
    assert final_workflow.status == "COMPLETED"
    assert final_workflow.overall_progress_percent == 100
    assert final_workflow.output_id == "out_999"
