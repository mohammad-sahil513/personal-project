"""
End-to-End Mock Integration Test
=================================
Simulates the complete workflow lifecycle:
  1. Document upload (binary)
  2. Template upload (binary)
  3. Workflow creation
  4. Ingestion execution (mocked orchestrator)
  5. Template resolution & section planning (mocked resolve bridge)
  6. Section progress initialization
  7. Retrieval result population (simulated)
  8. Section generation (mocked generation bridge)
  9. Document assembly
 10. Output export & DOCX rendering
"""

import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure the backend module is in python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.application.services.document_service import DocumentService
from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.workflow_service import WorkflowService
from backend.application.services.workflow_executor_service import WorkflowExecutorService
from backend.application.dto.generation_dto import GenerationResultDTO
from backend.modules.ingestion.contracts.stage_1_contracts import (
    Stage1Output, BlobArtifactReference, IngestionJobRecord,
    IngestionJobStatus, IngestionStageName, Stage1Metrics,
)


async def run_e2e_mock():
    print("=== Starting End-to-End Mock Integration Run ===\n")

    # ---------------------------------------------------------------
    # STEP 1: Data Fixture Setup
    # ---------------------------------------------------------------
    print("[1/7] Data Fixture Setup")
    doc_service = DocumentService()
    template_service = TemplateAppService()
    wf_service = WorkflowService()

    mock_pdf_bytes = b"mock pdf content for e2e"
    mock_docx_bytes = b"PK\x03\x04mockdocx"

    doc = doc_service.create_document(
        filename="input.pdf",
        content_type="application/pdf",
        size=len(mock_pdf_bytes),
        file_bytes=mock_pdf_bytes,
    )
    print(f"      Document : {doc.document_id}")

    tpl = template_service.create_template(
        filename="template.docx",
        version="1",
        file_bytes=mock_docx_bytes,
    )
    print(f"      Template : {tpl.template_id}")

    wf = wf_service.create_workflow(
        document_id=doc.document_id,
        template_id=tpl.template_id,
    )
    print(f"      Workflow : {wf.workflow_run_id}")

    # ---------------------------------------------------------------
    # STEP 2: Ingestion Phase (mocked orchestrator)
    # ---------------------------------------------------------------
    print("\n[2/7] Ingestion Phase Execution")

    mock_stage_1_out = Stage1Output(
        process_id="proc_e2e",
        document_id=doc.document_id,
        sha256_hash="a" * 64,
        original_file=BlobArtifactReference(
            container_name="test",
            blob_path="sahil_storage/e2e_blob.pdf",
            content_type="application/pdf",
            size_bytes=len(mock_pdf_bytes),
        ),
        is_duplicate=False,
        duplicate_of_document_id=None,
        job_record=IngestionJobRecord(
            process_id="proc_e2e",
            document_id=doc.document_id,
            file_name="input.pdf",
            content_type="application/pdf",
            sha256_hash="a" * 64,
            source_blob=BlobArtifactReference(
                container_name="test",
                blob_path="sahil_storage/e2e_blob.pdf",
                content_type="application/pdf",
                size_bytes=len(mock_pdf_bytes),
            ),
            status=IngestionJobStatus.COMPLETED,
            current_stage=IngestionStageName.UPLOAD_AND_DEDUP,
        ),
        metrics=Stage1Metrics(
            file_size_bytes=len(mock_pdf_bytes),
            upload_duration_ms=10.0,
            duplicate_lookup_duration_ms=5.0,
            total_duration_ms=15.0,
        ),
    )

    class MockIngestionPipelineResult:
        def __init__(self):
            self.status = "COMPLETED"
            self.stage_1_output = mock_stage_1_out
            self.stage_2_output = None
            self.stage_3_output = None

    mock_orchestrator = AsyncMock()
    mock_orchestrator.run.return_value = MockIngestionPipelineResult()
    mock_orchestrator.execute.return_value = MockIngestionPipelineResult()

    mock_runtime = MagicMock()
    mock_runtime.run_ingestion = AsyncMock(return_value=MockIngestionPipelineResult())

    with patch(
        "backend.modules.ingestion.live_wiring.build_ingestion_runtime",
        return_value=mock_runtime,
    ):
        executor = WorkflowExecutorService(workflow_service=wf_service)

        await executor.execute_workflow_skeleton(wf.workflow_run_id)
        current = wf_service.get_workflow(wf.workflow_run_id)
        print(f"      Phase    : {current.current_phase}")
        print(f"      Progress : {current.overall_progress_percent}%")

    # ---------------------------------------------------------------
    # STEP 3: Section Planning (mocked template resolve bridge)
    # ---------------------------------------------------------------
    print("\n[3/7] Template Resolution & Section Planning")

    mock_resolved_sections = [
        {
            "section_id": "sec_e2e_1",
            "title": "Executive Summary",
            "execution_order": 1,
            "generation_strategy": "SUMMARIZE",
            "retrieval_profile": "BROAD",
            "dependencies": [],
        },
        {
            "section_id": "sec_e2e_2",
            "title": "Technical Architecture",
            "execution_order": 2,
            "generation_strategy": "DEEP_DIVE",
            "retrieval_profile": "DEEP",
            "dependencies": ["sec_e2e_1"],
        },
    ]

    mock_resolve = AsyncMock(
        return_value={"status": "COMPLETED", "resolved_sections": mock_resolved_sections}
    )

    with patch(
        "backend.application.services.template_resolve_bridge.TemplateResolveBridge.run_resolve",
        new=mock_resolve,
    ):
        await executor.build_and_attach_section_plan(wf.workflow_run_id)

    current = wf_service.get_workflow(wf.workflow_run_id)
    print(f"      Sections : {current.section_plan['total_sections']}")
    for s in current.section_plan["sections"]:
        print(f"        - [{s['execution_order']}] {s['title']} ({s['generation_strategy']})")

    # ---------------------------------------------------------------
    # STEP 4: Initialize Section Progress
    # ---------------------------------------------------------------
    print("\n[4/7] Section Progress Initialization")

    await executor.initialize_section_progress(wf.workflow_run_id)
    current = wf_service.get_workflow(wf.workflow_run_id)
    sp = current.section_progress
    print(f"      Total    : {sp['total_sections']}")
    print(f"      Running  : {sp['running_sections']}")
    print(f"      Complete : {sp['completed_sections']}")

    # ---------------------------------------------------------------
    # STEP 5: Simulate Retrieval Results + Run Generation
    # ---------------------------------------------------------------
    print("\n[5/7] Retrieval Simulation & Section Generation")

    # Populate retrieval results for each section (simulated)
    wf_service.update_workflow(wf.workflow_run_id, {
        "section_retrieval_results": {
            "sec_e2e_1": {"status": "COMPLETED", "evidence_bundle": {"chunks": ["c1"]}},
            "sec_e2e_2": {"status": "COMPLETED", "evidence_bundle": {"chunks": ["c2", "c3"]}},
        }
    })

    # Mock the generation bridge at the lowest level so the executor
    # iteration logic (per-section loop in run_section_generation) still exercises.
    mock_gen_result_1 = GenerationResultDTO(
        section_id="sec_e2e_1",
        generation_strategy="SUMMARIZE",
        status="COMPLETED",
        output_type="MARKDOWN",
        content="# Executive Summary\nThis proposal outlines a scalable AI engine.",
    )
    mock_gen_result_2 = GenerationResultDTO(
        section_id="sec_e2e_2",
        generation_strategy="DEEP_DIVE",
        status="COMPLETED",
        output_type="MARKDOWN",
        content="# Technical Architecture\nThe system uses a modular monolith pattern.",
    )

    gen_side_effects = [mock_gen_result_1, mock_gen_result_2]
    gen_call_index = {"i": 0}

    async def mock_generate_for_section(section_plan_item, retrieval_result):
        idx = gen_call_index["i"]
        gen_call_index["i"] += 1
        return gen_side_effects[idx]

    with patch.object(
        executor.workflow_section_generation_service.section_generation_service,
        "generate_for_section",
        side_effect=mock_generate_for_section,
    ):
        await executor.run_section_generation(wf.workflow_run_id)

    current = wf_service.get_workflow(wf.workflow_run_id)
    gen_results = current.section_generation_results
    print(f"      Generated sections: {list(gen_results.keys())}")
    for sid, res in gen_results.items():
        print(f"        - {sid}: {res['output_type']} ({len(res.get('content', ''))} chars)")

    # ---------------------------------------------------------------
    # STEP 6: Document Assembly
    # ---------------------------------------------------------------
    print("\n[6/7] Document Assembly")

    await executor.assemble_generated_sections(wf.workflow_run_id)
    current = wf_service.get_workflow(wf.workflow_run_id)
    assembled = current.assembled_document
    print(f"      Title    : {assembled['title']}")
    print(f"      Sections : {assembled['total_sections']}")
    for sec in assembled["sections"]:
        print(f"        - {sec['title']} ({sec['output_type']})")

    # ---------------------------------------------------------------
    # STEP 7: Output Export & DOCX Rendering
    # ---------------------------------------------------------------
    print("\n[7/7] Output Export & DOCX Rendering")

    await executor.prepare_output_export(wf.workflow_run_id)
    await executor.render_and_finalize_output(wf.workflow_run_id)

    current = wf_service.get_workflow(wf.workflow_run_id)
    output_svc = executor.output_export_service.output_service
    out_dto = output_svc.get_output(current.output_id)

    print(f"      Output ID     : {out_dto.output_id}")
    print(f"      Status        : {out_dto.status}")
    print(f"      Format        : {out_dto.format}")
    print(f"      Artifact Path : {out_dto.artifact_path}")

    assert out_dto.artifact_path is not None, "Output artifact_path is None"
    assert os.path.exists(out_dto.artifact_path), f"DOCX not found at {out_dto.artifact_path}"

    file_size = os.path.getsize(out_dto.artifact_path)
    print(f"      File Size     : {file_size} bytes")

    # ---------------------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------------------
    print("\n" + "=" * 60)
    print("  END-TO-END MOCK INTEGRATION: ALL PHASES PASSED")
    print("=" * 60)
    print(f"  Document   -> {doc.document_id}")
    print(f"  Template   -> {tpl.template_id}")
    print(f"  Workflow   -> {wf.workflow_run_id}")
    print(f"  Output     -> {out_dto.output_id}")
    print(f"  DOCX       -> {out_dto.artifact_path} ({file_size}B)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_e2e_mock())
