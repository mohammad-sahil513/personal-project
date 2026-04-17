# 08 - Connection Map (Folder, Service, Stage)

This document shows how folders, key classes, and workflow stages connect.

## Folder-to-Folder Connection Map

- `main.py` -> `api/router.py`
- `api/routes/*` -> `application/services/*`
- `application/services/*` -> `repositories/*`
- `application/services/*` -> `workers/*`
- `application/services/*` -> `modules/*/live_wiring.py` (through bridges)
- `modules/*` -> `infrastructure/*` for cloud SDK calls
- `modules/*` -> module repositories/contracts for domain logic
- `core/*` is shared across all layers

## Stage-to-Service Connection Map

## `INPUT_PREPARATION`
- `WorkflowExecutorService.prepare_workflow_execution`
- `ProgressService.initialize_progress`
- `IngestionIntegrationService.create_ingestion_execution`

## `INGESTION`
- `WorkflowExecutorService.execute_workflow_skeleton`
- `IngestionRuntimeBridge.run_ingestion`
- `modules/ingestion/live_wiring.py`
- `modules/ingestion/stages/*`

## `TEMPLATE_PREPARATION`
- `TemplateAppService`
- `TemplateCompileService`
- `TemplateRuntimeBridge`

## `SECTION_PLANNING`
- `SectionPlanningService.build_plan_dict`
- `SectionProgressService.initialize_from_section_plan`

## `RETRIEVAL`
- `WorkflowSectionRetrievalService.run_retrieval_for_workflow`
- `SectionRetrievalService.retrieve_for_section`
- `modules/retrieval/live_wiring.py`

## `GENERATION`
- `WorkflowExecutorService.run_section_generation`
- `WorkflowSectionGenerationService.run_generation_for_workflow`
- `SectionGenerationService.generate_for_section`
- `modules/generation/live_wiring.py`

## `ASSEMBLY_VALIDATION`
- `DocumentAssemblyService.build_assembled_document`
- workflow attach assembled document

## `RENDER_EXPORT`
- `OutputExportService.prepare_docx_export`
- `OutputExportService.export_docx`
- `DocxRendererService.render`

## API-to-Stage Connection

- `/workflow-runs` (POST) -> creates and dispatches workflow.
- `/workflow-runs/{id}/status` -> current stage and progress visibility.
- `/workflow-runs/{id}/sections` -> section planning output.
- `/workflow-runs/{id}/observability` -> cross-stage diagnostics and cost summary.
- `/outputs/{output_id}` + `/download` -> export stage output consumption.

## Event Connection

- Workflow-level events are published through `WorkflowEventService`.
- Live stream endpoint: `/workflow-runs/{workflow_run_id}/events`.
- Generation module has separate SSE stream endpoint under `/api/generate-document/{job_id}/events`.
