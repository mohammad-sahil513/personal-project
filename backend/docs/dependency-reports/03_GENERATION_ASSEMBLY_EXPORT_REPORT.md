# Generation, Assembly, and Export Dependency Report

This report covers dependencies from section generation through assembly and DOCX export.

## Upstream Dependencies

- Required inputs before generation:
  - `section_plan` from planning phase
  - `section_retrieval_results` from retrieval phase
  - template context resolved during template preparation

- Upstream orchestrators/services:
  - `backend/application/services/workflow_executor_service.py`
  - `backend/application/services/workflow_section_generation_service.py`
  - `backend/application/services/section_generation_service.py`
  - `backend/application/services/generation_runtime_bridge.py`

## Core Files by Capability

### Generation Runtime

- `backend/modules/generation/live_wiring.py`
- `backend/modules/generation/orchestrators/section_executor.py`
- `backend/modules/generation/orchestrators/generation_orchestrator.py`
- `backend/modules/generation/generators/prompt_assembler.py`
- `backend/modules/generation/generators/text_generator.py`
- `backend/modules/generation/generators/table_generator.py`
- `backend/modules/generation/generators/diagram_generator.py`
- `backend/modules/generation/validators/output_validator.py`
- `backend/modules/generation/contracts/*.py`

### Assembly

- `backend/application/services/document_assembly_service.py`
- `backend/modules/generation/assembly/section_assembler.py`
- `backend/modules/generation/assembly/toc_generator.py`
- `backend/application/dto/assembled_document_dto.py`

### Export and Output Metadata

- `backend/application/services/output_export_service.py`
- `backend/application/services/docx_renderer_service.py`
- `backend/application/services/output_service.py`
- `backend/repositories/output_repository.py`
- `backend/api/routes/output_routes.py`

## Downstream Consumers

- Workflow state and API responses:
  - `backend/api/routes/workflow_routes.py`
  - `backend/api/routes/output_routes.py`

- Frontend output rendering and download:
  - `frontend/src/pages/OutputPage.tsx`
  - `frontend/src/components/output/DocumentTabs.tsx`
  - `frontend/src/components/output/SectionSidebar.tsx`
  - `frontend/src/components/output/DocxViewer.tsx`
  - `frontend/src/components/output/DownloadPanel.tsx`
  - `frontend/src/api/outputApi.ts`

## Contract Chain

- Generation result:
  - `backend/application/dto/generation_dto.py`
- Assembled document:
  - `backend/application/dto/assembled_document_dto.py`
- Output metadata:
  - `backend/application/dto/output_dto.py`
- Workflow aggregate:
  - `backend/application/dto/workflow_dto.py`

Frontend expects these workflow fields for success path:
- `status = COMPLETED`
- `assembled_document.sections[].content`
- `output_id`

## Storage and Artifacts

- Output metadata:
  - `backend/storage/outputs/{output_id}.json`
- Rendered DOCX artifact:
  - `backend/storage/outputs/{workflow_run_id}/{output_id}.docx` (path shape may vary by renderer/service config)

## Tests and Scripts

- Integration:
  - `backend/tests/integration/test_workflow_lifecycle.py`
  - `backend/tests/integration/modules/generation/test_generation_pipeline.py`
- Unit:
  - `backend/tests/unit/modules/generation/*.py`
  - `backend/tests/unit/application/services/test_app_services.py`
- Manual/scripts:
  - `backend/manual_testing/run_generation_manual.py`
  - `backend/manual_testing/run_assembly_export_manual.py`
  - `backend/scripts/test_phase3_retrieval_generation_bridge.py`
  - `backend/scripts/test_phase4_rendering.py`

## Practical Gaps for This Segment

- The primary API start path may not automatically execute full generation -> assembly -> export chain.
- Generation-specific API module exists but is not mounted in main router.
- Frontend depends on completed assembly content and `output_id`; when absent, UI appears incomplete despite earlier phase progress.
