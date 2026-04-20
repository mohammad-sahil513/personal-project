# Phase Traceability Matrix

This matrix maps each major workflow phase to API surface, orchestration service, module runtime, produced artifacts, and frontend consumers.

## Matrix

| Phase | API Surface | Core Service(s) | Module / Runtime | Primary Artifacts | Frontend Consumer |
|---|---|---|---|---|---|
| `INPUT_PREPARATION` | `POST /api/workflow-runs` | `WorkflowService`, `WorkflowExecutorService` | Workflow orchestration layer | Workflow run record, execution refs, initial progress state | `UploadPage.tsx` (create), `ProgressPage.tsx` (status polling) |
| `INGESTION` | `GET /api/workflow-runs/{id}/status` | `IngestionRuntimeBridge`, `IngestionIntegrationService`, `IngestionStatusService` | `modules/ingestion` + `pipeline/orchestrators/ingestion_orchestrator.py` | Stage outputs, ingestion logs, chunk/index payloads, ingestion execution metadata | `ProgressPage.tsx`, `useJobStore.ts` |
| `TEMPLATE_PREPARATION` | `POST /api/templates/{id}/compile`, `GET /api/templates/{id}/compiled`, `/resolve`, `/validate` | `TemplateCompileService`, `TemplateIntrospectionService`, template bridges | `modules/template` | Compiled template definition, optional manifest/shell artifacts, template status updates | `TemplatesPage.tsx` and template APIs (library flow); main generation flow depends indirectly |
| `SECTION_PLANNING` | `GET /api/workflow-runs/{id}/sections` | `SectionPlanningService`, `SectionProgressService` | `pipeline/planners/section_execution_planner.py` | `section_plan`, `section_progress` attached to workflow | Indirect in `ProgressPage.tsx`/`OutputPage.tsx` via workflow payload |
| `RETRIEVAL` | `GET /api/workflow-runs/{id}` and `/observability` | `WorkflowSectionRetrievalService`, `SectionRetrievalService`, `RetrievalRuntimeBridge` | `modules/retrieval` (`RetrievalService`, query/search/rerank/packager) | `section_retrieval_results`, diagnostics, confidence/evidence bundle metadata | `OutputPage.tsx` depends on downstream generation that uses retrieval outputs |
| `GENERATION` | `GET /api/workflow-runs/{id}`, `/events` | `WorkflowSectionGenerationService`, `SectionGenerationService`, `GenerationRuntimeBridge` | `modules/generation` (prompt assembly, text/table/diagram generators, validators) | `section_generation_results` including content/artifacts/diagnostics | `OutputPage.tsx`, `DocxViewer.tsx`, `SectionSidebar.tsx` |
| `ASSEMBLY_VALIDATION` | `GET /api/workflow-runs/{id}` | `DocumentAssemblyService` | `modules/generation/assembly` | `assembled_document.sections` in ordered structure | `OutputPage.tsx` (tabs + section rendering) |
| `RENDER_EXPORT` | `GET /api/outputs/{output_id}`, `GET /api/outputs/{output_id}/download` | `OutputExportService`, `DocxRendererService`, `OutputService` | Export/render path in application layer | Output metadata (`output_id`, `status`, `artifact_path`) + final DOCX | `DownloadPanel.tsx`, `outputApi.ts` |

## Notes for Audit

- Frontend mostly consumes lifecycle via polling endpoints (`/workflow-runs/{id}/status`, `/workflow-runs/{id}`) rather than SSE.
- Template compile/resolve/validate endpoints are present, but the upload-to-generate flow is mostly driven by template selection and workflow run creation.
- The generation module route file exists separately (`/api/generate-document`) but is not currently mounted in the main router path.
- End-user completion criteria in UI effectively require:
  - workflow `status = COMPLETED`
  - `assembled_document.sections` available
  - `output_id` available for download
